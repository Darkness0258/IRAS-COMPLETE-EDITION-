from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def cloud(): return (ROOT/'src/iras/cloud_api.py').read_text(encoding='utf-8')
def web(): return (ROOT/'clients/web/index.html').read_text(encoding='utf-8')
def test_queue_timeout_handles_real_device_workflows():
    t=cloud(); assert '"IRAS_CHAT_QUEUE_TIMEOUT"' in t; assert '"180"' in t; assert '300.0' in t; assert '15.0' in t
def test_contended_request_queues_before_wait():
    t=cloud(); a=t.index('blocking=False'); b=t.index('"queued"',a); c=t.index('deadline =',b); assert a<b<c
def test_queue_has_sse_heartbeats():
    t=cloud(); assert 'timeout=min(5.0, remaining)' in t; assert 'waited_ms' in t; assert 'remains queued' in t
def test_busy_only_after_queue_deadline():
    t=cloud(); assert t.index('deadline =') < t.index('IRAS request queue timed out')
def test_done_reports_queue_wait():
    assert '"queue_wait_ms": queue_wait_ms' in cloud()
def test_web_handles_queued_event():
    t=web(); assert 'event==="queued"' in t; assert 'IRAS queued' in t; assert 'queue_wait_ms' in t
def test_busy_error_maps_queue_exhaustion():
    t=cloud().lower(); assert 'request queue timed out' in t; assert 'error_code = "request_busy"' in t
def test_v344_version_contract():
    assert '3.4.4' in (ROOT/'src/iras/__init__.py').read_text(encoding='utf-8')
    assert 'version = "3.4.4"' in (ROOT/'pyproject.toml').read_text(encoding='utf-8')
