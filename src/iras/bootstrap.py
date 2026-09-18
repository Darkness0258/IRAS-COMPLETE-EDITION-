from __future__ import annotations
import json
import os
from iras.config import Settings
from iras.models import PermissionLevel
from iras.security.audit import AuditLogger
from iras.security.permissions import PermissionEngine
from iras.memory.store import MemoryStore
from iras.tools.registry import ToolRegistry
from iras.tools.filesystem import TOOLS as FILES
from iras.tools.shell import TOOLS as SHELL
from iras.tools.system import TOOLS as SYSTEM
from iras.tools.web import TOOLS as WEB
from iras.tools.git import TOOLS as GIT
from iras.tools.api_access import TOOLS as API_ACCESS
from iras.tools.remote import TOOLS as REMOTE
from iras.tools.memory import make_tools as memory_tools
from iras.tools.personality import make_tools as personality_tools
from iras.personality import AdaptivePersonality
from iras.browser.playwright_tools import BrowserSession, make_tools as browser_tools
from iras.automations.store import AutomationStore
from iras.tools.automations import make_tools as automation_tools
from iras.providers.demo import DemoProvider
from iras.providers.openai_compatible import OpenAICompatibleProvider
from iras.providers.openrouter import OpenRouterProvider
from iras.core.agent import IRASAgent
from iras.device_bridge.recovery_learning import RecoveryRoutePerformanceStore
from iras.device_bridge.local_store import LocalDeviceBridgeStore
from iras.device_bridge.tools import make_tools as device_bridge_tools
from iras.device_bridge.skill_tools import make_tools as device_skill_tools
from iras.device_bridge.skills import PersistentSkillStore
from iras.persona import build_system_prompt
from iras.v5 import build_v5_runtime
from iras.tools.v5 import make_tools as v5_tools
from iras.tools.vision import make_tools as vision_tools
from iras.vision.omniparser_runtime import OmniParserRuntimeManager
from iras.orchestration import OrchestrationManager

class Runtime:
    def __init__(self,settings,agent,registry,memory,audit,browser,automations,personality,v5=None,vision=None):
        self.settings=settings; self.agent=agent; self.registry=registry; self.memory=memory; self.audit=audit; self.browser=browser; self.automations=automations; self.personality=personality; self.v5=v5; self.vision=vision

def build_runtime(settings=None,approval_callback=None,hard_cap=PermissionLevel.CRITICAL):
    s=settings or Settings.load(); audit=AuditLogger(s.audit_path); memory=MemoryStore(s.db_path); auto=PermissionLevel(max(0,min(s.auto_permission_level,3)))
    perms=PermissionEngine(auto,approval_callback,s.always_confirm_critical,hard_cap); reg=ToolRegistry(perms,audit); browser=BrowserSession(); autos=AutomationStore(memory); personality=AdaptivePersonality(memory,audit,enabled=s.adaptive_personality)
    local_device = LocalDeviceBridgeStore()
    skill_path = s.data_dir / "app_skills.json"
    app_skills = PersistentSkillStore(skill_path)
    os.environ["IRAS_SKILL_STORE"] = str(skill_path)
    vision = OmniParserRuntimeManager()
    for t in [*FILES,*SHELL,*SYSTEM,*WEB,*GIT,*API_ACCESS,*REMOTE,*memory_tools(memory),*personality_tools(personality),*browser_tools(browser),*automation_tools(autos),*device_bridge_tools(local_device),*device_skill_tools(local_device, app_skills),*vision_tools(vision)]: reg.register(t)
    if s.provider == 'demo':
        provider = DemoProvider()
    elif s.provider == 'openrouter':
        provider = OpenRouterProvider(
            api_key=s.api_key, model=s.model, timeout=s.request_timeout,
            base_url=s.base_url, app_name=s.system_name
        )
    elif s.provider in {'openai_compatible', 'ollama'}:
        provider = OpenAICompatibleProvider(s.base_url, s.api_key, s.model, s.request_timeout)
    else:
        raise ValueError(f'Unknown IRAS_PROVIDER={s.provider}')
    v5 = build_v5_runtime(state_dir=s.data_dir / "v5")
    for t in v5_tools(v5):
        if t.name not in reg.names(): reg.register(t)
    v5.bind_tool_executor(reg.execute)
    agent=IRASAgent(provider,reg,memory,audit,s.max_agent_steps,system_prompt=build_system_prompt(s.voice_profile),personality=personality,voice_profile=s.voice_profile,recovery_performance_store=RecoveryRoutePerformanceStore(s.data_dir / 'recovery_route_performance.json'))

    # Local RC3 orchestration is real but fail-closed: background workers get a
    # separate READ-only registry, so schedules/research can inspect data without
    # silently inheriting the interactive session's state-changing permissions.
    def local_plan(objective, context):
        if context.get("research_project"):
            return [
                {"task_id":"research","title":"Research","prompt":objective,"role":"researcher"},
                {"task_id":"review","title":"Review evidence","prompt":"Review the research for correctness, gaps, and conflicting evidence.","role":"reviewer","depends_on":["research"]},
            ]
        if context.get("debate_review"):
            return [
                {"task_id":"propose","title":"Propose","prompt":objective,"role":"general"},
                {"task_id":"challenge","title":"Challenge","prompt":"Challenge the proposal and identify concrete failure modes.","role":"reviewer","depends_on":["propose"]},
                {"task_id":"test","title":"Test reasoning","prompt":"Test the proposal against the challenge and report what is actually supported.","role":"tester","depends_on":["challenge"]},
            ]
        return [{"task_id":"work","title":"Execute read-only objective","prompt":objective,"role":"general"}]

    def local_worker(prompt, context):
        worker_perms = PermissionEngine(PermissionLevel.READ, None, True, PermissionLevel.READ)
        worker_reg = ToolRegistry(worker_perms, audit)
        for tool in [*FILES, *WEB, *GIT, *API_ACCESS, *memory_tools(memory), *device_bridge_tools(local_device), *v5_tools(v5)]:
            if tool.name not in worker_reg.names():
                worker_reg.register(tool)
        if s.provider == 'demo':
            worker_provider = DemoProvider()
        elif s.provider == 'openrouter':
            worker_provider = OpenRouterProvider(api_key=s.api_key, model=s.model, timeout=s.request_timeout, base_url=s.base_url, app_name=s.system_name)
        elif s.provider in {'openai_compatible', 'ollama'}:
            worker_provider = OpenAICompatibleProvider(s.base_url, s.api_key, s.model, s.request_timeout)
        else:
            raise ValueError(f'Unknown IRAS_PROVIDER={s.provider}')
        role = str(context.get("role_directive") or "You are a bounded read-only IRAS worker.")
        deps = context.get("dependency_results") or []
        worker_prompt = role + "\n\nTask: " + str(prompt)
        if deps:
            worker_prompt += "\n\nDependency results:\n" + json.dumps(deps, ensure_ascii=False, default=str)[:20000]
        worker_agent = IRASAgent(worker_provider, worker_reg, memory, audit, s.max_agent_steps, system_prompt=build_system_prompt(s.voice_profile), personality=personality, voice_profile=s.voice_profile)
        try:
            return {"result": worker_agent.handle(worker_prompt), "metrics": {"permission_cap": "READ", "local": True}}
        finally:
            close = getattr(worker_provider, "close", None)
            if callable(close):
                close()

    v5.orchestration_manager = OrchestrationManager(
        local_worker, local_plan, journal_path=s.data_dir / "v5" / "orchestration_runs.json"
    )
    return Runtime(s,agent,reg,memory,audit,browser,autos,personality,v5=v5,vision=vision)
