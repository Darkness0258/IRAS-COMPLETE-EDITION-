from pathlib import Path
from types import SimpleNamespace

from iras.device_bridge.ui_control import WindowsUIController

ROOT = Path(__file__).resolve().parents[1]


def test_managed_omniparser_keeps_minimal_openai_import_dependency():
    setup = (ROOT / "setup-omniparser.ps1").read_text(encoding="utf-8")
    assert '"openai==1.3.5"' in setup
    excluded_line = next(line for line in setup.splitlines() if "$excluded =" in line)
    assert "|openai|" not in excluded_line
    cleanup = setup[setup.index("$cleanupPackages = @("):setup.index("$previousErrorActionPreference")]
    assert '"openai"' not in cleanup


class _SemanticCandidateController(WindowsUIController):
    def __init__(self):
        pass

    def _spotify_semantic_snapshot(self, hwnd, *, max_elements=300):
        return {
            "elements": [
                {"index": 0, "name": "What do you want to play?", "role": "Edit", "enabled": True,
                 "rect": {"left": 600, "top": 20, "width": 400, "height": 40}},
                {"index": 1, "name": "Heart touching naat sharif", "role": "ListItem", "enabled": True,
                 "rect": {"left": 500, "top": 220, "width": 260, "height": 60}},
                {"index": 2, "name": "naat old library item", "role": "Text", "enabled": True,
                 "rect": {"left": 20, "top": 330, "width": 250, "height": 40}},
                {"index": 3, "name": "Play", "role": "Button", "enabled": True,
                 "rect": {"left": 760, "top": 800, "width": 50, "height": 50}},
            ]
        }

    def _physical_window_rect(self, hwnd):
        return SimpleNamespace(left=0, top=0, right=1600, bottom=900)


def test_query_result_prefers_central_semantic_match_over_library_sidebar():
    c = _SemanticCandidateController()
    result = c._spotify_find_query_result(1, "naat")
    assert result is not None
    assert result["name"] == "Heart touching naat sharif"


def test_content_play_button_excludes_bottom_transport_play():
    c = _SemanticCandidateController()
    # Existing synthetic Play is in bottom transport and must be ignored.
    assert c._spotify_find_content_play_button(1) is None
