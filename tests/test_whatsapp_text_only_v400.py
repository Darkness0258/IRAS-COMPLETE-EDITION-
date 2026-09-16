from __future__ import annotations

import iras.device_bridge.whatsapp_workflow as workflow


def test_whatsapp_full_semantic_model_is_opt_in(monkeypatch):
    monkeypatch.delenv("IRAS_WHATSAPP_FULL_VISION_FALLBACK", raising=False)
    assert workflow._full_vision_fallback_enabled() is False
    monkeypatch.setenv("IRAS_WHATSAPP_FULL_VISION_FALLBACK", "true")
    assert workflow._full_vision_fallback_enabled() is True


def test_workspace_roi_is_text_only_controller_owned():
    class Computer:
        def __init__(self):
            self.call = None
        def observe_region(self, **kwargs):
            self.call = kwargs
            return {"elements": [], "observation_id": "o"}

    c = Computer()
    workflow._roi_observation(
        c,
        {"left": 10, "top": 20, "width": 1000, "height": 800},
        purpose="workspace",
    )
    assert c.call["mode"] == "text"
    assert c.call["label"] == "whatsapp_workspace"
    assert c.call["region"] == {"left": 10, "top": 20, "width": 1000, "height": 800}
