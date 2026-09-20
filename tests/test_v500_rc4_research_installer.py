from pathlib import Path

from iras.models import PermissionLevel
from iras.remote_access import action_permission
from iras.research_agent import build_research_agent_graph, parse_research_command, research_agent_status
from iras.software_installer import (
    build_software_install_graph,
    parse_installer_command,
    software_installer_status,
)
from iras.device_bridge.executor import DEFAULT_CAPABILITIES
from iras.device_bridge.local_store import LocalDeviceBridgeStore
from iras.device_bridge.tools import make_tools
from iras.orchestration import _infer_task_blocker


def test_research_agent_has_dedicated_evidence_workflow_and_commands():
    assert parse_research_command('/research latest Windows package manager changes') == (
        'run', 'latest Windows package manager changes'
    )
    assert parse_research_command('/research status abc') == ('status', 'abc')
    graph = build_research_agent_graph('What changed?')
    assert [item['id'] for item in graph] == [
        'research-scope', 'research-discover', 'research-evidence', 'research-crosscheck', 'research-review'
    ]
    assert all(item['role'] in {'researcher', 'reviewer'} for item in graph)
    status = research_agent_status()
    assert status['mode'] == 'dedicated_web_research_agent'
    assert status['read_only'] is True
    assert {'web_search', 'http_get'}.issubset(status['tools'])


def test_installer_agent_supports_winget_and_verified_direct_url_paths():
    assert parse_installer_command('/install search vlc') == ('search', 'vlc')
    assert parse_installer_command('/install VideoLAN.VLC') == ('run', 'VideoLAN.VLC')
    assert parse_installer_command('/install url https://example.com/setup.exe') == (
        'url', 'https://example.com/setup.exe'
    )
    winget_graph = build_software_install_graph('VideoLAN.VLC')
    assert [item['id'] for item in winget_graph] == [
        'install-discover', 'install-inspect', 'install-execute', 'install-verify'
    ]
    url_graph = build_software_install_graph('https://example.com/setup.exe', direct_url=True)
    assert [item['id'] for item in url_graph] == [
        'install-research', 'install-prepare', 'install-execute', 'install-verify'
    ]
    status = software_installer_status()
    assert status['package_manager'] == 'winget'
    assert status['mode'] == 'permissioned_software_lifecycle_agent'
    assert status['direct_url']['requires_valid_authenticode'] is True
    assert status['direct_url']['cache_receipt_required'] is True


def test_installer_remote_permission_levels_fail_closed():
    assert action_permission('software_manager_status', {}) == PermissionLevel.READ
    assert action_permission('software_search', {'query': 'vlc'}) == PermissionLevel.READ
    assert action_permission('software_show', {'package_id': 'VideoLAN.VLC'}) == PermissionLevel.READ
    assert action_permission('software_list', {'package_id': 'VideoLAN.VLC'}) == PermissionLevel.READ
    assert action_permission('software_prepare_url', {'url': 'https://example.com/setup.exe'}) == PermissionLevel.SYSTEM_ACTION
    assert action_permission('software_install', {'package_id': 'VideoLAN.VLC'}) == PermissionLevel.CRITICAL
    assert action_permission('software_install_prepared', {'receipt_id': 'a' * 24}) == PermissionLevel.CRITICAL


def test_device_contract_exposes_installer_actions_without_generic_path_execution():
    expected = {
        'software_manager_status', 'software_search', 'software_show', 'software_list',
        'software_install', 'software_prepare_url', 'software_install_prepared',
    }
    assert expected.issubset(set(DEFAULT_CAPABILITIES))
    names = {tool.name for tool in make_tools(LocalDeviceBridgeStore.__new__(LocalDeviceBridgeStore))}
    assert {
        'device_software_manager_status', 'device_software_search', 'device_software_show',
        'device_software_list', 'device_software_install', 'device_software_prepare_url',
        'device_software_install_prepared',
    }.issubset(names)


def test_cloud_and_windows_client_expose_research_and_installer_surfaces():
    cloud = Path('src/iras/cloud_api.py').read_text(encoding='utf-8')
    client = Path('src/iras/cloud_client.py').read_text(encoding='utf-8')
    for route in (
        '@app.get("/v1/research-agent/status")',
        '@app.post("/v1/research-agent/runs")',
        '@app.get("/v1/software-installer/status")',
        '@app.get("/v1/software-installer/search")',
        '@app.post("/v1/software-installer/runs")',
    ):
        assert route in cloud
    assert '/research <question>' in client
    assert '/install search <software>' in client
    assert '/install url <https-url>' in client


def test_blocker_text_cannot_be_silently_treated_as_completed_work():
    assert _infer_task_blocker("I can't proceed with the login fix because remote access is locally disarmed.")
    assert _infer_task_blocker("All device tools are still blocked by the local remote guard.")
    assert _infer_task_blocker("Implemented the fix and verified 12 tests passed.") == ''


def test_clean_tree_validator_ignores_virtual_environment_but_not_source_caches():
    text = Path('scripts/validate_v500_clean_tree.py').read_text(encoding='utf-8')
    assert "ignored_roots={'.venv','.git','.tox','.nox','node_modules'}" in text
    assert "'__pycache__'" in text


def test_remote_protocol_remains_version_one():
    text = Path('src/iras/remote_protocol.py').read_text(encoding='utf-8')
    assert 'REMOTE_PROTOCOL_VERSION = 1' in text
