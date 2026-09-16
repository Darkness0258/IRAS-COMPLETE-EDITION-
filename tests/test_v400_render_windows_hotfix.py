from __future__ import annotations

from pathlib import Path


def test_render_docker_port_matches_render_default():
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "PORT=10000" in text
    assert "EXPOSE 10000" in text
    assert "EXPOSE 8000" not in text


def test_cloud_health_is_shallow_and_ready_is_detailed():
    text = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    health_start = text.index('@app.get("/health")')
    ready_start = text.index('@app.get("/ready")')
    health_block = text[health_start:ready_start]
    assert "runtime.agent.provider.status" not in health_block
    assert '"uptime_seconds"' in health_block
    assert 'os.getenv(\n            "PORT",\n            "10000"' in text


def test_token_generator_works_on_windows_powershell_51_contract():
    text = Path("generate-iras-token.ps1").read_text(encoding="utf-8")
    assert "RandomNumberGenerator]::Create()" in text
    assert ".GetBytes($bytes)" in text
    assert "RandomNumberGenerator]::Fill" not in text
    assert "generation failed" in text


def test_validation_cleans_cache_and_egg_info_before_clean_tree():
    runner = Path("run-v400-validation.ps1").read_text(encoding="utf-8")
    cleaner = Path("scripts/maintenance/clean-v400-validation-debris.ps1").read_text(encoding="utf-8")
    assert "clean-v400-validation-debris.ps1" in runner
    assert "*.egg-info" in cleaner
    assert ".pytest_cache" in cleaner


def test_remote_setup_rejects_placeholder_cloud_url():
    text = Path("scripts/windows/setup-remote-access.ps1").read_text(encoding="utf-8")
    assert "YOUR-IRAS-CLOUD" in text
    assert "real deployed IRAS URL" in text


def test_ci_runs_current_release_validator():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "IRAS v4.2 RC3 multi-agent validation" in text
    assert ".\\run-v420-validation.ps1" in text
    assert "run-v370-validation.ps1" not in text
