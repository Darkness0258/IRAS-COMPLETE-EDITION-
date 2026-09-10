from __future__ import annotations

import json
import platform
import uuid

import httpx


class IRASRemoteClient:
    def __init__(self, server_url: str, token: str, timeout: float = 120):
        self.server_url = server_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        self.device_id = f"{platform.system().lower()}-{uuid.getnode():x}"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Device-ID": self.device_id,
            "Content-Type": "application/json",
        }

    def health(self):
        with httpx.Client(timeout=20) as client:
            r = client.get(f"{self.server_url}/health")
            r.raise_for_status()
            return r.json()

    def chat(self, message: str) -> str:
        if not self.server_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("Use HTTPS for remote IRAS servers.")
        if not self.token:
            raise ValueError("IRAS access token is missing.")
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.server_url}/v1/chat",
                headers=self._headers(),
                json={"message": message, "device_id": self.device_id},
            )
            if r.status_code == 401:
                raise RuntimeError("IRAS server rejected the access token.")
            r.raise_for_status()
            return r.json()["response"]
