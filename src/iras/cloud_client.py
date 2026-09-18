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
    value = (
        override
        or os.getenv("IRAS_CLOUD_URL", "")
        or settings.public_base_url
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
        raise RuntimeError(f"Cloud HTTP {response.status_code}: {response.text[:1200]}")
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

    with httpx.Client(base_url=server, timeout=120.0) as client:
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
                "Shared with web + Android. Commands: /new, /history, /exit"
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
                    headers={"X-Device-ID": client_id},
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


if __name__ == "__main__":
    main()
