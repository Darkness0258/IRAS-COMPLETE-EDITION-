from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OBSOLETE_ROOT_FILES = {
    "ADAPTIVE_RECOVERY_ROUTE_SCORING_V3.5.19.md",
    "AUTOMATIC_OUTCOME_RECOVERY_V3.5.11.md",
    "AUTOMATIC_RECOVERY_ROUTE_SELECTION_V3.5.12.md",
    "CONTEXT_AWARE_RECOVERY_LEARNING_V3.5.21.md",
    "FRESH_PLAN_EXECUTION_AND_VERIFICATION_V3.5.15.md",
    "MATERIAL_REPLAN_GUARD_V3.5.17.md",
    "PERSISTENT_LEARNED_APP_SKILLS_V3.4.0.md",
    "RECOVERY_AWARE_FRESH_ACTION_PLANNING_V3.5.14.md",
    "RECOVERY_CONFIDENCE_CALIBRATION_V3.5.22.md",
    "RECOVERY_HISTORY_AWARE_PLANNER_V3.5.18.md",
    "RECOVERY_ROUTE_EXECUTION_ORCHESTRATION_V3.5.13.md",
    "RECOVERY_ROUTE_PERFORMANCE_LEARNING_V3.5.20.md",
    "SPOTIFY_CLOSED_LOOP_V3.5.md",
    "STRONG_OUTCOME_POLICY_V3.5.6.md",
    "UNIVERSAL_COMPUTER_USE_V3.4.6.md",
    "VERIFICATION_RESULT_DRIVEN_REPLANNING_V3.5.16.md",
    "WHATSAPP_PRE_SEND_VERIFICATION_V3.5.8.md",
    "WHATSAPP_SEARCH_STATE_RECOVERY_V3.5.9.md",
    "WHATSAPP_STARTUP_REACQUIRE_V3.5.10.md",
}

LEGACY_ROOT_DOCS = {
    'ACTION_TRUTH_SPOTIFY_V2.7.2.md',
    'ADULT_ANIME_VOICE.md',
    'ANIME_VOICE.md',
    'AUTONOMOUS_PLANNER_V3.0.0.md',
    'AUTONOMOUS_WORKFLOW_ENGINE_V3.3.0.md',
    'AUTO_APP_CONTROL_V2.9.0.md',
    'AUTO_APP_CONTROL_V2.9.0_FIX.md',
    'BOOTSTRAP_APP_LAUNCHER_V3.0.2.md',
    'BUILD_STATUS.md',
    'BUILD_STATUS_V2.1.md',
    'CLIPBOARDLESS_INPUT_V2.7.3.md',
    'CONTINUOUS_VOICE_V2.5.0.md',
    'DB_LATENCY_FIX_V2.2.2.md',
    'DESKTOP_INTERACTION_V2.7.0.md',
    'DETERMINISTIC_MEDIA_V2.7.4.md',
    'DEVICE_BRIDGE_V2.6.0.md',
    'DEVICE_CLIENTS_V2.1.1.md',
    'DEVICE_INTENT_LOCK_V2.6.2.md',
    'HUMANLIKE_PERSONALITY_V2.3.1.md',
    'LATENCY_HOTFIX_V2.2.1.md',
    'LATENCY_OPTIMIZATION_V2.2.0.md',
    'MODEL_FALLBACK_V2.1.3.md',
    'MULTI_PROVIDER_V2.4.0.md',
    'PERSONALITY_TEST_HOTFIX_V2.3.1a.md',
    'PROVIDER_STABILITY_V2.6.1.md',
    'REAL_DEVICE_RELIABILITY_V3.4.2.md',
    'RELEASE_V2.5.1.md',
    'RENDER_BOOT_FIX_V2.2.3.md',
    'REQUEST_QUEUE_BACKPRESSURE_V3.4.4.md',
    'SOCIAL_PRESENCE_V2.3.2.md',
    'SOCIAL_STREAM_HOTFIX_V2.3.3.md',
    'SPOTIFY_PHYSICAL_PLAYBACK_V2.7.7.md',
    'SPOTIFY_PLAY_BUTTON_V2.7.6.md',
    'SPOTIFY_QUICK_SEARCH_V3.4.5.md',
    'SPOTIFY_RELIABLE_CONTROL_V2.7.5.md',
    'SPOTIFY_VERIFIED_SELECTION_V2.8.1.md',
    'STREAMING_V2.3.0.md',
    'STREAM_LATENCY_GUARD_V2.7.1.md',
    'STREAM_LOCK_LIFECYCLE_V3.4.3.md',
    'TEST_ALIGNMENT_V2.3.4a.md',
    'TITLE_RATE_LIMIT_FIX_V2.3.4.md',
    'UNIVERSAL_APP_LAUNCHER_FIX.md',
    'UNIVERSAL_MEDIA_V2.8.0.md',
    'UNIVERSAL_SAFE_APP_LAUNCHER_V3.1.0.md',
    'VISUAL_COMPUTER_CONTROL_V3.2.0.md',
    'VOICE_FIX.md',
    'WAKE_ALIASES_V2.5.3.md',
    'WEB_HANDSFREE_V2.5.1.md',
    'WINDOWS_MIC_V2.1.2.md',
    'TEST_REPORT.md',
    'apply-device-client-patch.ps1',
    'apply-model-fallback-patch.ps1',
    'apply-windows-mic-patch.ps1',
    '.github/workflows/tests.yml',
}

MOVED_DOC_ROOT_FILES = {
    "BUILD_APPS.md",
    "CLOUD_ARCHITECTURE.md",
    "CLOUD_DEPLOY.md",
    "CROSS_APP_WORKFLOW_MEMORY_V3.6.0.md",
    "HUMAN_SPEECH.md",
    "OMNIPARSER_IRAS_SETUP.md",
    "RENDER_SUPABASE_DEPLOY.md",
    "ROLEPLAY_GUIDE.md",
    "SELF_ADAPTING_PERSONALITY.md",
}

OBSOLETE_RUNNERS = {
    "run-spotify-v35-validation.ps1",
    "run-v3511-recovery-validation.ps1",
    "run-v3512-route-validation.ps1",
    "run-v3513-orchestration-validation.ps1",
    "run-v3514-fresh-action-validation.ps1",
    "run-v3515-execution-validation.ps1",
    "run-v3516-replanning-validation.ps1",
    "run-v3517-material-replan-validation.ps1",
    "run-v3518-planner-history-validation.ps1",
    "run-v3519-adaptive-recovery-validation.ps1",
    "run-v3520-recovery-learning-validation.ps1",
    "run-v3521-contextual-learning-validation.ps1",
    "run-v3522-recovery-calibration-validation.ps1",
    "run-whatsapp-v35-validation.ps1",
    "run-whatsapp-darkness-v357-validation.ps1",
    "run-whatsapp-darkness-v358-validation.ps1",
    "run-whatsapp-darkness-v359-validation.ps1",
    "run-whatsapp-darkness-v3510-validation.ps1",
}

DANGEROUS_ONE_OFF_VALIDATORS = {
    "scripts/validate_whatsapp_closed_loop_v35.py",
    "scripts/validate_whatsapp_darkness_send_v357.py",
    "scripts/validate_whatsapp_darkness_send_v358.py",
    "scripts/validate_whatsapp_darkness_send_v359.py",
    "scripts/validate_whatsapp_darkness_send_v3510.py",
}

REQUIRED = {
    ".gitignore",
    "ARCHITECTURE.md",
    "README.md",
    "pyproject.toml",
    "run-v360-validation.ps1",
    "run-v360-real-device-smoke.ps1",
    "scripts/validate_v360_integrated.py",
    "scripts/validate_v360_real_device.py",
    "src/iras/__init__.py",
    "tests/__init__.py",
    "tests/test_cross_app_workflow_memory_v360.py",
}

SECRET_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
)
TEXT_SUFFIXES = {".py", ".ps1", ".md", ".toml", ".yml", ".yaml", ".json", ".html", ".java", ".xml", ".gradle", ".txt"}


def _git_check(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None


def local_env_release_problem(root: Path = ROOT) -> str | None:
    """Allow a developer's ignored .env while rejecting release leakage.

    The validator runs inside the real checkout as well as CI. A local .env is
    expected in the former and must survive ZIP extraction/updates. What matters
    for release hygiene is that it is not tracked and remains ignored. If this is
    not a Git checkout, any .env is treated as packaged release content.
    """
    env_path = root / ".env"
    if not env_path.exists():
        return None

    repo = _git_check(root, "rev-parse", "--is-inside-work-tree")
    if repo is None or repo.returncode != 0 or repo.stdout.strip().lower() != "true":
        return "local .env must not be part of a packaged release tree"

    tracked = _git_check(root, "ls-files", "--error-unmatch", "--", ".env")
    if tracked is not None and tracked.returncode == 0:
        return "local .env is tracked by git"

    ignored = _git_check(root, "check-ignore", "-q", "--", ".env")
    if ignored is None or ignored.returncode != 0:
        return "local .env exists but is not ignored by git"

    return None


def main() -> None:
    problems: list[str] = []

    for rel in sorted(LEGACY_ROOT_DOCS | OBSOLETE_ROOT_FILES | MOVED_DOC_ROOT_FILES | OBSOLETE_RUNNERS | DANGEROUS_ONE_OFF_VALIDATORS):
        if (ROOT / rel).exists():
            problems.append(f"obsolete artifact still present: {rel}")

    if (ROOT / "docs" / "history").exists():
        problems.append("obsolete docs/history directory still present")

    for rel in sorted(REQUIRED):
        if not (ROOT / rel).exists():
            problems.append(f"required release file missing: {rel}")

    env_problem = local_env_release_problem(ROOT)
    if env_problem:
        problems.append(env_problem)

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        parts = set(path.parts)
        if {".venv", "venv", "node_modules"} & parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"possible committed secret pattern in {path.relative_to(ROOT)}")
                break

    if problems:
        print("=== IRAS v3.6.0 CLEAN TREE VALIDATION ===")
        for item in problems:
            print("FAIL:", item)
        raise SystemExit(1)

    print("=== IRAS v3.6.0 CLEAN TREE VALIDATION ===")
    print("LEGACY ROOT DOCS PRESENT: False")
    print("OBSOLETE ROOT RELEASE NOTES PRESENT: False")
    print("DUPLICATE ROOT DOCS PRESENT: False")
    print("OBSOLETE HISTORICAL RUNNERS PRESENT: False")
    print("REAL-MESSAGE ONE-OFF VALIDATORS PRESENT: False")
    print("DOCS HISTORY PRESENT: False")
    print(f"LOCAL .ENV PRESENT: {(ROOT / '.env').exists()}")
    print(f"LOCAL .ENV RELEASE SAFE: {local_env_release_problem(ROOT) is None}")
    print("OBVIOUS SECRET PATTERNS FOUND: False")
    print("CURRENT RELEASE FILES PRESENT: True")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
