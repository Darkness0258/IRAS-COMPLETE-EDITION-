from pathlib import Path

from iras.device_bridge.ui_control import WindowsUIController

ROOT = Path(__file__).resolve().parents[1]


class OverlayController(WindowsUIController):
    def __init__(self):
        self.snapshots = [
            {"elements": [{"name": "What do you want to play?", "role": "Edit"}]},
            {"elements": []},
        ]
        self.keys = []
        self.foreground = []

    def _spotify_semantic_snapshot(self, hwnd, *, max_elements=300):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def _force_foreground(self, hwnd):
        self.foreground.append(hwnd)
        return True

    def press(self, key):
        self.keys.append(key)


def test_spotify_detects_and_dismisses_quick_search_overlay(monkeypatch):
    monkeypatch.setattr("iras.device_bridge.ui_control.time.sleep", lambda *_: None)
    c = OverlayController()
    result = c._dismiss_spotify_quick_search_overlay(42)
    assert result == {"present_before": True, "dismissed": True, "attempts": 1}
    assert c.keys == ["esc"]


def test_spotify_play_closes_overlay_before_content_play_and_prefers_uia_invoke():
    text = (ROOT / "src/iras/device_bridge/ui_control.py").read_text(encoding="utf-8")
    start = text.index("    def spotify_play(")
    end = text.index("    def _send_media_appcommand(", start)
    block = text[start:end]

    assert block.index("_dismiss_spotify_quick_search_overlay") < block.index("_spotify_find_content_play_button")
    assert block.index("_invoke_spotify_observed_element") < block.index("_click_spotify_observed_element(hwnd, play_button")
    assert '"uia_invoke_content_play_button"' in block
    assert '"semantic_play_button_space"' not in block
    assert "_click_spotify_play_button" not in block
    assert '"quick_search_overlay": success.get("overlay")' in block


def test_spotify_uia_invoke_supports_invoke_and_legacy_default_action():
    ui = (ROOT / "src/iras/device_bridge/ui_control.py").read_text(encoding="utf-8")
    visual = (ROOT / "src/iras/device_bridge/visual_control.py").read_text(encoding="utf-8")
    assert "SemanticVisualController(self).invoke_observed_element" in ui
    assert "InvokePattern" in visual
    assert "LegacyIAccessiblePattern" in visual
    assert "DoDefaultAction" in visual
    assert "The previously observed UI element is no longer present" in visual
