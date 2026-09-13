from __future__ import annotations

import json

from iras.device_bridge.skills import (
    LearnedStep,
    PersistentSkillStore,
    resolve_semantic_target,
)
from iras.device_bridge.task_engine import TaskTracker


def verified_step(app="Discord", target="User Settings"):
    return LearnedStep(
        app=app,
        action="click",
        locator={
            "name": target,
            "automation_id": "settings-button",
            "role": "Button",
            "occurrence": 1,
            # Deliberately hostile geometry: it must be stripped on disk.
            "bounds": {"left": 1, "top": 2, "right": 3, "bottom": 4},
        },
        expected_state={
            "verified": True,
            "window_name": app,
            "bounds": [1, 2, 3, 4],
            "rect": {"left": 1, "top": 2, "width": 3, "height": 4},
            "x": 123,
            "y": 456,
        },
    )


def test_store_never_persists_coordinates(tmp_path):
    path = tmp_path / "skills.json"
    store = PersistentSkillStore(path)
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None
    raw = path.read_text(encoding="utf-8").casefold()
    assert '"bounds"' not in raw
    assert '"left"' not in raw
    assert '"top"' not in raw
    assert '"right"' not in raw
    assert '"bottom"' not in raw
    assert '"rect"' not in raw
    assert '"x"' not in raw
    assert '"y"' not in raw


def test_parameterized_skill_binds_contact_and_text(tmp_path):
    store = PersistentSkillStore(tmp_path / "skills.json")
    step = LearnedStep(
        app="Discord",
        action="type_into",
        locator={
            "name": "Message {contact}",
            "automation_id": "message-box",
            "role": "Edit",
            "occurrence": 1,
        },
        text="{text}",
        expected_state={"verified": True},
    )
    skill = store.learn_verified(
        "message {contact} {text}",
        [step],
        parameters=["contact", "text"],
    )
    assert skill is not None
    match = store.find("message Hamza hello there", app="Discord")
    assert match is not None
    assert match["parameters"]["contact"] == "Hamza"
    assert match["parameters"]["text"] == "hello there"
    assert match["steps"][0]["text"] == "hello there"
    assert match["steps"][0]["locator"]["name"] == "Message Hamza"


def test_unsafe_shell_and_admin_apps_are_rejected(tmp_path):
    store = PersistentSkillStore(tmp_path / "skills.json")
    for app in ("PowerShell", "cmd", "Windows Terminal", "Registry Editor", "wsl", "bash", "python"):
        step = LearnedStep(
            app=app,
            action="click",
            locator={"name": "Run", "automation_id": "run", "role": "Button"},
            expected_state={"verified": True},
        )
        assert store.learn_verified(f"unsafe {app}", [step]) is None


def test_repeated_failure_demotes_broken_skill(tmp_path):
    store = PersistentSkillStore(tmp_path / "skills.json")
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None
    one = store.record_failure(skill.skill_id)
    assert one is not None
    assert one.status == "active"
    two = store.record_failure(skill.skill_id)
    assert two is not None
    assert two.status == "demoted"
    assert store.find("Open Discord settings", app="Discord") is None
    assert store.get(skill.skill_id).status == "demoted"


def test_semantic_resolution_prefers_automation_id_and_adapts_name():
    observation = {
        "window_name": "Discord",
        "elements": [
            {
                "name": "Settings",
                "automation_id": "new-settings-id",
                "role": "Button",
                "bounds": [10, 10, 20, 20],
            },
            {
                "name": "User Settings",
                "automation_id": "stable-settings-id",
                "role": "Button",
                "x": 99,
                "y": 99,
            },
        ],
    }
    resolved = resolve_semantic_target(
        observation,
        {
            "name": "Old Settings Label",
            "automation_id": "stable-settings-id",
            "role": "Button",
            "occurrence": 1,
        },
    )
    assert resolved is not None
    assert resolved["target"] == "stable-settings-id"
    assert resolved["name"] == "User Settings"
    assert "x" not in resolved and "y" not in resolved


def test_tracker_learns_only_after_verified_semantic_success(tmp_path, monkeypatch):
    path = tmp_path / "skills.json"
    monkeypatch.setenv("IRAS_SKILL_STORE", str(path))

    unverified = TaskTracker("Open Discord settings")
    unverified.record(
        "device_semantic_action",
        {"app": "Discord", "action": "click", "target": "User Settings"},
        {"ok": True, "output": {}},
    )
    assert unverified.needs_verification is True
    assert unverified.learnable_steps == []
    assert "not verified" in unverified.finalization_nudge().lower()
    assert not path.exists()

    verified = TaskTracker("Open Discord settings")
    verified.record(
        "device_semantic_action",
        {
            "app": "Discord",
            "action": "click",
            "target": "User Settings",
            "role": "Button",
        },
        {
            "ok": True,
            "output": {
                "verification_observation": {
                    "window_name": "Discord",
                    "element_count": 20,
                    "elements": [
                        {"name": "Voice & Video", "role": "ListItem", "bounds": [1, 2, 3, 4]}
                    ],
                }
            },
        },
    )
    assert verified.finalization_nudge() == ""
    assert verified.learned_skill_id
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["skills"]) == 1
    assert payload["skills"][0]["app"] == "Discord"
    assert '"bounds"' not in path.read_text(encoding="utf-8").casefold()


def test_coordinate_interaction_is_never_learned(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Click the thing")
    tracker.record(
        "device_interact_app",
        {
            "app": "Discord",
            "actions": [{"action": "click", "x": 500, "y": 400}],
        },
        {"ok": True, "output": {}},
    )
    assert tracker.learnable_steps == []
    assert tracker.needs_verification is True


def test_validation_is_read_only_and_adapts_changed_locator(tmp_path):
    from iras.device_bridge.skill_tools import make_tools

    store = PersistentSkillStore(tmp_path / "skills.json")
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None

    class DeviceStore:
        def __init__(self):
            self.calls = []

        def request_and_wait(self, action, arguments, device_id=None, timeout=0):
            self.calls.append((action, arguments))
            return {
                "window_name": "Discord",
                "elements": [
                    {
                        "name": "User Settings",
                        "automation_id": "settings-button-v2",
                        "role": "Button",
                        "bounds": [10, 10, 100, 40],
                    }
                ],
            }

    device = DeviceStore()
    tools = {tool.name: tool for tool in make_tools(device, store)}
    result = tools["device_skill_validate"].handler(
        skill_id=skill.skill_id,
        step_index=0,
        app="Discord",
    )
    assert result["valid"] is True
    assert result["target"] == "settings-button-v2"
    assert device.calls == [
        (
            "observe_ui",
            {
                "app": "Discord",
                "ensure_open": False,
                "max_elements": 220,
                "screenshot": False,
            },
        )
    ]
    refreshed = store.get(skill.skill_id)
    assert refreshed.steps[0].locator["automation_id"] == "settings-button-v2"


def test_missing_learned_target_triggers_live_observation_and_demotion(tmp_path):
    from iras.device_bridge.skill_tools import make_tools

    store = PersistentSkillStore(tmp_path / "skills.json")
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None

    class EmptyDeviceStore:
        def request_and_wait(self, **kwargs):
            return {"window_name": "Discord", "elements": []}

    validate = {
        tool.name: tool for tool in make_tools(EmptyDeviceStore(), store)
    }["device_skill_validate"].handler

    first = validate(skill.skill_id, 0, app="Discord")
    assert first["valid"] is False
    assert first["fallback_required"] is True
    assert "observation" in first
    second = validate(skill.skill_id, 0, app="Discord")
    assert second["status"] == "demoted"
    assert store.get(skill.skill_id).status == "demoted"


def test_mixed_coordinate_workflow_is_not_persisted(tmp_path, monkeypatch):
    path = tmp_path / "skills.json"
    monkeypatch.setenv("IRAS_SKILL_STORE", str(path))
    tracker = TaskTracker("Open Discord settings")
    tracker.record(
        "device_interact_app",
        {"app": "Discord", "actions": [{"action": "click", "x": 1, "y": 2}]},
        {"ok": True, "output": {}},
    )
    tracker.record(
        "device_observe_ui",
        {"app": "Discord"},
        {"ok": True, "output": {"elements": []}},
    )
    tracker.record(
        "device_semantic_action",
        {"app": "Discord", "action": "click", "target": "User Settings"},
        {
            "ok": True,
            "output": {
                "verification_observation": {"window_name": "Discord", "elements": []}
            },
        },
    )
    assert tracker.finalization_nudge() == ""
    assert tracker.learning_blocked is True
    assert tracker.learned_skill_id == ""
    assert not path.exists()


def test_parameterized_validation_renders_without_destroying_template(tmp_path):
    from iras.device_bridge.skill_tools import make_tools

    store = PersistentSkillStore(tmp_path / "skills.json")
    step = LearnedStep(
        app="Discord",
        action="type_into",
        locator={
            "name": "Message {contact}",
            "automation_id": "message-box-old",
            "role": "Edit",
            "occurrence": 1,
        },
        text="{text}",
        expected_state={"verified": True},
    )
    skill = store.learn_verified(
        "message {contact} {text}",
        [step],
        parameters=["contact", "text"],
    )
    assert skill is not None

    class DeviceStore:
        def request_and_wait(self, **kwargs):
            return {
                "window_name": "Discord",
                "elements": [
                    {
                        "name": "Message Hamza",
                        "automation_id": "message-box-v2",
                        "role": "Edit",
                    }
                ],
            }

    validate = {
        tool.name: tool for tool in make_tools(DeviceStore(), store)
    }["device_skill_validate"].handler
    result = validate(
        skill.skill_id,
        0,
        app="Discord",
        parameters={"contact": "Hamza", "text": "hello there"},
    )
    assert result["valid"] is True
    assert result["text"] == "hello there"
    refreshed = store.get(skill.skill_id)
    assert refreshed.steps[0].locator["name"] == "Message {contact}"
    assert refreshed.steps[0].locator["automation_id"] == "message-box-v2"
    assert refreshed.steps[0].text == "{text}"


def test_active_skill_action_failure_lowers_confidence_and_blocks_learning(tmp_path):
    store = PersistentSkillStore(tmp_path / "skills.json")
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None
    before = skill.confidence

    tracker = TaskTracker(
        "Open Discord settings",
        skill_store=store,
    )
    tracker.active_skill_id = skill.skill_id
    tracker.record(
        "device_semantic_action",
        {"app": "Discord", "action": "click", "target": "User Settings"},
        {"ok": False, "output": None, "error": "element disappeared"},
    )
    assert tracker.learning_recovery_pending is True
    assert store.get(skill.skill_id).confidence < before
    assert tracker.learned_skill_id == ""


def test_verified_recovery_clears_stale_pending_state(tmp_path):
    store = PersistentSkillStore(tmp_path / "skills.json")
    skill = store.learn_verified("Open Discord settings", [verified_step()])
    assert skill is not None
    tracker = TaskTracker("Open Discord settings", skill_store=store)
    tracker.active_skill_id = skill.skill_id
    tracker.record(
        "device_skill_validate",
        {"skill_id": skill.skill_id, "step_index": 0, "app": "Discord"},
        {"ok": True, "output": {"valid": False, "fallback_required": True}},
    )
    assert tracker.learning_recovery_pending is True
    tracker.record(
        "device_semantic_action",
        {"app": "Discord", "action": "click", "target": "Settings", "role": "Button"},
        {
            "ok": True,
            "output": {
                "selected_element": {
                    "name": "Settings",
                    "automation_id": "settings-v3",
                    "role": "Button",
                    "rect": {"left": 1, "top": 2, "width": 3, "height": 4},
                },
                "verification_observation": {
                    "window_name": "Discord",
                    "elements": [],
                },
            },
        },
    )
    assert tracker.learning_recovery_pending is False
    assert tracker.finalization_nudge() == ""
    assert tracker.learned_skill_id == skill.skill_id
    refreshed = store.get(skill.skill_id)
    assert refreshed.steps[0].locator["automation_id"] == "settings-v3"


def test_role_only_match_is_rejected_for_stale_locator():
    observation = {
        "elements": [
            {"name": "Delete Account", "automation_id": "danger", "role": "Button"},
            {"name": "Log Out", "automation_id": "logout", "role": "Button"},
        ]
    }
    resolved = resolve_semantic_target(
        observation,
        {
            "name": "User Settings",
            "automation_id": "settings-old",
            "role": "Button",
            "occurrence": 1,
        },
    )
    assert resolved is None
