from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any


_FAILURE_PATTERNS = {
    "permission": (r"permission", r"unauthori[sz]ed", r"forbidden", r"access denied", r"requires .*approval", r"uac"),
    "ui_grounding": (r"element.*not found", r"stale", r"foreground.*changed", r"omniparser", r"uia", r"screen", r"visual", r"click"),
    "process_state": (r"process", r"not running", r"exited", r"not responding", r"app.*closed", r"failed to launch"),
    "connectivity": (r"timeout", r"connection", r"network", r"dns", r"http 5\d\d", r"unreachable", r"reset by peer"),
    "verification": (r"verify", r"verification", r"inconclusive", r"expected.*not", r"assert", r"mismatch"),
    "dependency": (r"module not found", r"no module named", r"dependency", r"package", r"not installed", r"missing executable"),
    "file_state": (r"file", r"git", r"merge", r"conflict", r"path", r"directory", r"read-only", r"readonly"),
    "provider": (r"rate limit", r"provider", r"model", r"quota", r"429", r"context length"),
}

_STRATEGIES = {
    "permission": [
        ("inspect_authority", "Inspect the active permission/Remote/Master state; do not repeat the blocked action."),
        ("request_required_authorization", "Request only the minimum missing authorization if the user's goal still requires it."),
        ("use_lower_privilege_route", "Look for a read-only or reversible route that stays inside current authority."),
    ],
    "ui_grounding": [
        ("deep_desktop_context", "Refresh screen + UIA + vision + process context before another GUI action."),
        ("semantic_alternative", "Prefer a semantic/UIA or specialized app action instead of repeating the same click."),
        ("visual_alternative", "If UIA is weak, use fresh visual grounding and a new element_id."),
        ("refocus_or_reopen", "Refocus or reopen the intended app only if live process/window evidence says it is missing or stale."),
    ],
    "process_state": [
        ("process_snapshot", "Inspect structured running-process and visible-window state."),
        ("verify_app_state", "Confirm whether the required app is running, responsive, and foreground-capable."),
        ("relaunch_if_authorized", "Relaunch only the affected app if evidence shows it exited or is unavailable."),
    ],
    "connectivity": [
        ("health_probe", "Run a bounded health/status probe before retrying."),
        ("bounded_backoff", "Use a bounded retry/backoff rather than rapid repetition."),
        ("alternate_endpoint_or_provider", "Use an already-authorized alternate endpoint/provider when available."),
    ],
    "verification": [
        ("fresh_verification", "Gather fresh independent evidence of the requested end state."),
        ("alternate_verifier", "Verify with a different signal such as UI state, file state, process state, or tests."),
        ("repair_smallest_gap", "Repair only the smallest proven gap, then verify again."),
    ],
    "dependency": [
        ("inspect_environment", "Inspect the exact runtime/dependency state and version before changing anything."),
        ("targeted_dependency_fix", "Apply the smallest targeted dependency correction."),
        ("rerun_specific_check", "Re-run the narrow failing check before broad validation."),
    ],
    "file_state": [
        ("inspect_status_diff", "Inspect file/Git state first and identify the smallest conflicting state."),
        ("minimal_reversible_edit", "Make one bounded reversible edit rather than a broad rewrite."),
        ("targeted_test", "Run the smallest relevant test/check and inspect the resulting diff."),
    ],
    "provider": [
        ("provider_status", "Inspect provider cooldown/failure state."),
        ("authorized_fallback", "Use the next configured provider/model without changing task scope."),
        ("reduce_context", "Trim nonessential context if the failure is context-size related."),
    ],
    "unknown": [
        ("gather_fresh_evidence", "Do not guess. Gather fresh state from the most relevant read-only tools."),
        ("narrow_problem", "Reduce the failure to one reproducible component or step."),
        ("choose_reversible_probe", "Use the least invasive reversible diagnostic probe next."),
    ],
}


class CalmDeliberationEngine:
    """Deterministic planning guard that discourages thrashing after failures."""

    def __init__(self):
        try:
            self.max_candidates = max(2, min(int(os.getenv("IRAS_DELIBERATION_CANDIDATES", "4")), 8))
        except ValueError:
            self.max_candidates = 4

    @staticmethod
    def classify(problem: str, evidence: Any = None) -> tuple[str, float, list[str]]:
        blob = " ".join(
            [str(problem or ""), json.dumps(evidence, ensure_ascii=False, default=str) if evidence is not None else ""]
        ).lower()[:100_000]
        scores: list[tuple[int, str, list[str]]] = []
        for category, patterns in _FAILURE_PATTERNS.items():
            hits = [pattern for pattern in patterns if re.search(pattern, blob, flags=re.I)]
            if hits:
                scores.append((len(hits), category, hits))
        if not scores:
            return "unknown", 0.35, []
        scores.sort(reverse=True)
        count, category, hits = scores[0]
        confidence = min(0.95, 0.5 + 0.1 * count)
        return category, confidence, hits

    @staticmethod
    def _attempt_keys(attempts: list[Any]) -> set[str]:
        keys = set()
        for item in attempts or []:
            if isinstance(item, dict):
                raw = str(item.get("strategy") or item.get("route") or item.get("action") or "")
            else:
                raw = str(item or "")
            raw = " ".join(raw.lower().split())
            if raw:
                keys.add(raw)
        return keys

    def plan(
        self,
        problem: str,
        *,
        evidence: Any = None,
        attempts: list[Any] | None = None,
        goal: str = "",
        risk: str = "low",
    ) -> dict[str, Any]:
        problem = " ".join(str(problem or "").split())
        if not problem:
            raise ValueError("problem is required.")
        risk = str(risk or "low").strip().lower()
        if risk not in {"low", "normal", "high"}:
            raise ValueError("risk must be low, normal, or high.")

        category, confidence, signals = self.classify(problem, evidence)
        attempted = self._attempt_keys(list(attempts or []))
        candidates = []
        for index, (strategy, reason) in enumerate(_STRATEGIES.get(category, _STRATEGIES["unknown"])):
            repeated = strategy.lower() in attempted
            score = 1.0 - index * 0.08 - (0.5 if repeated else 0.0)
            if risk == "high" and strategy not in {"inspect_authority", "gather_fresh_evidence", "fresh_verification", "health_probe", "process_snapshot", "inspect_status_diff", "inspect_environment", "provider_status", "deep_desktop_context"}:
                score -= 0.15
            candidates.append(
                {
                    "strategy": strategy,
                    "reason": reason,
                    "score": round(max(0.0, score), 3),
                    "already_attempted": repeated,
                    "recommended": False,
                }
            )
        candidates.sort(key=lambda item: (item["already_attempted"], -item["score"], item["strategy"]))
        candidates = candidates[: self.max_candidates]
        fresh = next((item for item in candidates if not item["already_attempted"]), None)
        if fresh is not None:
            fresh["recommended"] = True

        fingerprint = hashlib.sha256(
            json.dumps(
                {"category": category, "problem": problem, "attempts": sorted(attempted)},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "mode": "deliberate_calm",
            "goal": str(goal or "").strip()[:4000] or None,
            "problem": problem[:12000],
            "failure_class": category,
            "classification_confidence": round(confidence, 3),
            "signals": signals,
            "risk": risk,
            "fingerprint": fingerprint,
            "rules": [
                "Gather fresh ground truth before changing state.",
                "Make one bounded reversible change at a time.",
                "Do not repeat the same failed route without new evidence.",
                "Verify the user's real end state after each repair.",
                "If the best route requires more authority, stop at the permission boundary.",
            ],
            "candidates": candidates,
            "recommended_strategy": fresh["strategy"] if fresh is not None else None,
            "stop_conditions": [
                "requested end state is independently verified",
                "permission or human-input boundary is reached",
                "all materially different bounded routes are exhausted",
                "new evidence shows the original diagnosis was wrong",
            ],
        }

    def status(self) -> dict[str, Any]:
        return {
            "mode": "deliberate_calm",
            "failure_classes": sorted([*list(_FAILURE_PATTERNS), "unknown"]),
            "max_candidates": self.max_candidates,
            "one_change_at_a_time": True,
            "fresh_evidence_first": True,
            "no_repeat_without_new_evidence": True,
            "verification_required": True,
            "artificial_delay": False,
        }
