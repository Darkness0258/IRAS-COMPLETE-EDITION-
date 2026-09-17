from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "clients" / "web" / "index.html"


def _web() -> str:
    return WEB.read_text(encoding="utf-8")


def test_engineering_noun_form_triggers_browser_remote_preflight():
    text = _web()
    assert "improv(?:e|ement)" in text
    assert "async function ensureRemoteAuthorization()" in text
    assert "return await ensureRemoteAuthorization();" in text


def test_streaming_authorization_gate_resumes_same_turn_once():
    text = _web()
    assert 'completion.execution_mode==="authorization_required"' in text
    assert 'Remote authorized. Resuming your request...' in text
    assert 'server did not accept it. Reopen Remote and try again.' in text
    # The continuation reuses streamReply with the existing `text` and bubble;
    # it does not call sendText recursively (which would duplicate the user turn).
    continuation = text.split('if(completion&&completion.execution_mode==="authorization_required")', 1)[1]
    continuation = continuation.split('if(generation!==chatGeneration)return;', 1)[0]
    assert "sendText(" not in continuation
    assert "streamReply(base,c,text,bubble,session,controller.signal)" in continuation


def test_tasks_goal_retries_remote_403_after_explicit_consent():
    text = _web()
    start = text.split("async function startAgentGoal(){", 1)[1].split("async function loadLatestGoal(){", 1)[0]
    assert "retriedAfterAuthorization" in start
    assert "r.status===403" in start
    assert "ensureRemoteAuthorization()" in start
    assert "Remote authorized. Starting the goal automatically..." in start
    assert "Remote authorization was not granted, so the goal was not started." in start


def test_authorization_gate_response_is_not_spoken_before_continuation():
    text = _web()
    assert 'if(data.execution_mode==="authorization_required")' in text
    gate = text.split('if(data.execution_mode==="authorization_required")', 1)[1].split('}else{', 1)[0]
    assert 'voiceBuffer=""' in gate
    assert "stopCurrentAudio();" in gate
