from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import os
import threading
import time
from typing import Any


_SHARED_HEALTH_LOCK = threading.RLock()
_SHARED_HEALTH: dict[str, dict[str, Any]] = {}


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
    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_latency_ms: int = 0
    last_probe_at: float = 0.0
    last_probe_latency_ms: int = 0
    last_probe_state: str = "configured"
    last_probe_error: str = ""
    last_probe_status_code: int | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class MultiProvider:
    """Cross-provider failover for IRAS with health-aware routing telemetry."""

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
        try:
            self.health_stale_seconds = max(30, min(int(os.getenv("IRAS_PROVIDER_HEALTH_STALE_SECONDS", "300")), 3600))
        except ValueError:
            self.health_stale_seconds = 300

    @staticmethod
    def _status_code(exc: RuntimeError) -> int | None:
        text = str(exc)
        for code in (400, 401, 402, 403, 404, 405, 408, 409, 429, 500, 502, 503, 504):
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
        if code in {400, 404, 405}:
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

    @staticmethod
    def _shared_key(slot: ProviderSlot) -> str:
        return f"{slot.name.casefold()}|{str(getattr(slot.provider, 'model', '') or '').casefold()}"

    def _sync_from_shared(self, slot: ProviderSlot) -> None:
        key = self._shared_key(slot)
        with _SHARED_HEALTH_LOCK:
            shared = dict(_SHARED_HEALTH.get(key) or {})
        if not shared:
            return
        for field_name in (
            "failures", "last_error", "last_attempt_at", "last_success_at", "last_failure_at",
            "last_latency_ms", "last_status_code", "total_attempts", "total_successes",
            "total_failures", "total_latency_ms", "last_probe_at", "last_probe_latency_ms",
            "last_probe_state", "last_probe_error", "last_probe_status_code",
        ):
            if field_name in shared:
                setattr(slot, field_name, shared[field_name])
        history = shared.get("history")
        if isinstance(history, list):
            slot.history = list(history[-40:])
        cooldown_epoch = float(shared.get("cooldown_until_epoch") or 0.0)
        if cooldown_epoch > time.time():
            slot.cooldown_until = time.monotonic() + (cooldown_epoch - time.time())
        else:
            slot.cooldown_until = 0.0

    def _publish_shared(self, slot: ProviderSlot) -> None:
        key = self._shared_key(slot)
        remaining = max(0.0, slot.cooldown_until - time.monotonic())
        payload = {
            "failures": slot.failures,
            "last_error": slot.last_error,
            "last_attempt_at": slot.last_attempt_at,
            "last_success_at": slot.last_success_at,
            "last_failure_at": slot.last_failure_at,
            "last_latency_ms": slot.last_latency_ms,
            "last_status_code": slot.last_status_code,
            "total_attempts": slot.total_attempts,
            "total_successes": slot.total_successes,
            "total_failures": slot.total_failures,
            "total_latency_ms": slot.total_latency_ms,
            "last_probe_at": slot.last_probe_at,
            "last_probe_latency_ms": slot.last_probe_latency_ms,
            "last_probe_state": slot.last_probe_state,
            "last_probe_error": slot.last_probe_error,
            "last_probe_status_code": slot.last_probe_status_code,
            "history": list(slot.history[-40:]),
            "cooldown_until_epoch": time.time() + remaining if remaining else 0.0,
        }
        with _SHARED_HEALTH_LOCK:
            _SHARED_HEALTH[key] = payload

    @classmethod
    def _state_from_error(cls, exc: Exception) -> str:
        text = str(exc).lower()
        code = cls._status_code(exc if isinstance(exc, RuntimeError) else RuntimeError(str(exc)))
        if code == 429 or "rate limit" in text or "rate-limit" in text:
            return "rate_limited"
        if code in {401, 403} or "unauthorized" in text or "invalid api" in text:
            return "auth_error"
        if code == 402 or "quota" in text or "billing" in text:
            return "quota_error"
        if "timed out" in text or "network error" in text or code in {408, 500, 502, 503, 504}:
            return "offline"
        return "cooldown"

    def _record_history(self, slot: ProviderSlot, *, ok: bool, latency_ms: int, error: str = "", status_code: int | None = None, source: str = "request") -> None:
        slot.history.append({
            "at": time.time(),
            "ok": bool(ok),
            "latency_ms": max(0, int(latency_ms or 0)),
            "error": str(error or "")[:160],
            "status_code": status_code,
            "source": str(source or "request")[:24],
        })
        if len(slot.history) > 40:
            del slot.history[:-40]

    def _mark_failed(self, slot: ProviderSlot, exc: RuntimeError) -> None:
        slot.failures += 1
        slot.total_attempts += 1
        slot.total_failures += 1
        slot.total_latency_ms += max(0, int(slot.last_latency_ms or 0))
        slot.last_error = self._safe_error(exc)
        slot.last_failure_at = time.time()
        slot.last_status_code = self._status_code(exc)
        slot.cooldown_until = time.monotonic() + self._cooldown_for(exc)
        self._record_history(slot, ok=False, latency_ms=slot.last_latency_ms, error=slot.last_error, status_code=slot.last_status_code)
        self._publish_shared(slot)

    def _mark_success(self, slot: ProviderSlot) -> None:
        slot.total_attempts += 1
        slot.total_successes += 1
        slot.total_latency_ms += max(0, int(slot.last_latency_ms or 0))
        slot.failures = 0
        slot.last_error = ""
        slot.last_success_at = time.time()
        slot.last_status_code = None
        slot.cooldown_until = 0.0
        self._record_history(slot, ok=True, latency_ms=slot.last_latency_ms)
        self._publish_shared(slot)

    def _mark_probe(self, slot: ProviderSlot, result: dict[str, Any] | None = None, exc: Exception | None = None) -> None:
        slot.last_probe_at = time.time()
        if exc is not None:
            err = self._safe_error(exc)
            state = self._state_from_error(exc)
            code = self._status_code(exc if isinstance(exc, RuntimeError) else RuntimeError(str(exc)))
            slot.last_probe_state = state
            slot.last_probe_error = err
            slot.last_probe_status_code = code
            if state in {"rate_limited", "auth_error", "quota_error", "offline", "cooldown"}:
                slot.last_error = err
                slot.last_status_code = code
                slot.cooldown_until = max(slot.cooldown_until, time.monotonic() + self._cooldown_for(exc if isinstance(exc, RuntimeError) else RuntimeError(str(exc))))
            self._record_history(slot, ok=False, latency_ms=slot.last_probe_latency_ms, error=err, status_code=code, source="probe")
            self._publish_shared(slot)
            return
        data = dict(result or {})
        slot.last_probe_latency_ms = max(0, int(data.get("latency_ms") or 0))
        slot.last_probe_status_code = data.get("status_code")
        slot.last_probe_state = str(data.get("state") or ("online" if data.get("ok") else "configured"))
        slot.last_probe_error = str(data.get("detail") or "")[:240]
        if data.get("ok"):
            slot.last_error = ""
            slot.last_status_code = None
            slot.cooldown_until = 0.0
        self._record_history(slot, ok=bool(data.get("ok")), latency_ms=slot.last_probe_latency_ms, error=slot.last_probe_error, status_code=slot.last_probe_status_code, source="probe")
        self._publish_shared(slot)

    def _health_score(self, slot: ProviderSlot, index: int) -> float:
        # Static order remains the tie-breaker, while repeated failures and
        # proven latency can move a healthier provider ahead after real use.
        score = 1000.0 - (index * 12.0)
        if slot.total_attempts:
            success_rate = slot.total_successes / max(1, slot.total_attempts)
            score += success_rate * 80.0
            score -= min(200.0, slot.failures * 55.0)
            avg_latency = slot.total_latency_ms / max(1, slot.total_attempts)
            score -= min(40.0, avg_latency / 250.0)
        if slot.last_probe_at and slot.last_probe_state not in {"online", "configured"}:
            score -= 100.0
        return score

    def _available(self) -> list[ProviderSlot]:
        now = time.monotonic()
        for slot in self.slots:
            self._sync_from_shared(slot)
        candidates = [(self._health_score(slot, index), index, slot) for index, slot in enumerate(self.slots) if slot.cooldown_until <= now]
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [slot for _, _, slot in candidates]

    def route_order(self) -> list[str]:
        return [slot.name for slot in self._available()]

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

    def _public_state(self, slot: ProviderSlot, now_mono: float) -> str:
        if slot.cooldown_until > now_mono:
            return self._state_from_error(RuntimeError(slot.last_error or f"LLM HTTP {slot.last_status_code or 503}"))
        freshest = max(slot.last_success_at or 0.0, slot.last_probe_at or 0.0)
        if freshest and (time.time() - freshest) <= self.health_stale_seconds:
            if slot.last_probe_at >= slot.last_success_at and slot.last_probe_state not in {"", "configured"}:
                return slot.last_probe_state
            return "online"
        if freshest:
            return "stale"
        return "configured"

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
        for slot in self.slots:
            self._sync_from_shared(slot)
        ranked = self._available()
        next_name = ranked[0].name if ranked else ""
        rows = []
        for index, slot in enumerate(self.slots):
            state = self._public_state(slot, now)
            attempts = max(0, slot.total_attempts)
            success_rate = (slot.total_successes / attempts) if attempts else None
            avg_latency = int(slot.total_latency_ms / attempts) if attempts else 0
            rows.append(
                {
                    "name": slot.name,
                    "model": getattr(slot.provider, "model", ""),
                    "state": state,
                    "ready": state == "online",
                    "routable": slot.cooldown_until <= now,
                    "configured": True,
                    "order": index + 1,
                    "route_rank": ([item.name for item in ranked].index(slot.name) + 1) if slot in ranked else None,
                    "health_score": round(self._health_score(slot, index), 2),
                    "next": bool(slot.name == next_name),
                    "active": bool(slot.name == self.last_provider and slot.last_success_at > 0),
                    "cooldown_seconds": max(0, int(slot.cooldown_until - now)),
                    "failures": slot.failures,
                    "attempts": attempts,
                    "successes": slot.total_successes,
                    "success_rate": round(success_rate * 100.0, 1) if success_rate is not None else None,
                    "avg_latency_ms": avg_latency,
                    "last_error": slot.last_error or slot.last_probe_error,
                    "last_attempt_at": slot.last_attempt_at or None,
                    "last_success_at": slot.last_success_at or None,
                    "last_failure_at": slot.last_failure_at or None,
                    "latency_ms": slot.last_latency_ms or slot.last_probe_latency_ms,
                    "status_code": slot.last_status_code or slot.last_probe_status_code,
                    "last_probe_at": slot.last_probe_at or None,
                    "probe_state": slot.last_probe_state,
                    "recent": list(slot.history[-10:]),
                }
            )
        return rows

    def probe_all(self, timeout: float = 6.0) -> list[dict]:
        """Actively verify configured cloud providers without generating text."""
        timeout = max(1.0, min(float(timeout), 12.0))

        def probe_slot(slot: ProviderSlot):
            probe = getattr(slot.provider, "probe", None)
            if not callable(probe):
                return slot, {"ok": False, "verified": False, "state": "configured", "detail": "Provider has no active health probe."}, None
            started = time.perf_counter()
            try:
                result = probe(timeout=timeout)
                if isinstance(result, dict):
                    result.setdefault("latency_ms", int((time.perf_counter() - started) * 1000))
                return slot, result if isinstance(result, dict) else {"ok": True, "state": "online"}, None
            except Exception as exc:
                return slot, None, exc

        with ThreadPoolExecutor(max_workers=min(6, len(self.slots)), thread_name_prefix="iras-provider-probe") as pool:
            futures = [pool.submit(probe_slot, slot) for slot in self.slots]
            for future in as_completed(futures):
                slot, result, exc = future.result()
                if result is not None:
                    slot.last_probe_latency_ms = int(result.get("latency_ms") or 0)
                self._mark_probe(slot, result, exc)
        return self.diagnostics()

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
