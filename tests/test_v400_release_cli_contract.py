from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


def test_iras_cli_exposes_version_without_starting_runtime():
    env = os.environ.copy()
    source_root = str(Path("src").resolve())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = source_root + (os.pathsep + existing if existing else "")
    completed = subprocess.run(
        [sys.executable, '-m', 'iras', '--version'],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert completed.returncode == 0
    assert '5.0.0-rc12' in completed.stdout


def test_remote_setup_requires_32_character_master_token():
    text = Path('scripts/windows/setup-remote-access.ps1').read_text(encoding='utf-8')
    assert '$plainToken.Length -lt 32' in text
