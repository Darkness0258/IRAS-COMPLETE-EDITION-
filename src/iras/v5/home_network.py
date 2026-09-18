from __future__ import annotations

import ipaddress
from urllib.parse import quote
from typing import Any, Callable

import httpx


class HttpJsonHomeAdapter:
    """Bounded local-network JSON adapter with fixed host and path validation."""

    allowed_actions = ("status", "command")
    read_only_actions = ("status",)

    def __init__(self, *, use_https: bool = False, timeout: float = 8.0):
        self.scheme = "https" if use_https else "http"
        self.timeout = max(1.0, min(float(timeout), 30.0))

    @staticmethod
    def _path(value: str) -> str:
        path = str(value or "/").strip()
        if not path.startswith("/") or ".." in path or "\\" in path:
            raise ValueError("Home-adapter path must be an absolute bounded URL path.")
        return path

    def status(self, host: str, path: str = "/status") -> Any:
        url = f"{self.scheme}://{host}{self._path(path)}"
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            response = client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            if "json" in response.headers.get("content-type", ""):
                return response.json()
            return {"status": response.status_code, "text": response.text[:12000]}

    def command(self, host: str, path: str = "/command", payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.scheme}://{host}{self._path(path)}"
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            response = client.post(url, json=dict(payload or {}), headers={"Accept": "application/json"})
            response.raise_for_status()
            if "json" in response.headers.get("content-type", ""):
                return response.json()
            return {"status": response.status_code, "text": response.text[:12000]}


class HomeNetworkHub:
    """Restricted adapter hub; no discovery/scanning is performed automatically."""

    def __init__(self, allowed_networks: list[str] | None = None):
        self.allowed = [ipaddress.ip_network(x, strict=False) for x in (allowed_networks or ["127.0.0.0/8"])]
        self.adapters: dict[str, Any] = {}

    def host_allowed(self, host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            return any(ip in net for net in self.allowed)
        except ValueError:
            return host in {"localhost"}

    def register(self, name: str, adapter: Any) -> None:
        self.adapters[name] = adapter

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "allowed_actions": list(getattr(adapter, "allowed_actions", ())),
                "read_only_actions": list(getattr(adapter, "read_only_actions", ())),
            }
            for name, adapter in sorted(self.adapters.items())
        ]

    def invoke(self, name: str, action: str, *, host: str, approval: Callable[[str, str], bool] | None = None, **kwargs):
        if not self.host_allowed(host):
            raise PermissionError("Host is outside configured home/network allowlist.")
        adapter = self.adapters.get(name)
        if adapter is None:
            raise KeyError(name)
        if action not in set(getattr(adapter, "allowed_actions", ())):
            raise PermissionError("Adapter action is not declared.")
        if action not in set(getattr(adapter, "read_only_actions", ())):
            if not approval or not approval(name, action):
                raise PermissionError("State-changing home/network action requires approval.")
        return getattr(adapter, action)(host=host, **kwargs)
