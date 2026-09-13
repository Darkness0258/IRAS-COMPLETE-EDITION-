from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def src(): return (ROOT/"src/iras/device_bridge/ui_control.py").read_text(encoding="utf-8")
def block():
    t=src(); a=t.index("    def spotify_play("); b=t.index("    def _send_media_appcommand(",a); return t[a:b]

def test_spotify_keeps_legacy_visual_detector():
    t=src()
    assert "def _spotify_play_button_point(" in t
    assert "ImageGrab.grab(" in t
    assert "def _click_spotify_play_button(" in t

def test_spotify_quick_search_uses_shift_enter():
    t=src()
    assert "def _play_spotify_quick_search_result(" in t
    assert '"shift"' in t and '"enter"' in t
    assert '"quick_search_shift_enter"' in t

def test_quick_search_is_primary_and_green_button_is_fallback():
    t=block()
    assert t.index("_play_spotify_quick_search_result") < t.index("_click_spotify_play_button")

def test_query_play_never_uses_generic_media_play():
    t=block()
    assert "_send_spotify_play_command(" not in t
    assert '"media_play_sent": False' in t
