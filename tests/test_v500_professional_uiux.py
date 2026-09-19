from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_uses_professional_adaptive_motion_system():
    text = (ROOT / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    for marker in (
        "app-shell",
        "brand-orb",
        "prompt-grid",
        "composer-wrap",
        "@keyframes messageIn",
        "dialog[open]",
        "prefers-reduced-motion",
        "MutationObserver",
        'aria-live="polite"',
    ):
        assert marker in text
    assert "cdn." not in text.lower()


def test_android_uses_adaptive_tonal_ui_and_motion():
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
        "GradientDrawable",
        "DecelerateInterpolator",
        "animateIn(",
        "setOnApplyWindowInsetsListener",
        "setContentDescription",
        "Unified intelligence workspace",
        "CLOUD ONLINE",
    ):
        assert marker in text


def test_windows_desktop_has_structured_workspace_and_motion():
    text = (ROOT / "src" / "iras" / "desktop.py").read_text(encoding="utf-8")
    for marker in (
        "Intelligence Workspace",
        "Command Center",
        "_fade_in",
        "_pulse_status",
        "_show_approval",
        "<Control-l>",
    ):
        assert marker.lower() in text.lower()


def test_uiux_research_notes_are_packaged():
    notes = (ROOT / "docs" / "UI_UX_PROFESSIONAL_RC3.md").read_text(encoding="utf-8")
    assert "Fluent 2 Motion" in notes
    assert "Material 3" in notes
    assert "prefers-reduced-motion" in notes
