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
    assert "$bridgeCommand = \"& '$escapedDeviceExe' $taskArgument\"" in text


def test_remote_startup_task_runs_hidden_without_leaving_interactive_session():
    text = _script()
    assert '-WindowStyle Hidden -EncodedCommand $encodedBridgeCommand' in text
    assert 'New-ScheduledTaskAction -Execute "powershell.exe" -Argument $hiddenTaskArgs' in text
    assert '-LogonType Interactive' in text


def test_remote_setup_rejects_unhealthy_cloud_before_secret_prompt():
    text = _script()
    assert '$ServerUrl + "/health"' in text
    assert text.index('$ServerUrl + "/health"') < text.index('Read-Host "IRAS_API_TOKEN')


def test_remote_setup_uses_protocol_contract_not_release_major():
    text = _script()
    assert "$health.version" in text
    assert "-notmatch '^4\\.'" not in text
    assert '$health.service_id -ne "iras-cloud"' in text
    assert '[int]$health.remote_protocol -ne 1' in text
    assert "incompatible IRAS remote protocol" in text
