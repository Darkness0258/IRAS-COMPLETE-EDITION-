from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_iras_cli_exposes_version_without_starting_runtime():
    completed = subprocess.run(
        [sys.executable, '-m', 'iras', '--version'],
        capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0
    assert '4.0.0-rc1' in completed.stdout


def test_remote_setup_requires_32_character_master_token():
    text = Path('scripts/windows/setup-remote-access.ps1').read_text(encoding='utf-8')
    assert '$plainToken.Length -lt 32' in text


def test_token_generator_is_windows_powershell_51_compatible():
    text = Path('generate-iras-token.ps1').read_text(encoding='utf-8')
    assert 'RandomNumberGenerator]::Fill' not in text
    assert 'RandomNumberGenerator]::Create()' in text
    assert '$rng.GetBytes($bytes)' in text
    assert '$ErrorActionPreference = "Stop"' in text


def test_remote_setup_rejects_placeholder_before_pairing():
    text = Path('scripts/windows/setup-remote-access.ps1').read_text(encoding='utf-8')
    assert 'Test-IRASPlaceholderUrl' in text
    assert 'ServerUrl is still a placeholder' in text
    assert '/health' in text
    # Windows PowerShell 5.1 does not support the PowerShell 7 null-coalescing operator.
    assert '??' not in text


def test_v4_validation_removes_local_runtime_caches():
    text = Path('run-v400-validation.ps1').read_text(encoding='utf-8')
    assert 'cleanup_v400_runtime_artifacts.py' in text
    assert '-p no:cacheprovider' in text
    assert 'FINAL CLEAN TREE RECHECK' in text
    assert '$env:PYTHONPATH = $sourcePath' in text
