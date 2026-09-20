from __future__ import annotations

import base64
from pathlib import Path

import pytest

from iras.v5.encrypted_sync import EncryptedSync
from iras.v5.runtime import V5Runtime, FEATURES
from iras.v5.connectors import FixtureConnectorAdapter
from iras.v5.skills import SkillManifest, SkillMarketplace
from iras.tools.v5 import make_tools


class DummyOrchestrator:
    def submit_objective(self, objective, context=None, requester_device="test"):
        return {"run_id": "run_test", "objective": objective, "context": context or {}, "requester_device": requester_device}


def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_VAULT_MASTER_KEY", EncryptedSync.new_key())
    return V5Runtime(tmp_path / "v5", orchestration_manager=DummyOrchestrator())


def test_every_rc3_feature_has_operating_surface(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    names = {tool.name for tool in make_tools(rt)}
    assert len(FEATURES) == 36
    required = {
        "v5_status", "v5_feature_status", "v5_migration_status",
        "v5_schedule_add", "v5_monitor_add", "v5_visual_fuse", "v5_browser_navigate",
        "v5_workflow_replay", "v5_memory_search", "v5_project_graph_build",
        "v5_workspace_create", "v5_recovery_stats", "v5_capability_propose",
        "v5_connector_configure", "v5_connector_authorize", "v5_connector_connect", "v5_connector_invoke",
        "v5_voice_status", "v5_mobile_request_approval", "v5_notification_list",
        "v5_artifact_document", "v5_vault_reference", "v5_sandbox_python",
        "v5_research_start", "v5_debate_start", "v5_resource_route",
        "v5_rollback_capture", "v5_audit_summary", "v5_skill_verify",
        "v5_home_status", "v5_profile_create", "v5_profile_sync_export", "v5_goal_add",
    }
    assert required <= names
    status = rt.status()
    assert status["feature_count"] == len(FEATURES)
    assert {row["feature"] for row in status["feature_status"]} == set(FEATURES)


def test_connectors_require_authorization_and_support_offline_fixture(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    rt.vault.set("github.token", "not-exposed")
    assert rt.connectors.status("github")["credentials"]["ready"] is True
    with pytest.raises(PermissionError):
        rt.connectors.invoke("github", "repos.read")
    rt.connectors.authorize("github", scopes=["repos.read"])
    adapter = FixtureConnectorAdapter({"repos.read": {"repos": ["demo"]}})
    rt.connectors.attach("github", adapter)
    assert rt.connectors.invoke("github", "repos.read") == {"repos": ["demo"]}
    assert "not-exposed" not in repr(rt.connectors.status("github"))


def test_connector_expiry_fails_closed(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    rt.vault.set("github.token", "secret")
    with pytest.raises(PermissionError):
        rt.connectors.authorize("github", expires_at="2000-01-01T00:00:00+00:00")
    assert rt.connectors.status("github")["authorization"]["state"] == "expired"


def test_signed_skill_detects_file_tampering(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    manifest = SkillManifest("integrity", "1.0.0", "test", ["READ"], "skill.py", "test")
    files = {"skill.py": "VALUE = 1\n", "README.md": "signed\n"}
    signature = private.sign(SkillMarketplace._payload(manifest, files))
    market = SkillMarketplace(tmp_path / "skills")
    target = Path(market.install(
        manifest, files,
        signature_b64=base64.b64encode(signature).decode(),
        public_key_b64=base64.b64encode(public).decode(),
        approved=True,
    ))
    assert market.verify_installed("integrity", "1.0.0")["integrity_ok"] is True
    (target / "skill.py").write_text("VALUE = 2\n", encoding="utf-8")
    check = market.verify_installed("integrity", "1.0.0")
    assert check["integrity_ok"] is False
    assert "hash_mismatch" in check["reason"]


def test_profile_encrypted_sync_round_trip(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    sync_key = EncryptedSync.new_key()
    rt.vault.set("profile.sync", sync_key)
    profile = rt.profiles.create("Hamza", ["READ"])
    rt.semantic_memory.remember("IRAS sync fact", namespace=profile["memory_namespace"], source="test")
    exported = rt.export_profile_sync(profile["profile_id"], "profile.sync")
    assert exported["bundle_base64"]
    restored = rt.import_profile_sync(exported["bundle_base64"], "profile.sync", approved=True)
    assert restored["profile"]["profile_id"] == profile["profile_id"]
    assert restored["sha256"] == exported["sha256"]


def test_migrations_and_home_adapters_are_operational(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    migration = rt.migrations.status()
    assert migration["complete"] is True
    assert len(migration["history"]) >= 3
    adapters = {row["name"] for row in rt.home_network.list()}
    assert {"http-json", "https-json"} <= adapters
    assert rt.home_network.host_allowed("127.0.0.1") is True
    assert rt.home_network.host_allowed("8.8.8.8") is False


def test_installer_preserves_unmanaged_omniparser_and_reuses_venv():
    root = Path(__file__).resolve().parents[1]
    install = (root / "install.ps1").read_text(encoding="utf-8")
    setup = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")
    assert 'Test-Path .\\.venv\\Scripts\\python.exe' in install
    assert 'Reusing existing IRAS virtual environment' in install
    assert 'Preserving unmanaged OmniParser tree' in setup
    assert '"-iras-managed"' in setup
    assert '--vision-stop' in setup
    assert 'IRAS_OMNIPARSER_URL' in setup


def test_cloud_api_has_full_android_companion_contract():
    root = Path(__file__).resolve().parents[1]
    cloud = (root / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    for route in (
        '/v1/v5/mobile/register',
        '/v1/v5/mobile/{mobile_id}/heartbeat',
        '/v1/v5/mobile/{mobile_id}/events',
        '/v1/v5/mobile/{mobile_id}/events/{event_id}/ack',
        '/v1/v5/mobile/approvals/{approval_id}',
        '/v1/v5/features', '/v1/v5/migrations', '/v1/v5/artifacts',
        '/v1/v5/recovery', '/v1/v5/capabilities', '/v1/v5/home-adapters',
    ):
        assert route in cloud


def test_android_rc3_companion_is_not_chat_only():
    root = Path(__file__).resolve().parents[1]
    java = (root / "clients" / "android" / "app" / "src" / "main" / "java" / "com" / "darkness" / "iras" / "MainActivity.java").read_text(encoding="utf-8")
    gradle = (root / "clients" / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
    manifest = (root / "clients" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert '/v1/v5/mobile/register' in java
    assert '/events?limit=50' in java
    assert '/v1/v5/mobile/approvals/' in java
    assert 'showCompanionApproval' in java
    assert 'companionPollRunnable' in java
    assert "versionName '5.0.0-rc5'" in gradle
    assert 'POST_NOTIFICATIONS' in manifest


def test_web_control_center_surfaces_full_feature_matrix():
    root = Path(__file__).resolve().parents[1]
    web = (root / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    assert '/v1/v5/features' in web
    assert '/v1/v5/artifacts' in web
    assert '/v1/v5/capabilities' in web
    assert 'Feature matrix:' in web
