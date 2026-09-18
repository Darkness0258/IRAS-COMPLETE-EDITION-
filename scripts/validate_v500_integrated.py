from __future__ import annotations

import json
import re
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.remote_protocol import REMOTE_PROTOCOL_VERSION
from iras.tools.v5 import make_tools
from iras.v5.encrypted_sync import EncryptedSync
from iras.v5.runtime import FEATURES, V5Runtime


REQUIRED_TOOL_SURFACE = {
    # control / migrations / goals
    "v5_status", "v5_feature_status", "v5_migration_status", "v5_goal_add", "v5_goal_tree",
    # autonomy + monitoring
    "v5_schedule_add", "v5_schedule_cancel", "v5_monitor_add", "v5_monitor_check_all",
    # memory / knowledge / coding / workflows
    "v5_memory_search", "v5_project_graph_build", "v5_workspace_create", "v5_workspace_commit",
    "v5_workspace_merge", "v5_workflow_replay",
    # notifications / companion / connectors / vault
    "v5_notify", "v5_mobile_request_approval", "v5_connector_configure", "v5_connector_authorize",
    "v5_connector_connect", "v5_connector_invoke", "v5_vault_reference",
    # browser / voice / perception
    "v5_browser_start", "v5_browser_navigate", "v5_browser_submit", "v5_voice_status",
    "v5_voice_barge_in", "v5_visual_fuse",
    # artifacts / sandbox / learning / recovery / research
    "v5_artifact_document", "v5_artifact_pdf", "v5_artifact_spreadsheet", "v5_artifact_presentation",
    "v5_sandbox_python", "v5_capability_propose", "v5_capability_install", "v5_recovery_stats",
    "v5_research_start", "v5_debate_start", "v5_resource_route",
    # skills / profiles / sync / home / rollback / audit
    "v5_skill_verify", "v5_skill_install", "v5_profile_create", "v5_profile_sync_export",
    "v5_profile_sync_import", "v5_home_status", "v5_home_command", "v5_rollback_restore",
    "v5_audit_rows",
}


def main() -> None:
    print("=== IRAS v5.0 RC3 COMPLETE OPERATING LAYER INTEGRATED VALIDATION ===")
    assert __version__ == "5.0.0-rc3"
    assert REMOTE_PROTOCOL_VERSION == 1
    assert len(FEATURES) == 33
    assert len(set(FEATURES)) == 33

    with tempfile.TemporaryDirectory() as td:
        os.environ["IRAS_VAULT_MASTER_KEY"] = EncryptedSync.new_key()
        rt = V5Runtime(td)
        status = rt.status()
        assert status["feature_count"] == 33
        assert {x["feature"] for x in status["feature_status"]} == set(FEATURES)
        assert status["remote_protocol"] == 1
        assert status["migrations"]["complete"] is True

        tools = make_tools(rt)
        names = {tool.name for tool in tools}
        assert len(names) >= 100
        assert REQUIRED_TOOL_SURFACE <= names

        schedule = rt.scheduler.add(name="brief", prompt="brief me", interval_seconds=3600)
        assert rt.scheduler.get(schedule["job_id"])["enabled"] is True
        goal = rt.goals.add("Ship IRAS v5", level="goal")
        assert rt.goals.get(goal["item_id"])["title"] == "Ship IRAS v5"
        mid = rt.semantic_memory.remember("provider recovery knowledge", namespace="iras")
        assert rt.semantic_memory.search("provider recovery", namespace="iras")[0]["memory_id"] == mid
        key = EncryptedSync.new_key()
        blob = EncryptedSync.encrypt({"ok": True}, key)
        assert EncryptedSync.decrypt(blob, key)["ok"] is True

    cloud = (ROOT / "src/iras/cloud_api.py").read_text(encoding="utf-8")
    web = (ROOT / "clients/web/index.html").read_text(encoding="utf-8")
    boot = (ROOT / "src/iras/cloud_bootstrap.py").read_text(encoding="utf-8")
    local_boot = (ROOT / "src/iras/bootstrap.py").read_text(encoding="utf-8")
    android = (ROOT / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java").read_text(encoding="utf-8")
    android_gradle = (ROOT / "clients/android/app/build.gradle").read_text(encoding="utf-8")

    for endpoint in (
        "/v1/v5/status", "/v1/v5/features", "/v1/v5/migrations", "/v1/v5/schedules",
        "/v1/v5/goals", "/v1/v5/mobile/register", "/v1/v5/mobile/{mobile_id}/heartbeat",
        "/v1/v5/mobile/{mobile_id}/events", "/v1/v5/artifacts", "/v1/v5/recovery",
        "/v1/v5/capabilities", "/v1/v5/home-adapters",
    ):
        assert endpoint in cloud
    assert "IRAS Autonomy Control Center" in web and "Feature matrix" in web
    assert "v5_tools(runtime.v5)" in boot
    assert "OrchestrationManager" in local_boot and "PermissionLevel.READ" in local_boot
    assert "/v1/v5/mobile/register" in android and "showCompanionApproval" in android
    assert re.search(r"versionName\s+['\"]5\.0\.0-rc3['\"]", android_gradle)

    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert ".[cloud,browser,artifacts,crypto]" in docker
    assert "playwright install --with-deps chromium" in docker
    assert "IRAS_VAULT_MASTER_KEY" in render and "IRAS_V5_SCHEDULER_ENABLED" in render

    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "IRAS v5.0 RC3" in ci and r".\run-v500-validation.ps1" in ci

    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    launcher = (ROOT / "run-iras.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    omni_setup = (ROOT / "setup-omniparser.ps1").read_text(encoding="utf-8")
    omni_runtime = (ROOT / "src/iras/vision/omniparser_runtime.py").read_text(encoding="utf-8")
    omni_bridge = (ROOT / "src/iras/vision/omniparser_bridge_server.py").read_text(encoding="utf-8")
    assert "IRAS_OMNIPARSER_EAGER_START=true" in env
    assert "IRAS_OMNIPARSER_WATCHDOG=true" in env
    assert "IRAS_OMNIPARSER_ALLOW_EXTERNAL=false" in env
    assert "--vision-start" in launcher and "setup-omniparser.ps1 -Repair" in launcher
    assert "Reusing existing IRAS virtual environment" in installer
    assert "microsoft/OmniParser.git" in omni_setup and "icon_detect_v3/model.pt" in omni_setup
    assert "Preserving unmanaged OmniParser tree" in omni_setup and "-iras-managed" in omni_setup
    assert "allow_external_enabled" in omni_runtime and "external_unmanaged" in omni_runtime
    assert "start_supervisor" in omni_runtime and "def restart(" in omni_runtime and "def stop(" in omni_runtime
    assert "X-IRAS-Control-Token" in omni_bridge and "IRAS_OMNIPARSER_DISABLE_PADDLE" in omni_bridge

    skills = (ROOT / "src/iras/v5/skills.py").read_text(encoding="utf-8")
    connectors = (ROOT / "src/iras/v5/connectors.py").read_text(encoding="utf-8")
    adapters = (ROOT / "src/iras/v5/connector_adapters.py").read_text(encoding="utf-8")
    migrations = (ROOT / "src/iras/v5/migrations.py").read_text(encoding="utf-8")
    assert "iras-skill-ed25519-sha256-v2" in skills and "file_hashes" in skills
    assert "expired" in connectors and "authorize" in connectors
    assert "build_builtin_adapter" in adapters and "GitHubAdapter" in adapters and "SupabaseAdapter" in adapters
    assert "v5_schema_migrations" in migrations

    manifest = json.loads((ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "5.0.0-rc3"
    assert manifest["remote_protocol"] == 1
    assert manifest["feature_count"] == 33
    assert manifest["managed_omniparser"]["default_eager_start"] is True
    assert manifest["managed_omniparser"]["preserves_unmanaged_legacy_tree"] is True
    assert manifest["cloud_model_acceptance_used"] is False
    assert (ROOT / "RC3-FEATURE-MATRIX.md").is_file()
    assert (ROOT / "scripts/package_v500_rc3.py").is_file()

    for feature in FEATURES:
        print(f"{feature.upper()}: True")
    print("V5 MODEL-FACING TOOL COUNT:", len(names))
    print("REMOTE PROTOCOL VERSION:", REMOTE_PROTOCOL_VERSION)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
