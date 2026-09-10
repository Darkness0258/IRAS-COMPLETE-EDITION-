from iras.tools.shell import classify
from iras.tools.git import classify as gc
from iras.models import PermissionLevel

def test_shell_classification(): assert classify({'command':'whoami'})==PermissionLevel.SYSTEM_ACTION; assert classify({'command':'git reset --hard HEAD'})==PermissionLevel.CRITICAL
def test_git_classification(): assert gc({'arguments':['status']})==PermissionLevel.READ; assert gc({'arguments':['push','--force']})==PermissionLevel.CRITICAL
