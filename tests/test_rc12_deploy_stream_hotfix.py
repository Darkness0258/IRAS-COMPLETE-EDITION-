from pathlib import Path


def test_ci_creates_the_venv_expected_by_release_validator():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m venv .venv" in text
    assert r".\.venv\Scripts\python.exe -m pip install -e" in text


def test_cloud_stream_binds_generator_resumes_to_one_context():
    text = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "from contextvars import copy_context" in text
    assert "stream_context = copy_context()" in text
    assert "stream_context.run(next, stream_iter)" in text
    assert "for chunk in events():" not in text


def test_voice_doctor_avoids_windows_powershell_html_execution_prompt():
    text = Path("voice-doctor.ps1").read_text(encoding="utf-8")
    assert "-UseBasicParsing" in text