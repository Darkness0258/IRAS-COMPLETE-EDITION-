from __future__ import annotations

import os

from iras.config import Settings
from iras.core.agent import IRASAgent
from iras.memory.store import MemoryStore
from iras.memory.postgres_store import PostgresMemoryStore
from iras.models import PermissionLevel
from iras.persona import build_system_prompt
from iras.personality import AdaptivePersonality
from iras.providers.openrouter import OpenRouterProvider
from iras.providers.provider_factory import build_multi_provider
from iras.security.audit import AuditLogger
from iras.security.permissions import PermissionEngine
from iras.tools.registry import ToolRegistry
from iras.tools.web import TOOLS as WEB
from iras.tools.api_access import TOOLS as API_ACCESS
from iras.tools.memory import make_tools as memory_tools
from iras.tools.personality import make_tools as personality_tools
from iras.device_bridge.store import DeviceBridgeStore
from iras.device_bridge.tools import make_tools as device_bridge_tools
from iras.device_bridge.skill_tools import make_tools as device_skill_tools
from iras.device_bridge.skills import PersistentSkillStore


class CloudRuntime:
    def __init__(
        self,
        settings,
        agent,
        registry,
        memory,
        audit,
        personality,
        device_bridge,
        app_skills,
    ):
        self.settings = settings
        self.agent = agent
        self.registry = registry
        self.memory = memory
        self.audit = audit
        self.personality = personality
        self.device_bridge = device_bridge
        self.app_skills = app_skills


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(
            minimum,
            int(os.getenv(name, str(default))),
        )
    except ValueError:
        return default


def build_cloud_runtime(settings: Settings | None = None) -> CloudRuntime:
    s = settings or Settings.load()

    if s.provider not in {"openrouter", "multi"}:
        raise ValueError(
            "The hosted IRAS server requires IRAS_PROVIDER=openrouter or "
            "IRAS_PROVIDER=multi."
        )

    audit = AuditLogger(s.audit_path)

    if s.database_url:
        memory = PostgresMemoryStore(s.database_url)
    else:
        memory = MemoryStore(s.db_path)

    device_bridge = DeviceBridgeStore(
        database_url=s.database_url,
        sqlite_path=s.data_dir / "device_bridge.db",
    )

    skill_path = os.getenv(
        "IRAS_SKILL_STORE",
        str(s.data_dir / "app_skills.json"),
    )
    skill_database_url = os.getenv(
        "IRAS_SKILL_DATABASE_URL",
        s.database_url,
    ).strip()
    app_skills = PersistentSkillStore(
        skill_path,
        database_url=(skill_database_url or None),
    )
    # TaskTracker constructs its own lightweight store handle. Pin its defaults
    # to the exact backend used by this runtime so learning and management tools
    # always address the same persistent skill set.
    os.environ["IRAS_SKILL_STORE"] = str(app_skills.path)
    if skill_database_url:
        os.environ["IRAS_SKILL_DATABASE_URL"] = skill_database_url
    else:
        os.environ.pop("IRAS_SKILL_DATABASE_URL", None)

    permissions = PermissionEngine(
        auto_level=PermissionLevel.SAFE_ACTION,
        approval_callback=None,
        always_confirm_critical=True,
        hard_cap=PermissionLevel.SAFE_ACTION,
    )

    registry = ToolRegistry(permissions, audit)

    personality = AdaptivePersonality(
        memory,
        audit,
        enabled=s.adaptive_personality,
    )

    for tool in [
        *WEB,
        *API_ACCESS,
        *memory_tools(memory),
        *personality_tools(personality),
        *device_bridge_tools(device_bridge),
        *device_skill_tools(device_bridge, app_skills),
    ]:
        registry.register(tool)

    if s.provider == "multi":
        provider = build_multi_provider(s)
    else:
        provider = OpenRouterProvider(
            api_key=s.api_key,
            model=s.model,
            timeout=s.request_timeout,
            base_url=s.base_url,
            app_name=s.system_name,
        )

    agent = IRASAgent(
        provider,
        registry,
        memory,
        audit,
        s.max_agent_steps,
        system_prompt=build_system_prompt(s.voice_profile),
        personality=personality,
        voice_profile=s.voice_profile,
        context_fact_limit=_env_int("IRAS_CONTEXT_FACTS", 10, 0),
        context_message_limit=_env_int("IRAS_CONTEXT_MESSAGES", 8, 2),
        smart_tools=_env_bool("IRAS_SMART_TOOLS", True),
    )

    return CloudRuntime(
        s,
        agent,
        registry,
        memory,
        audit,
        personality,
        device_bridge,
        app_skills,
    )
