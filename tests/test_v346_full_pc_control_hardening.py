from __future__ import annotations

import os
import time

import pytest

from iras.device_bridge.computer_use import UniversalComputerController
from iras.device_bridge.universal_control import UniversalWindowsController


class _FakeUI:
    def __init__(self):
        self.typed = []
        self.hotkeys = []
        self.pressed = []
        self.scrolled = []

    def type_text(self, text):
        self.typed.append(text)

    def hotkey(self, keys):
        self.hotkeys.append(list(keys))

    def press(self, key):
        self.pressed.append(key)

    def _key_code(self, key):
        if not key:
            raise ValueError("missing key")
        return 1

    def scroll(self, amount):
        self.scrolled.append(amount)


class _FakeUser32:
    def __init__(self, hwnd=101):
        self.hwnd = hwnd
        self.foreground = hwnd
        self.iconic = False
        self.zoomed = False
        self.exists = True

    def GetForegroundWindow(self):
        return self.foreground

    def ShowWindowAsync(self, hwnd, command):
        assert hwnd == self.hwnd
        if command == 6:  # SW_MINIMIZE
            self.iconic = True
            self.zoomed = False
        elif command == 3:  # SW_MAXIMIZE
            self.iconic = False
            self.zoomed = True
        elif command == 9:  # SW_RESTORE
            self.iconic = False
            self.zoomed = False
        return 1

    def IsIconic(self, hwnd):
        return int(self.exists and self.iconic)

    def IsZoomed(self, hwnd):
        return int(self.exists and self.zoomed)

    def IsWindow(self, hwnd):
        return int(self.exists)

    def PostMessageW(self, hwnd, message, wparam, lparam):
        assert hwnd == self.hwnd
        assert message == 0x0010  # WM_CLOSE
        self.exists = False
        return 1


class _WindowController(UniversalWindowsController):
    def __init__(self, user32):
        self._fake_user32 = user32

    @classmethod
    def canonical_app(cls, app: str) -> str:
        return str(app).strip().lower()

    def _find_window(self, canonical):
        return self._fake_user32.hwnd if self._fake_user32.exists else None

    def _user32(self):
        return self._fake_user32

    def _force_foreground(self, hwnd):
        self._fake_user32.foreground = hwnd
        return True


def _observation(element=None):
    elements = [] if element is None else [element]
    return {
        "observation_id": "obs-1",
        "captured_at": time.time(),
        "foreground": {"hwnd": 77, "title": "Test"},
        "screenshot": {"sha256": "screen-a"},
        "visual_sha256": "visual-a",
        "elements": elements,
    }


def test_uia_focusable_custom_control_is_actionable_but_numeric_pane_is_not():
    elements = UniversalComputerController._uia_elements(
        {
            "elements": [
                {
                    "name": "15",
                    "automation_id": "15",
                    "role": "Pane",
                    "enabled": True,
                    "focusable": False,
                    "rect": {"left": 0, "top": 0, "width": 50, "height": 50},
                },
                {
                    "name": "Search songs",
                    "automation_id": "SearchBox",
                    "role": "Custom",
                    "enabled": True,
                    "focusable": True,
                    "rect": {"left": 60, "top": 0, "width": 120, "height": 30},
                },
            ]
        }
    )

    assert elements[0]["interactive"] is False
    assert elements[1]["interactive"] is True
    assert UniversalComputerController._uia_has_actionable_elements(elements) is True
    assert UniversalComputerController._uia_has_actionable_elements([elements[0]]) is False


def test_mouse_action_rejects_changed_foreground(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    element = {
        "element_id": "vision:1",
        "label": "File",
        "name": "File",
        "automation_id": "",
        "role": "icon",
        "enabled": True,
        "interactive": True,
        "rect": {"left": 10, "top": 20, "width": 40, "height": 20},
    }
    observation = _observation(element)
    controller._observations["obs-1"] = observation

    monkeypatch.setattr(controller, "_foreground_still_matches", lambda obs: False)

    with pytest.raises(RuntimeError, match="foreground window changed"):
        controller.action(
            observation_id="obs-1",
            action="click",
            element_id="vision:1",
            verify=False,
        )


def test_type_into_rechecks_foreground_after_focus_click(monkeypatch):
    ui = _FakeUI()
    controller = UniversalComputerController(ui, object())
    element = {
        "element_id": "uia:2",
        "label": "Search",
        "name": "Search",
        "automation_id": "SearchBox",
        "role": "Edit",
        "enabled": True,
        "interactive": True,
        "rect": {"left": 10, "top": 20, "width": 100, "height": 25},
    }
    controller._observations["obs-1"] = _observation(element)

    states = iter([True, False])
    monkeypatch.setattr(
        controller,
        "_foreground_still_matches",
        lambda obs: next(states),
    )
    monkeypatch.setattr(controller, "_mouse_click", lambda *args, **kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="foreground window changed"):
        controller.action(
            observation_id="obs-1",
            action="type_into",
            element_id="uia:2",
            text="hello",
            verify=False,
        )

    assert ui.typed == []


def test_semantic_verify_auto_escalates_to_vision(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    observations = [
        {
            "observation_id": "uia-only",
            "foreground": {"title": "Notepad"},
            "screenshot": {"sha256": "a"},
            "vision_available": False,
            "elements": [],
        },
        {
            "observation_id": "vision",
            "foreground": {"title": "Notepad"},
            "screenshot": {"sha256": "b"},
            "vision_available": True,
            "elements": [
                {
                    "label": "Save As",
                    "name": "Save As",
                    "automation_id": "",
                    "role": "text",
                    "value": "",
                }
            ],
        },
    ]
    calls = []

    def fake_observe(*, vision, scope, max_elements):
        calls.append(vision)
        return observations[len(calls) - 1]

    monkeypatch.setattr(controller, "observe", fake_observe)
    monkeypatch.setattr(controller, "_omniparser_endpoint", lambda: "http://local/parse/")

    result = controller.verify(
        condition="text_contains",
        target="Save As",
        vision="auto",
    )

    assert calls == ["auto", "always"]
    assert result["status"] == "PASS"
    assert result["vision_escalated"] is True


def test_element_absence_is_confirmed_visually_before_pass(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    observations = [
        {
            "observation_id": "uia-only",
            "foreground": {"title": "App"},
            "screenshot": {"sha256": "a"},
            "vision_available": False,
            "elements": [],
        },
        {
            "observation_id": "vision",
            "foreground": {"title": "App"},
            "screenshot": {"sha256": "b"},
            "vision_available": True,
            "elements": [
                {
                    "label": "Delete",
                    "name": "Delete",
                    "automation_id": "",
                    "role": "text",
                    "value": "",
                }
            ],
        },
    ]
    calls = []

    def fake_observe(*, vision, scope, max_elements):
        calls.append(vision)
        return observations[len(calls) - 1]

    monkeypatch.setattr(controller, "observe", fake_observe)
    monkeypatch.setattr(controller, "_omniparser_endpoint", lambda: "http://local/parse/")

    result = controller.verify(
        condition="element_absent",
        target="Delete",
        vision="auto",
    )

    assert calls == ["auto", "always"]
    assert result["status"] == "FAIL"
    assert result["vision_escalated"] is True


def test_visual_change_predicates_use_foreground_visual_hash():
    prior = {
        "foreground": {"hwnd": 1},
        "screenshot": {"sha256": "same-desktop"},
        "visual_sha256": "before",
        "elements": [],
    }
    after = {
        "foreground": {"hwnd": 1},
        "screenshot": {"sha256": "same-desktop"},
        "visual_sha256": "after",
        "elements": [],
    }

    status, evidence = UniversalComputerController._evaluate_condition(
        after,
        condition="visual_changed",
        prior=prior,
    )
    assert status == "PASS"
    assert evidence["visual_changed"] is True

    status, evidence = UniversalComputerController._evaluate_condition(
        after,
        condition="visual_stable",
        prior=prior,
    )
    assert status == "FAIL"
    assert evidence["visual_stable"] is False


def test_capture_pruning_removes_old_and_excess_artifacts(tmp_path):
    now = time.time()
    for index in range(15):
        path = tmp_path / f"desktop-{index}.jpg"
        path.write_bytes(b"x")
        os.utime(path, (now - index, now - index))

    old = tmp_path / "foreground-old.png"
    old.write_bytes(b"x")
    os.utime(old, (now - 5000, now - 5000))
    unrelated = tmp_path / "keep-me.txt"
    unrelated.write_text("keep")

    UniversalComputerController._prune_capture_files(
        tmp_path,
        keep=12,
        max_age_seconds=1000,
    )

    captures = list(tmp_path.glob("desktop-*.jpg")) + list(tmp_path.glob("foreground-*.png"))
    assert len(captures) == 12
    assert not old.exists()
    assert unrelated.exists()


@pytest.mark.parametrize("action", ["focus", "minimize", "maximize", "restore", "close"])
def test_app_window_controls_report_verified_state(action):
    user32 = _FakeUser32()
    if action == "restore":
        user32.zoomed = True
    controller = _WindowController(user32)

    result = controller.app_control("Notepad", action)

    assert result["command_sent"] is True
    assert result["verified_state"] is True
    assert result["verification"]["window"] == user32.hwnd


def test_task_tracker_uses_actionable_uia_and_verified_window_state(tmp_path):
    from iras.device_bridge.skills import PersistentSkillStore
    from iras.device_bridge.task_engine import TaskTracker

    tracker = TaskTracker(
        goal="control app",
        skill_store=PersistentSkillStore(tmp_path / "skills.json"),
    )

    tracker.record(
        "device_computer_observe",
        {},
        {
            "ok": True,
            "output": {
                "uia_available": True,
                "uia_actionable": False,
                "vision_available": False,
            },
        },
    )
    assert tracker.accessibility_limited is True

    tracker.record(
        "device_computer_observe",
        {},
        {
            "ok": True,
            "output": {
                "observation_scope": "desktop",
                "uia_actionable": True,
                "vision_available": False,
            },
        },
    )
    assert tracker.accessibility_limited is True

    tracker.record(
        "device_app_control",
        {"app": "Notepad", "action": "maximize"},
        {"ok": True, "output": {"verified_state": True}},
    )
    assert tracker.needs_verification is False

    tracker.record(
        "device_app_control",
        {"app": "Notepad", "action": "close"},
        {"ok": True, "output": {"verified_state": False}},
    )
    assert tracker.needs_verification is True


def test_tool_schema_exposes_visual_verification_predicates():
    from pathlib import Path

    source = Path("src/iras/device_bridge/tools.py").read_text(encoding="utf-8")
    assert '"visual_changed"' in source
    assert '"visual_stable"' in source
    assert "verified_state" in source


class _FakeVisual:
    def _run_uia_observer(self, hwnd, max_elements):
        return {
            "elements": [
                {
                    "name": "Search",
                    "automation_id": "SearchBox",
                    "role": "Edit",
                    "enabled": True,
                    "focusable": True,
                    "rect": {"left": 100, "top": 100, "width": 200, "height": 30},
                }
            ]
        }


def test_desktop_scope_runs_visual_grounding_even_when_foreground_uia_is_actionable(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), _FakeVisual())
    screenshot = {
        "path": "desktop.jpg",
        "sha256": "desktop-hash",
        "bytes": 100,
        "image_width": 1600,
        "image_height": 900,
        "source_width": 1920,
        "source_height": 1080,
        "desktop_rect": {"left": 0, "top": 0, "width": 1920, "height": 1080},
        "capture_scope": "desktop",
    }
    calls = []

    monkeypatch.setattr(controller, "_require_windows", lambda: None)
    monkeypatch.setattr(controller, "_capture_desktop", lambda: screenshot)
    monkeypatch.setattr(
        controller,
        "_foreground",
        lambda: {
            "hwnd": 10,
            "title": "Spotify",
            "rect": {"left": 100, "top": 100, "width": 900, "height": 700},
        },
    )
    monkeypatch.setattr(controller, "_cursor", lambda: {"x": 1, "y": 2})
    monkeypatch.setattr(controller, "_omniparser_endpoint", lambda: "http://local/parse/")
    monkeypatch.setattr(
        controller,
        "_capture_foreground",
        lambda rect: (_ for _ in ()).throw(AssertionError("foreground crop should not run")),
    )

    def fake_parser(capture):
        calls.append(capture)
        return {
            "status": "available",
            "available": True,
            "elements": [],
            "annotated_screenshot": None,
        }

    monkeypatch.setattr(controller, "_run_omniparser", fake_parser)
    monkeypatch.setattr(controller, "_prune_capture_files", lambda: None)

    result = controller.observe(vision="auto", scope="desktop", max_elements=100)

    assert result["uia_actionable"] is True
    assert result["vision_available"] is True
    assert result["observation_scope"] == "desktop"
    assert result["vision_scope"] == "desktop"
    assert calls == [screenshot]


def test_action_reobserve_preserves_original_scope_and_vision_mode(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    element = {
        "element_id": "vision:9",
        "label": "Taskbar app",
        "name": "Taskbar app",
        "automation_id": "",
        "role": "icon",
        "enabled": True,
        "interactive": True,
        "rect": {"left": 400, "top": 900, "width": 40, "height": 40},
    }
    observation = _observation(element)
    observation["vision_requested"] = "always"
    observation["observation_scope"] = "desktop"
    controller._observations["obs-1"] = observation

    monkeypatch.setattr(controller, "_foreground_still_matches", lambda obs: True)
    monkeypatch.setattr(controller, "_mouse_click", lambda *args, **kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    calls = []

    def fake_observe(*, vision, scope, max_elements):
        calls.append((vision, scope, max_elements))
        return {
            "observation_id": "after",
            "foreground": {"hwnd": 77, "title": "Test"},
            "screenshot": {"sha256": "screen-b"},
            "visual_sha256": "visual-b",
            "elements": [],
        }

    monkeypatch.setattr(controller, "observe", fake_observe)

    result = controller.action(
        observation_id="obs-1",
        action="click",
        element_id="vision:9",
        verify=True,
    )

    assert calls == [("always", "desktop", 180)]
    assert result["closed_loop_observed"] is True
    assert result["screen_changed"] is True
    assert result["visual_changed"] is True


def test_foreground_freshness_guard_detects_window_move(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    observation = _observation()
    observation["foreground"]["rect"] = {
        "left": 100,
        "top": 100,
        "width": 800,
        "height": 600,
    }

    monkeypatch.setattr(
        controller,
        "_foreground",
        lambda: {
            "hwnd": 77,
            "title": "Test",
            "rect": {"left": 120, "top": 100, "width": 800, "height": 600},
        },
    )

    assert controller._foreground_still_matches(observation) is False


def test_desktop_observations_have_shorter_coordinate_ttl(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    now = 10_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    monkeypatch.setenv("IRAS_COMPUTER_OBSERVATION_TTL", "30")

    desktop = _observation()
    desktop["captured_at"] = now - 11.0
    desktop["observation_scope"] = "desktop"
    controller._observations["desktop"] = desktop

    with pytest.raises(RuntimeError, match="too old"):
        controller._observation("desktop")

    foreground = _observation()
    foreground["captured_at"] = now - 11.0
    foreground["observation_scope"] = "foreground"
    controller._observations["foreground"] = foreground

    assert controller._observation("foreground") is foreground


def test_wait_action_is_not_reported_as_input_injection(monkeypatch):
    controller = UniversalComputerController(_FakeUI(), object())
    observation = _observation()
    controller._observations["obs-1"] = observation
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    result = controller.action(
        observation_id="obs-1",
        action="wait",
        seconds=0.1,
        verify=False,
    )

    assert result["input_injected"] is False
