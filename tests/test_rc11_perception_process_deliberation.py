from pathlib import Path

from PIL import Image

from iras.process_awareness import ProcessAwareness
from iras.device_bridge.screen_intelligence import temporal_delta
from iras.v5.deliberation import CalmDeliberationEngine
from iras.device_bridge.planner import SAFE_DEVICE_PLANNER_TOOLS
from iras.device_bridge.task_engine import READ_VERIFY_TOOLS
from iras.remote_access import READ_ACTIONS
from iras.coding_agent import CODING_AGENT_READ_TOOLS


def _row(pid, name, memory=10, cpu=0, title="", path="", responding=True):
    return {
        "pid": pid,
        "parent_pid": 1,
        "name": name,
        "working_set_mb": memory,
        "private_mb": memory / 2,
        "cpu_seconds": cpu,
        "threads": 4,
        "handles": 20,
        "session_id": 1,
        "responding": responding,
        "main_window_title": title,
        "start_time": "2026-09-22T00:00:00Z",
        "path": path,
    }


def test_process_snapshot_is_structured_and_never_collects_command_lines():
    awareness = ProcessAwareness()
    result = awareness.snapshot_from_rows(
        [
            _row(10, "chrome.exe", 400, 12, "ChatGPT"),
            _row(20, "Code.exe", 300, 8, "IRAS - Visual Studio Code"),
            _row(30, "svchost.exe", 50, 2),
        ],
        sort_by="memory",
    )
    assert result["process_count"] == 3
    assert result["visible_app_count"] == 2
    assert result["command_lines_collected"] is False
    assert result["processes"][0]["category"] == "browser"
    assert "command_line" not in result["processes"][0]


def test_process_snapshot_tracks_started_and_exited_processes():
    awareness = ProcessAwareness()
    awareness.snapshot_from_rows([_row(10, "chrome.exe"), _row(20, "Code.exe")])
    second = awareness.snapshot_from_rows([_row(20, "Code.exe"), _row(40, "Spotify.exe")])
    assert {item["name"] for item in second["changes"]["started"]} == {"Spotify.exe"}
    assert {item["name"] for item in second["changes"]["exited"]} == {"chrome.exe"}


def test_process_paths_are_hidden_by_default_and_opt_in_only():
    awareness = ProcessAwareness()
    rows = [_row(20, "Code.exe", path=r"C:\\Users\\Dark\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe")]
    hidden = awareness.snapshot_from_rows(rows, include_path=False)
    shown = awareness.snapshot_from_rows(rows, include_path=True, track_changes=False)
    assert "path" not in hidden["processes"][0]
    assert shown["processes"][0]["path"].endswith("Code.exe")


def test_temporal_screen_memory_detects_visual_and_semantic_change(tmp_path):
    old_image = tmp_path / "old.png"
    new_image = tmp_path / "new.png"
    Image.new("RGB", (320, 180), "black").save(old_image)
    Image.new("RGB", (320, 180), "white").save(new_image)
    previous = {
        "observation_id": "old",
        "screenshot": {"path": str(old_image)},
        "foreground": {"hwnd": 1, "pid": 10, "title": "Old"},
        "elements": [{"element_id": "uia:a", "label": "Open", "role": "button", "source": "uia"}],
    }
    current = {
        "observation_id": "new",
        "screenshot": {"path": str(new_image)},
        "foreground": {"hwnd": 2, "pid": 20, "title": "New"},
        "elements": [{"element_id": "uia:b", "label": "Save", "role": "button", "source": "uia"}],
    }
    delta = temporal_delta(previous, current)
    assert delta["changed"] is True
    assert delta["change_level"] == "major"
    assert delta["foreground_changed"] is True
    assert delta["appeared"][0]["label"] == "Save"
    assert delta["disappeared"][0]["label"] == "Open"


def test_deliberation_classifies_ui_failure_and_prefers_fresh_context():
    engine = CalmDeliberationEngine()
    plan = engine.plan(
        "The click failed because the observation is stale and the foreground window changed.",
        evidence={"verification": "FAIL"},
    )
    assert plan["failure_class"] == "ui_grounding"
    assert plan["recommended_strategy"] == "deep_desktop_context"
    assert plan["mode"] == "deliberate_calm"


def test_deliberation_does_not_recommend_the_same_failed_route():
    engine = CalmDeliberationEngine()
    plan = engine.plan(
        "The click failed because the screen target is stale.",
        attempts=[{"strategy": "deep_desktop_context"}],
    )
    assert plan["recommended_strategy"] != "deep_desktop_context"
    repeated = next(item for item in plan["candidates"] if item["strategy"] == "deep_desktop_context")
    assert repeated["already_attempted"] is True
    assert repeated["recommended"] is False


def test_desktop_context_is_read_only_and_available_to_planners():
    assert "device_desktop_context" in SAFE_DEVICE_PLANNER_TOOLS
    assert "device_desktop_context" in READ_VERIFY_TOOLS
    assert "desktop_context" in READ_ACTIONS
    assert "device_desktop_context" in CODING_AGENT_READ_TOOLS
    assert "device_list_processes" in SAFE_DEVICE_PLANNER_TOOLS


def test_rc11_calm_repair_contract_is_in_system_prompt_and_v5_tools():
    persona = Path("src/iras/persona.py").read_text(encoding="utf-8")
    tools = Path("src/iras/tools/v5.py").read_text(encoding="utf-8")
    assert "CALM DELIBERATION AND REPAIR" in persona
    assert "Never repeat the same failed click" in persona
    assert "v5_deliberation_status" in tools
    assert "v5_deliberate_repair" in tools
