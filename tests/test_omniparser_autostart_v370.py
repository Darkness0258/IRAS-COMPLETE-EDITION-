from __future__ import annotations

from pathlib import Path

from iras.vision.omniparser_runtime import (
    DEFAULT_BASE_URL,
    OmniParserRuntimeManager,
    RuntimeProbe,
)


def test_v370_omniparser_defaults_to_lazy_local_autostart(monkeypatch):
    monkeypatch.delenv("IRAS_OMNIPARSER_URL", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_AUTOSTART", raising=False)

    assert OmniParserRuntimeManager.autostart_enabled() is True
    assert OmniParserRuntimeManager.base_url() == DEFAULT_BASE_URL
    assert OmniParserRuntimeManager.parse_url().endswith("/parse/")
    assert OmniParserRuntimeManager.text_parse_url().endswith("/parse_text/")
    assert OmniParserRuntimeManager.probe_url().endswith("/probe/")
    assert OmniParserRuntimeManager.bridge_enabled() is True
    assert OmniParserRuntimeManager.text_prewarm_enabled() is True


def test_v370_omniparser_can_be_fully_disabled(monkeypatch):
    monkeypatch.delenv("IRAS_OMNIPARSER_URL", raising=False)
    monkeypatch.setenv("IRAS_OMNIPARSER_AUTOSTART", "false")

    assert OmniParserRuntimeManager.autostart_enabled() is False
    assert OmniParserRuntimeManager.base_url() == ""


def test_v370_remote_endpoint_is_never_process_autostarted(monkeypatch):
    monkeypatch.setenv("IRAS_OMNIPARSER_URL", "https://vision.example.test")
    monkeypatch.setenv("IRAS_OMNIPARSER_AUTOSTART", "true")
    manager = OmniParserRuntimeManager()

    monkeypatch.setattr(
        manager,
        "probe",
        lambda **_: RuntimeProbe(
            ready=False,
            status="unreachable",
            reason="offline",
            base_url=manager.base_url(),
        ),
    )
    spawned = []
    monkeypatch.setattr(manager, "_spawn", lambda: spawned.append(True))

    result = manager.ensure_ready(start=True)

    assert result.ready is False
    assert result.status == "remote_unreachable"
    assert spawned == []


def test_v370_local_endpoint_starts_once_and_waits_for_probe(monkeypatch):
    monkeypatch.setenv("IRAS_OMNIPARSER_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("IRAS_OMNIPARSER_AUTOSTART", "true")
    monkeypatch.setenv("IRAS_OMNIPARSER_START_TIMEOUT", "3")
    manager = OmniParserRuntimeManager()

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    calls = {"probe": 0, "spawn": 0}

    def fake_probe(**_):
        calls["probe"] += 1
        ready = calls["probe"] >= 3
        return RuntimeProbe(
            ready=ready,
            status="ready" if ready else "unreachable",
            reason="" if ready else "not yet",
            pid=4242 if ready else None,
            started_by_iras=ready,
            base_url=manager.base_url(),
        )

    def fake_spawn():
        calls["spawn"] += 1
        return FakeProcess()

    monkeypatch.setattr(manager, "probe", fake_probe)
    monkeypatch.setattr(manager, "_spawn", fake_spawn)
    monkeypatch.setattr(manager, "_write_runtime_state", lambda *_: None)
    monkeypatch.setattr("iras.vision.omniparser_runtime.time.sleep", lambda *_: None)

    result = manager.ensure_ready(start=True)

    assert result.ready is True
    assert result.status == "ready_autostarted"
    assert result.pid == 4242
    assert result.started_by_iras is True
    assert calls["spawn"] == 1


def test_v370_start_json_is_argv_not_shell(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "IRAS_OMNIPARSER_START_JSON",
        '["python.exe","-m","omniparserserver","--port","8010"]',
    )
    monkeypatch.setenv("IRAS_OMNIPARSER_ROOT", str(tmp_path))
    manager = OmniParserRuntimeManager()

    command, cwd = manager._build_command()

    assert command == ["python.exe", "-m", "omniparserserver", "--port", "8010"]
    assert cwd == tmp_path.resolve()
    assert all("&" not in part and ";" not in part for part in command)


def test_v370_missing_installation_fails_with_one_time_setup_hint(monkeypatch):
    monkeypatch.delenv("IRAS_OMNIPARSER_START_JSON", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_START_COMMAND", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_ROOT", raising=False)
    manager = OmniParserRuntimeManager()
    monkeypatch.setattr(manager, "_candidate_roots", lambda: [])

    try:
        manager._build_command()
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected missing OmniParser installation to fail")

    assert "IRAS_OMNIPARSER_ROOT" in text
    assert "automatically" in text

def test_v370_default_server_command_uses_lazy_iras_bridge(monkeypatch, tmp_path):
    root = tmp_path / "OmniParser"
    server = root / "omnitool" / "omniparserserver"
    python = root / ".venv" / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    server.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    monkeypatch.setenv("IRAS_OMNIPARSER_ROOT", str(root))
    monkeypatch.delenv("IRAS_OMNIPARSER_START_JSON", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_START_COMMAND", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_BRIDGE", raising=False)
    manager = OmniParserRuntimeManager()

    command, cwd = manager._build_command()

    assert command[0] == str(python.resolve())
    assert command[1].endswith("omniparser_bridge_server.py")
    assert "--omniparser-root" in command
    assert str(root.resolve()) in command
    assert "--caption-model-name" in command
    assert "--host" in command
    assert "--prewarm-text" in command
    assert cwd == server.resolve()


def test_v370_upstream_fallback_preloads_torch_and_disables_reloader(monkeypatch, tmp_path):
    root = tmp_path / "OmniParser"
    server = root / "omnitool" / "omniparserserver"
    python = root / ".venv" / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    server.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setenv("IRAS_OMNIPARSER_ROOT", str(root))
    monkeypatch.setenv("IRAS_OMNIPARSER_BRIDGE", "false")
    monkeypatch.delenv("IRAS_OMNIPARSER_START_JSON", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_START_COMMAND", raising=False)

    command, _ = OmniParserRuntimeManager()._build_command()

    assert command[1] == "-c"
    assert "import runpy, torch" in command[2]
    assert "run_module('omniparserserver'" in command[2]
    assert "reload=False" in command[2]



def test_v370_runtime_ownership_survives_manager_instance_boundary(monkeypatch):
    monkeypatch.setenv("IRAS_OMNIPARSER_URL", "http://127.0.0.1:8010")
    manager = OmniParserRuntimeManager()
    monkeypatch.setattr(
        OmniParserRuntimeManager,
        "_read_runtime_state",
        classmethod(lambda cls: {
            "pid": 4242,
            "base_url": "http://127.0.0.1:8010",
            "started_by_iras": True,
        }),
    )
    monkeypatch.setattr(
        OmniParserRuntimeManager,
        "_pid_alive",
        staticmethod(lambda pid: int(pid) == 4242),
    )

    assert manager._owned_runtime_pid() == 4242



def test_v370_text_prewarm_can_be_disabled(monkeypatch, tmp_path):
    root = tmp_path / "OmniParser"
    server = root / "omnitool" / "omniparserserver"
    python = root / ".venv" / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    server.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setenv("IRAS_OMNIPARSER_ROOT", str(root))
    monkeypatch.setenv("IRAS_OMNIPARSER_TEXT_PREWARM", "false")
    monkeypatch.delenv("IRAS_OMNIPARSER_START_JSON", raising=False)
    monkeypatch.delenv("IRAS_OMNIPARSER_START_COMMAND", raising=False)

    command, _ = OmniParserRuntimeManager()._build_command()

    assert "--prewarm-text" not in command


def test_v370_status_surfaces_bridge_text_warmup_state(monkeypatch):
    manager = OmniParserRuntimeManager()
    monkeypatch.setattr(
        manager,
        "probe",
        lambda **_: RuntimeProbe(
            ready=True,
            status="ready",
            pid=4242,
            started_by_iras=True,
            base_url="http://127.0.0.1:8010",
        ),
    )
    monkeypatch.setattr(
        manager,
        "_probe_details",
        lambda **_: {
            "bridge": "iras-v3.7-r5",
            "text_model_state": "ready",
            "text_model_loaded": True,
            "text_model_warmup_ms": 4321,
            "text_model_error": None,
            "full_model_loaded": False,
        },
    )

    status = manager.status()

    assert status["bridge_runtime"] == "iras-v3.7-r5"
    assert status["text_model_state"] == "ready"
    assert status["text_model_loaded"] is True
    assert status["text_model_warmup_ms"] == 4321
    assert status["full_model_loaded"] is False
