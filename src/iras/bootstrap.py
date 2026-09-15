from __future__ import annotations
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

class Runtime:
    def __init__(self,settings,agent,registry,memory,audit,browser,automations,personality): self.settings=settings; self.agent=agent; self.registry=registry; self.memory=memory; self.audit=audit; self.browser=browser; self.automations=automations; self.personality=personality

def build_runtime(settings=None,approval_callback=None,hard_cap=PermissionLevel.CRITICAL):
    s=settings or Settings.load(); audit=AuditLogger(s.audit_path); memory=MemoryStore(s.db_path); auto=PermissionLevel(max(0,min(s.auto_permission_level,3)))
    perms=PermissionEngine(auto,approval_callback,s.always_confirm_critical,hard_cap); reg=ToolRegistry(perms,audit); browser=BrowserSession(); autos=AutomationStore(memory); personality=AdaptivePersonality(memory,audit,enabled=s.adaptive_personality)
    local_device = LocalDeviceBridgeStore()
    skill_path = s.data_dir / "app_skills.json"
    app_skills = PersistentSkillStore(skill_path)
    os.environ["IRAS_SKILL_STORE"] = str(skill_path)
    for t in [*FILES,*SHELL,*SYSTEM,*WEB,*GIT,*API_ACCESS,*REMOTE,*memory_tools(memory),*personality_tools(personality),*browser_tools(browser),*automation_tools(autos),*device_bridge_tools(local_device),*device_skill_tools(local_device, app_skills)]: reg.register(t)
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
    agent=IRASAgent(provider,reg,memory,audit,s.max_agent_steps,system_prompt=build_system_prompt(s.voice_profile),personality=personality,voice_profile=s.voice_profile,recovery_performance_store=RecoveryRoutePerformanceStore(s.data_dir / 'recovery_route_performance.json'))
    return Runtime(s,agent,reg,memory,audit,browser,autos,personality)
