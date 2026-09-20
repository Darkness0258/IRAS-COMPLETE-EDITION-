from __future__ import annotations

from typing import Any


RESEARCH_AGENT_TOOLS = {
    "web_search",
    "http_get",
    "api_request",
}

RESEARCH_AGENT_COMMANDS = {"status", "pause", "resume", "cancel"}


def parse_research_command(text: str) -> tuple[str, str] | None:
    raw = str(text or "").strip()
    lower = raw.casefold()
    if lower == "/research":
        return ("status", "")
    if not lower.startswith("/research "):
        return None
    remainder = raw[len("/research "):].strip()
    if not remainder:
        return ("status", "")
    first, _, rest = remainder.partition(" ")
    command = first.casefold()
    if command in RESEARCH_AGENT_COMMANDS:
        return (command, rest.strip())
    return ("run", remainder)


def build_research_agent_graph(question: str) -> list[dict[str, Any]]:
    goal = " ".join(str(question or "").strip().split())
    if not goal:
        raise ValueError("Research question is required.")
    return [
        {
            "id": "research-scope",
            "title": "Define research scope",
            "prompt": (
                "Turn the question into a bounded research plan. Identify the key sub-questions, freshness requirements, "
                "primary/authoritative source types, and search terms. Do not answer from memory when current web evidence is needed. "
                "Question: " + goal
            ),
            "role": "researcher",
            "priority": 95,
            "depends_on": [],
            "max_retries": 1,
        },
        {
            "id": "research-discover",
            "title": "Discover authoritative sources",
            "prompt": (
                "Use web_search to discover multiple relevant sources for the research plan. Prefer primary sources, official documentation, "
                "recognized institutions, and strong independent reporting where appropriate. Record source title, URL, date/freshness when visible, "
                "and why each source matters. Avoid relying on search snippets as final evidence. Question: " + goal
            ),
            "role": "researcher",
            "priority": 90,
            "depends_on": ["research-scope"],
            "max_retries": 2,
        },
        {
            "id": "research-evidence",
            "title": "Read and extract evidence",
            "prompt": (
                "Open the strongest discovered sources with http_get. Extract concrete claims and evidence with the exact source URL for every major finding. "
                "Separate facts from interpretation, note publication/update dates where available, and explicitly record uncertainty or missing evidence. "
                "Do not invent citations or claim to have read a source you did not fetch. Question: " + goal
            ),
            "role": "researcher",
            "priority": 88,
            "depends_on": ["research-discover"],
            "max_retries": 2,
        },
        {
            "id": "research-crosscheck",
            "title": "Cross-check claims and conflicts",
            "prompt": (
                "Cross-check the evidence against additional independent/primary sources where useful. Identify contradictions, stale information, "
                "unsupported claims, and source-quality limitations. Produce a compact evidence table in your result with claim, support, source URL, "
                "and confidence. Question: " + goal
            ),
            "role": "researcher",
            "priority": 84,
            "depends_on": ["research-evidence"],
            "max_retries": 1,
            "continue_on_failure": True,
        },
        {
            "id": "research-review",
            "title": "Review research quality",
            "prompt": (
                "Review the collected research for accuracy, source quality, recency, missing counter-evidence, and unsupported conclusions. "
                "List any material gaps that must be reflected in the final answer. Do not introduce new factual claims without a source. Question: " + goal
            ),
            "role": "reviewer",
            "priority": 80,
            "depends_on": ["research-crosscheck"],
            "max_retries": 1,
            "continue_on_failure": True,
        },
    ]


def research_agent_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "mode": "dedicated_web_research_agent",
        "workflow": ["scope", "discover", "read", "crosscheck", "review", "coordinate"],
        "tools": sorted(RESEARCH_AGENT_TOOLS),
        "read_only": True,
        "commands": [
            "/research <question>",
            "/research status [run-id]",
            "/research pause [run-id]",
            "/research resume [run-id]",
            "/research cancel [run-id]",
        ],
    }
