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

    Some local models emit a tool request as a plain JSON assistant message
    instead of populating OpenAI ``tool_calls``. IRAS normalizes only *entire*
    JSON messages whose tool name is one of the schemas supplied for the turn.
    This keeps the fallback interoperable without turning arbitrary prose or
    untrusted JSON into executable actions.
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
        prepared: list[tuple[dict, int]] = []
        for item in messages[-32:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")[:24]
            content = item.get("content")
            clean = dict(item)
            clean["role"] = role
            if isinstance(content, str):
                clean["content"] = content[:18000]
            encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
            prepared.append((clean, len(encoded)))

        # Keep the newest tool results/current prompt when the context must be
        # trimmed. RC6 accumulated from the oldest retained message forward,
        # which could discard the latest tool round—the worst possible end of
        # the conversation to lose.
        out_reversed: list[dict] = []
        total = 0
        for clean, size in reversed(prepared):
            if total + size > 70000:
                continue
            out_reversed.append(clean)
            total += size
        out = list(reversed(out_reversed))
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

    @staticmethod
    def _allowed_tool_names(tools: list[dict]) -> set[str]:
        names: set[str] = set()
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "").strip()
            else:
                name = str(tool.get("name") or "").strip()
            if name:
                names.add(name)
        return names

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        raw = str(content or "").strip()
        if not raw.startswith("```"):
            return raw
        lines = raw.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            return raw
        first = lines[0].strip().lower()
        if first not in {"```", "```json"}:
            return raw
        return "\n".join(lines[1:-1]).strip()

    @classmethod
    def _content_tool_calls(cls, content: str, tools: list[dict]) -> list[ToolCall]:
        """Normalize content-only local-model tool requests conservatively.

        Only a complete JSON object/list is eligible, and every requested tool
        must already be present in the schemas supplied for this turn. Unknown
        names remain ordinary assistant text and are never executed.
        """
        allowed = cls._allowed_tool_names(tools)
        if not allowed:
            return []
        raw = cls._strip_json_fence(content)
        if not raw or raw[0] not in "[{":
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if isinstance(data, dict) and isinstance(data.get("tool_calls"), list):
            candidates = data["tool_calls"]
        elif isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            candidates = [data]
        else:
            return []

        calls: list[ToolCall] = []
        for item in candidates[:8]:
            if not isinstance(item, dict):
                return []
            function = item.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "").strip()
                arguments = function.get("arguments") or {}
            else:
                name = str(item.get("name") or item.get("tool") or "").strip()
                arguments = item.get("arguments")
                if arguments is None:
                    arguments = item.get("args") or {}
            if name not in allowed:
                return []
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    return []
            if not isinstance(arguments, dict):
                return []
            calls.append(
                ToolCall(
                    str(item.get("id") or uuid.uuid4()),
                    name,
                    arguments,
                )
            )
        return calls

    @staticmethod
    def _payload_tool_calls(payload: dict[str, Any]) -> list[ToolCall]:
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
        return calls

    def complete(self, messages, tools):
        import time

        bounded_tools = self._bounded_tools(tools)
        bounded_messages = self._bounded_messages(messages)
        if bounded_tools:
            bounded_messages = [
                {
                    "role": "system",
                    "content": (
                        "IRAS local fallback tool protocol: use the supplied function tools when external "
                        "evidence or actions are needed. Prefer native tool_calls. If this model/runtime cannot "
                        "emit native tool_calls, respond with ONLY one JSON object of the form "
                        "{\"name\":\"tool_name\",\"arguments\":{...}} using a tool that was supplied. "
                        "Do not present a tool-call JSON object as a completed result."
                    ),
                },
                *bounded_messages,
            ]
        started = time.perf_counter()
        try:
            payload = self._request(
                "local_llm_complete",
                {
                    "messages": bounded_messages,
                    "tools": bounded_tools,
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
        calls = self._payload_tool_calls(payload)

        if not calls and content:
            normalized = self._content_tool_calls(content, bounded_tools)
            if normalized:
                calls = normalized
                content = ""
                payload = dict(payload)
                payload["normalized_content_tool_calls"] = True

        if not content and not calls:
            raise RuntimeError("DEVICE_OLLAMA_UNAVAILABLE: local model returned no text or tool calls.")

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
                for call in calls
            ]
        return ProviderReply(content, calls, assistant_message)

    def stream_text(self, messages, tools):
        """Fallback streaming shim for cloud chat.

        Device Ollama is reached through the paired-PC bridge, so it naturally
        returns one completed response.  Exposing it as a one-chunk stream lets
        MultiProvider fail over cleanly for ordinary streaming chat when every
        cloud provider is unavailable before the first token.
        """
        reply = self.complete(messages, tools)
        if reply.tool_calls:
            raise RuntimeError(
                "DEVICE_OLLAMA_UNAVAILABLE: local streaming fallback produced tool calls."
            )
        if reply.text:
            yield reply.text

    def close(self) -> None:
        return None
