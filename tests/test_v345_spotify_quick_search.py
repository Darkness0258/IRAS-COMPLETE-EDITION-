from pathlib import Path
from types import SimpleNamespace

from iras.device_bridge.intent import result_message

ROOT = Path(__file__).resolve().parents[1]


def ui_source() -> str:
    return (ROOT / 'src/iras/device_bridge/ui_control.py').read_text(encoding='utf-8')


def spotify_play_block() -> str:
    text = ui_source()
    start = text.index('    def spotify_play(')
    end = text.index('    def _send_media_appcommand(', start)
    return text[start:end]


def test_semantic_spotify_selection_is_primary():
    block = spotify_play_block()
    assert '_spotify_find_query_results' in block
    assert '_open_spotify_search_uri' in block
    assert '_play_spotify_quick_search_result(' not in block
    assert '"uia_invoke_result"' in block
    assert '"uia_invoke_content_play_button"' in block


def test_quick_search_helper_uses_shift_enter_and_foreground_guard():
    text = ui_source()
    start = text.index('    def _play_spotify_quick_search_result(')
    end = text.index('    def spotify_play(', start)
    helper = text[start:end]
    assert '"shift"' in helper
    assert '"enter"' in helper
    assert '_force_foreground' in helper
    assert '"shift+enter"' in helper


def test_query_play_does_not_use_generic_media_play_fallback():
    block = spotify_play_block()
    assert '_send_spotify_play_command(' not in block
    assert '"media_play_sent": False' in block


def test_query_play_forbids_unanchored_green_or_space_fallbacks():
    block = spotify_play_block()
    assert '_spotify_find_content_play_button' in block
    assert '_click_spotify_play_button' not in block
    assert '"visual_green_play_button"' not in block
    assert '"semantic_play_button_space"' not in block


def test_duplicate_remote_exception_prefixes_are_cleaned():
    action = {
        'tool': 'device_spotify_play',
        'arguments': {'query': 'Majboor song'},
    }
    result = SimpleNamespace(
        ok=False,
        error='RuntimeError: RuntimeError: Spotify test failure',
    )
    message = result_message(action, result)
    assert message == "I couldn't complete that action on your PC: Spotify test failure"
    assert 'RuntimeError:' not in message


def test_spotify_success_message_does_not_claim_verified_playback():
    action = {
        'tool': 'device_spotify_play',
        'arguments': {'query': 'Majboor song'},
    }
    result = SimpleNamespace(ok=True, error='')
    message = result_message(action, result)
    assert message == 'I searched Spotify and sent Play for “Majboor song”.'


def test_v345_or_newer_version_contract():
    import re

    init = (ROOT / 'src/iras/__init__.py').read_text(encoding='utf-8')
    project = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    im = re.search(r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)', init)
    pm = re.search(r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)', project)
    assert im is not None and pm is not None
    version = tuple(int(x) for x in im.groups())
    assert version >= (3, 4, 5)
    assert tuple(int(x) for x in pm.groups()) == version
