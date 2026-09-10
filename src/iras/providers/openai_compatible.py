from __future__ import annotations

import json
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
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.25,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def complete(self, messages, tools):
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(messages, tools),
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"LLM request timed out after {self.timeout:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LLM network error: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:1000]
            if response.status_code == 401:
                raise RuntimeError("LLM HTTP 401: API key is invalid or unauthorized.")
            if response.status_code == 402:
                raise RuntimeError("LLM HTTP 402: OpenRouter account has insufficient credits for this model.")
            if response.status_code == 429:
                raise RuntimeError("LLM HTTP 429: rate limit reached. Retry later or choose another model.")
            raise RuntimeError(f"LLM HTTP {response.status_code}: {detail}")

        try:
            body = response.json()
            msg = body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM returned an unexpected response format.") from exc

        calls = []
        for tc in msg.get("tool_calls") or []:
            function = tc.get("function") or {}
            raw = function.get("arguments", "{}")
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            calls.append(
                ToolCall(
                    tc.get("id") or str(uuid.uuid4()),
                    function.get("name", ""),
                    args or {},
                )
            )

        return ProviderReply(msg.get("content") or "", calls, msg)
