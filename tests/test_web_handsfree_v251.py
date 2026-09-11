from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_web_handsfree_uses_restartable_utterance_sessions():
    text = (
        ROOT / "clients" / "web" / "index.html"
    ).read_text(encoding="utf-8")

    assert "ensureMicrophoneAccess" in text
    assert "r.continuous=false" in text
    assert "scheduleHandsRestart" in text
    assert "onaudiostart" in text
    assert "onspeechstart" in text
    assert "Wake word heard · keep talking..." in text
    assert 'code==="audio-capture"' in text
    assert 'code==="network"' in text
