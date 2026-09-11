from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloud_runtime_registers_device_tools():
    text = (ROOT / "src" / "iras" / "cloud_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "DeviceBridgeStore" in text
    assert "device_bridge_tools" in text


def test_cloud_api_has_pair_and_long_poll_endpoints():
    text = (ROOT / "src" / "iras" / "cloud_api.py").read_text(
        encoding="utf-8"
    )
    assert '"/v1/devices/pair"' in text
    assert '"/v1/device/commands/next"' in text
    assert "X-IRAS-Device-Token" in text


def test_windows_desktop_starts_outbound_bridge():
    text = (ROOT / "src" / "iras" / "remote_desktop.py").read_text(
        encoding="utf-8"
    )
    assert "DeviceBridgeAgent" in text
    assert "_start_device_bridge" in text
    assert "_stop_device_bridge" in text


def test_smart_routing_knows_device_tools():
    text = (ROOT / "src" / "iras" / "core" / "agent.py").read_text(
        encoding="utf-8"
    )
    assert '"device_open_app"' in text
    assert '"device_git_status"' in text
    assert '"device_run_tests"' in text
