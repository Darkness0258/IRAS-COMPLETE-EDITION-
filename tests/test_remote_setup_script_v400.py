from pathlib import Path


def _script() -> str:
    return Path("scripts/windows/setup-remote-access.ps1").read_text(encoding="utf-8")


def test_remote_setup_falls_back_when_iras_device_entrypoint_is_missing():
    text = _script()
    assert "Get-Command iras-device -ErrorAction SilentlyContinue" in text
    assert '@("-m", "iras.device_bridge.agent")' in text
    assert "& $deviceExe @devicePrefixArgs @configureArgs" in text


def test_remote_startup_task_supports_python_module_fallback():
    text = _script()
    assert "$taskArgument = '-m iras.device_bridge.agent'" in text
    assert "New-ScheduledTaskAction -Execute $deviceExe -Argument $taskArgument" in text

def test_remote_setup_rejects_unhealthy_cloud_before_secret_prompt():
    text = _script()
    assert '$ServerUrl + "/health"' in text
    assert text.index('$ServerUrl + "/health"') < text.index('Read-Host "IRAS_API_TOKEN')

def test_remote_setup_rejects_old_cloud_backend_version():
    text = _script()
    assert "$health.version" in text
    assert "not running the v4 remote backend" in text
    assert "-notmatch '^4\\.'" in text

