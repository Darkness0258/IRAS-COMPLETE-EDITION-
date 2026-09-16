from __future__ import annotations

from pathlib import Path

from iras.core.agent import IRASAgent


def test_descriptive_screenshot_routes_to_multimodal_observation():
    names = IRASAgent._device_tool_names(
        "Take a screenshot of my Windows computer and describe what is open."
    )
    assert names == {"device_computer_observe"}


def test_plain_screenshot_still_uses_durable_capture_tool():
    names = IRASAgent._device_tool_names("Take a screenshot of my Windows computer.")
    assert names == {"device_capture_screen"}


def test_multimodal_tool_description_explains_descriptive_screen_use():
    text = Path("src/iras/device_bridge/tools.py").read_text(encoding="utf-8")
    assert "asks IRAS to describe/read a screenshot" in text
