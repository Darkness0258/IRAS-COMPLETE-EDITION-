from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import json
import math
import os
import re
import time


DEFAULT_HALF_LIFE_SECONDS = 14 * 24 * 60 * 60
MAX_EFFECTIVE_WEIGHT = 32.0
MAX_CONTEXTS = 96
KNOWN_ROUTES = {
    "fresh_observe",
    "uia_reground",
    "foreground_vision",
    "desktop_vision",
    "app_refocus_reacquire",
    "full_replan",
}
SEMANTIC_CONDITIONS = {
    "element_exists",
    "element_absent",
    "text_contains",
    "window_title_contains",
}


def _finite_nonnegative(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number < 0:
        return 0.0
    return number


def _route_name(value: Any) -> str:
    route = str(value or "").strip()
    return route if route in KNOWN_ROUTES else ""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _safe_app_identity(title: Any) -> str:
    """Map a window caption to a small non-user-content app vocabulary.

    Arbitrary window/document titles are never persisted. Unknown captions are
    collapsed to ``unknown`` so contextual learning cannot accidentally store a
    filename, contact, page title, or other user content.
    """

    text = _norm(title)
    if not text:
        return "unknown"
    mappings = (
        (r"\bwhatsapp\b", "whatsapp"),
        (r"\bspotify\b", "spotify"),
        (r"\bdiscord\b", "discord"),
        (r"\bnotepad\b", "notepad"),
        (r"\bgoogle chrome\b|\bchrome\b", "chrome"),
        (r"\bmicrosoft edge\b|\bedge\b", "edge"),
        (r"\bwindows powershell\b|\bpowershell\b", "powershell"),
    )
    for pattern, app in mappings:
        if re.search(pattern, text):
            return app
    return "unknown"


def normalize_recovery_learning_context(context: dict[str, Any] | None) -> dict[str, Any]:
    raw = context if isinstance(context, dict) else {}
    app = str(raw.get("app") or "").strip().lower()
    if app not in {
        "whatsapp",
        "spotify",
        "discord",
        "notepad",
        "chrome",
        "edge",
        "powershell",
        "unknown",
    }:
        app = _safe_app_identity(raw.get("foreground_title"))
    if not app:
        app = "unknown"

    raw_uia = raw.get("uia_actionable")
    if raw_uia is True or str(raw_uia).strip().lower() in {"1", "true"}:
        uia = "1"
    elif raw_uia is False or str(raw_uia).strip().lower() in {"0", "false"}:
        uia = "0"
    else:
        uia = "x"

    vision_scope = str(raw.get("vision_scope") or "none").strip().lower()
    if vision_scope not in {"none", "foreground", "desktop"}:
        vision_scope = "none"

    raw_semantic = raw.get("semantic")
    if raw_semantic is True or str(raw_semantic).strip().lower() in {"1", "true"}:
        semantic = "1"
    elif raw_semantic is False or str(raw_semantic).strip().lower() in {"0", "false"}:
        semantic = "0"
    else:
        semantic = "x"

    return {
        "app": app,
        "uia_actionable": uia,
        "vision_scope": vision_scope,
        "semantic": semantic,
    }


def recovery_learning_context_key(context: dict[str, Any] | None) -> str:
    normalized = normalize_recovery_learning_context(context)
    return (
        f"app={normalized['app']}|uia={normalized['uia_actionable']}|"
        f"vision={normalized['vision_scope']}|semantic={normalized['semantic']}"
    )


def recovery_learning_context_from_verification(
    verification_output: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = verification_output if isinstance(verification_output, dict) else {}
    arguments = verification_arguments if isinstance(verification_arguments, dict) else {}
    observation = output.get("observation")
    observation = observation if isinstance(observation, dict) else {}
    foreground = observation.get("foreground")
    foreground = foreground if isinstance(foreground, dict) else {}
    prior_foreground = output.get("prior_foreground")
    prior_foreground = prior_foreground if isinstance(prior_foreground, dict) else {}

    title = str(foreground.get("title") or prior_foreground.get("title") or "")
    condition = _norm(output.get("condition") or arguments.get("condition"))
    vision_scope = str(
        observation.get("vision_scope")
        or output.get("vision_scope")
        or ("foreground" if output.get("vision_escalated") else "none")
    ).strip().lower()

    return normalize_recovery_learning_context(
        {
            "app": _safe_app_identity(title),
            "uia_actionable": observation.get("uia_actionable"),
            "vision_scope": vision_scope,
            "semantic": condition in SEMANTIC_CONDITIONS,
        }
    )


class RecoveryRoutePerformanceStore:
    """Persist bounded global + contextual recovery-route outcome evidence.

    v3.5.21 introduced the privacy-bounded context layer. Context contains only a small
    whitelisted app identity plus coarse UIA/vision/semantic state. Arbitrary
    titles, screenshots, element labels, goals, target text, coordinates, and
    action arguments are never persisted.

    Global priors remain as a fallback. Context priors may only nudge ranking
    among routes already allowed by live evidence and controller safety guards.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
        max_effective_weight: float = MAX_EFFECTIVE_WEIGHT,
        clock: Callable[[], float] | None = None,
    ):
        if path is None:
            data_dir = Path(os.getenv("IRAS_DATA_DIR", "data"))
            path = data_dir / "recovery_route_performance.json"
        self.path = Path(path).expanduser()
        self.half_life_seconds = max(1.0, float(half_life_seconds))
        self.max_effective_weight = max(1.0, float(max_effective_weight))
        self.clock = clock or time.time

    def _empty(self) -> dict[str, Any]:
        return {"version": "3.6.0", "routes": {}, "contexts": {}}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self._empty()
        if not isinstance(raw, dict):
            return self._empty()
        routes = raw.get("routes")
        contexts = raw.get("contexts")
        if not isinstance(routes, dict):
            routes = {}
        if not isinstance(contexts, dict):
            contexts = {}
        # v3.5.20/v3.5.21 files migrate lazily: global priors are retained and
        # any existing context table is preserved. v3.5.22 changes calibration,
        # not the privacy-bounded persisted schema.
        return {"version": "3.6.0", "routes": routes, "contexts": contexts}

    def _decay(self, entry: dict[str, Any], now: float) -> tuple[float, float]:
        last_updated = _finite_nonnegative(entry.get("last_updated"))
        age = max(0.0, now - last_updated) if last_updated else 0.0
        factor = 0.5 ** (age / self.half_life_seconds) if age else 1.0
        success = _finite_nonnegative(entry.get("success_weight")) * factor
        failure = _finite_nonnegative(entry.get("failure_weight")) * factor
        return success, failure

    def _bounded(self, success: float, failure: float) -> tuple[float, float]:
        total = success + failure
        if total <= self.max_effective_weight or total <= 0:
            return success, failure
        scale = self.max_effective_weight / total
        return success * scale, failure * scale

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(payload, encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _update_route_table(
        self,
        table: dict[str, Any],
        route: str,
        *,
        success: bool,
        now: float,
    ) -> None:
        raw_entry = table.get(route)
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        success_weight, failure_weight = self._decay(entry, now)
        if success:
            success_weight += 1.0
            consecutive_successes = int(entry.get("consecutive_successes") or 0) + 1
            consecutive_failures = 0
            last_outcome = "success"
        else:
            failure_weight += 1.0
            consecutive_successes = 0
            consecutive_failures = int(entry.get("consecutive_failures") or 0) + 1
            last_outcome = "failure"
        success_weight, failure_weight = self._bounded(success_weight, failure_weight)
        table[route] = {
            "success_weight": round(success_weight, 6),
            "failure_weight": round(failure_weight, 6),
            "last_updated": now,
            "updates": int(entry.get("updates") or 0) + 1,
            "consecutive_successes": consecutive_successes,
            "consecutive_failures": consecutive_failures,
            "last_outcome": last_outcome,
        }

    def _prune_contexts(self, contexts: dict[str, Any]) -> None:
        if len(contexts) <= MAX_CONTEXTS:
            return
        ordered = sorted(
            contexts.items(),
            key=lambda item: _finite_nonnegative(
                item[1].get("last_updated") if isinstance(item[1], dict) else 0
            ),
            reverse=True,
        )
        keep = dict(ordered[:MAX_CONTEXTS])
        contexts.clear()
        contexts.update(keep)

    def record(
        self,
        route: str,
        *,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route = _route_name(route)
        if not route:
            return {}
        now = float(self.clock())
        data = self._load()
        routes = data.setdefault("routes", {})
        self._update_route_table(routes, route, success=success, now=now)

        if isinstance(context, dict) and context:
            normalized_context = normalize_recovery_learning_context(context)
            key = recovery_learning_context_key(normalized_context)
            contexts = data.setdefault("contexts", {})
            bucket = contexts.get(key)
            if not isinstance(bucket, dict):
                bucket = {}
            route_table = bucket.get("routes")
            if not isinstance(route_table, dict):
                route_table = {}
            self._update_route_table(route_table, route, success=success, now=now)
            contexts[key] = {
                "context": normalized_context,
                "routes": route_table,
                "last_updated": now,
            }
            self._prune_contexts(contexts)

        data["version"] = "3.6.0"
        data["updated_at"] = now
        self._save(data)
        return self.snapshot().get(route, {})

    def _route_snapshot(self, routes: dict[str, Any], now: float) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw_route, raw_entry in routes.items():
            route = _route_name(raw_route)
            if not route or not isinstance(raw_entry, dict):
                continue
            success, failure = self._decay(raw_entry, now)
            success, failure = self._bounded(success, failure)
            effective = success + failure
            if effective < 0.01:
                continue
            success_rate = (success + 1.0) / (effective + 2.0)
            result[route] = {
                "success_weight": round(success, 6),
                "failure_weight": round(failure, 6),
                "effective_samples": round(effective, 6),
                "success_rate": round(success_rate, 6),
                "updates": int(raw_entry.get("updates") or 0),
                "last_updated": _finite_nonnegative(raw_entry.get("last_updated")),
                "consecutive_successes": int(raw_entry.get("consecutive_successes") or 0),
                "consecutive_failures": int(raw_entry.get("consecutive_failures") or 0),
                "last_outcome": str(raw_entry.get("last_outcome") or ""),
            }
        return result

    def snapshot(self) -> dict[str, dict[str, Any]]:
        now = float(self.clock())
        data = self._load()
        return deepcopy(self._route_snapshot(data.get("routes") or {}, now))

    def context_snapshot(
        self,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = float(self.clock())
        data = self._load()
        contexts = data.get("contexts") or {}
        if not isinstance(contexts, dict):
            return {}

        def one(raw: Any) -> dict[str, Any]:
            if not isinstance(raw, dict):
                return {}
            route_table = raw.get("routes")
            if not isinstance(route_table, dict):
                route_table = {}
            return {
                "context": deepcopy(raw.get("context") if isinstance(raw.get("context"), dict) else {}),
                "routes": self._route_snapshot(route_table, now),
                "last_updated": _finite_nonnegative(raw.get("last_updated")),
            }

        if isinstance(context, dict):
            return one(contexts.get(recovery_learning_context_key(context)))

        result: dict[str, Any] = {}
        for key, raw in contexts.items():
            item = one(raw)
            if item.get("routes"):
                result[str(key)] = item
        return deepcopy(result)


def learned_route_prior_message(
    priors: dict[str, Any] | None,
    context_priors: dict[str, Any] | None = None,
) -> str:
    values = priors if isinstance(priors, dict) else {}
    compact = {
        route: {
            "success_rate": item.get("success_rate"),
            "effective_samples": item.get("effective_samples"),
        }
        for route, item in values.items()
        if isinstance(item, dict)
    }
    context_count = len(context_priors) if isinstance(context_priors, dict) else 0
    return (
        "RECOVERY ROUTE PERFORMANCE LEARNING v3.6.0: "
        f"global_priors={compact!r}; contextual_prior_buckets={context_count}. "
        "Context contains only a whitelisted app identity plus coarse UIA/vision/semantic state. "
        "Contextual priors are bounded and decay over time; global priors are fallback guidance. "
        "Both may only nudge ranking among routes already supported by live UI evidence. "
        "They never override exhausted/forbidden routes and never grant action replay."
    )
