from pathlib import Path

import pytest

from iras.core.agent import IRASAgent
from iras.device_bridge.executor import DeviceExecutor
from iras.execution_router import fallback_orchestration_graph, needs_remote_state_change
from iras.models import PermissionLevel
from iras.remote_access import action_permission
from iras.tools.web import _parse_duck_results, html_to_text


def test_html_research_extraction_removes_script_and_keeps_content():
    raw = """
    <html><head><style>.x{display:none}</style><script>alert(1)</script></head>
    <body><h1>Python 3.14</h1><p>Free-threaded mode changed.</p></body></html>
    """
    text = html_to_text(raw)
    assert "Python 3.14" in text
    assert "Free-threaded mode changed." in text
    assert "alert(1)" not in text
    assert "display:none" not in text


def test_duck_search_parser_returns_public_target_url():
    raw = (
        '<a class="result__a" href="//duckduckgo.com/l/?uddg='
        'https%3A%2F%2Fdocs.python.org%2F3.14%2Fwhatsnew%2F3.14.html">'
        "What's New In Python 3.14</a>"
    )
    results = _parse_duck_results(raw, 5)
    assert results == [{
        "title": "What's New In Python 3.14",
        "url": "https://docs.python.org/3.14/whatsnew/3.14.html",
    }]


def test_direct_research_turn_exposes_text_research_tools():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    names = set(agent._smart_tool_names("research the latest Python 3.14 changes"))
    assert {"web_search", "http_get"}.issubset(names)


def test_specialized_agent_tool_allowlist_overrides_generic_routing():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    agent.tool_allowlist = {"device_read_text", "device_replace_text"}
    assert agent._smart_tool_names("open Spotify and play music") == [
        "device_read_text",
        "device_replace_text",
    ]


def test_local_fallback_planner_preserves_engineering_phases():
    graph = fallback_orchestration_graph(
        "Inspect the IRAS project, find one safe improvement, implement it, run tests, review regressions, and report."
    )
    assert [task["role"] for task in graph] == [
        "reviewer",
        "coder",
        "tester",
        "reviewer",
    ]
    assert graph[1]["depends_on"] == ["inspect-current"]
    assert graph[2]["depends_on"] == ["implement-change"]
    assert graph[3]["depends_on"] == ["test-change"]


def test_replace_text_is_bounded_and_exact(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("before = 1\nvalue = 2\n", encoding="utf-8")
    executor = DeviceExecutor([str(tmp_path)])
    out = executor.replace_text(str(target), "value = 2", "value = 3")
    assert out["replacements"] == 1
    assert target.read_text(encoding="utf-8") == "before = 1\nvalue = 3\n"
    with pytest.raises(ValueError):
        executor.replace_text(str(target), "missing snippet", "x")


def test_replace_text_keeps_system_action_permission():
    assert action_permission("replace_text", {}) == PermissionLevel.SYSTEM_ACTION


def test_state_changing_autonomous_goals_preflight_remote_but_questions_do_not():
    assert needs_remote_state_change(
        "Inspect IRAS, implement one safe improvement, run tests, and review it"
    ) is True
    assert needs_remote_state_change(
        "Explain how to improve IRAS safely"
    ) is False
