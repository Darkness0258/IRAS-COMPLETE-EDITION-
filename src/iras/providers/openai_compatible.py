from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterator

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

        self._client: httpx.Client | None = None

        self.last_request_ms = 0
        self.last_first_token_ms = 0
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

    @staticmethod
    def _env_seconds(
        name: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            value = float(
                os.getenv(
                    name,
                    str(default),
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            value = default

        return max(
            minimum,
            min(
                value,
                maximum,
            ),
        )

    @classmethod
    def _first_token_timeout_seconds(
        cls,
    ) -> float:
        return cls._env_seconds(
            "IRAS_FIRST_TOKEN_TIMEOUT",
            8.0,
            minimum=3.0,
            maximum=30.0,
        )

    @classmethod
    def _stream_read_timeout_seconds(
        cls,
    ) -> float:
        first = (
            cls
            ._first_token_timeout_seconds()
        )

        configured = cls._env_seconds(
            "IRAS_STREAM_READ_TIMEOUT",
            10.0,
            minimum=5.0,
            maximum=45.0,
        )

        return max(
            configured,
            first + 1.0,
        )

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

    @staticmethod
    def _runtime_http_error(
        status_code: int,
        detail: str,
    ) -> RuntimeError:
        if status_code == 401:
            return RuntimeError(
                "LLM HTTP 401: API key is invalid "
                "or unauthorized."
            )

        if status_code == 402:
            clean = (
                detail.strip()
                or (
                    "Provider requires credits, billing, "
                    "or additional quota."
                )
            )
            return RuntimeError(
                "LLM HTTP 402: "
                + clean[:900]
            )

        if status_code == 429:
            return RuntimeError(
                "LLM HTTP 429: rate limit reached. "
                "Retry later or choose another model."
            )

        return RuntimeError(
            "LLM HTTP "
            f"{status_code}: "
            f"{detail[:1000]}"
        )

    def _check_response(
        self,
        response: httpx.Response,
    ) -> None:
        if response.status_code < 400:
            return

        try:
            response.read()
            detail = response.text
        except Exception:
            detail = ""

        raise self._runtime_http_error(
            response.status_code,
            detail,
        )

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

        self._check_response(response)

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

    @staticmethod
    def _content_text(content) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []

            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)

            return "".join(parts)

        return ""

    def stream_text(
        self,
        messages,
        tools,
    ) -> Iterator[str]:
        """
        Stream text deltas from an OpenAI-compatible SSE endpoint.

        IRAS uses this for normal conversation where no tool calls are
        required. Tool-bearing turns continue through complete().
        """
        started = time.perf_counter()
        self.last_first_token_ms = 0

        payload = self._payload(
            messages,
            tools,
        )
        payload["stream"] = True

        first_token_timeout = (
            self
            ._first_token_timeout_seconds()
        )
        stream_read_timeout = (
            self
            ._stream_read_timeout_seconds()
        )

        request_timeout = httpx.Timeout(
            connect=min(
                max(
                    3.0,
                    float(self.timeout),
                ),
                10.0,
            ),
            read=stream_read_timeout,
            write=min(
                max(
                    5.0,
                    float(self.timeout),
                ),
                20.0,
            ),
            pool=10.0,
        )

        try:
            with self._get_client().stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=request_timeout,
            ) as response:
                self._check_response(response)

                for line in response.iter_lines():
                    if (
                        not self.last_first_token_ms
                        and (
                            time.perf_counter()
                            - started
                        )
                        > first_token_timeout
                    ):
                        raise RuntimeError(
                            "LLM timed out waiting for first token after "
                            f"{first_token_timeout:g} seconds."
                        )

                    if not line:
                        continue

                    if line.startswith(":"):
                        continue

                    if not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()

                    if raw == "[DONE]":
                        break

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    error = event.get("error")

                    if error:
                        code = error.get("code")
                        message = (
                            error.get("message")
                            or str(error)
                        )

                        try:
                            status_code = int(code)
                        except (
                            TypeError,
                            ValueError,
                        ):
                            status_code = 500

                        raise self._runtime_http_error(
                            status_code,
                            message,
                        )

                    model = event.get("model")
                    if model:
                        self.last_response_model = model

                    try:
                        delta = (
                            event["choices"][0]
                            .get("delta")
                            or {}
                        )
                    except (
                        KeyError,
                        IndexError,
                        TypeError,
                    ):
                        continue

                    text = self._content_text(
                        delta.get("content")
                    )

                    if not text:
                        continue

                    if not self.last_first_token_ms:
                        self.last_first_token_ms = int(
                            (
                                time.perf_counter()
                                - started
                            )
                            * 1000
                        )

                    yield text

        except httpx.TimeoutException as exc:
            if not self.last_first_token_ms:
                raise RuntimeError(
                    "LLM timed out waiting for first token after "
                    f"{first_token_timeout:g} seconds."
                ) from exc

            raise RuntimeError(
                "LLM stream stalled for "
                f"{stream_read_timeout:g} seconds."
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
