from pathlib import Path
import pytest
from iras.models import PermissionLevel
from iras.remote_access import action_permission
from iras.software_installer import build_software_install_graph, parse_installer_command, software_installer_status
from iras.device_bridge.executor import DEFAULT_CAPABILITIES
from iras.device_bridge.local_store import LocalDeviceBridgeStore
from iras.device_bridge.tools import make_tools
from iras.device_bridge import software_install

def test_lifecycle_command_parser_and_graphs():
    assert parse_installer_command('/install updates') == ('updates', '')
    assert parse_installer_command('/install updates VideoLAN.VLC') == ('updates', 'VideoLAN.VLC')
    assert parse_installer_command('/install update VideoLAN.VLC') == ('update', 'VideoLAN.VLC')
    assert parse_installer_command('/install update all') == ('update', 'all')
    assert parse_installer_command('/install uninstall VideoLAN.VLC') == ('uninstall', 'VideoLAN.VLC')
    assert [x['id'] for x in build_software_install_graph('VideoLAN.VLC', operation='update')] == ['update-discover','update-execute','update-verify']
    assert [x['id'] for x in build_software_install_graph('all', operation='update')] == ['update-discover','update-execute','update-verify']
    assert [x['id'] for x in build_software_install_graph('VideoLAN.VLC', operation='uninstall')] == ['uninstall-discover','uninstall-execute','uninstall-verify']
    with pytest.raises(ValueError):
        build_software_install_graph('https://example.com/setup.exe', direct_url=True, operation='update')

def test_lifecycle_permissions_and_device_contract():
    assert action_permission('software_upgrades', {}) == PermissionLevel.READ
    assert action_permission('software_upgrade', {'package_id':'VideoLAN.VLC'}) == PermissionLevel.CRITICAL
    assert action_permission('software_uninstall', {'package_id':'VideoLAN.VLC'}) == PermissionLevel.CRITICAL
    assert {'software_upgrades','software_upgrade','software_uninstall'} <= set(DEFAULT_CAPABILITIES)
    names={tool.name for tool in make_tools(LocalDeviceBridgeStore.__new__(LocalDeviceBridgeStore))}
    assert {'device_software_upgrades','device_software_upgrade','device_software_uninstall'} <= names

def test_update_all_must_be_explicit_and_targeted_update_uses_exact_id(monkeypatch):
    calls=[]
    monkeypatch.setattr(software_install,'_winget_path',lambda:r'C:\winget.exe')
    def fake_run(argv, timeout=90.0):
        calls.append(list(argv)); return {'returncode':0,'stdout':'ok','stderr':'','argv':argv[1:]}
    monkeypatch.setattr(software_install,'_run',fake_run)
    monkeypatch.setattr(software_install,'available_upgrades',lambda **kwargs:{'returncode':0,'stdout':'',**kwargs})
    monkeypatch.setattr(software_install,'list_installed',lambda **kwargs:{'returncode':0,'stdout':'VideoLAN.VLC 3.0.0',**kwargs})
    software_install.upgrade('VideoLAN.VLC')
    assert calls[0][1:5] == ['upgrade','--id','VideoLAN.VLC','--exact']
    calls.clear(); software_install.upgrade('',all_packages=True); assert '--all' in calls[0]
    with pytest.raises(ValueError): software_install.upgrade('not an id')

def test_uninstall_requires_installed_exact_id_and_verifies_absence(monkeypatch):
    monkeypatch.setattr(software_install,'_winget_path',lambda:r'C:\winget.exe')
    states=iter([{'returncode':0,'stdout':'VideoLAN.VLC 3.0.0'},{'returncode':1,'stdout':'No installed package found'}])
    monkeypatch.setattr(software_install,'list_installed',lambda **kwargs:next(states))
    seen=[]
    def fake_run(argv, timeout=90.0):
        seen.append(list(argv)); return {'returncode':0,'stdout':'Successfully uninstalled','stderr':'','argv':argv[1:]}
    monkeypatch.setattr(software_install,'_run',fake_run)
    result=software_install.uninstall('VideoLAN.VLC')
    assert result['verified_removed'] is True
    assert seen[0][1:5] == ['uninstall','--id','VideoLAN.VLC','--exact']

def test_status_and_client_document_lifecycle_commands():
    status=software_installer_status(); assert status['mode']=='permissioned_software_lifecycle_agent'
    commands=set(status['commands']); assert '/install update all' in commands; assert '/install uninstall <software-or-package-id>' in commands
    client=Path('src/iras/cloud_client.py').read_text(encoding='utf-8')
    assert '/install updates [id]' in client
    assert '/install update <software|id|all>' in client
    assert '/install uninstall <software|id>' in client

def test_remote_protocol_stays_one():
    assert 'REMOTE_PROTOCOL_VERSION = 1' in Path('src/iras/remote_protocol.py').read_text(encoding='utf-8')
