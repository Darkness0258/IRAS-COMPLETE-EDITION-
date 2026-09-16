from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tool_bearing_sse_does_not_hold_lock_during_network_yield():
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
    assert "runtime.agent.handle_stream(" not in branch
    assert "agent_lock.release()" in branch
    assert 'yield _sse(' in branch
    assert branch.index(
        "agent_lock.release()"
    ) < branch.index(
        'yield _sse('
    )


def test_normal_conversation_still_uses_true_streaming_path():
    text = (
        ROOT
        / "src"
        / "iras"
        / "cloud_api.py"
    ).read_text(
        encoding="utf-8"
    )

    assert ".handle_stream(" in text
    assert '"token"' in text
    assert '"done"' in text


def test_busy_lock_is_not_mislabeled_as_ai_provider_failure():
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
    assert "still finishing a previous request" in cloud
    assert 'err.code=data.code||"request_failed"' in web
    assert 'e.code==="request_busy"' in web
    assert "IRAS busy · retry in a moment" in web


def test_v343_or_newer_version_contract():
    import re

    init = (
        ROOT
        / "src"
        / "iras"
        / "__init__.py"
    ).read_text(
        encoding="utf-8"
    )
    pyproject = (
        ROOT
        / "pyproject.toml"
    ).read_text(
        encoding="utf-8"
    )

    init_match = re.search(
        r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)',
        init,
    )
    pyproject_match = re.search(
        r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)',
        pyproject,
    )

    assert init_match is not None
    assert pyproject_match is not None

    init_version = tuple(
        int(part)
        for part in init_match.groups()
    )
    pyproject_version = tuple(
        int(part)
        for part in pyproject_match.groups()
    )

    assert init_version >= (3, 4, 3)
    assert pyproject_version == init_version
