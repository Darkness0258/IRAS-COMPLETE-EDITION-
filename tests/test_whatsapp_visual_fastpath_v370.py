from __future__ import annotations

from iras.core.agent import IRASAgent
from iras.device_bridge.intent import direct_device_intent
from iras.device_bridge.whatsapp_workflow import (
    find_chat_header_target,
    find_contact_target,
)
from iras.models import ToolResult


class _NoModelProvider:
    def complete(self, *_args, **_kwargs):
        raise AssertionError("WhatsApp visual fast path must not call the model")


class _Memory:
    def __init__(self):
        self.messages = []

    def add_message(self, role, text):
        self.messages.append((role, text))

    def all_facts(self, _limit):
        return []

    def recent_messages(self, _limit):
        return []

    def remember(self, *_args, **_kwargs):
        return None


class _Audit:
    def __init__(self):
        self.events = []

    def record(self, name, payload):
        self.events.append((name, payload))


class _WhatsAppTools:
    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        assert name == "device_whatsapp_open_chat"
        return ToolResult(
            True,
            output={
                "verified": True,
                "verified_header": str(arguments["contact"]).upper(),
                "messages_sent": 0,
                "typed_into_composer": False,
                "action_replay_allowed": False,
            },
        )


def test_user_acceptance_phrase_routes_to_one_bounded_whatsapp_tool():
    action = direct_device_intent(
        "Open WhatsApp, find Darkness and open that chat. Do not send anything. "
        "Verify visually that the chat header says Darkness."
    )

    assert action == {
        "tool": "device_whatsapp_open_chat",
        "arguments": {"contact": "Darkness"},
        "kind": "whatsapp_open_chat_verified",
    }


def test_whatsapp_fastpath_does_not_swallow_positive_send_request():
    action = direct_device_intent(
        "Open WhatsApp, find Darkness and open that chat, then send hello."
    )
    assert action is None


def test_agent_executes_whatsapp_navigation_without_model_rounds():
    tools = _WhatsAppTools()
    agent = IRASAgent(
        _NoModelProvider(),
        tools=tools,
        memory=_Memory(),
        audit=_Audit(),
        personality=None,
    )

    result = agent.handle(
        "Open WhatsApp, find Darkness and open that chat. Do not send anything. "
        "Verify visually that the chat header says Darkness."
    )

    assert tools.calls == [
        ("device_whatsapp_open_chat", {"contact": "Darkness"})
    ]
    assert 'visual header shows "DARKNESS"' in result
    assert "No message was sent" in result
    assert agent.last_metrics["model_ms"] == 0
    assert agent.last_metrics["tool_rounds"] == 1
    assert agent.last_metrics["model"] == "deterministic-device-router"


def test_header_grounding_rejects_matching_name_in_left_chat_list():
    elements = [
        {
            "element_id": "vision:list",
            "source": "vision",
            "label": "Darkness",
            "role": "text",
            "rect": {"left": 90, "top": 180, "width": 130, "height": 30},
        },
        {
            "element_id": "vision:header",
            "source": "vision",
            "label": "DARKNESS",
            "role": "text",
            "rect": {"left": 515, "top": 45, "width": 150, "height": 30},
        },
    ]
    found = find_chat_header_target(
        elements,
        contact="Darkness",
        foreground_rect={"left": 0, "top": 0, "width": 1536, "height": 864},
    )
    assert found["element_id"] == "vision:header"


def test_contact_grounding_excludes_same_label_search_field_and_right_header():
    search = {
        "element_id": "vision:search",
        "source": "vision",
        "label": "Darkness",
        "role": "input",
        "rect": {"left": 80, "top": 95, "width": 350, "height": 42},
    }
    contact = {
        "element_id": "vision:contact",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "rect": {"left": 95, "top": 190, "width": 150, "height": 30},
    }
    header = {
        "element_id": "vision:header",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "rect": {"left": 620, "top": 45, "width": 150, "height": 30},
    }
    found = find_contact_target(
        [search, contact, header],
        contact="Darkness",
        search_rect=search["rect"],
        foreground_rect={"left": 0, "top": 0, "width": 1536, "height": 864},
    )
    assert found["element_id"] == "vision:contact"


class _FakeUI:
    def __init__(self):
        self.calls = []
        self.catalog = self

    def app_control(self, app, action):
        self.calls.append(("app_control", app, action))
        return {"verified_state": True}

    def launch(self, app):
        self.calls.append(("launch", app))
        return {"launch_verified": True}


class _FakeComputer:
    def __init__(self, observations):
        self.observations = list(observations)
        self.actions = []

    def _foreground(self):
        return {
            "title": "WhatsApp",
            "hwnd": 10,
            "rect": {"left": 0, "top": 0, "width": 1536, "height": 864},
        }

    def observe(self, **kwargs):
        assert self.observations, "unexpected extra observation"
        item = dict(self.observations.pop(0))
        item.setdefault("foreground", self._foreground())
        return item

    def action(self, **kwargs):
        self.actions.append(dict(kwargs))
        return {"observation_consumed": True, "action_replay_allowed": False}


def _obs(observation_id, elements, *, vision_available=True):
    return {
        "observation_id": observation_id,
        "vision_available": vision_available,
        "elements": elements,
        "foreground": {
            "title": "WhatsApp",
            "hwnd": 10,
            "rect": {"left": 0, "top": 0, "width": 1536, "height": 864},
        },
    }


def test_controller_fastpath_returns_after_one_visual_header_proof():
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify

    header = {
        "element_id": "vision:header",
        "source": "vision",
        "label": "DARKNESS",
        "role": "text",
        "confidence": 0.9,
        "rect": {"left": 515, "top": 45, "width": 150, "height": 30},
    }
    computer = _FakeComputer([_obs("obs-1", [header])])
    result = open_chat_and_verify(_FakeUI(), computer, contact="Darkness")

    assert result["verified"] is True
    assert result["verified_header"] == "DARKNESS"
    assert result["observations"] == 1
    assert result["actions"] == []
    assert result["messages_sent"] == 0
    assert computer.actions == []


def test_controller_fastpath_searches_then_clicks_with_fresh_observations(monkeypatch):
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify
    import iras.device_bridge.whatsapp_workflow as workflow

    monkeypatch.setattr(workflow.time, "sleep", lambda *_: None)
    search = {
        "element_id": "vision:search",
        "source": "vision",
        "label": "Search or start new chat",
        "role": "textbox",
        "confidence": 0.9,
        "rect": {"left": 80, "top": 95, "width": 350, "height": 42},
    }
    contact = {
        "element_id": "vision:contact",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "confidence": 0.82,
        "ambiguous_label": True,
        "rect": {"left": 95, "top": 190, "width": 150, "height": 30},
    }
    header = {
        "element_id": "vision:header",
        "source": "vision",
        "label": "DARKNESS",
        "role": "text",
        "confidence": 0.9,
        "rect": {"left": 515, "top": 45, "width": 150, "height": 30},
    }
    computer = _FakeComputer(
        [
            _obs("obs-search", [search]),
            _obs("obs-contact", [search, contact]),
            _obs("obs-header", [header]),
        ]
    )

    result = open_chat_and_verify(_FakeUI(), computer, contact="Darkness")

    assert result["verified"] is True
    assert result["observations"] == 3
    assert [item["action"] for item in computer.actions] == ["type_into", "click"]
    assert computer.actions[0]["observation_id"] == "obs-search"
    assert computer.actions[0]["verify"] is False
    assert computer.actions[1]["observation_id"] == "obs-contact"
    assert computer.actions[1]["verify"] is False
    assert computer.actions[1]["allow_controller_disambiguation"] is True
    assert result["messages_sent"] == 0
    assert result["typed_into_composer"] is False

class _ROIFakeComputer(_FakeComputer):
    def __init__(self, roi_observations):
        super().__init__([])
        self.roi_observations = list(roi_observations)
        self.roi_calls = []

    def observe_region(self, **kwargs):
        self.roi_calls.append(dict(kwargs))
        assert self.roi_observations, "unexpected extra ROI observation"
        item = dict(self.roi_observations.pop(0))
        item.setdefault("foreground", self._foreground())
        item.setdefault("performance", {"total_ms": 12, "parse_mode": "text_roi"})
        item.setdefault("roi_label", kwargs.get("label"))
        item.setdefault("vision_parse_mode", "text_roi")
        return item

    def observe(self, **kwargs):
        raise AssertionError("R4 ROI fast path should not broaden on successful flow")


def test_r5_roi_fastpath_uses_text_regions_and_preserves_fresh_action_binding(monkeypatch):
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify
    import iras.device_bridge.whatsapp_workflow as workflow

    monkeypatch.setattr(workflow.time, "sleep", lambda *_: None)
    search = {
        "element_id": "vision:search-roi",
        "source": "vision",
        "label": "Search or start new chat",
        "role": "text",
        "confidence": 0.96,
        "rect": {"left": 95, "top": 90, "width": 220, "height": 28},
    }
    contact = {
        "element_id": "vision:contact-roi",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "confidence": 0.94,
        "rect": {"left": 110, "top": 190, "width": 120, "height": 28},
    }
    header = {
        "element_id": "vision:header-roi",
        "source": "vision",
        "label": "DARKNESS",
        "role": "text",
        "confidence": 0.97,
        "rect": {"left": 610, "top": 48, "width": 140, "height": 30},
    }
    computer = _ROIFakeComputer(
        [
            _obs("roi-header-initial", []),
            _obs("roi-search", [search]),
            _obs("roi-results", [contact]),
            _obs("roi-header", [header]),
        ]
    )

    result = open_chat_and_verify(_FakeUI(), computer, contact="Darkness")

    assert result["verified"] is True
    assert result["roi_fastpath"] is True
    assert result["verification_source"] == "vision_roi_text"
    assert result["observations"] == 4
    assert result["route"] == "r5_search_results_header"
    assert [call["label"] for call in computer.roi_calls] == [
        "whatsapp_header",
        "whatsapp_search",
        "whatsapp_results",
        "whatsapp_header",
    ]
    assert all(call["mode"] == "text" for call in computer.roi_calls)
    assert [item["action"] for item in computer.actions] == ["type_into", "click"]
    assert computer.actions[0]["observation_id"] == "roi-search"
    assert computer.actions[1]["observation_id"] == "roi-results"
    assert result["messages_sent"] == 0
    assert result["typed_into_composer"] is False
    assert result["action_replay_allowed"] is False


def test_r5_roi_fastpath_finishes_after_header_roi_when_chat_already_open():
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify

    header = {
        "element_id": "vision:header-roi",
        "source": "vision",
        "label": "DARKNESS",
        "role": "text",
        "confidence": 0.98,
        "rect": {"left": 610, "top": 48, "width": 140, "height": 30},
    }
    computer = _ROIFakeComputer([_obs("roi-header", [header])])

    result = open_chat_and_verify(_FakeUI(), computer, contact="Darkness")

    assert result["verified"] is True
    assert result["observations"] == 1
    assert result["actions"] == []
    assert len(computer.roi_calls) == 1
    assert computer.roi_calls[0]["label"] == "whatsapp_header"
    assert result["route"] == "r5_header_roi"



def test_r5_cold_text_retries_stay_in_roi_and_do_not_broaden(monkeypatch):
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify
    import iras.device_bridge.whatsapp_workflow as workflow

    monkeypatch.setattr(workflow.time, "sleep", lambda *_: None)
    monkeypatch.setenv("IRAS_WHATSAPP_COLD_ROI_RETRIES", "2")
    search = {
        "element_id": "vision:search-cold",
        "source": "vision",
        "label": "Search or start new chat",
        "role": "text",
        "confidence": 0.95,
        "rect": {"left": 90, "top": 90, "width": 250, "height": 30},
    }
    contact = {
        "element_id": "vision:contact-cold",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "confidence": 0.95,
        "rect": {"left": 105, "top": 190, "width": 130, "height": 30},
    }
    header = {
        "element_id": "vision:header-cold",
        "source": "vision",
        "label": "DARKNESS",
        "role": "text",
        "confidence": 0.98,
        "rect": {"left": 610, "top": 48, "width": 140, "height": 30},
    }
    computer = _ROIFakeComputer(
        [
            _obs("cold-header-0", []),
            _obs("cold-search-0", []),
            _obs("cold-search-1", [search]),
            _obs("cold-results-0", []),
            _obs("cold-results-1", [contact]),
            _obs("cold-header-1", []),
            _obs("cold-header-2", [header]),
        ]
    )

    result = open_chat_and_verify(_FakeUI(), computer, contact="Darkness")

    assert result["verified"] is True
    assert result["roi_fastpath"] is True
    assert result["route"] == "r5_search_results_header"
    assert result["observations"] == 7
    assert [call["label"] for call in computer.roi_calls] == [
        "whatsapp_header",
        "whatsapp_search",
        "whatsapp_search",
        "whatsapp_results",
        "whatsapp_results",
        "whatsapp_header",
        "whatsapp_header",
    ]
    assert [item["action"] for item in computer.actions] == ["type_into", "click"]


def test_r5_never_retypes_search_after_state_change_when_results_stay_missing(monkeypatch):
    from iras.device_bridge.whatsapp_workflow import open_chat_and_verify
    import iras.device_bridge.whatsapp_workflow as workflow

    monkeypatch.setattr(workflow.time, "sleep", lambda *_: None)
    monkeypatch.setenv("IRAS_WHATSAPP_COLD_ROI_RETRIES", "2")
    search = {
        "element_id": "vision:search-only",
        "source": "vision",
        "label": "Search or start new chat",
        "role": "text",
        "confidence": 0.96,
        "rect": {"left": 90, "top": 90, "width": 250, "height": 30},
    }
    computer = _ROIFakeComputer(
        [
            _obs("header-empty", []),
            _obs("search-found", [search]),
            _obs("results-empty-1", []),
            _obs("results-empty-2", []),
        ]
    )

    try:
        open_chat_and_verify(_FakeUI(), computer, contact="Darkness")
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected bounded missing-result failure")

    assert "not replayed" in text
    assert [item["action"] for item in computer.actions] == ["type_into"]
