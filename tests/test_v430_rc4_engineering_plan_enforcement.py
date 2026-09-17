from __future__ import annotations

from iras.execution_router import (
    engineering_plan_is_adequate,
    fallback_orchestration_graph,
)


OBJECTIVE = (
    "Inspect the IRAS project for one reliability issue, make one bounded safe "
    "improvement, run relevant tests, review regressions, and give a final report."
)


def test_generic_valid_json_plan_is_not_adequate_for_engineering():
    weak = [
        {
            "id": "execute-objective",
            "title": "Execute objective",
            "prompt": "Do everything",
            "role": "general",
            "depends_on": [],
        },
        {
            "id": "verify-outcome",
            "title": "Verify outcome",
            "prompt": "Verify it",
            "role": "tester",
            "depends_on": ["execute-objective"],
        },
    ]
    adequate, reason = engineering_plan_is_adequate(OBJECTIVE, weak)
    assert adequate is False
    assert "fewer than three" in reason or "missing required roles" in reason


def test_specialized_fallback_is_adequate_for_engineering():
    graph = fallback_orchestration_graph(OBJECTIVE)
    adequate, reason = engineering_plan_is_adequate(OBJECTIVE, graph)
    assert adequate is True, reason
    roles = {task["role"] for task in graph}
    assert {"coder", "tester", "reviewer"}.issubset(roles)


def test_engineering_plan_requires_verification_after_coder():
    unordered = [
        {"id": "code", "title": "Code", "prompt": "Edit", "role": "coder", "depends_on": []},
        {"id": "test", "title": "Test", "prompt": "Test", "role": "tester", "depends_on": []},
        {"id": "review", "title": "Review", "prompt": "Review", "role": "reviewer", "depends_on": ["test"]},
    ]
    adequate, reason = engineering_plan_is_adequate(OBJECTIVE, unordered)
    assert adequate is False
    assert "after implementation" in reason
