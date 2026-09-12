from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_launcher_contract():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "early_exit_code" in text
    assert "cwd=str(" in text
    assert "SAFE_PROTOCOL_FALLBACKS" in text
    assert '"steam": "steam://open/main"' in text
    assert "registered_protocol" in text


def test_old_immediate_exit_exception_removed():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "exited immediately with code" not in text
