from iras.device_bridge.planner import planner_system_nudge
from iras.device_bridge.task_engine import TaskTracker
from iras.device_bridge.visual_control import SemanticVisualController


def _semantic_payload(target, visible_names):
    return {
        "ok": True,
        "output": {
            "selected_element": {
                "name": target,
                "automation_id": "",
                "role": "Button",
            },
            "verification_observation": {
                "window_name": "Spotify",
                "element_count": len(visible_names),
                "elements": [
                    {"name": name, "role": "Text"}
                    for name in visible_names
                ],
                "accessibility_available": True,
                "accessibility_status": "available",
                "vision_fallback_recommended": False,
            },
        },
    }


def _observe_payload(app="Spotify", names=None):
    names = list(names or [])
    return {
        "ok": True,
        "output": {
            "app": app.lower(),
            "window_name": app,
            "element_count": len(names),
            "elements": [
                {"name": name, "role": "Text"}
                for name in names
            ],
            "accessibility_available": bool(names),
            "accessibility_status": "available" if names else "unavailable",
            "accessibility_reason": (
                "" if names else
                "Windows UI Automation returned no usable visible semantic controls for this rendered window. This does not prove that the visual interface is blank."
            ),
            "vision_fallback_recommended": not bool(names),
        },
    }


def test_spotify_compound_goal_requires_terminal_target_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Open Spotify and open Settings.")

    tracker.record(
        "device_semantic_action",
        {"app": "Spotify", "action": "click", "target": "Profile"},
        _semantic_payload("Profile", ["Account", "Settings", "Log out"]),
    )
    assert tracker.goal_checkpoint_required is True
    assert "whole" in tracker.after_result_nudge(
        _semantic_payload("Profile", ["Account", "Settings"])
    ).lower()

    tracker.record(
        "device_observe_ui",
        {"app": "Spotify"},
        _observe_payload("Spotify", ["Account", "Settings", "Log out"]),
    )
    assert tracker.goal_checkpoint_required is True
    assert "settings" in tracker.finalization_nudge().lower()

    tracker.record(
        "device_semantic_action",
        {"app": "Spotify", "action": "click", "target": "Settings"},
        _semantic_payload("Settings", ["Settings", "Audio quality"]),
    )
    assert tracker.goal_checkpoint_required is True

    tracker.record(
        "device_observe_ui",
        {"app": "Spotify"},
        _observe_payload("Spotify", ["Settings", "Audio quality"]),
    )
    assert tracker.goal_checkpoint_required is False


def test_incomplete_compound_goal_does_not_learn(tmp_path, monkeypatch):
    path = tmp_path / "skills.json"
    monkeypatch.setenv("IRAS_SKILL_STORE", str(path))
    tracker = TaskTracker("Open Spotify and open Settings.")
    tracker.record(
        "device_semantic_action",
        {"app": "Spotify", "action": "click", "target": "Profile"},
        _semantic_payload("Profile", ["Settings"]),
    )
    assert tracker.goal_checkpoint_required is True
    assert tracker.learned_skill_id == ""
    assert tracker.finalization_nudge()
    assert not path.exists()


def test_empty_uia_is_not_called_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Message Darkness on whatsapp saying hello.")
    payload = _observe_payload("WhatsApp", [])
    tracker.record("device_observe_ui", {"app": "WhatsApp"}, payload)
    assert tracker.accessibility_limited is True
    nudge = tracker.after_result_nudge(payload).lower()
    assert "does not mean" in nudge
    assert "blank" in nudge
    fallback = tracker.empty_final_response().lower()
    assert "does not mean" in fallback
    assert "visually blank" in fallback
    assert tracker.learned_skill_id == ""


def test_visual_observation_marks_empty_tree_as_accessibility_unavailable(monkeypatch):
    controller = SemanticVisualController(object())
    monkeypatch.setattr(controller, "_ensure_window", lambda app, ensure_open: ("whatsapp", 123, False))
    monkeypatch.setattr(controller, "_run_uia_observer", lambda hwnd, max_elements: {
        "window_name": "WhatsApp", "element_count": 0, "elements": []
    })
    monkeypatch.setattr(controller, "_capture_window", lambda app, hwnd: {
        "path": r"C:\fake\whatsapp.jpg", "width": 1200, "height": 800,
        "sha256": "abc", "bytes": 123,
    })
    result = controller.observe("WhatsApp", screenshot=True)
    assert result["accessibility_available"] is False
    assert result["accessibility_status"] == "unavailable"
    assert result["vision_fallback_recommended"] is True
    assert "does not prove" in result["accessibility_reason"].lower()
    assert result["screenshot"]["path"].endswith("whatsapp.jpg")


def test_nonempty_uia_marks_accessibility_available(monkeypatch):
    controller = SemanticVisualController(object())
    monkeypatch.setattr(controller, "_ensure_window", lambda app, ensure_open: ("spotify", 456, False))
    monkeypatch.setattr(controller, "_run_uia_observer", lambda hwnd, max_elements: {
        "window_name": "Spotify",
        "element_count": 1,
        "elements": [{"name": "Settings", "automation_id": "", "role": "Button"}],
    })
    result = controller.observe("Spotify", screenshot=False)
    assert result["accessibility_available"] is True
    assert result["accessibility_status"] == "available"
    assert result["vision_fallback_recommended"] is False


def test_planner_prompt_distinguishes_action_from_goal_completion():
    prompt = planner_system_nudge(
        "Open Spotify and open Settings.", ["Spotify"]
    ).lower()
    assert "specific interaction" in prompt
    assert "entire goal" in prompt
    assert "accessibility_available=false" in prompt
    assert "do not describe the app as blank" in prompt


def test_empty_final_never_claims_compound_goal_completed(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Open Spotify and open Settings.")
    tracker.successful_calls = 2
    tracker.goal_checkpoint_required = True
    text = tracker.empty_final_response().lower()
    assert "partial ui progress" in text
    assert "whole goal" in text
    assert "completed verified tool steps" not in text
