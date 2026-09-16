from __future__ import annotations

from pathlib import Path
import time

import pytest
from PIL import Image

from iras.device_bridge.computer_use import UniversalComputerController


class FakeUI:
    def hotkey(self, *_):
        return None

    def press(self, *_):
        return None

    def scroll(self, *_):
        return None

    def type_text(self, *_):
        return None

    def _key_code(self, *_):
        return 1


class FakeVisual:
    def _run_uia_observer(self, hwnd, max_elements):
        return {"elements": []}


def observation(element, observation_id="obs"):
    return {
        "observation_id": observation_id,
        "captured_at": time.time(),
        "foreground": {
            "hwnd": 10,
            "title": "App",
            "rect": {"left": 0, "top": 0, "width": 800, "height": 600},
        },
        "vision_requested": "always",
        "observation_scope": "foreground",
        "screenshot": {"sha256": "a"},
        "visual_sha256": "a",
        "elements": [element],
    }


def test_v370_low_confidence_visual_action_fails_closed(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    element = {
        "element_id": "vision:low",
        "source": "omniparser",
        "label": "Send",
        "role": "button",
        "interactive": True,
        "enabled": True,
        "confidence": 0.51,
        "rect": {"left": 10, "top": 10, "width": 50, "height": 20},
    }
    controller._observations["obs"] = observation(element)
    monkeypatch.setattr(controller, "_foreground_still_matches", lambda *_: True)

    with pytest.raises(RuntimeError, match="confidence is too low"):
        controller.action(
            observation_id="obs",
            action="click",
            element_id="vision:low",
            verify=False,
        )


def test_v370_one_state_changing_action_consumes_observation(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    element = {
        "element_id": "vision:ok",
        "source": "omniparser",
        "label": "Open",
        "role": "button",
        "interactive": True,
        "enabled": True,
        "confidence": 0.93,
        "rect": {"left": 10, "top": 10, "width": 50, "height": 20},
    }
    controller._observations["obs"] = observation(element)
    monkeypatch.setattr(controller, "_foreground_still_matches", lambda *_: True)
    monkeypatch.setattr(controller, "_mouse_click", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    first = controller.action(
        observation_id="obs",
        action="click",
        element_id="vision:ok",
        verify=False,
    )
    assert first["observation_consumed"] is True
    assert first["reobserve_required"] is True
    assert first["action_replay_allowed"] is False

    with pytest.raises(RuntimeError, match="already authorized one state-changing input"):
        controller.action(
            observation_id="obs",
            action="click",
            element_id="vision:ok",
            verify=False,
        )


def test_v370_move_does_not_consume_binding(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    element = {
        "element_id": "uia:item",
        "source": "uia",
        "label": "Item",
        "role": "button",
        "interactive": True,
        "enabled": True,
        "confidence": 0.99,
        "rect": {"left": 10, "top": 10, "width": 50, "height": 20},
    }
    controller._observations["obs"] = observation(element)
    monkeypatch.setattr(controller, "_foreground_still_matches", lambda *_: True)
    monkeypatch.setattr(controller, "_set_cursor", lambda *_: None)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    first = controller.action(
        observation_id="obs", action="move", element_id="uia:item", verify=False
    )
    second = controller.action(
        observation_id="obs", action="move", element_id="uia:item", verify=False
    )
    assert first["observation_consumed"] is False
    assert second["observation_consumed"] is False


def test_v370_image_change_score_detects_visual_difference(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (200, 120), "white").save(before)
    image = Image.new("RGB", (200, 120), "white")
    for x in range(50, 150):
        for y in range(30, 90):
            image.putpixel((x, y), (0, 0, 0))
    image.save(after)

    score = UniversalComputerController._image_change_score(str(before), str(after))
    assert score is not None
    assert score > 0.05


def test_v370_auto_scope_cascades_foreground_vision_to_desktop(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    desktop = {
        "path": "desktop.jpg",
        "sha256": "desktop",
        "bytes": 10,
        "image_width": 1600,
        "image_height": 900,
        "source_width": 1600,
        "source_height": 900,
        "desktop_rect": {"left": 0, "top": 0, "width": 1600, "height": 900},
        "capture_scope": "desktop",
    }
    foreground = dict(desktop)
    foreground.update(
        {
            "path": "foreground.png",
            "sha256": "foreground",
            "desktop_rect": {"left": 100, "top": 100, "width": 900, "height": 700},
            "capture_scope": "foreground",
        }
    )

    monkeypatch.setattr(controller, "_require_windows", lambda: None)
    monkeypatch.setattr(controller, "_capture_desktop", lambda: desktop)
    monkeypatch.setattr(controller, "_capture_foreground", lambda *_: foreground)
    monkeypatch.setattr(
        controller,
        "_foreground",
        lambda: {
            "hwnd": 10,
            "title": "WhatsApp",
            "rect": {"left": 100, "top": 100, "width": 900, "height": 700},
        },
    )
    monkeypatch.setattr(controller, "_cursor", lambda: {"x": 0, "y": 0})
    monkeypatch.setattr(controller, "_omniparser_endpoint", lambda: "http://local/parse/")
    monkeypatch.setattr(controller, "_prune_capture_files", lambda: None)
    monkeypatch.setattr(controller.omniparser, "status", lambda: {"status": "ready", "ready": True})

    calls = []

    def parser(capture):
        calls.append(capture["capture_scope"])
        if capture["capture_scope"] == "foreground":
            return {"status": "available", "available": True, "elements": []}
        return {
            "status": "available",
            "available": True,
            "elements": [
                {
                    "element_id": "vision:old-index",
                    "source": "omniparser",
                    "label": "Darkness",
                    "name": "Darkness",
                    "automation_id": "",
                    "role": "text",
                    "enabled": True,
                    "interactive": True,
                    "confidence": 0.9,
                    "rect": {"left": 200, "top": 200, "width": 100, "height": 30},
                }
            ],
        }

    monkeypatch.setattr(controller, "_run_omniparser", parser)

    result = controller.observe(vision="auto", scope="auto", max_elements=100)

    assert calls == ["foreground", "desktop"]
    assert result["vision_scope"] == "desktop"
    assert result["vision_fallback_chain"] == ["foreground", "desktop"]
    assert result["scene_visual_only_count"] == 1
    assert result["elements"][0]["element_id"].startswith("vision:")


def test_v370_exact_visual_parse_cache_is_bounded_and_marks_hits():
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    result = {
        "status": "available",
        "available": True,
        "elements": [{"element_id": "vision:x", "label": "Darkness"}],
        "runtime": {"ready": True},
        "cache_hit": False,
    }
    controller._vision_cache_put("same-shot", result)

    cached = controller._vision_cache_get("same-shot")

    assert cached is not None
    assert cached["cache_hit"] is True
    assert cached["status"] == "available_cached"
    assert cached["elements"][0]["label"] == "Darkness"
    assert controller._vision_cache_get("different-shot") is None


def test_v370_identical_screen_observations_still_receive_fresh_ids(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    desktop = {
        "path": "desktop.jpg",
        "sha256": "same-screen",
        "bytes": 10,
        "image_width": 800,
        "image_height": 600,
        "source_width": 800,
        "source_height": 600,
        "desktop_rect": {"left": 0, "top": 0, "width": 800, "height": 600},
        "capture_scope": "desktop",
    }
    monkeypatch.setattr(controller, "_require_windows", lambda: None)
    monkeypatch.setattr(controller, "_capture_desktop", lambda: dict(desktop))
    monkeypatch.setattr(
        controller,
        "_foreground",
        lambda: {
            "hwnd": 10,
            "title": "WhatsApp",
            "rect": {"left": 0, "top": 0, "width": 800, "height": 600},
        },
    )
    monkeypatch.setattr(controller, "_cursor", lambda: {"x": 0, "y": 0})
    monkeypatch.setattr(controller, "_prune_capture_files", lambda: None)
    monkeypatch.setattr(controller.omniparser, "status", lambda: {"status": "ready"})

    first = controller.observe(vision="off", scope="foreground")
    second = controller.observe(vision="off", scope="foreground")

    assert first["screenshot"]["sha256"] == second["screenshot"]["sha256"]
    assert first["observation_id"] != second["observation_id"]


def test_r4_roi_observation_preserves_absolute_geometry_and_fresh_id(monkeypatch):
    controller = UniversalComputerController(FakeUI(), FakeVisual())
    monkeypatch.setattr(controller, "_require_windows", lambda: None)
    monkeypatch.setattr(
        controller,
        "_foreground",
        lambda: {
            "hwnd": 10,
            "title": "WhatsApp",
            "rect": {"left": 100, "top": 50, "width": 1200, "height": 800},
        },
    )
    monkeypatch.setattr(controller, "_cursor", lambda: {"x": 0, "y": 0})
    monkeypatch.setattr(controller, "_prune_capture_files", lambda: None)
    monkeypatch.setattr(
        controller,
        "_capture_region",
        lambda region, **_: {
            "path": "roi.png",
            "sha256": "roi-hash",
            "bytes": 10,
            "image_width": 600,
            "image_height": 200,
            "source_width": 600,
            "source_height": 200,
            "desktop_rect": dict(region),
            "capture_scope": "roi",
            "capture_ms": 2,
        },
    )
    monkeypatch.setattr(
        controller,
        "_run_omniparser",
        lambda screenshot, mode="full": {
            "status": "available",
            "available": True,
            "elements": [
                {
                    "source": "omniparser",
                    "label": "DARKNESS",
                    "name": "DARKNESS",
                    "role": "text",
                    "interactive": True,
                    "enabled": True,
                    "confidence": 0.96,
                    "rect": {"left": 620, "top": 70, "width": 140, "height": 28},
                }
            ],
            "latency": 0.01,
            "http_ms": 12,
            "parse_mode": "text_roi",
            "requested_parse_mode": mode,
            "fallback_to_full": False,
            "runtime": {"ready": True},
            "cache_hit": False,
        },
    )

    first = controller.observe_region(
        region={"left": 450, "top": 50, "width": 850, "height": 180},
        label="whatsapp_header",
        mode="text",
    )
    second = controller.observe_region(
        region={"left": 450, "top": 50, "width": 850, "height": 180},
        label="whatsapp_header",
        mode="text",
    )

    assert first["vision_scope"] == "roi:whatsapp_header"
    assert first["vision_parse_mode"] == "text_roi"
    assert first["roi"]["left"] == 450
    assert first["elements"][0]["rect"]["left"] == 620
    assert first["observation_id"] != second["observation_id"]
    assert first["performance"]["input_pixels"] == 120000
    assert first["action_policy"].startswith("Controller-internal ROI observation")
