from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "docs/V4_4_RC1_NOTES.md",
    "docs/V4_4_RC2_NOTES.md",
    "tests/test_v440_persistent_jobs_and_provider_status.py",
    "scripts/validate_v440_integrated.py",
    "scripts/validate_v440_clean_tree.py",
    "run-v440-validation.ps1",
    "src/iras/orchestration.py",
    "src/iras/providers/multi_provider.py",
    "src/iras/device_bridge/executor.py",
    "clients/web/index.html",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)(?:sk-or-v1|sk-proj|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)OPENROUTER_API_KEY\s*=\s*(?!your_|$)[^\s#]{20,}"),
]


def main() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).exists()]
    cache, debris, secrets = [], [], []
    for path in ROOT.rglob("*"):
        rel = str(path.relative_to(ROOT))
        if {"__pycache__", ".pytest_cache"} & set(path.parts) or path.suffix == ".pyc":
            cache.append(rel)
        if any(part in {"build", "dist"} or part.endswith(".egg-info") for part in path.parts):
            debris.append(rel)
        if path.is_file() and path.name != ".env" and path.suffix.lower() in {".py", ".md", ".toml", ".yml", ".yaml", ".ps1", ".html", ".example"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                secrets.append(rel)
    print("=== IRAS v4.4 RC2 CLEAN TREE VALIDATION ===")
    print("LOCAL .ENV PRESENT:", (ROOT / ".env").exists())
    print("REQUIRED V4.4 FILES PRESENT:", not missing)
    print("CACHE/COMPILED DEBRIS PRESENT:", bool(cache))
    print("BUILD/PACKAGING DEBRIS PRESENT:", bool(debris))
    print("OBVIOUS SECRET PATTERNS FOUND:", bool(secrets))
    if missing: print("MISSING:", missing)
    if cache: print("CACHE SAMPLE:", cache[:12])
    if debris: print("DEBRIS SAMPLE:", debris[:12])
    if secrets: print("SECRET SAMPLE:", secrets[:12])
    assert not missing
    assert not cache
    assert not debris
    assert not secrets
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
