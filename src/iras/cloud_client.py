from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import httpx
from rich.console import Console
from rich.panel import Panel

from iras import __version__
from iras.config import Settings
from iras.master_control import MasterControl


def _state_path() -> Path:
    return Path.home() / ".iras" / "cloud-client.json"


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_state(value: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _server(settings: Settings, override: str = "") -> str:
    # IRAS_PUBLIC_BASE_URL describes the server's own public identity and may
    # point at a local/dev service in a Windows .env. The cloud client must
    # never inherit it implicitly. Use IRAS_CLOUD_URL/--server to override the
    # production cloud endpoint explicitly.
    value = (
        override
        or os.getenv("IRAS_CLOUD_URL", "")
        or "https://iras-cloud.onrender.com"
    )
    return value.strip().rstrip("/")


def _token(settings: Settings, override: str = "") -> str:
    return (override or os.getenv("IRAS_CLOUD_TOKEN", "") or settings.api_token).strip()


def _request(client: httpx.Client, method: str, path: str, *, token: str, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, path, headers=headers, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Cloud HTTP {response.status_code} for {response.request.url}: "
            f"{response.text[:1200]}"
        )
    return response


def main() -> None:
    parser = argparse.ArgumentParser(prog="iras-cloud-client")
    parser.add_argument("--server", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--new-thread", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    console = Console()
    settings = Settings.load()
    server = _server(settings, args.server)
    token = _token(settings, args.token)
    if not token or token == "change-me-before-remote-use":
        raise SystemExit("Configure IRAS_CLOUD_TOKEN or IRAS_API_TOKEN first.")
    if not server.lower().startswith("https://") and not server.lower().startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit("Remote IRAS Cloud requires HTTPS.")

    state = _load_state()
    client_id = str(state.get("client_id") or f"pc_{uuid.uuid4().hex}")
    master = MasterControl()
    remote_session: dict | None = None

    with httpx.Client(base_url=server, timeout=120.0) as client:
        console.print(f"[dim]IRAS Cloud: {server}[/dim]")
        try:
            health = client.get("/health", timeout=30.0)
            if health.status_code >= 400:
                raise RuntimeError(
                    f"Cloud preflight HTTP {health.status_code} for "
                    f"{health.request.url}: {health.text[:1200]}"
                )
        except Exception as exc:
            raise SystemExit(
                f"IRAS Cloud preflight failed for {server}: {exc}"
            ) from exc

        registration = _request(
            client,
            "POST",
            "/v1/cloud/clients/register",
            token=token,
            json={
                "client_id": client_id,
                "name": os.getenv("COMPUTERNAME", "IRAS Windows"),
                "platform": "windows",
                "app_version": __version__,
                "capabilities": ["chat", "cloud-sync", "remote-node"],
            },
        ).json()
        thread_id = str(state.get("thread_id") or registration.get("active_thread_id") or "")
        if args.new_thread:
            thread = _request(
                client,
                "POST",
                "/v1/cloud/threads",
                token=token,
                json={"title": "IRAS Windows"},
            ).json()
            thread_id = str(thread["thread_id"])
            _request(client, "POST", f"/v1/cloud/threads/{thread_id}/activate", token=token, json={})
        if not thread_id:
            session = _request(client, "GET", "/v1/cloud/session", token=token).json()
            thread_id = str(session["active_thread_id"])

        state.update({"client_id": client_id, "thread_id": thread_id, "server": server})
        _save_state(state)

        def revoke_master_session() -> None:
            nonlocal remote_session
            if not remote_session:
                return
            try:
                _request(
                    client, "DELETE",
                    f"/v1/remote/sessions/{remote_session.get('session_id')}",
                    token=token,
                )
            except Exception:
                pass
            remote_session = None

        def enable_master_session(minutes: int = 30) -> dict:
            nonlocal remote_session
            current = master.status()
            if not current.get("enabled"):
                console.print(
                    Panel(
                        "Master Control grants CRITICAL registered-tool authority, shell/power Remote capability, "
                        "and suppresses per-action approval prompts for the bounded session.\n\n"
                        "Emergency stop, audit, filesystem roots, Remote authentication and Windows/UAC remain enforced.",
                        title="IRAS Master Control",
                        border_style="red",
                    )
                )
                phrase = console.input("[bold red]Type ENABLE MASTER CONTROL: [/bold red]").strip()
                if phrase != "ENABLE MASTER CONTROL":
                    raise RuntimeError("Master Control was not enabled.")
                current = master.enable(
                    minutes=minutes, allow_power=True, allow_shell=True, autonomous=True,
                    source="cloud_client_local",
                )

            devices = _request(client, "GET", "/v1/devices", token=token).json().get("devices", [])
            machine = os.getenv("COMPUTERNAME", "").strip().casefold()
            device = next(
                (d for d in devices if d.get("online") and str(d.get("display_name") or "").strip().casefold() == machine),
                None,
            ) or next(
                (d for d in devices if d.get("online") and "windows" in str(d.get("platform") or "").lower()),
                None,
            )
            if not device:
                raise RuntimeError("No paired Windows device is online for Master Control.")
            remaining = current.get("remaining_seconds")
            ttl = max(60, min(12 * 60 * 60, int(remaining or minutes * 60)))
            remote_session = _request(
                client, "POST", "/v1/remote/sessions", token=token,
                headers={"X-Device-ID": client_id},
                json={
                    "device_id": device.get("device_id"),
                    "mode": "full",
                    "ttl_seconds": ttl,
                    "scopes": ["windows", "master"],
                },
            ).json()
            return remote_session

        if args.history:
            history = _request(
                client,
                "GET",
                f"/v1/cloud/threads/{thread_id}/messages?limit=80",
                token=token,
            ).json().get("messages", [])
            for item in history:
                who = "You" if item.get("role") == "user" else "IRAS"
                console.print(f"[bold]{who}[/bold] > {item.get('content','')}")

        console.print(
            Panel.fit(
                f"[bold]IRAS Cloud Client {__version__}[/bold]\n"
                f"Server: {server}\n"
                f"Thread: {thread_id}\n"
                "Shared with web + Android. Commands: /new, /history, /agent, /master, /master on, /master off, /exit"
            )
        )

        while True:
            try:
                text = console.input("[bold cyan]You > [/bold cyan]").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not text:
                continue
            if text.lower() in {"/exit", "exit", "quit"}:
                break
            if text.lower() == "/new":
                thread = _request(
                    client,
                    "POST",
                    "/v1/cloud/threads",
                    token=token,
                    json={"title": "IRAS Windows"},
                ).json()
                thread_id = str(thread["thread_id"])
                _request(client, "POST", f"/v1/cloud/threads/{thread_id}/activate", token=token, json={})
                state["thread_id"] = thread_id
                _save_state(state)
                console.print(f"[dim]New shared thread: {thread_id}[/dim]")
                continue
            if text.lower() in {"/agent", "/agent status"}:
                try:
                    status = _request(
                        client, "GET", "/v1/agent/status", token=token
                    ).json()
                    console.print_json(data=status)
                except Exception as exc:
                    console.print(f"[bold red]Agent status failed:[/bold red] {exc}")
                continue
            if text.lower() in {"/master", "/master status"}:
                local_status = master.status()
                console.print_json(data={
                    "local_master": local_status,
                    "cloud_master_session": {
                        "active": bool(remote_session),
                        "session_id": (remote_session or {}).get("session_id"),
                        "expires_at": (remote_session or {}).get("expires_at"),
                    },
                })
                continue
            if text.lower().startswith("/master on"):
                minutes = 30
                parts = text.split()
                for item in parts:
                    if item.isdigit():
                        minutes = int(item)
                        break
                try:
                    session = enable_master_session(minutes)
                    console.print(
                        f"[bold red]MASTER CONTROL ACTIVE[/bold red] · "
                        f"{session.get('max_permission')} · session {str(session.get('session_id') or '')[:12]}"
                    )
                except Exception as exc:
                    console.print(f"[bold red]Master Control failed:[/bold red] {exc}")
                continue
            if text.lower() in {"/master off", "/master disable"}:
                revoke_master_session()
                console.print_json(data=master.disable(source="cloud_client_local"))
                continue
            if text.lower() == "/history":
                history = _request(
                    client,
                    "GET",
                    f"/v1/cloud/threads/{thread_id}/messages?limit=80",
                    token=token,
                ).json().get("messages", [])
                for item in history:
                    who = "You" if item.get("role") == "user" else "IRAS"
                    console.print(f"[bold]{who}[/bold] > {item.get('content','')}")
                continue

            try:
                response = _request(
                    client,
                    "POST",
                    "/v1/chat",
                    token=token,
                    headers={
                        "X-Device-ID": client_id,
                        **({
                            "X-IRAS-Remote-Session-ID": str(remote_session.get("session_id") or ""),
                            "X-IRAS-Remote-Token": str(remote_session.get("session_token") or ""),
                        } if remote_session else {}),
                    },
                    json={
                        "message": text,
                        "device_id": client_id,
                        "client_id": client_id,
                        "thread_id": thread_id,
                        "turn_id": "turn_" + uuid.uuid4().hex,
                    },
                ).json()
                thread_id = str(response.get("thread_id") or thread_id)
                state["thread_id"] = thread_id
                _save_state(state)
                console.print(f"[bold magenta]IRAS > [/bold magenta]{response.get('response','')}")
            except Exception as exc:
                console.print(f"[bold red]Cloud error:[/bold red] {exc}")

        revoke_master_session()


if __name__ == "__main__":
    main()
