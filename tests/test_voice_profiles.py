from iras.persona import build_system_prompt
from iras.voice.profiles import get_profile, normalize_profile
from iras.voice.tts import Speaker
from iras.cli import _voice_profile_intent


def test_profile_aliases():
    assert normalize_profile('soft') == 'anime_soft'
    assert normalize_profile('genki') == 'anime_genki'
    assert normalize_profile('cool') == 'anime_cool'
    assert normalize_profile('normal') == 'normal'


def test_anime_soft_uses_adult_jenny_voice():
    p = get_profile('anime_soft')
    assert p.voice == 'en-US-JennyNeural'
    assert p.pitch.startswith('+')


def test_speaker_switches_profiles():
    s = Speaker('edge', 'en-US-AriaNeural', 'anime_soft')
    assert s.voice == 'en-US-JennyNeural'
    s.set_profile('cool')
    assert s.profile_name == 'anime_cool'
    assert s.voice == 'en-US-AriaNeural'


def test_persona_changes_with_profile():
    soft = build_system_prompt('anime_soft')
    cool = build_system_prompt('anime_cool')
    assert 'Anime Young Adult' in soft
    assert 'Anime Cool' in cool
    assert soft != cool


def test_cli_profile_intents():
    assert _voice_profile_intent('voice styles') == ('list', None)
    assert _voice_profile_intent('voice style soft') == ('set', 'anime_soft')
    assert _voice_profile_intent('anime genki') == ('set', 'anime_genki')
    assert _voice_profile_intent('hello') is None
