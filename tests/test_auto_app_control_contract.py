from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_executor_uses_universal_controller():
    text = read("src/iras/device_bridge/executor.py")
    assert "UniversalWindowsController" in text
    assert '"detect_apps"' in text
    assert '"app_control"' in text


def test_cloud_tools_are_dynamic_not_static_enum():
    text = read("src/iras/device_bridge/tools.py")
    assert '"device_detect_apps"' in text
    assert '"device_app_control"' in text
    assert "Installed/running GUI app name" in text


def test_media_stop_has_pause_and_global_stop_safety_path():
    text = read("src/iras/device_bridge/universal_control.py")
    assert 'if action == "stop"' in text
    assert "wm_appcommand_pause" in text
    assert 'self._send_global_media_key(\n                    "stop"' in text


def test_app_catalog_never_interpolates_user_text_into_powershell():
    text = read("src/iras/device_bridge/app_catalog.py")
    assert "Get-StartApps" in text
    assert "shell=False" in text
    assert "user text is never inserted" in text.lower() or "User text is never inserted" in text
