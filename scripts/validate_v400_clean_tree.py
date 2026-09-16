from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/iras/remote_access.py",
    "src/iras/remote_protocol.py",
    "src/iras/safety_runtime.py",
    "src/iras/security/secret_store.py",
    "src/iras/observability.py",
    "src/iras/device_bridge/primitives.py",
    "src/iras/device_bridge/verifiers.py",
    "src/iras/device_bridge/agent.py",
    "src/iras/device_bridge/remote_context.py",
    "src/iras/vision/omniparser_bridge_server.py",
    "docs/REMOTE_WINDOWS_ACCESS_V4.md",
    "docs/PRODUCTION_READINESS_V4.md",
    "docs/REMOTE_ACCEPTANCE_CHECKLIST_V4.md",
    "clients/web/index.html",
    "scripts/windows/setup-remote-access.ps1",
    "scripts/maintenance/clean-v400-validation-debris.ps1",
    "run-v400-validation.ps1",
    "setup-remote-windows.ps1",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)(?:sk-or-v1|sk-proj|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)OPENROUTER_API_KEY\s*=\s*(?!your_|$)[^\s#]{20,}"),
]


def main() -> None:
    legacy_docs = [p for p in ROOT.glob("*RELEASE*.md") if p.name not in {"README.md"}]
    missing = [name for name in REQUIRED if not (ROOT / name).exists()]
    bad_cache: list[str] = []
    package_debris: list[str] = []
    secret_hits: list[str] = []

    for path in ROOT.rglob("*"):
        rel = str(path.relative_to(ROOT))
        parts = set(path.parts)
        if {"__pycache__", ".pytest_cache"} & parts or path.suffix == ".pyc":
            bad_cache.append(rel)
        if any(part in {"build", "dist"} or part.endswith(".egg-info") for part in path.parts):
            package_debris.append(rel)
        if (
            path.is_file()
            and path.name != ".env"
            and path.suffix.lower() in {".py", ".md", ".toml", ".yml", ".yaml", ".ps1", ".html", ".example"}
        ):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    secret_hits.append(rel)
                    break

    local_env = ROOT / ".env"
    print("=== IRAS v4.0 RC2 CLEAN TREE VALIDATION ===")
    print("LEGACY ROOT RELEASE DOCS PRESENT:", bool(legacy_docs))
    print("LOCAL .ENV PRESENT:", local_env.exists())
    print("REQUIRED V4 FILES PRESENT:", not missing)
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
    assert not legacy_docs
    assert not missing
    assert not bad_cache
    assert not package_debris
    assert not secret_hits
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
