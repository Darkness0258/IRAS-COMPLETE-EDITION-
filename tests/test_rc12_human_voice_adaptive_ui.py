from pathlib import Path

from iras.config import Settings
from iras.voice.multilingual_voice import resolve_voice
from iras.voice.profiles import get_profile, normalize_profile, profile_catalog
from iras.voice.tts import Speaker


ROOT = Path(__file__).resolve().parents[1]


def test_iras_human_is_the_new_default_feminine_identity(monkeypatch):
    monkeypatch.delenv("IRAS_HUMAN_VOICE", raising=False)
    monkeypatch.delenv("IRAS_HUMAN_VOICE_FALLBACKS", raising=False)
    assert normalize_profile(None) == "iras_human"
    profile = get_profile("iras_human")
    assert profile.voice == "en-US-AvaMultilingualNeural"
    assert profile.signature == "human-feminine-multilingual"
    assert profile.fallback_voices == (
        "en-US-EmmaMultilingualNeural",
        "en-US-PhoebeMultilingualNeural",
        "en-US-JennyNeural",
    )
    assert all("Guy" not in voice for voice in (profile.voice, *profile.fallback_voices))


def test_iras_human_voice_is_runtime_configurable(monkeypatch):
    monkeypatch.setenv("IRAS_HUMAN_VOICE", "en-US-EmmaMultilingualNeural")
    monkeypatch.setenv("IRAS_HUMAN_VOICE_FALLBACKS", "en-US-AvaMultilingualNeural,en-US-JennyNeural")
    profile = get_profile("human")
    assert profile.voice == "en-US-EmmaMultilingualNeural"
    assert profile.fallback_voices == (
        "en-US-AvaMultilingualNeural",
        "en-US-JennyNeural",
    )
    row = next(item for item in profile_catalog() if item["key"] == "iras_human")
    assert row["voice"] == "en-US-EmmaMultilingualNeural"


def test_human_speaker_never_uses_male_english_fallback(monkeypatch):
    monkeypatch.delenv("IRAS_HUMAN_VOICE", raising=False)
    monkeypatch.delenv("IRAS_HUMAN_VOICE_FALLBACKS", raising=False)
    speaker = Speaker("edge", profile="iras_human")
    assert speaker.voice == "en-US-AvaMultilingualNeural"
    assert speaker.alternate_voice == "en-US-EmmaMultilingualNeural"
    assert all("Guy" not in voice for voice in speaker._voice_candidates())
    choice = resolve_voice(
        "Hello, I am ready.",
        english_voice=speaker.voice,
        english_alternate=speaker.alternate_voice,
        mood="warm",
    )
    assert choice.voice == "en-US-AvaMultilingualNeural"
    assert choice.alternate_voice == "en-US-EmmaMultilingualNeural"
    assert choice.gender == "female"


def test_default_settings_use_human_voice(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRAS_VOICE_PROFILE", raising=False)
    settings = Settings.load()
    assert settings.voice_profile == "iras_human"


def test_cloud_tts_accepts_client_voice_profile_and_exposes_catalog():
    text = (ROOT / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    assert 'voice_profile: str = Field(default="", max_length=64)' in text
    assert '@app.get("/v1/voice/profiles")' in text
    assert 'body.voice_profile or settings.voice_profile' in text
    assert '"X-IRAS-Voice-Profile"' in text or '"Voice-Profile"' in text
    assert '*profile.fallback_voices' in text


def test_web_ui_has_live_voice_presence_and_responsive_mobile_dock():
    text = (ROOT / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    for marker in (
        'id="voicePresence"',
        'id="voiceProfile"',
        'value="iras_human"',
        'function syncVoicePresence()',
        'voice_profile:c.voiceProfile||"iras_human"',
        '@media(max-width:760px)',
        'env(safe-area-inset-bottom)',
        'body[data-ui-state="speaking"]',
    ):
        assert marker in text


def test_android_ui_has_human_voice_surface_and_profile_request():
    text = (
        ROOT
        / "clients"
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "darkness"
        / "iras"
        / "MainActivity.java"
    ).read_text(encoding="utf-8")
    for marker in (
        "IRAS HUMAN  ·  READY",
        "Ava multilingual · warm neural identity",
        "syncVoicePresence",
        'prefs.getString("voice_profile", "iras_human")',
        'body.put("voice_profile"',
        "voiceCard",
    ):
        assert marker in text


def test_desktop_ui_exposes_voice_identity_and_profile_switcher():
    text = (ROOT / "src" / "iras" / "desktop.py").read_text(encoding="utf-8")
    for marker in (
        "_cycle_voice_profile",
        "header_voice_label",
        "voice_identity",
        '"iras_human", "anime_soft", "anime_cool", "anime_genki", "normal"',
        "IRAS HUMAN · READY",
    ):
        assert marker in text
