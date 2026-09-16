from pathlib import Path


def test_web_has_model_independent_direct_remote_action_console():
    text = Path('clients/web/index.html').read_text(encoding='utf-8')
    assert 'id="direct"' in text
    assert 'id="directAction"' in text
    assert 'id="directArgs"' in text
    assert 'async function invokeRemoteAction' in text
    assert 'async function runDirectAction' in text
    assert '/v1/remote/invoke' in text
    assert 'X-IRAS-Remote-Token' in text
