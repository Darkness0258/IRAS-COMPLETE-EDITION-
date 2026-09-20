from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
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
    r"\b(build|implement|develop|refactor|upgrade|improv(?:e|ement)|fix|modify|edit|design|integrate|migrate|deploy|configure|install)\b",
    re.IGNORECASE,
)
_VALIDATION_RE = re.compile(
    r"\b(test|verify|validate|review|benchmark|debug|inspect|regression|audit|report)\b",
    re.IGNORECASE,
)
_WORKFLOW_VERB_RE = re.compile(
    r"\b(build|implement|develop|refactor|upgrade|improv(?:e|ement)|fix|modify|edit|design|integrate|migrate|deploy|configure|install|research|inspect|test|verify|validate|review|benchmark|debug|report)\b",
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

_INFORMATIONAL_REQUEST_RE = re.compile(
    r"^(?:how\b|what\b|why\b|explain\b|tell me about\b|show me how\b|teach me\b|can you explain\b)",
    re.IGNORECASE,
)

_PROJECT_WORK_RE = re.compile(
    r"\b(project|repository|repo|codebase|source|implementation|git|pytest|tests?|regression|IRAS)\b",
    re.IGNORECASE,
)

_PARALLEL_CUE_RE = re.compile(
    r"\b(in parallel|simultaneously|at the same time|independent tasks?|do these tasks?|all three|all four|both tasks?)\b",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _project_identity_tokens(value: str) -> tuple[str, ...]:
    """Normalize a project identifier without guessing unrelated aliases."""
    return tuple(
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").casefold())
        if token
    )


def _project_identity_compact(value: str) -> str:
    return "".join(_project_identity_tokens(value))


_NESTED_PROJECT_NOISE = {
    "artifact", "artifacts", "mock", "mocks", "mockup", "mockups", "sandbox",
    "fixture", "fixtures", "test", "tests", "testing", "example", "examples",
    "sample", "samples", "demo", "demos", "tmp", "temp", "build", "dist",
    "generated", "output", "outputs", "coverage", "node_modules", "vendor",
}


def project_candidate_identity_score(query: str, candidate: dict[str, object]) -> int:
    """Return a conservative typo-tolerant identity score, or -1 when unrelated.

    Candidate *names* are authoritative. Path components are secondary evidence so
    a nested repo such as ``Portfolio/artifacts/mockup-sandbox`` cannot outrank
    the real ``Portfolio`` project root merely because the parent path contains
    the requested name.
    """
    cleaned = _clean(query).casefold()
    if not cleaned:
        return 0

    name = str(candidate.get("name") or "").strip().casefold()
    path = str(candidate.get("path") or "").strip().casefold()
    if not name and not path:
        return -1

    query_compact = _project_identity_compact(cleaned)
    name_compact = _project_identity_compact(name)
    if not query_compact:
        return -1

    score = -1
    if query_compact == name_compact:
        score = 1400
    elif cleaned == name:
        score = 1380
    elif cleaned and cleaned in name:
        score = 1180 - min(180, abs(len(name) - len(cleaned)) * 4)
    elif name_compact and query_compact in name_compact:
        score = 1120 - min(180, abs(len(name_compact) - len(query_compact)) * 4)
    elif name_compact:
        ratio = SequenceMatcher(None, query_compact, name_compact).ratio()
        # Strong enough for ordinary transpositions/one-character typos such as
        # portfoilo -> Portfolio, but deliberately too strict for generic names.
        if ratio >= 0.80 and min(len(query_compact), len(name_compact)) >= 5:
            score = 900 + int(ratio * 160)

    path_tokens = _project_identity_tokens(path)
    path_parts = [part for part in re.split(r"[\\/]+", path) if part]
    path_compacts = [_project_identity_compact(part) for part in path_parts]
    if score < 0:
        # Secondary path evidence is accepted only when a path component itself
        # identifies the requested project. It is intentionally weaker than a
        # matching basename so nested generated/test repos rank below roots.
        if query_compact in path_compacts:
            score = 760
        else:
            best_ratio = max(
                (SequenceMatcher(None, query_compact, part).ratio() for part in path_compacts if part),
                default=0.0,
            )
            if best_ratio >= 0.86 and len(query_compact) >= 5:
                score = 680 + int(best_ratio * 80)

    if score < 0:
        query_tokens = set(_project_identity_tokens(cleaned))
        candidate_tokens = set(_project_identity_tokens(name))
        if query_tokens and query_tokens.issubset(candidate_tokens):
            score = 820 + min(100, len(query_tokens) * 12)

    if score < 0:
        return -1

    try:
        depth = max(0, int(candidate.get("depth") or 0))
    except (TypeError, ValueError):
        depth = 0
    noise_hits = sum(1 for token in path_tokens if token in _NESTED_PROJECT_NOISE)
    basename_noise = sum(1 for token in _project_identity_tokens(name) if token in _NESTED_PROJECT_NOISE)
    score -= min(180, depth * 12)
    score -= min(300, noise_hits * 55)
    score -= min(260, basename_noise * 100)
    if bool(candidate.get("git")):
        score += 18
    # Weak ancestor-only/path matches are useful as diagnostics, not as an
    # autonomous binding signal. Failing closed here prevents a nested mockup,
    # artifact, or test repository from being silently selected.
    return score if score >= 600 else -1


def rank_matching_project_candidates(
    query: str,
    projects: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return only candidates that safely match the requested project identity."""
    if not _clean(query):
        return sorted(
            [item for item in projects if isinstance(item, dict)],
            key=lambda item: (
                int(item.get("depth") or 0),
                -int(item.get("score") or 0),
                str(item.get("path") or "").casefold(),
            ),
        )
    scored: list[tuple[int, int, int, str, dict[str, object]]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        identity = project_candidate_identity_score(query, item)
        if identity < 0:
            continue
        try:
            discovery_score = int(item.get("score") or 0)
        except (TypeError, ValueError):
            discovery_score = 0
        try:
            depth = int(item.get("depth") or 0)
        except (TypeError, ValueError):
            depth = 0
        scored.append(
            (
                -identity,
                depth,
                -discovery_score,
                str(item.get("path") or "").casefold(),
                item,
            )
        )
    scored.sort(key=lambda row: row[:4])
    return [row[4] for row in scored]


def project_candidates_are_ambiguous(
    query: str,
    projects: list[dict[str, object]],
    *,
    score_margin: int = 90,
) -> bool:
    """Return True only when the two strongest named matches are genuinely close."""
    if not _clean(query) or len(projects) < 2:
        return False
    first = project_candidate_identity_score(query, projects[0])
    second = project_candidate_identity_score(query, projects[1])
    if first < 0 or second < 0:
        return False
    return (first - second) < max(1, int(score_margin))


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



def engineering_plan_is_adequate(objective: str, tasks: list[dict[str, object]]) -> tuple[bool, str]:
    """Validate that an implementation plan can actually execute engineering work.

    This is semantic validation on top of JSON/schema validation. A planner that
    returns a generic worker plus verifier for a code-change objective is not
    adequate even though the JSON is syntactically valid.
    """
    cleaned = _clean(objective)
    if not _IMPLEMENTATION_RE.search(cleaned):
        return True, "not an engineering implementation objective"
    if not isinstance(tasks, list) or len(tasks) < 3:
        return False, "engineering plan has fewer than three executable phases"

    normalized = [item for item in tasks if isinstance(item, dict)]
    roles = {str(item.get("role") or "general").strip().lower() for item in normalized}
    required_roles = {"coder", "tester", "reviewer"}
    missing = sorted(required_roles - roles)
    if missing:
        return False, "engineering plan is missing required roles: " + ", ".join(missing)

    ids = {str(item.get("id") or "").strip() for item in normalized}
    edges: list[tuple[str, str]] = []
    for item in normalized:
        task_id = str(item.get("id") or "").strip()
        deps = item.get("depends_on") or []
        if isinstance(deps, list):
            edges.extend((task_id, str(dep).strip()) for dep in deps if str(dep).strip())
    if not edges:
        return False, "engineering plan has no dependency ordering"
    if any(dep not in ids for _, dep in edges):
        return False, "engineering plan references an unknown dependency"

    coder_ids = {str(item.get("id") or "").strip() for item in normalized if str(item.get("role") or "").lower() == "coder"}
    tester_items = [item for item in normalized if str(item.get("role") or "").lower() == "tester"]
    reviewer_items = [item for item in normalized if str(item.get("role") or "").lower() == "reviewer"]
    if coder_ids and not any(set(map(str, item.get("depends_on") or [])) & coder_ids for item in tester_items + reviewer_items):
        return False, "engineering verification/review is not ordered after implementation"

    return True, "engineering plan contains implementation, verification, review, and dependency ordering"

def needs_remote_state_change(text: str) -> bool:
    """Conservative local preflight for objectives likely to mutate user state."""
    cleaned = _clean(text)
    if not cleaned or _INFORMATIONAL_REQUEST_RE.search(cleaned):
        return False
    if parse_exact_file_objective(cleaned) is not None:
        return True
    return bool(_IMPLEMENTATION_RE.search(cleaned))



def needs_project_workspace(text: str) -> bool:
    """Return True when an objective needs a concrete development workspace.

    This is deliberately lexical and conservative; it is used only for
    preflight/path resolution, never as permission to mutate files.
    """
    cleaned = _clean(text)
    return bool(cleaned and _PROJECT_WORK_RE.search(cleaned))

def fallback_orchestration_graph(objective: str) -> list[dict[str, object]]:
    """Build a useful local DAG when the Planner model is unavailable.

    Implementation-oriented requests retain an inspect -> code -> test -> review
    structure instead of collapsing into one over-broad general worker. This
    planner is deliberately local and conservative; the workers still use the
    normal permission/session boundaries for any external action.
    """
    cleaned = _clean(objective)
    implementation = bool(_IMPLEMENTATION_RE.search(cleaned))
    validation = bool(_VALIDATION_RE.search(cleaned))
    if implementation:
        graph: list[dict[str, object]] = [
            {
                "id": "inspect-current",
                "title": "Inspect current implementation",
                "prompt": (
                    "Inspect the relevant project state and identify one concrete, bounded, safe change that "
                    "advances the objective. Read only what is needed and report exact files/evidence. Objective: "
                    + cleaned
                ),
                "role": "reviewer",
                "priority": 90,
                "depends_on": [],
                "max_retries": 1,
            },
            {
                "id": "implement-change",
                "title": "Implement bounded change",
                "prompt": (
                    "Using the upstream inspection evidence, implement the smallest safe change that satisfies the "
                    "objective. Inspect before editing, prefer exact text replacement for existing files, and report "
                    "every changed file. Objective: " + cleaned
                ),
                "role": "coder",
                "priority": 85,
                "depends_on": ["inspect-current"],
                "max_retries": 1,
            },
            {
                "id": "test-change",
                "title": "Test implemented change",
                "prompt": (
                    "Run the strongest relevant bounded tests for the implemented change. Report pass/fail evidence "
                    "and concrete failures. Objective: " + cleaned
                ),
                "role": "tester",
                "priority": 80,
                "depends_on": ["implement-change"],
                "max_retries": 1,
            },
            {
                "id": "review-change",
                "title": "Review change and regressions",
                "prompt": (
                    "Review the implemented change, git working tree, test evidence, safety, and regression risk. "
                    "Distinguish verified facts from unresolved issues. Objective: " + cleaned
                ),
                "role": "reviewer",
                "priority": 75,
                "depends_on": ["test-change"],
                "max_retries": 1,
            },
        ]
        return graph

    return [
        {
            "id": "execute-objective",
            "title": "Execute objective",
            "prompt": (
                "Complete the objective in a bounded, evidence-based way. Inspect relevant state first, perform only "
                "authorized actions, and report the concrete result. Objective: " + cleaned
            ),
            "role": "general",
            "priority": 80,
            "depends_on": [],
            "max_retries": 1,
        },
        {
            "id": "verify-outcome",
            "title": "Verify outcome",
            "prompt": (
                "Independently verify whether the objective was actually completed. Run safe checks where possible "
                "and report any failure or unresolved risk. Objective: " + cleaned
            ),
            "role": "tester" if validation else "reviewer",
            "priority": 70,
            "depends_on": ["execute-objective"],
            "max_retries": 1,
        },
    ]
