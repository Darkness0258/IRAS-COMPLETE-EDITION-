from __future__ import annotations

from iras import __version__
from iras.autonomy import (
    AutonomySupervisor,
    local_identity_reply,
    looks_like_private_deliberation,
)
from iras.core.agent import IRASAgent
from iras.device_bridge.intent import direct_device_intent
from iras.models import ToolResult


class _NoModelProvider:
    def complete(self, *_args, **_kwargs):
        raise AssertionError("version query should not call the model")


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


def test_contextual_spotify_followup_resolves_it_from_live_session_context():
    autonomy = AutonomySupervisor()
    autonomy.note_tool_result(
        "device_open_app",
        {"app": "spotify"},
        {"ok": True, "output": {"app": "spotify"}},
    )

    assert autonomy.contextual_direct_action("now play music in it") == {
        "tool": "device_media_control",
        "arguments": {"command": "play", "app": "spotify"},
        "kind": "contextual_media_control",
    }


def test_contextual_media_followup_fails_closed_without_media_context():
    autonomy = AutonomySupervisor()
    assert autonomy.contextual_direct_action("now play music in it") is None


def test_autonomy_supervisor_keeps_decision_authority_bounded():
    message = AutonomySupervisor().system_message().lower()
    assert "choose the next smallest safe" in message
    assert "never invent a new external goal" in message
    assert "bypass permissions" in message
    assert "replay a failed state-changing action automatically" in message


def test_runtime_version_query_is_answered_locally_without_model():
    memory = _Memory()
    audit = _Audit()
    agent = IRASAgent(
        _NoModelProvider(),
        tools=None,
        memory=memory,
        audit=audit,
        personality=None,
    )

    result = agent.handle("What version are you?")

    assert result == f"IRAS {__version__}."
    assert memory.messages[-1] == ("assistant", result)
    assert agent.last_metrics["model_ms"] == 0
    assert agent.last_metrics["model"] == "local-runtime-identity"


def test_local_identity_reply_accepts_common_version_phrasing():
    assert local_identity_reply("IRAS version?") == f"IRAS {__version__}."
    assert local_identity_reply("what version is IRAS running?") == f"IRAS {__version__}."


def test_open_notepad_type_exactly_is_one_bounded_interaction():
    action = direct_device_intent(
        "Open Notepad, type exactly: IRAS v3.6 real-device test PASS"
    )

    assert action == {
        "tool": "device_interact_app",
        "arguments": {
            "app": "Notepad",
            "actions": [
                {
                    "action": "type",
                    "text": "IRAS v3.6 real-device test PASS",
                }
            ],
            "ensure_open": True,
        },
        "kind": "app_open_and_type",
    }



class _DeviceTools:
    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "device_open_app":
            return ToolResult(
                True,
                output={
                    "app": arguments.get("app"),
                    "launch_verified": True,
                    "foreground_verified": True,
                },
            )
        if name == "device_media_control":
            return ToolResult(
                True,
                output={
                    "command": arguments.get("command"),
                    "target_app": arguments.get("app"),
                    "command_sent": True,
                },
            )
        raise AssertionError(f"unexpected tool {name}")


def test_agent_resolves_natural_media_followup_without_model_call():
    memory = _Memory()
    audit = _Audit()
    tools = _DeviceTools()
    agent = IRASAgent(
        _NoModelProvider(),
        tools=tools,
        memory=memory,
        audit=audit,
        personality=None,
    )

    opened = agent.handle("Open Spotify.")
    resumed = agent.handle("now play music in it")

    assert "opened spotify" in opened.lower()
    assert "play media command on spotify" in resumed.lower()
    assert tools.calls == [
        ("device_open_app", {"app": "Spotify"}),
        ("device_media_control", {"command": "play", "app": "spotify"}),
    ]

def test_private_planner_scratchpad_is_detected_before_user_output():
    text = (
        "Actually, looking at the elements, I need to understand what is in "
        "the WebView. Let me try to interact with it, but first let me check "
        "whether there is a search field I can type into."
    )
    assert looks_like_private_deliberation(text) is True
    assert looks_like_private_deliberation("Spotify is open and verified.") is False
