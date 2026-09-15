from __future__ import annotations

from pathlib import Path

import validate_v360_clean_tree as base

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_370 = {
    ".gitignore",
    "ARCHITECTURE.md",
    "README.md",
    "pyproject.toml",
    "run-v370-validation.ps1",
    "run-v370-real-device-smoke.ps1",
    "scripts/validate_v370_integrated.py",
    "scripts/validate_v370_real_device.py",
    "src/iras/__init__.py",
    "src/iras/autonomy.py",
    "src/iras/vision/__init__.py",
    "src/iras/vision/omniparser_runtime.py",
    "src/iras/vision/scene_graph.py",
    "src/iras/device_bridge/whatsapp_workflow.py",
    "docs/MULTIMODAL_GROUNDING_V3.7.0.md",
    "docs/OMNIPARSER_IRAS_SETUP.md",
    "tests/test_multimodal_scene_graph_v370.py",
    "tests/test_multimodal_controller_v370.py",
    "tests/test_omniparser_autostart_v370.py",
    "tests/test_whatsapp_visual_fastpath_v370.py",
}


def main() -> None:
    problems: list[str] = []
    forbidden = (
        base.LEGACY_ROOT_DOCS
        | base.OBSOLETE_ROOT_FILES
        | base.MOVED_DOC_ROOT_FILES
        | base.OBSOLETE_RUNNERS
        | base.DANGEROUS_ONE_OFF_VALIDATORS
    )
    for rel in sorted(forbidden):
        if (ROOT / rel).exists():
            problems.append(f"obsolete artifact still present: {rel}")

    if (ROOT / "docs" / "history").exists():
        problems.append("obsolete docs/history directory still present")

    for rel in sorted(REQUIRED_370):
        if not (ROOT / rel).exists():
            problems.append(f"required v3.7 file missing: {rel}")

    env_problem = base.local_env_release_problem(ROOT)
    if env_problem:
        problems.append(env_problem)

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in base.TEXT_SUFFIXES:
            continue
        if {".venv", "venv", "node_modules"} & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in base.SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(
                    f"possible committed secret pattern in {path.relative_to(ROOT)}"
                )
                break

    if problems:
        print("=== IRAS v3.7.0 CLEAN TREE VALIDATION ===")
        for item in problems:
            print("FAIL:", item)
        raise SystemExit(1)

    print("=== IRAS v3.7.0 CLEAN TREE VALIDATION ===")
    print("LEGACY ROOT DOCS PRESENT: False")
    print("OBSOLETE ROOT RELEASE NOTES PRESENT: False")
    print("REAL-MESSAGE ONE-OFF VALIDATORS PRESENT: False")
    print(f"LOCAL .ENV PRESENT: {(ROOT / '.env').exists()}")
    print(f"LOCAL .ENV RELEASE SAFE: {base.local_env_release_problem(ROOT) is None}")
    print("OBVIOUS SECRET PATTERNS FOUND: False")
    print("V3.7 MULTIMODAL FILES PRESENT: True")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
