from __future__ import annotations

from pathlib import Path
import time

from iras.models import PermissionLevel
from iras.tools.vision import make_tools
from iras.vision.omniparser_runtime import OmniParserRuntimeManager, RuntimeProbe


def test_managed_vision_defaults_are_eager_and_watched(monkeypatch):
    for name in (
        "IRAS_OMNIPARSER_AUTOSTART",
        "IRAS_OMNIPARSER_EAGER_START",
        "IRAS_OMNIPARSER_WATCHDOG",
        "IRAS_OMNIPARSER_WATCHDOG_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert OmniParserRuntimeManager.autostart_enabled() is True
    assert OmniParserRuntimeManager.eager_start_enabled() is True
    assert OmniParserRuntimeManager.watchdog_enabled() is True
    assert OmniParserRuntimeManager.watchdog_interval() == 20.0


def test_managed_bridge_command_uses_v3_detector_and_absolute_caption(monkeypatch, tmp_path):
    root = tmp_path / "OmniParser"
    server = root / "omnitool" / "omniparserserver"
    python = root / ".venv" / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
    server.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    detector = root / "weights" / "icon_detect_v3" / "model.pt"
    caption = root / "weights" / "icon_caption_florence" / "model.safetensors"
    detector.parent.mkdir(parents=True)
    caption.parent.mkdir(parents=True)
    detector.write_bytes(b"x")
    caption.write_bytes(b"x")

    monkeypatch.setenv("IRAS_OMNIPARSER_ROOT", str(root))
    manager = OmniParserRuntimeManager()
    command, _ = manager._build_command()

    assert "--som-model-path" in command
    assert str(detector.resolve()) in command
    assert "--caption-model-path" in command
    assert str(caption.parent.resolve()) in command
    assert "--control-token" not in command


def test_installation_status_requires_python_and_both_weight_sets(monkeypatch, tmp_path):
    root = tmp_path / "OmniParser"
    root.mkdir()
    detector = root / "weights" / "icon_detect_v3" / "model.pt"
    caption = root / "weights" / "icon_caption_florence" / "model.safetensors"
    detector.parent.mkdir(parents=True)
    caption.parent.mkdir(parents=True)
    detector.write_bytes(b"x")
    caption.write_bytes(b"x")
    monkeypatch.setattr(OmniParserRuntimeManager, "_candidate_roots", staticmethod(lambda: [root]))
    monkeypatch.setattr(OmniParserRuntimeManager, "_python_for_root", staticmethod(lambda _: "python312"))

    state = OmniParserRuntimeManager.installation_status()

    assert state["ready"] is True
    assert state["detector_ready"] is True
    assert state["caption_ready"] is True


def test_supervisor_eager_starts_and_self_heals(monkeypatch):
    manager = OmniParserRuntimeManager()
    calls = {"ensure": 0, "probe": 0}

    def ensure_ready(*, start=True):
        calls["ensure"] += 1
        return RuntimeProbe(True, "ready", base_url="http://127.0.0.1:8010")

    def probe(*, timeout=None):
        calls["probe"] += 1
        return RuntimeProbe(False, "unreachable", base_url="http://127.0.0.1:8010")

    monkeypatch.setattr(manager, "ensure_ready", ensure_ready)
    monkeypatch.setattr(manager, "probe", probe)
    monkeypatch.setattr(manager, "watchdog_interval", lambda: 0.01)
    monkeypatch.setattr(manager, "_is_local_endpoint", lambda: True)
    monkeypatch.setattr(manager, "autostart_enabled", lambda: True)
    monkeypatch.setattr(manager, "watchdog_enabled", lambda: True)

    manager.start_supervisor(eager=True)
    time.sleep(0.05)
    manager.stop_supervisor()

    assert calls["ensure"] >= 2  # eager start + at least one recovery attempt
    assert calls["probe"] >= 1


def test_vision_lifecycle_tools_keep_stop_restart_elevated():
    tools = {tool.name: tool for tool in make_tools(OmniParserRuntimeManager())}
    assert tools["vision_runtime_status"].permission == PermissionLevel.READ
    assert tools["vision_runtime_start"].permission == PermissionLevel.SAFE_ACTION
    assert tools["vision_runtime_restart"].permission == PermissionLevel.SYSTEM_ACTION
    assert tools["vision_runtime_stop"].permission == PermissionLevel.SYSTEM_ACTION


def test_windows_launcher_and_installer_provision_complete_vision_runtime():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "run-iras.ps1").read_text(encoding="utf-8")
    installer = (root / "install.ps1").read_text(encoding="utf-8")
    setup = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")

    assert "--vision-start" in launcher
    assert "setup-omniparser.ps1" in launcher
    assert "playwright install chromium" in installer
    assert "setup-omniparser.ps1" in installer
    assert "Python.Python.3.12" in setup
    assert "https://github.com/microsoft/OmniParser.git" in setup
    assert "icon_detect_v3/model.pt" in setup
    assert "icon_caption/model.safetensors" in setup
    assert "microsoft/Florence-2-base" in setup
    assert "full_warmup" in setup
    assert "paddle(paddle|ocr)" in setup


def test_bridge_uses_fail_closed_paddle_stub_and_authenticated_stop_endpoint():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "iras" / "vision" / "omniparser_bridge_server.py").read_text(encoding="utf-8")
    assert 'IRAS_OMNIPARSER_DISABLE_PADDLE' in source
    assert 'raise RuntimeError(' in source
    assert '@app.post("/control/stop")' in source
    assert 'X-IRAS-Control-Token' in source
    assert 'IRAS_OMNIPARSER_CONTROL_TOKEN' in source
    assert 'hmac.compare_digest' in source


def test_reachable_unowned_local_vision_requires_explicit_external_opt_in(monkeypatch):
    monkeypatch.setenv("IRAS_OMNIPARSER_URL", "http://127.0.0.1:8010")
    monkeypatch.delenv("IRAS_OMNIPARSER_ALLOW_EXTERNAL", raising=False)
    manager = OmniParserRuntimeManager()

    class Response:
        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("iras.vision.omniparser_runtime.httpx.Client", Client)
    monkeypatch.setattr(manager, "_owned_runtime_pid", lambda: None)

    blocked = manager.probe(timeout=0.1)
    assert blocked.ready is False
    assert blocked.status == "external_unmanaged"

    monkeypatch.setenv("IRAS_OMNIPARSER_ALLOW_EXTERNAL", "true")
    allowed = manager.probe(timeout=0.1)
    assert allowed.ready is True
    assert allowed.status == "ready_external"
    assert allowed.started_by_iras is False


def test_launcher_repairs_unowned_or_unhealthy_managed_vision():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "run-iras.ps1").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    setup = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")
    assert "setup-omniparser.ps1 -Repair" in launcher
    assert "IRAS_OMNIPARSER_ALLOW_EXTERNAL=false" in env
    assert 'Set-DotEnvValue "IRAS_OMNIPARSER_ALLOW_EXTERNAL" "false"' in setup


def test_managed_vision_installer_uses_headless_dependency_surface():
    root = Path(__file__).resolve().parents[1]
    setup = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")
    assert "gradio|streamlit|azure-identity" in setup
    assert '"openai==1.3.5"' in setup
    assert '"huggingface-hub==0.36.2"' in setup
    assert "pip uninstall -y @cleanupPackages" in setup
    assert '(?:\\[[^\\]]+\\])?' in setup
    assert '$ErrorActionPreference = "SilentlyContinue"' in setup
    assert '1>$null 2>$null' in setup
