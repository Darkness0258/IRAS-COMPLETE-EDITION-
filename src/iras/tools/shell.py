from __future__ import annotations
import subprocess,re,os
from iras.models import PermissionLevel
from iras.tools.base import Tool

CRITICAL=[r'\bformat\b',r'\bdiskpart\b',r'\bbcdedit\b',r'\breg\s+delete\b',r'\bshutdown\b',r'\brm\s+-rf\b',r'\bdel\s+/[sfq]',r'\brmdir\s+/s',r'remove-item.+-recurse',r'git\s+push.+--force',r'git\s+reset\s+--hard',r'git\s+clean\s+-[a-z]*f']
def classify(a):
    c=a.get('command','').lower()
    return PermissionLevel.CRITICAL if any(re.search(p,c,re.I) for p in CRITICAL) else PermissionLevel.SYSTEM_ACTION

def run_shell(command,cwd=None,timeout=60):
    cp=subprocess.run(command,cwd=str(cwd) if cwd else None,shell=True,capture_output=True,text=True,timeout=max(1,min(timeout,600)),errors='replace')
    return {'returncode':cp.returncode,'stdout':cp.stdout[-30000:],'stderr':cp.stderr[-30000:],'cwd':str(cwd or os.getcwd())}

TOOLS=[Tool('run_shell','Run a shell/PowerShell command on the local authorized computer. Elevated approval is required; destructive patterns are critical.',{'type':'object','properties':{'command':{'type':'string'},'cwd':{'type':'string'},'timeout':{'type':'integer'}},'required':['command']},run_shell,PermissionLevel.SYSTEM_ACTION,classify)]
