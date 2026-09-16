from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]


def test_stream_has_first_token_timeout():
    text = (
        ROOT
        / "src"
        / "iras"
        / "providers"
        / "openai_compatible.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "IRAS_FIRST_TOKEN_TIMEOUT" in text
    assert "timed out waiting for first token" in text
    assert "timeout=request_timeout" in text


def test_chat_lock_is_bounded():
    text = (
        ROOT
        / "src"
        / "iras"
        / "cloud_api.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "IRAS_CHAT_QUEUE_TIMEOUT" in text
    assert "blocking=False" in text

def test_tool_stream_releases_lock_before_single_result_is_yielded():
    text = (
        ROOT
        / "src"
        / "iras"
        / "cloud_api.py"
    ).read_text(
        encoding="utf-8"
    )

    branch = text.split(
        "if not direct_stream:",
        1,
    )[1].split(
        "else:",
        1,
    )[0]

    assert "runtime.agent.handle(" in branch
    assert "agent_lock.release()" in branch
    assert 'yield _sse(' in branch
    assert branch.index(
        "agent_lock.release()"
    ) < branch.index(
        'yield _sse('
    )


def test_stream_busy_has_distinct_error_code_and_web_status():
    cloud = (
        ROOT
        / "src"
        / "iras"
        / "cloud_api.py"
    ).read_text(
        encoding="utf-8"
    )
    web = (
        ROOT
        / "clients"
        / "web"
        / "index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'error_code = "request_busy"' in cloud
    assert 'err.code=data.code||"request_failed"' in web
    assert 'e.code==="request_busy"' in web
    assert "IRAS busy · retry in a moment" in web

def test_stream_queue_has_heartbeat_and_long_workflow_backpressure():
    text = (ROOT / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    web = (ROOT / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    assert '"IRAS_CHAT_QUEUE_TIMEOUT"' in text
    assert '"180"' in text
    assert '"queued"' in text
    assert "deadline" in text
    assert "5.0" in text
    assert "queue_wait_ms" in text
    assert 'event==="queued"' in web
    assert "IRAS queued" in web
