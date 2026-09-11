import pytest

from iras.device_bridge.executor import DeviceExecutor


def test_executor_reads_only_inside_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    file_path = allowed / "hello.txt"
    file_path.write_text("hello bridge", encoding="utf-8")

    executor = DeviceExecutor([str(allowed)])
    result = executor.read_text(str(file_path))
    assert result["content"] == "hello bridge"

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(PermissionError):
        executor.read_text(str(outside))


def test_executor_rejects_arbitrary_app_names(tmp_path):
    executor = DeviceExecutor([str(tmp_path)])

    with pytest.raises(PermissionError):
        executor.open_app("powershell")


def test_executor_rejects_arbitrary_actions(tmp_path):
    executor = DeviceExecutor([str(tmp_path)])

    with pytest.raises(PermissionError):
        executor.execute("run_shell", {"command": "whoami"})
