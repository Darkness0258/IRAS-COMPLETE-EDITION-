from __future__ import annotations

import time

from iras.models import ApprovalRequest, PermissionLevel
from iras.tools.terminal import (
    TOOLS,
    classify_terminal,
    terminal_capabilities,
    terminal_discover,
    terminal_exec,
    terminal_read,
    terminal_start,
)
from iras.voice.approval import VoiceApprovalManager


class FakeListener:
    def __init__(self, heard: str):
        self.heard = heard
        self.calls = 0

    def listen_phrase(self, **_kwargs):
        self.calls += 1
        return self.heard


class FakeSpeaker:
    def __init__(self):
        self.spoken = []

    def speak(self, text: str):
        self.spoken.append(text)
        return "fake"


def test_universal_terminal_tool_surface_is_generic_not_per_cli():
    names = {tool.name for tool in TOOLS}
    assert {
        "terminal_capabilities",
        "terminal_discover",
        "terminal_which",
        "terminal_exec",
        "terminal_start",
        "terminal_read",
        "terminal_send",
        "terminal_stop",
        "terminal_sessions",
    } <= names
    status = terminal_capabilities()
    assert status["unrestricted_by_cli_name"] is True


def test_terminal_discovery_and_execution_work_without_cli_allowlist():
    discovered = terminal_discover("python", limit=20, include_powershell=False)
    assert discovered["unrestricted_by_name"] is True
    result = terminal_exec("echo IRAS_TERMINAL_OK", timeout=15)
    assert result["returncode"] == 0
    assert "IRAS_TERMINAL_OK" in result["stdout"]


def test_terminal_background_session_can_be_read():
    started = terminal_start("echo IRAS_SESSION_OK")
    session_id = started["session_id"]
    deadline = time.time() + 3
    snapshot = started
    output = started.get("stdout", "")
    while time.time() < deadline:
        snapshot = terminal_read(session_id)
        output += snapshot.get("stdout", "")
        if not snapshot["running"]:
            break
        time.sleep(0.05)
    # Output can arrive a few milliseconds after process exit; one extra drain is deterministic.
    time.sleep(0.05)
    snapshot = terminal_read(session_id)
    output += snapshot.get("stdout", "")
    assert snapshot["returncode"] == 0
    assert "IRAS_SESSION_OK" in output


def test_terminal_destructive_commands_promote_to_critical():
    assert classify_terminal({"command": "python --version"}) == PermissionLevel.SYSTEM_ACTION
    assert classify_terminal({"command": "git reset --hard HEAD~1"}) == PermissionLevel.CRITICAL
    assert classify_terminal({"command": "Remove-Item C:\\Temp -Recurse -Force"}) == PermissionLevel.CRITICAL


def test_voice_system_permission_requires_explicit_iras_approval_phrase():
    request = ApprovalRequest("terminal_exec", PermissionLevel.SYSTEM_ACTION, {"command": "git status"}, "test")
    speaker = FakeSpeaker()
    approved = VoiceApprovalManager(FakeListener("IRAS approve"), speaker, enabled=True).request(request)
    assert approved.resolved is True
    assert approved.approved is True
    assert speaker.spoken

    ambiguous = VoiceApprovalManager(FakeListener("yes"), speaker, enabled=True).request(request)
    assert ambiguous.resolved is False
    assert ambiguous.approved is False


def test_voice_critical_permission_uses_fresh_spoken_challenge(monkeypatch):
    request = ApprovalRequest("terminal_exec", PermissionLevel.CRITICAL, {"command": "git reset --hard HEAD~1"}, "test")
    monkeypatch.setattr(VoiceApprovalManager, "_challenge_code", staticmethod(lambda: "7429"))

    manager = VoiceApprovalManager(
        FakeListener("IRAS authorize seven four two nine"),
        FakeSpeaker(),
        enabled=True,
        critical_enabled=True,
    )
    result = manager.request(request)
    assert result.resolved is True
    assert result.approved is True
    assert result.challenge == "7429"

    wrong = VoiceApprovalManager(
        FakeListener("IRAS authorize seven four two eight"),
        FakeSpeaker(),
        enabled=True,
        critical_enabled=True,
    ).request(request)
    assert wrong.resolved is False
    assert wrong.approved is False


def test_voice_denial_is_final_for_request():
    request = ApprovalRequest("terminal_exec", PermissionLevel.SYSTEM_ACTION, {"command": "git status"}, "test")
    result = VoiceApprovalManager(FakeListener("IRAS deny"), FakeSpeaker(), enabled=True).request(request)
    assert result.resolved is True
    assert result.approved is False


def test_voice_prompt_does_not_speak_terminal_arguments():
    request = ApprovalRequest(
        "terminal_exec",
        PermissionLevel.SYSTEM_ACTION,
        {"command": "example-cli --token super-private-value"},
        "test",
    )
    speaker = FakeSpeaker()
    result = VoiceApprovalManager(FakeListener("IRAS deny"), speaker, enabled=True).request(request)
    assert result.resolved is True
    spoken = " ".join(speaker.spoken).lower()
    assert "super-private-value" not in spoken
    assert "--token" not in spoken


def test_remote_cli_discovery_is_read_only_but_execution_stays_critical():
    from iras.remote_access import action_permission

    assert action_permission("cli_discover") == PermissionLevel.READ
    assert action_permission("run_command") == PermissionLevel.CRITICAL


def test_invalid_voice_approval_timeout_falls_back_to_safe_default(monkeypatch):
    from iras.config import Settings

    monkeypatch.setenv("IRAS_VOICE_APPROVAL_TIMEOUT", "not-a-number")
    assert Settings.load().voice_approval_timeout == 9
