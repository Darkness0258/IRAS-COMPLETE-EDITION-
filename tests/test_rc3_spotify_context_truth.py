from types import SimpleNamespace

from iras.device_bridge.ui_control import WindowsUIController


class _TruthController(WindowsUIController):
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def _physical_window_rect(self, hwnd):
        return SimpleNamespace(left=0, top=0, right=1600, bottom=900)


def _patch_snapshot(monkeypatch, snapshot):
    class FakeSemanticVisualController:
        def __init__(self, ui):
            self.ui = ui

        def observe(self, *args, **kwargs):
            return snapshot

    monkeypatch.setattr(
        "iras.device_bridge.visual_control.SemanticVisualController",
        FakeSemanticVisualController,
    )


def test_library_query_text_does_not_verify_unrelated_now_playing(monkeypatch):
    snapshot = {
        "element_count": 6,
        "elements": [
            {"name": "Pause", "role": "Button", "rect": {"left": 780, "top": 820, "width": 40, "height": 40}},
            {"name": "Heart touching naat sharif", "role": "Text", "rect": {"left": 50, "top": 300, "width": 250, "height": 30}},
            {"name": "Darkness", "role": "Text", "rect": {"left": 1300, "top": 70, "width": 200, "height": 30}},
            {"name": "Through The Skies", "role": "Text", "rect": {"left": 1300, "top": 470, "width": 220, "height": 30}},
            {"name": "Through The Skies", "role": "Text", "rect": {"left": 80, "top": 840, "width": 220, "height": 30}},
        ],
    }
    _patch_snapshot(monkeypatch, snapshot)
    c = _TruthController(snapshot)
    result = c._verify_spotify_playback(1, "naat")
    assert result["playing"] is True
    assert result["query_match"] is False
    assert result["verified"] is False
    assert "Heart touching naat sharif" not in result["query_evidence"]


def test_spotify_cant_play_toast_forces_verification_failure(monkeypatch):
    snapshot = {
        "element_count": 5,
        "elements": [
            {"name": "Pause", "role": "Button", "rect": {"left": 780, "top": 820, "width": 40, "height": 40}},
            {"name": "Heart touching naat sharif", "role": "Text", "rect": {"left": 1300, "top": 70, "width": 250, "height": 30}},
            {"name": "Haal E Dil Kis Ko Sunain", "role": "Text", "rect": {"left": 1300, "top": 470, "width": 250, "height": 30}},
            {"name": "Spotify can't play this right now. If you have the file on your computer, you can import it.", "role": "Text", "rect": {"left": 600, "top": 760, "width": 500, "height": 40}},
        ],
    }
    _patch_snapshot(monkeypatch, snapshot)
    c = _TruthController(snapshot)
    result = c._verify_spotify_playback(1, "naat")
    assert result["playing"] is True
    assert result["query_match"] is True
    assert result["spotify_error"] is not None
    assert result["verified"] is False


def test_query_result_ranker_returns_multiple_unique_central_matches():
    class CandidateController(WindowsUIController):
        def __init__(self):
            pass

        def _spotify_semantic_snapshot(self, hwnd, *, max_elements=300):
            return {
                "elements": [
                    {"index": 0, "name": "Heart touching naat sharif", "role": "ListItem", "enabled": True,
                     "rect": {"left": 500, "top": 220, "width": 260, "height": 60}},
                    {"index": 1, "name": "Beautiful naat collection", "role": "ListItem", "enabled": True,
                     "rect": {"left": 850, "top": 220, "width": 260, "height": 60}},
                    {"index": 2, "name": "naat library", "role": "Text", "enabled": True,
                     "rect": {"left": 20, "top": 330, "width": 250, "height": 40}},
                ]
            }

        def _physical_window_rect(self, hwnd):
            return SimpleNamespace(left=0, top=0, right=1600, bottom=900)

    c = CandidateController()
    results = c._spotify_find_query_results(1, "naat", limit=4)
    names = [item["name"] for item in results]
    assert "Heart touching naat sharif" in names
    assert "Beautiful naat collection" in names
    assert names[0] != "naat library"


def test_spotify_query_play_uses_uri_first_and_has_no_global_resume_fallbacks():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "src/iras/device_bridge/ui_control.py").read_text(encoding="utf-8")
    start = text.index("    def spotify_play(")
    end = text.index("    def _send_media_appcommand(", start)
    block = text[start:end]

    assert block.index("_open_spotify_search_uri") < block.index('self.hotkey(["ctrl", "k"])')
    assert "spotify_error" in block
    assert "candidate_attempts" in block
    assert "_click_spotify_play_button" not in block
    assert "semantic_play_button_space" not in block
    assert "_send_media_appcommand" not in block
