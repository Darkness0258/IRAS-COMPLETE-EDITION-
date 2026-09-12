from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_multi_strategy_windows_launcher():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "ShellExecuteW" in text
    assert "explorer_app_id" in text
    assert "direct_exe" in text
    assert "ranked_matches" in text
    assert "launch_verified" in text
    assert "attempts" in text


def test_catalog_collapses_versioned_app_families():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "def app_family_name(" in text
    assert "same application family" in text
