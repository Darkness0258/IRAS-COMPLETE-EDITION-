from __future__ import annotations

import json
import subprocess
from pathlib import Path

from iras.device_bridge.executor import DeviceExecutor
from iras.execution_router import (
    project_candidate_identity_score,
    rank_matching_project_candidates,
)
from iras.providers.device_ollama import DeviceOllamaProvider


def _repo(path: Path, name: str) -> Path:
    repo = path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "pyproject.toml").write_text(
        "[project]\nname='sample'\nversion='0'\n",
        encoding="utf-8",
    )
    return repo


def test_named_project_lookup_never_returns_unrelated_repository(tmp_path):
    root = tmp_path / "Projects"
    root.mkdir()
    _repo(root, "Agent-Reach")

    executor = DeviceExecutor([str(root)])
    result = executor.find_projects("IRAS", max_depth=2)

    assert result["projects"] == []


def test_project_discovery_fairly_scans_later_allowed_roots(tmp_path):
    first = tmp_path / "Users"
    second = tmp_path / "Projects"
    first.mkdir()
    second.mkdir()
    _repo(first, "Agent-Reach")
    target = _repo(second, "IRAS-complete")

    # Reproduce RC6's real failure mode: a huge first root used to exhaust one
    # global scan budget before the later D:\\Projects-style root was visited.
    noise = first / "noise"
    noise.mkdir()
    for index in range(2600):
        (noise / f"dir-{index:04d}").mkdir()

    executor = DeviceExecutor([str(first), str(second)])
    result = executor.find_projects("IRAS", max_depth=2)

    assert result["projects"]
    assert Path(result["projects"][0]["path"]) == target.resolve()
    assert str(first.resolve()) in result["scanned_by_root"]
    assert str(second.resolve()) in result["scanned_by_root"]


def test_project_identity_ranking_filters_wrong_repo():
    projects = [
        {"name": "Agent-Reach", "path": r"C:\\Users\\mhamz\\Agent-Reach", "score": 52},
        {"name": "IRAS-complete", "path": r"D:\\Projects\\IRAS-complete", "score": 52},
    ]
    ranked = rank_matching_project_candidates("IRAS", projects)
    assert [item["name"] for item in ranked] == ["IRAS-complete"]
    assert project_candidate_identity_score("IRAS", projects[0]) < 0
    assert project_candidate_identity_score("IRAS", projects[1]) > 0


def _tool_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"type": "object"}},
    }


def test_device_ollama_normalizes_plain_json_tool_request():
    provider = DeviceOllamaProvider(
        lambda action, arguments, timeout: {
            "model": "qwen2.5-coder:7b",
            "content": json.dumps(
                {
                    "name": "device_search_text",
                    "arguments": {"root": ".", "query": "IRAS"},
                }
            ),
            "tool_calls": [],
        }
    )
    reply = provider.complete(
        [{"role": "user", "content": "inspect"}],
        [_tool_schema("device_search_text")],
    )

    assert reply.text == ""
    assert len(reply.tool_calls) == 1
    assert reply.tool_calls[0].name == "device_search_text"
    assert reply.tool_calls[0].arguments == {"root": ".", "query": "IRAS"}
    assert reply.assistant_message["role"] == "assistant"
    assert reply.assistant_message["tool_calls"][0]["function"]["name"] == "device_search_text"


def test_device_ollama_normalizes_fenced_json_tool_request():
    provider = DeviceOllamaProvider(
        lambda action, arguments, timeout: {
            "model": "qwen2.5-coder:7b",
            "content": '```json\n{"tool":"device_git_log","args":{"repo":".","limit":5}}\n```',
            "tool_calls": [],
        }
    )
    reply = provider.complete(
        [{"role": "user", "content": "inspect"}],
        [_tool_schema("device_git_log")],
    )
    assert reply.tool_calls[0].name == "device_git_log"
    assert reply.tool_calls[0].arguments == {"repo": ".", "limit": 5}


def test_device_ollama_does_not_execute_unknown_json_tool_name():
    content = '{"name":"device_delete_everything","arguments":{"root":"C:\\\\"}}'
    provider = DeviceOllamaProvider(
        lambda action, arguments, timeout: {
            "model": "qwen2.5-coder:7b",
            "content": content,
            "tool_calls": [],
        }
    )
    reply = provider.complete(
        [{"role": "user", "content": "inspect"}],
        [_tool_schema("device_search_text")],
    )
    assert reply.text == content
    assert reply.tool_calls == []
    assert reply.assistant_message == {"role": "assistant", "content": content}


def test_device_ollama_context_trimming_preserves_newest_messages():
    messages = [
        {"role": "user", "content": f"old-{index}-" + ("x" * 18000)}
        for index in range(5)
    ]
    messages.append({"role": "user", "content": "LATEST-CURRENT-TASK"})
    bounded = DeviceOllamaProvider._bounded_messages(messages)
    contents = [str(item.get("content") or "") for item in bounded]
    assert "LATEST-CURRENT-TASK" in contents
