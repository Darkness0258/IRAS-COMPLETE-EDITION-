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
        self._client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=4,
                max_connections=8,
                keepalive_expiry=60,
            ),
        )

    def _headers(self):
        return {
            "Authorization": (
                f"Bearer {self.token}"
            ),
            "X-Device-ID": (
                self.device_id
            ),
            "Content-Type": (
                "application/json"
            ),
        }

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

    def close(self):
        if not self._client.is_closed:
            self._client.close()
