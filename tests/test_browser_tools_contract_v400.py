from pathlib import Path


def test_browser_runtime_exposes_production_navigation_primitives():
    text = Path("src/iras/browser/playwright_tools.py").read_text(encoding="utf-8")
    for name in (
        "browser_wait_text",
        "browser_upload",
        "browser_new_tab",
        "browser_tabs",
        "browser_switch_tab",
        "browser_back",
        "browser_forward",
    ):
        assert name in text
    assert "set_input_files" in text
