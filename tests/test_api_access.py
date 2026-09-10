from iras.tools.api_access import classify
from iras.models import PermissionLevel

def test_api_permissions():
    assert classify({'method':'GET'})==PermissionLevel.READ
    assert classify({'method':'POST'})==PermissionLevel.SYSTEM_ACTION
    assert classify({'method':'DELETE'})==PermissionLevel.CRITICAL
