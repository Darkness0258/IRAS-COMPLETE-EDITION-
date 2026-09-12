from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_open_uses_universal_catalog():
    executor = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "executor.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "return self.ui.catalog.launch("
        in executor
    )


def test_app_control_open_uses_universal_catalog():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "universal_control.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "self.catalog.launch("
        in text
    )


def test_catalog_has_generic_fallback_stack():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "def _shortcut_discovery(" in text
    assert "def _launch_shell_path(" in text
    assert "shell_execute_shortcut" in text
    assert "early_exit_code" in text
    assert "accepted_unverified_after_all_fallbacks" in text


def test_no_app_specific_protocol_required():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "steam://open/main" not in text
