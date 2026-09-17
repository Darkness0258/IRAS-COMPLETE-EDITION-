from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from iras.models import ProviderReply, ToolCall
from iras.providers.base import Provider


class DeviceOllamaProvider(Provider):
    """OpenAI-style reasoning fallback executed on the paired Windows device.

    The cloud never connects to a laptop port directly. Requests travel through
    the authenticated outbound-only IRAS device queue, where DeviceExecutor is
    allowed to contact only a loopback Ollama endpoint. Tool calls returned by
    the local model still execute through the normal cloud ToolRegistry and its
    permission/session/project-root checks.
    """

    def __init__(
        self,
        request: Callable[[str, dict[str, Any], int], Any],
        *,
        model: str = "",
        timeout: int = 120,
    ):
        self._request = request
        self.model = model or "device-ollama:auto"
        self.timeout = max(20, min(int(timeout), 180))
        self.last_model = self.model
        self.last_response_model = self.model
        self.last_request_ms = 0
        self.last_first_token_ms = 0

    @staticmethod
    def _bounded_messages(messages: list[dict]) -> list[dict]:
        if not isinstance(messages, list):
            raise RuntimeError("Device Ollama messages must be a list.")
        out: list[dict] = []
        total = 0
        for item in messages[-32:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")[:24]
            content = item.get("content")
            # Preserve assistant tool-call metadata/tool responses where present;
            # JSON size is bounded before the command enters the queue.
            clean = dict(item)
            clean["role"] = role
            if isinstance(content, str):
                clean["content"] = content[:18000]
            encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
            total += len(encoded)
            if total > 70000:
                break
            out.append(clean)
        if not out:
            raise RuntimeError("Device Ollama received no usable messages.")
        return out

    @staticmethod
    def _bounded_tools(tools: list[dict]) -> list[dict]:
        if not isinstance(tools, list):
            return []
        out: list[dict] = []
        total = 0
        for tool in tools[:48]:
            if not isinstance(tool, dict):
                continue
            encoded = json.dumps(tool, ensure_ascii=False, separators=(",", ":"))
            total += len(encoded)
            if total > 50000:
                break
            out.append(tool)
        return out

    def complete(self, messages, tools):
        import time

        started = time.perf_counter()
        try:
            payload = self._request(
                "local_llm_complete",
                {
                    "messages": self._bounded_messages(messages),
                    "tools": self._bounded_tools(tools),
                    "model": "" if self.model == "device-ollama:auto" else self.model,
                    "max_tokens": 900,
                    "temperature": 0.15,
                    "timeout": min(self.timeout, 150),
                },
                self.timeout,
            )
        except Exception as exc:
            raise RuntimeError(f"DEVICE_OLLAMA_UNAVAILABLE: {exc}") from exc
        finally:
            self.last_request_ms = int((time.perf_counter() - started) * 1000)

        if not isinstance(payload, dict):
            raise RuntimeError("DEVICE_OLLAMA_UNAVAILABLE: local model returned an invalid response.")
        model = str(payload.get("model") or self.model)
        self.last_model = model
        self.last_response_model = model
        content = str(payload.get("content") or "")
        calls: list[ToolCall] = []
        for raw_call in payload.get("tool_calls") or []:
            if not isinstance(raw_call, dict):
                continue
            name = str(raw_call.get("name") or "")
            args = raw_call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if name:
                calls.append(
                    ToolCall(
                        str(raw_call.get("id") or uuid.uuid4()),
                        name,
                        args,
                    )
                )
        if not content and not calls:
            raise RuntimeError("DEVICE_OLLAMA_UNAVAILABLE: local model returned no text or tool calls.")
        return ProviderReply(content, calls, payload)

    def close(self) -> None:
        return None
