from __future__ import annotations

import json
import platform
import uuid

import httpx


class IRASRemoteClient:
    def __init__(
        self,
        server_url: str,
        token: str,
        timeout: float = 120,
    ):
        self.server_url = (
            server_url.rstrip("/")
        )
        self.token = token.strip()
        self.timeout = timeout
        self.device_id = (
            f"{platform.system().lower()}-"
            f"{uuid.getnode():x}"
        )
        self.remote_session_id = ""
        self.remote_session_token = ""
        self.remote_session_mode = ""
        self._client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=4,
                max_connections=8,
                keepalive_expiry=60,
            ),
        )

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Device-ID": self.device_id,
            "Content-Type": "application/json",
        }
        if self.remote_session_id and self.remote_session_token:
            headers["X-IRAS-Remote-Session-ID"] = self.remote_session_id
            headers["X-IRAS-Remote-Token"] = self.remote_session_token
        return headers

    def _validate(self):
        if not self.server_url.startswith(
            (
                "https://",
                "http://127.0.0.1",
                "http://localhost",
            )
        ):
            raise ValueError(
                "Use HTTPS for remote "
                "IRAS servers."
            )

        if not self.token:
            raise ValueError(
                "IRAS access token "
                "is missing."
            )

    def health(self):
        r = self._client.get(
            f"{self.server_url}/health",
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def chat(
        self,
        message: str,
    ) -> str:
        self._validate()

        r = self._client.post(
            f"{self.server_url}/v1/chat",
            headers=self._headers(),
            json={
                "message": message,
                "device_id": (
                    self.device_id
                ),
            },
        )

        if r.status_code == 401:
            raise RuntimeError(
                "IRAS server rejected "
                "the access token."
            )

        r.raise_for_status()

        return r.json()[
            "response"
        ]

    def chat_stream(
        self,
        message: str,
    ):
        self._validate()

        headers = {
            **self._headers(),
            "Accept": "text/event-stream",
        }

        with self._client.stream(
            "POST",
            (
                f"{self.server_url}"
                "/v1/chat/stream"
            ),
            headers=headers,
            json={
                "message": message,
                "device_id": (
                    self.device_id
                ),
            },
        ) as response:
            if response.status_code == 401:
                raise RuntimeError(
                    "IRAS server rejected "
                    "the access token."
                )

            if response.status_code == 404:
                yield {
                    "event": "token",
                    "data": {
                        "text": (
                            self.chat(
                                message
                            )
                        ),
                    },
                }
                yield {
                    "event": "done",
                    "data": {
                        "streamed": False,
                    },
                }
                return

            response.raise_for_status()

            event_name = "message"
            data_lines = []

            for line in (
                response.iter_lines()
            ):
                if line == "":
                    if data_lines:
                        raw = "\n".join(
                            data_lines
                        )

                        try:
                            data = (
                                json.loads(
                                    raw
                                )
                            )
                        except (
                            json.JSONDecodeError
                        ):
                            data = {
                                "raw": raw
                            }

                        yield {
                            "event": (
                                event_name
                            ),
                            "data": data,
                        }

                    event_name = (
                        "message"
                    )
                    data_lines = []
                    continue

                if line.startswith(
                    "event:"
                ):
                    event_name = (
                        line[6:].strip()
                    )
                elif line.startswith(
                    "data:"
                ):
                    data_lines.append(
                        line[5:]
                        .lstrip()
                    )

            if data_lines:
                raw = "\n".join(
                    data_lines
                )

                try:
                    data = json.loads(raw)
                except (
                    json.JSONDecodeError
                ):
                    data = {
                        "raw": raw
                    }

                yield {
                    "event": event_name,
                    "data": data,
                }

    def devices(self):
        self._validate()
        response = self._client.get(
            f"{self.server_url}/v1/devices",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("devices", [])

    def create_remote_session(self, *, device_id: str = "", mode: str = "control", ttl_seconds: int = 1800):
        self._validate()
        response = self._client.post(
            f"{self.server_url}/v1/remote/sessions",
            headers=self._headers(),
            json={
                "device_id": device_id or None,
                "mode": mode,
                "ttl_seconds": int(ttl_seconds),
                "scopes": ["windows"],
            },
        )
        response.raise_for_status()
        session = response.json()
        self.remote_session_id = str(session.get("session_id") or "")
        self.remote_session_token = str(session.get("session_token") or "")
        self.remote_session_mode = str(session.get("mode") or "")
        return session

    def revoke_remote_session(self):
        if not self.remote_session_id:
            return {"revoked": False}
        response = self._client.delete(
            f"{self.server_url}/v1/remote/sessions/{self.remote_session_id}",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        self.remote_session_id = ""
        self.remote_session_token = ""
        self.remote_session_mode = ""
        return payload

    def remote_invoke(self, action: str, arguments=None, *, timeout: float = 45.0):
        if not self.remote_session_id or not self.remote_session_token:
            raise RuntimeError("Create a remote session first.")
        response = self._client.post(
            f"{self.server_url}/v1/remote/invoke",
            headers={
                "Content-Type": "application/json",
                "X-Device-ID": self.device_id,
                "X-IRAS-Remote-Token": self.remote_session_token,
            },
            json={
                "session_id": self.remote_session_id,
                "action": action,
                "arguments": arguments or {},
                "timeout": float(timeout),
            },
            timeout=max(self.timeout, float(timeout) + 10),
        )
        response.raise_for_status()
        return response.json().get("result")

    def close(self):
        if not self._client.is_closed:
            self._client.close()
