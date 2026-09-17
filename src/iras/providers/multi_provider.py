from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any


@dataclass
class ProviderSlot:
    name: str
    provider: Any
    cooldown_until: float = 0.0
    failures: int = 0
    last_error: str = ""
    last_attempt_at: float = 0.0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    last_latency_ms: int = 0
    last_status_code: int | None = None


class MultiProvider:
    """Cross-provider failover for IRAS."""

    def __init__(self, slots: list[ProviderSlot], cooldown_seconds: int | None = None):
        if not slots:
            raise ValueError(
                "No AI providers are configured. Add at least one provider API key."
            )

        self.slots = slots
        self.model = "multi-provider"
        self.last_model = getattr(slots[0].provider, "model", "")
        self.last_provider = slots[0].name
        self.last_request_ms = 0
        self.last_first_token_ms = 0

        if cooldown_seconds is None:
            try:
                cooldown_seconds = max(
                    5,
                    int(os.getenv("IRAS_PROVIDER_COOLDOWN_SECONDS", "60")),
                )
            except ValueError:
                cooldown_seconds = 60

        self.cooldown_seconds = cooldown_seconds

    @staticmethod
    def _status_code(exc: RuntimeError) -> int | None:
        text = str(exc)
        for code in (400, 401, 402, 403, 404, 408, 409, 429, 500, 502, 503, 504):
            if f"HTTP {code}" in text:
                return code
        return None

    def _cooldown_for(self, exc: RuntimeError) -> int:
        code = self._status_code(exc)
        text = str(exc).lower()

        if code == 429:
            return self.cooldown_seconds
        if code in {401, 402, 403}:
            return max(300, self.cooldown_seconds)
        if code in {400, 404}:
            return max(120, self.cooldown_seconds)
        if (
            "timed out" in text
            or "network error" in text
            or code in {408, 409, 500, 502, 503, 504}
        ):
            return max(15, min(self.cooldown_seconds, 60))
        return self.cooldown_seconds

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc)
        return text if len(text) <= 240 else text[:240] + "..."

    def _mark_failed(self, slot: ProviderSlot, exc: RuntimeError) -> None:
        slot.failures += 1
        slot.last_error = self._safe_error(exc)
        slot.last_failure_at = time.time()
        slot.last_status_code = self._status_code(exc)
        slot.cooldown_until = time.monotonic() + self._cooldown_for(exc)

    @staticmethod
    def _mark_success(slot: ProviderSlot) -> None:
        slot.failures = 0
        slot.last_error = ""
        slot.last_success_at = time.time()
        slot.last_status_code = None
        slot.cooldown_until = 0.0

    def _available(self) -> list[ProviderSlot]:
        now = time.monotonic()
        return [slot for slot in self.slots if slot.cooldown_until <= now]

    def _no_provider_error(self) -> RuntimeError:
        now = time.monotonic()
        waits = [max(0, int(slot.cooldown_until - now)) for slot in self.slots]
        retry_in = min(waits) if waits else self.cooldown_seconds
        return RuntimeError(
            "ALL_PROVIDERS_UNAVAILABLE: all configured AI providers are "
            f"temporarily unavailable or cooling down. Retry in about {retry_in}s."
        )

    def _sync_metrics(self, slot: ProviderSlot) -> None:
        provider = slot.provider
        self.last_provider = slot.name
        self.last_model = (
            getattr(provider, "last_model", None)
            or getattr(provider, "last_response_model", None)
            or getattr(provider, "model", "")
        )
        self.last_request_ms = int(getattr(provider, "last_request_ms", 0) or 0)
        self.last_first_token_ms = int(
            getattr(provider, "last_first_token_ms", 0) or 0
        )

    def configured_names(self) -> list[str]:
        return [slot.name for slot in self.slots]

    @staticmethod
    def _public_state(slot: ProviderSlot, now_mono: float) -> str:
        if slot.cooldown_until > now_mono:
            code = slot.last_status_code
            text = slot.last_error.lower()
            if code == 429 or "rate limit" in text or "rate-limit" in text:
                return "rate_limited"
            if code in {401, 403} or "unauthorized" in text or "invalid api" in text:
                return "auth_error"
            if code in {402} or "quota" in text or "billing" in text:
                return "quota_error"
            if "timed out" in text or "network error" in text or code in {408, 500, 502, 503, 504}:
                return "offline"
            return "cooldown"
        return "online"

    def status(self) -> list[dict]:
        """Backward-compatible minimal provider readiness surface."""
        now = time.monotonic()
        return [
            {
                "name": slot.name,
                "model": getattr(slot.provider, "model", ""),
                "ready": slot.cooldown_until <= now,
                "cooldown_seconds": max(0, int(slot.cooldown_until - now)),
            }
            for slot in self.slots
        ]

    def diagnostics(self) -> list[dict]:
        """Rich health telemetry used by the v4.4 Providers panel."""
        now = time.monotonic()
        rows = []
        available_names = [slot.name for slot in self.slots if slot.cooldown_until <= now]
        next_name = available_names[0] if available_names else ""
        for index, slot in enumerate(self.slots):
            state = self._public_state(slot, now)
            rows.append(
                {
                    "name": slot.name,
                    "model": getattr(slot.provider, "model", ""),
                    "state": state,
                    "ready": state == "online",
                    "configured": True,
                    "order": index + 1,
                    "next": bool(slot.name == next_name),
                    "active": bool(slot.name == self.last_provider and slot.last_success_at > 0),
                    "cooldown_seconds": max(0, int(slot.cooldown_until - now)),
                    "failures": slot.failures,
                    "last_error": slot.last_error,
                    "last_attempt_at": slot.last_attempt_at or None,
                    "last_success_at": slot.last_success_at or None,
                    "last_failure_at": slot.last_failure_at or None,
                    "latency_ms": slot.last_latency_ms,
                    "status_code": slot.last_status_code,
                }
            )
        return rows

    def complete(self, messages, tools):
        slots = self._available()
        if not slots:
            raise self._no_provider_error()

        last_error = None
        for index, slot in enumerate(slots):
            attempt_started = time.perf_counter()
            slot.last_attempt_at = time.time()
            try:
                reply = slot.provider.complete(messages, tools)
                slot.last_latency_ms = int((time.perf_counter() - attempt_started) * 1000)
                self._mark_success(slot)
                self._sync_metrics(slot)

                if index > 0:
                    print(
                        "[IRAS PROVIDER FAILOVER] recovered with "
                        f"{slot.name}/{self.last_model}",
                        flush=True,
                    )
                return reply

            except RuntimeError as exc:
                slot.last_latency_ms = int((time.perf_counter() - attempt_started) * 1000)
                last_error = exc
                self._mark_failed(slot, exc)
                print(
                    "[IRAS PROVIDER FAILOVER] "
                    f"{slot.name} failed: {self._safe_error(exc)}",
                    flush=True,
                )

        raise self._no_provider_error() from last_error

    def stream_text(self, messages, tools):
        slots = self._available()
        if not slots:
            raise self._no_provider_error()

        last_error = None
        for index, slot in enumerate(slots):
            emitted = False
            attempt_started = time.perf_counter()
            slot.last_attempt_at = time.time()
            try:
                for text in slot.provider.stream_text(messages, tools):
                    emitted = True
                    yield text

                if not emitted:
                    raise RuntimeError("LLM returned an empty stream.")

                slot.last_latency_ms = int((time.perf_counter() - attempt_started) * 1000)
                self._mark_success(slot)
                self._sync_metrics(slot)

                if index > 0:
                    print(
                        "[IRAS PROVIDER FAILOVER] stream recovered with "
                        f"{slot.name}/{self.last_model}",
                        flush=True,
                    )
                return

            except RuntimeError as exc:
                slot.last_latency_ms = int((time.perf_counter() - attempt_started) * 1000)
                last_error = exc
                self._mark_failed(slot, exc)

                if emitted:
                    raise

                print(
                    "[IRAS PROVIDER FAILOVER] "
                    f"{slot.name} stream failed before first token: "
                    f"{self._safe_error(exc)}",
                    flush=True,
                )

        raise self._no_provider_error() from last_error

    def close(self) -> None:
        for slot in self.slots:
            close = getattr(slot.provider, "close", None)
            if callable(close):
                close()
