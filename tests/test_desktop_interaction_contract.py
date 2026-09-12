from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_executor_registers_interact_app():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "executor.py"
    ).read_text(encoding="utf-8")

    assert '"interact_app"' in text
    assert "UniversalWindowsController" in text


def test_cloud_tool_exists():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "tools.py"
    ).read_text(encoding="utf-8")

    assert '"device_interact_app"' in text


def test_no_remote_shell_added():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "subprocess" not in text
    assert "shell=True" not in text
