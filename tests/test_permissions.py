from iras.models import PermissionLevel,ApprovalRequest
from iras.security.permissions import PermissionEngine,PermissionDenied

def test_auto_safe(): PermissionEngine(PermissionLevel.SAFE_ACTION).authorize(ApprovalRequest('x',PermissionLevel.SAFE_ACTION,{},'x'))
def test_elevated_denied_without_callback():
    try: PermissionEngine(PermissionLevel.SAFE_ACTION).authorize(ApprovalRequest('x',PermissionLevel.SYSTEM_ACTION,{},'x'))
    except PermissionDenied:return
    assert False
def test_elevated_callback(): PermissionEngine(PermissionLevel.SAFE_ACTION,lambda r:True).authorize(ApprovalRequest('x',PermissionLevel.SYSTEM_ACTION,{},'x'))
def test_critical_always_confirms():
    e=PermissionEngine(PermissionLevel.CRITICAL,None,True)
    try:e.authorize(ApprovalRequest('x',PermissionLevel.CRITICAL,{},'x'))
    except PermissionDenied:return
    assert False
