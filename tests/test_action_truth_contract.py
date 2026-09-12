from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_refuses_text_only_tool_success():
    text = (
        ROOT
        / "src"
        / "iras"
        / "core"
        / "agent.py"
    ).read_text(encoding="utf-8")

    assert "required_tool_turn" in text
    assert "forced_tool_retry" in text
    assert "fabricated success statement" in text


def test_spotify_and_media_tools_are_registered():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "tools.py"
    ).read_text(encoding="utf-8")

    assert '"device_spotify_play"' in text
    assert '"device_media_control"' in text


def test_executor_has_bounded_media_handlers():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "executor.py"
    ).read_text(encoding="utf-8")

    assert '"spotify_play"' in text
    assert '"media_control"' in text
