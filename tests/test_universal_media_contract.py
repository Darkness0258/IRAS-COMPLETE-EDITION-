from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v280_media_stack_is_integrated():
    ui = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    executor = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "executor.py"
    ).read_text(encoding="utf-8")

    tools = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "tools.py"
    ).read_text(encoding="utf-8")

    agent = (
        ROOT
        / "src"
        / "iras"
        / "core"
        / "agent.py"
    ).read_text(encoding="utf-8")

    assert "def spotify_search(" in ui
    assert '"play": 46' in ui
    assert '"pause": 47' in ui
    assert '"spotify_search"' in executor
    assert '"device_spotify_search"' in tools
    assert '"device_spotify_search",' in agent
    assert '"device_media_control",' in agent
