from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from iras.models import ProviderReply, ToolCall
from iras.providers.base import Provider


class OpenAICompatibleProvider(Provider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 90,
        extra_headers: dict[str, str] | None = None,
        max_tokens: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})
        self.max_tokens = max_tokens

        # Lazily created and then reused. Reusing one HTTP client keeps the
        # TCP/TLS connection alive instead of reconnecting to OpenRouter on
        # every agent step and every chat turn.
        self._client: httpx.Client | None = None

        self.last_request_ms = 0
        self.last_response_model = model

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        if self.api_key:
            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )

        return headers

    def _get_client(self) -> httpx.Client:
        if (
            self._client is None
            or self._client.is_closed
        ):
            self._client = httpx.Client(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=8,
                    max_connections=16,
                    keepalive_expiry=60,
                ),
            )

        return self._client

    def close(self) -> None:
        if (
            self._client is not None
            and not self._client.is_closed
        ):
            self._client.close()

    def _payload(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.25,
        }

        if self.max_tokens:
            payload["max_tokens"] = int(
                self.max_tokens
            )

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        return payload

    def complete(self, messages, tools):
        started = time.perf_counter()

        try:
            response = self._get_client().post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(
                    messages,
                    tools,
                ),
            )

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "LLM request timed out after "
                f"{self.timeout:g} seconds."
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"LLM network error: {exc}"
            ) from exc

        finally:
            self.last_request_ms = int(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            )

        if response.status_code >= 400:
            detail = response.text[:1000]

            if response.status_code == 401:
                raise RuntimeError(
                    "LLM HTTP 401: API key is invalid "
                    "or unauthorized."
                )

            if response.status_code == 402:
                raise RuntimeError(
                    "LLM HTTP 402: OpenRouter account "
                    "has insufficient credits for this model."
                )

            if response.status_code == 429:
                raise RuntimeError(
                    "LLM HTTP 429: rate limit reached. "
                    "Retry later or choose another model."
                )

            raise RuntimeError(
                "LLM HTTP "
                f"{response.status_code}: "
                f"{detail}"
            )

        try:
            body = response.json()
            msg = body["choices"][0]["message"]
            self.last_response_model = (
                body.get("model")
                or self.model
            )

        except (
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise RuntimeError(
                "LLM returned an unexpected "
                "response format."
            ) from exc

        calls = []

        for tc in (
            msg.get("tool_calls")
            or []
        ):
            function = (
                tc.get("function")
                or {}
            )

            raw = function.get(
                "arguments",
                "{}",
            )

            try:
                args = (
                    json.loads(raw)
                    if isinstance(raw, str)
                    else raw
                )
            except json.JSONDecodeError:
                args = {}

            calls.append(
                ToolCall(
                    tc.get("id")
                    or str(uuid.uuid4()),
                    function.get(
                        "name",
                        "",
                    ),
                    args or {},
                )
            )

        return ProviderReply(
            msg.get("content") or "",
            calls,
            msg,
        )
