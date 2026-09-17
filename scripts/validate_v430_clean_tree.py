from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/iras/multitasking.py",
    "src/iras/orchestration.py",
    "src/iras/execution_router.py",
    "src/iras/remote_access.py",
    "src/iras/remote_protocol.py",
    "src/iras/safety_runtime.py",
    "src/iras/security/secret_store.py",
    "src/iras/device_bridge/agent.py",
    "src/iras/device_bridge/remote_context.py",
    "docs/V4_2_RC3_NOTES.md",
    "docs/V4_2_RC4_NOTES.md",
    "docs/V4_2_RC6_NOTES.md",
    "docs/V4_3_RC1_NOTES.md",
    "docs/V4_3_RC2_NOTES.md",
    "docs/V4_3_RC3_NOTES.md",
    "tests/test_v430_rc2_project_preflight.py",
    "tests/test_v430_rc3_result_delivery.py",
    "docs/V4_3_AUDIT_REPORT.md",
    "src/iras/security/tool_content.py",
    "tests/test_v430_deep_audit.py",
    "run-v430-validation.ps1",
    "docs/REMOTE_WINDOWS_ACCESS_V4.md",
    "clients/web/index.html",
    "scripts/windows/setup-remote-access.ps1",
    "scripts/maintenance/clean-v400-validation-debris.ps1",
    "run-v420-validation.ps1",
    "setup-remote-windows.ps1",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)(?:sk-or-v1|sk-proj|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)OPENROUTER_API_KEY\s*=\s*(?!your_|$)[^\s#]{20,}"),
]


def main() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).exists()]
    bad_cache, package_debris, secret_hits = [], [], []
    for path in ROOT.rglob("*"):
        rel = str(path.relative_to(ROOT))
        parts = set(path.parts)
        if {"__pycache__", ".pytest_cache"} & parts or path.suffix == ".pyc":
            bad_cache.append(rel)
        if any(part in {"build", "dist"} or part.endswith(".egg-info") for part in path.parts):
            package_debris.append(rel)
        if path.is_file() and path.name != ".env" and path.suffix.lower() in {
            ".py", ".md", ".toml", ".yml", ".yaml", ".ps1", ".html", ".example"
        }:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                secret_hits.append(rel)

    print("=== IRAS v4.3 RC3 CLEAN TREE VALIDATION ===")
    print("LOCAL .ENV PRESENT:", (ROOT / ".env").exists())
    print("REQUIRED V4.3 FILES PRESENT:", not missing)
    print("CACHE/COMPILED DEBRIS PRESENT:", bool(bad_cache))
    print("BUILD/PACKAGING DEBRIS PRESENT:", bool(package_debris))
    print("OBVIOUS SECRET PATTERNS FOUND:", bool(secret_hits))
    if missing:
        print("MISSING:", missing)
    if bad_cache:
        print("CACHE SAMPLE:", bad_cache[:12])
    if package_debris:
        print("BUILD DEBRIS SAMPLE:", package_debris[:12])
    if secret_hits:
        print("SECRET HIT SAMPLE:", secret_hits[:12])
    assert not missing
    assert not bad_cache
    assert not package_debris
    assert not secret_hits
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
