from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import httpx

from iras.remote_access import RemoteAccessPolicy
from iras.remote_protocol import validate_cloud_health
from iras.safety_runtime import EmergencyStop
from iras.security.secret_store import protection_backend
from iras.voice.stt import Listener
from iras.vision.omniparser_runtime import OmniParserRuntimeManager
from iras.master_control import MasterControl


def _free_gb(path: Path) -> float:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except Exception:
        return 0.0


def _device_bridge_config() -> dict:
    path = Path.home() / ".iras-device-bridge.json"
    if not path.exists():
        return {"present": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"present": True, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}
    return {
        "present": True,
        "path": str(path),
        "server_url": data.get("server_url"),
        "device_id": data.get("device_id"),
        "protected_device_token": bool(data.get("device_token_protected")),
        "protected_api_token": bool(data.get("api_token_protected")),
        "legacy_plain_device_token": bool(data.get("device_token")),
        "secret_backend": data.get("secret_backend"),
    }


def run(settings):
    checks = []

    def add(name, ok, detail):
        checks.append((name, bool(ok), detail))

    add("Python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    add("Windows target", os.name == "nt", sys.platform)
    add("Git", bool(shutil.which("git")), shutil.which("git") or "not found")
    mpv = shutil.which("mpv") or (
        r"C:\Program Files\MPV Player\mpv.exe"
        if os.name == "nt" and Path(r"C:\Program Files\MPV Player\mpv.exe").exists()
        else None
    )
    add("MPV voice playback", bool(mpv), mpv or "not found")
    add(
        "Edge TTS",
        importlib.util.find_spec("edge_tts") is not None,
        "installed" if importlib.util.find_spec("edge_tts") else "missing",
    )
    add(
        "Playwright browser",
        importlib.util.find_spec("playwright") is not None,
        "installed" if importlib.util.find_spec("playwright") else "optional extra not installed",
    )
    add(
        "Local Whisper",
        importlib.util.find_spec("faster_whisper") is not None,
        "installed" if importlib.util.find_spec("faster_whisper") else "optional extra not installed",
    )
    add(
        "Brain configured",
        settings.provider in {"demo", "ollama"} or bool(settings.api_key) or settings.provider == "multi",
        settings.provider,
    )

    try:
        multitask_workers = max(1, min(int(os.getenv("IRAS_MULTITASK_WORKERS", "4")), 8))
    except ValueError:
        multitask_workers = 4
    try:
        multitask_max_tasks = max(2, min(int(os.getenv("IRAS_MULTITASK_MAX_TASKS", "8")), 12))
    except ValueError:
        multitask_max_tasks = 8
    add(
        "Multitasking",
        multitask_workers >= 1 and multitask_max_tasks >= 2,
        f"workers={multitask_workers} max_tasks={multitask_max_tasks}",
    )

    try:
        orchestration_workers = max(1, min(int(os.getenv("IRAS_ORCHESTRATION_WORKERS", "4")), 8))
    except ValueError:
        orchestration_workers = 4
    try:
        orchestration_max_tasks = max(2, min(int(os.getenv("IRAS_ORCHESTRATION_MAX_TASKS", "12")), 20))
    except ValueError:
        orchestration_max_tasks = 12
    try:
        orchestration_provider_wait = max(0, min(int(os.getenv("IRAS_ORCHESTRATION_PROVIDER_WAIT_SECONDS", "21600")), 86400))
    except ValueError:
        orchestration_provider_wait = 900
    try:
        orchestration_agent_steps = max(8, min(int(os.getenv("IRAS_ORCHESTRATION_AGENT_MAX_STEPS", "14")), 24))
    except ValueError:
        orchestration_agent_steps = 14
    add(
        "Multi-agent execution",
        orchestration_workers >= 1 and orchestration_max_tasks >= 2,
        (
            f"workers={orchestration_workers} max_tasks={orchestration_max_tasks} "
            f"planner=enabled provider_wait={orchestration_provider_wait}s agent_steps={orchestration_agent_steps} "
            f"research_text=enabled bounded_patch=enabled deterministic_file=enabled"
        ),
    )

    autonomous_execution = str(os.getenv("IRAS_AUTONOMOUS_EXECUTION", "true")).strip().lower() not in {
        "0", "false", "no", "off"
    }
    add(
        "Autonomous execution routing",
        autonomous_execution,
        "direct/deterministic/parallel/orchestrate automatic chat routing",
    )

    device_ollama_enabled = str(os.getenv("IRAS_DEVICE_OLLAMA_FALLBACK", "true")).strip().lower() in {
        "1", "true", "yes", "on", "enabled"
    }
    ollama_ready = False
    ollama_detail = "disabled"
    if device_ollama_enabled:
        base = str(os.getenv("IRAS_DEVICE_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")).strip().rstrip("/")
        root = base[:-3] if base.endswith("/v1") else base
        try:
            response = httpx.get(root + "/api/tags", timeout=2.5, follow_redirects=False)
            response.raise_for_status()
            models = [
                str(item.get("name") or "")
                for item in (response.json().get("models") or [])
                if isinstance(item, dict) and item.get("name")
            ]
            ollama_ready = bool(models)
            ollama_detail = (
                "ready: " + ", ".join(models[:4])
                if models
                else "Ollama reachable but no local models are installed"
            )
        except Exception as exc:
            ollama_detail = f"optional fallback unavailable: {type(exc).__name__}: {exc}"[:220]
    add(
        "Device-local AI fallback",
        (not device_ollama_enabled) or ollama_ready,
        ollama_detail,
    )

    mic = Listener.microphone_status()
    add("Microphone input", mic.get("available"), f"{mic.get('count', 0)} input device(s)")

    vision = OmniParserRuntimeManager().status()
    add(
        "OmniParser installation",
        bool(vision.get("installation_ready")),
        vision.get("installation_root") or vision.get("installation_reason") or "not provisioned",
    )
    add(
        "OmniParser configuration",
        bool(vision.get("base_url")),
        (
            f"{vision.get('status')} @ {vision.get('base_url') or 'not configured'}; "
            f"eager={vision.get('eager_start_enabled')} watchdog={vision.get('watchdog_enabled')}"
        ),
    )
    full_state = str(vision.get("full_model_state") or "cold").strip().lower()
    full_error = str(vision.get("full_model_error") or "").strip()
    omni_ok = bool(vision.get("ready")) and full_state != "failed"
    omni_detail = vision.get("reason")
    if not omni_detail and full_state == "failed":
        omni_detail = "full visual model failed: " + (full_error or "unknown full-model error")
    if not omni_detail:
        device = vision.get("full_model_device") or "not loaded yet"
        omni_detail = f"ready; full_model_state={full_state} device={device}"
    add(
        "OmniParser ready",
        omni_ok,
        omni_detail,
    )

    master = MasterControl().status()
    add(
        "Master Control",
        True,
        (
            f"{'ENABLED' if master.get('enabled') else 'off'} "
            f"permission={master.get('permission_level') or 'normal'} "
            f"remaining={master.get('remaining_seconds')} "
            f"shell={master.get('allow_shell')} power={master.get('allow_power')} "
            f"autonomous={master.get('autonomous')} "
            f"execution={((master.get('execution_profile') or {}).get('mode') or 'normal')} "
            f"steps={((master.get('execution_profile') or {}).get('agent_steps') or 'normal')}"
        ),
    )

    remote = RemoteAccessPolicy().status()
    add(
        "Remote Windows local policy",
        bool(remote.get("enabled")),
        f"mode={remote.get('mode')} persistent={remote.get('persistent')} kill_switch={remote.get('kill_switch')}",
    )
    bridge = _device_bridge_config()
    add(
        "Remote device bridge configured",
        bool(bridge.get("present") and bridge.get("server_url") and bridge.get("device_id")),
        bridge,
    )
    add(
        "Remote secrets protected",
        bool(
            os.name != "nt"
            or (
                bridge.get("protected_device_token")
                and not bridge.get("legacy_plain_device_token")
                and bridge.get("secret_backend") == "windows-dpapi"
            )
        ),
        bridge.get("secret_backend") or protection_backend(),
    )

    free_gb = _free_gb(Path.home())
    add("Free disk space", free_gb >= 2.0, f"{free_gb:.1f} GB free")

    token = str(getattr(settings, "api_token", "") or "")
    add(
        "Cloud API token strength",
        bool(token and token != "change-me-before-remote-use" and len(token) >= 32),
        "strong/non-default" if token and token != "change-me-before-remote-use" and len(token) >= 32 else "configure a random 32+ byte token",
    )

    server = str(os.getenv("IRAS_SERVER_URL", "") or bridge.get("server_url") or "")
    secure_transport = bool(server.startswith("https://") or server.startswith("http://127.0.0.1") or server.startswith("http://localhost"))
    add(
        "Remote server transport",
        secure_transport,
        server or "not configured",
    )
    reachable = False
    compatible = False
    reach_detail = "not configured"
    compatibility_detail = "not configured"
    if secure_transport and server:
        try:
            response = httpx.get(server.rstrip("/") + "/health", timeout=4.0, follow_redirects=True)
            reachable = response.status_code == 200
            reach_detail = f"HTTP {response.status_code}"
            if reachable:
                try:
                    cloud = validate_cloud_health(response.json())
                    compatible = True
                    compatibility_detail = (
                        f"version={cloud['version']} remote_protocol={cloud['remote_protocol']}"
                    )
                    reach_detail += " " + compatibility_detail
                except Exception as exc:
                    compatibility_detail = f"{type(exc).__name__}: {exc}"[:220]
        except Exception as exc:
            reach_detail = f"{type(exc).__name__}: {exc}"[:220]
            compatibility_detail = reach_detail
    add("Remote server reachable", reachable, reach_detail)
    add("Remote protocol compatible", compatible, compatibility_detail)

    stop = EmergencyStop().status()
    add("Emergency stop clear", not stop.get("tripped"), stop)

    if os.name == "nt":
        try:
            task = subprocess.run(
                ["schtasks", "/Query", "/TN", "IRAS Remote Windows Agent"],
                capture_output=True, text=True, errors="replace", timeout=6, shell=False,
            )
            add("Remote startup task", task.returncode == 0, "registered" if task.returncode == 0 else "not registered")
        except Exception as exc:
            add("Remote startup task", False, f"{type(exc).__name__}: {exc}")

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    add("Hostname", bool(hostname), hostname)
    return checks
