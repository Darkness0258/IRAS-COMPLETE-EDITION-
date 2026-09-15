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
