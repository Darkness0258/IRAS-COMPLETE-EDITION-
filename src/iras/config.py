from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os


def _load_dotenv(path: Path = Path('.env')) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {'1', 'true', 'yes', 'on'}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


@dataclass(slots=True)
class Settings:
    provider: str
    model: str
    api_key: str
    base_url: str
    request_timeout: float
    auto_permission_level: int
    always_confirm_critical: bool
    api_token: str
    node_token: str
    node_max_permission_level: int
    tts_provider: str
    voice: str
    stt_provider: str
    whisper_model: str
    listen_seconds: int
    data_dir: Path
    log_dir: Path
    max_agent_steps: int
    system_name: str
    voice_replies: bool = True
    voice_profile: str = 'iras_human'
    adaptive_personality: bool = True
    database_url: str = ''
    public_base_url: str = ''
    cors_origins: str = '*'
    voice_approvals: bool = True
    voice_approval_critical: bool = True
    voice_approval_timeout: int = 9

    @classmethod
    def load(cls) -> 'Settings':
        _load_dotenv()
        provider = os.getenv('IRAS_PROVIDER', 'openrouter').strip().lower()

        if provider == 'ollama':
            default_base = 'http://127.0.0.1:11434/v1'
            default_model = 'qwen2.5-coder:7b'
            api_key = os.getenv('IRAS_API_KEY', '')
        elif provider == 'openrouter':
            default_base = 'https://openrouter.ai/api/v1'
            default_model = 'openrouter/free'
            api_key = os.getenv('OPENROUTER_API_KEY', os.getenv('IRAS_API_KEY', ''))
        elif provider == 'multi':
            default_base = 'https://openrouter.ai/api/v1'
            default_model = os.getenv(
                'IRAS_OPENROUTER_MODEL',
                'nex-agi/nex-n2.5-mini:free',
            )
            api_key = os.getenv(
                'OPENROUTER_API_KEY',
                os.getenv('IRAS_API_KEY', ''),
            )
        else:
            default_base = 'https://openrouter.ai/api/v1'
            default_model = 'openrouter/free'
            api_key = os.getenv('IRAS_API_KEY', '')

        return cls(
            provider=provider,
            model=os.getenv('IRAS_MODEL', default_model),
            api_key=api_key,
            base_url=os.getenv('IRAS_BASE_URL', default_base).rstrip('/'),
            request_timeout=float(os.getenv('IRAS_REQUEST_TIMEOUT', '90')),
            auto_permission_level=int(os.getenv('IRAS_AUTO_PERMISSION_LEVEL', '1')),
            always_confirm_critical=_bool('IRAS_ALWAYS_CONFIRM_CRITICAL', True),
            api_token=os.getenv('IRAS_API_TOKEN', 'change-me-before-remote-use'),
            node_token=os.getenv('IRAS_NODE_TOKEN', 'change-me-before-remote-use'),
            node_max_permission_level=int(os.getenv('IRAS_NODE_MAX_PERMISSION_LEVEL', '1')),
            tts_provider=os.getenv('IRAS_TTS_PROVIDER', 'edge'),
            voice=os.getenv('IRAS_VOICE', 'en-US-AriaNeural'),
            voice_replies=_bool('IRAS_VOICE_REPLIES', True),
            voice_profile=os.getenv('IRAS_VOICE_PROFILE', 'iras_human'),
            stt_provider=os.getenv('IRAS_STT_PROVIDER', 'whisper_local'),
            whisper_model=os.getenv('IRAS_WHISPER_MODEL', 'base'),
            listen_seconds=int(os.getenv('IRAS_LISTEN_SECONDS', '6')),
            data_dir=Path(os.getenv('IRAS_DATA_DIR', 'data')),
            log_dir=Path(os.getenv('IRAS_LOG_DIR', 'logs')),
            max_agent_steps=int(os.getenv('IRAS_MAX_AGENT_STEPS', '8')),
            system_name=os.getenv('IRAS_SYSTEM_NAME', 'IRAS'),
            adaptive_personality=_bool('IRAS_ADAPTIVE_PERSONALITY', True),
            database_url=os.getenv('DATABASE_URL', '').strip(),
            public_base_url=os.getenv('IRAS_PUBLIC_BASE_URL', '').strip().rstrip('/'),
            cors_origins=os.getenv('IRAS_CORS_ORIGINS', '*').strip(),
            voice_approvals=_bool('IRAS_VOICE_APPROVALS', True),
            voice_approval_critical=_bool('IRAS_VOICE_APPROVAL_CRITICAL', True),
            voice_approval_timeout=_int_env('IRAS_VOICE_APPROVAL_TIMEOUT', 9, 3, 30),
        )

    @property
    def db_path(self):
        return self.data_dir / 'iras.db'

    @property
    def audit_path(self):
        return self.log_dir / 'audit.jsonl'
