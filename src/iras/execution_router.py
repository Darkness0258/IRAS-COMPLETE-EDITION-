from __future__ import annotations

from dataclasses import dataclass
import re

from iras.deterministic_orchestration import parse_exact_file_objective


@dataclass(frozen=True)
class ExecutionDecision:
    """Local execution-mode decision for an ordinary chat turn.

    This router deliberately does not call an LLM. IRAS must still be able to
    choose a safe execution strategy while cloud model providers are cooling
    down. Explicit /goal and /parallel commands remain higher-priority manual
    overrides in the API layer.
    """

    mode: str
    reason: str
    tasks: tuple[str, ...] = ()
    objective: str = ""
    confidence: float = 1.0


_EXPLICIT_PREFIXES = (
    "/goal",
    "/orchestrate",
    "/agents",
    "/parallel",
    "/multitask",
)

# Verbs that often identify independent information-gathering jobs. Deliberately
# excludes media/app verbs such as "play" so "open Spotify and play naat" stays
# a single direct workflow.
_INDEPENDENT_VERBS = (
    "research",
    "check",
    "inspect",
    "analyze",
    "analyse",
    "find",
    "compare",
    "summarize",
    "summarise",
    "list",
    "report",
    "monitor",
    "search",
    "look up",
    "verify",
    "take a screenshot",
    "capture a screenshot",
)

_IMPLEMENTATION_RE = re.compile(
    r"\b(build|implement|develop|refactor|upgrade|improve|fix|modify|edit|design|integrate|migrate|deploy|configure|install)\b",
    re.IGNORECASE,
)
_VALIDATION_RE = re.compile(
    r"\b(test|verify|validate|review|benchmark|debug|inspect|regression|audit|report)\b",
    re.IGNORECASE,
)
_WORKFLOW_VERB_RE = re.compile(
    r"\b(build|implement|develop|refactor|upgrade|improve|fix|modify|edit|design|integrate|migrate|deploy|configure|install|research|inspect|test|verify|validate|review|benchmark|debug|report)\b",
    re.IGNORECASE,
)
_STRONG_ORCHESTRATION_RE = re.compile(
    r"\b(from scratch|end[- ]to[- ]end|all at once|complete(?:ly)?|fix (?:any|all) failures|until it works|then (?:test|verify|review|deploy)|run tests? and|review regressions?|final report)\b",
    re.IGNORECASE,
)
_DEPENDENT_PRONOUN_RE = re.compile(
    r"\b(it|that|this|them|those|these|the result|the output|the fix|the change|the implementation|the code|what you found|findings)\b",
    re.IGNORECASE,
)
_PARALLEL_CUE_RE = re.compile(
    r"\b(in parallel|simultaneously|at the same time|independent tasks?|do these tasks?|all three|all four|both tasks?)\b",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _strip_list_marker(text: str) -> str:
    return re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", text).strip()


def _split_independent_tasks(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []

    # Strong user-authored separators are safest and should be preserved.
    if "||" in text:
        parts = text.split("||")
    else:
        lines = [_strip_list_marker(line) for line in text.splitlines() if line.strip()]
        marked_lines = [
            line
            for line in text.splitlines()
            if re.match(r"^\s*(?:[-*•]+|\d+[.)])\s+", line)
        ]
        if len(marked_lines) >= 2:
            parts = lines
        elif text.count(";") >= 1:
            parts = text.split(";")
        else:
            # Split only when a connector is followed by a verb that commonly
            # begins an independent job. This avoids tearing apart ordinary
            # compositional commands.
            verb_pattern = "|".join(re.escape(item) for item in _INDEPENDENT_VERBS)
            parts = re.split(
                rf"\s*(?:,\s*|\band\s+)(?=(?:{verb_pattern})\b)",
                text,
                flags=re.IGNORECASE,
            )

    cleaned = [_clean(_strip_list_marker(part)) for part in parts]
    cleaned = [part for part in cleaned if len(part) >= 3]
    if len(cleaned) < 2:
        return []

    # A later clause that says "summarize it" etc. is normally dependent on a
    # previous clause and belongs in one agent workflow rather than true
    # parallel execution.
    for part in cleaned[1:]:
        if _DEPENDENT_PRONOUN_RE.search(part):
            return []

    # At this point each later clause begins with an independent-job verb and
    # does not refer back to a prior result, so two such clauses are sufficient
    # evidence for parallel execution.
    return cleaned[:8]


def decide_execution(text: str) -> ExecutionDecision:
    """Choose direct, deterministic, parallel, or multi-agent execution.

    The decision is intentionally conservative. A normal conversation remains
    direct unless the message clearly describes independent jobs or a
    dependency-heavy workflow.
    """

    raw = str(text or "").strip()
    cleaned = _clean(raw)
    if not cleaned:
        return ExecutionDecision("direct", "empty message", confidence=1.0)

    lower = cleaned.lower()
    if any(lower == prefix or lower.startswith(prefix + " ") for prefix in _EXPLICIT_PREFIXES):
        return ExecutionDecision(
            "direct",
            "explicit execution command is handled by the API override layer",
            confidence=1.0,
        )

    if parse_exact_file_objective(raw) is not None:
        return ExecutionDecision(
            "deterministic",
            "bounded exact-file operation has a provider-independent executor",
            objective=cleaned,
            confidence=1.0,
        )

    implementation = bool(_IMPLEMENTATION_RE.search(cleaned))
    validation = bool(_VALIDATION_RE.search(cleaned))
    workflow_verbs = len(_WORKFLOW_VERB_RE.findall(cleaned))
    strong_workflow = bool(_STRONG_ORCHESTRATION_RE.search(cleaned))

    # Dependency-heavy implementation work benefits from Planner/Coder/Tester/
    # Reviewer/Coordinator rather than sibling workers guessing at ordering.
    if (
        (implementation and validation and workflow_verbs >= 2)
        or (strong_workflow and workflow_verbs >= 2)
        or workflow_verbs >= 5
    ):
        return ExecutionDecision(
            "orchestrate",
            "request contains dependent implementation/verification phases",
            objective=cleaned,
            confidence=0.92,
        )

    tasks = _split_independent_tasks(raw)
    if tasks:
        return ExecutionDecision(
            "parallel",
            "request contains multiple independent jobs",
            tasks=tuple(tasks),
            objective=cleaned,
            confidence=0.88,
        )

    return ExecutionDecision(
        "direct",
        "single conversational or action-oriented request",
        objective=cleaned,
        confidence=0.95,
    )


def role_for_task(text: str) -> str:
    lower = _clean(text).lower()
    if re.search(r"\b(research|search|find|look up|compare|analy[sz]e)\b", lower):
        return "researcher"
    if re.search(r"\b(test|verify|validate|check|benchmark)\b", lower):
        return "tester"
    if re.search(r"\b(review|audit|security review|regression)\b", lower):
        return "reviewer"
    if re.search(r"\b(build|implement|develop|refactor|fix|modify|edit|code|create)\b", lower):
        return "coder"
    return "general"


def parallel_graph(tasks: tuple[str, ...] | list[str]) -> list[dict[str, object]]:
    """Convert independent chat jobs into a dependency-free agent graph."""
    graph: list[dict[str, object]] = []
    for index, raw in enumerate(tasks, start=1):
        prompt = _clean(raw).strip(" ,")
        if not prompt:
            continue
        graph.append(
            {
                "id": f"parallel-{index}",
                "title": prompt[:120],
                "prompt": prompt,
                "role": role_for_task(prompt),
                "priority": 60,
                "depends_on": [],
                "max_retries": 1,
            }
        )
    return graph
