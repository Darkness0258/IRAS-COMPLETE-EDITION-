from __future__ import annotations
import subprocess,re
from iras.models import PermissionLevel
from iras.tools.base import Tool

def _git(repo,args):
    cp=subprocess.run(['git',*args],cwd=repo,capture_output=True,text=True,timeout=120,errors='replace'); return {'returncode':cp.returncode,'stdout':cp.stdout[-30000:],'stderr':cp.stderr[-30000:]}
def git_status(repo='.'): return _git(repo,['status','--short','--branch'])
def git_log(repo='.',limit=10): return _git(repo,['log','--oneline','--decorate',f'-{min(max(int(limit),1),100)}'])
def git_diff(repo='.',staged=False): return _git(repo,['diff',*(['--cached'] if staged else [])])
def git_command(repo,arguments): return _git(repo,arguments)
def classify(a):
    x=' '.join(a.get('arguments',[])).lower()
    if re.search(r'\b(push\b.*--force|reset\s+--hard|clean\s+-[a-z]*f|rebase\b|filter-repo|branch\s+-d)',x): return PermissionLevel.CRITICAL
    if x.startswith(('push','commit','merge','checkout','switch','restore','reset','clean','tag','branch','pull','fetch','add','rm','mv')): return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.READ
TOOLS=[
 Tool('git_status','Show repository status.',{'type':'object','properties':{'repo':{'type':'string'}},'required':['repo']},git_status,PermissionLevel.READ),
 Tool('git_log','Show recent Git commits.',{'type':'object','properties':{'repo':{'type':'string'},'limit':{'type':'integer'}},'required':['repo']},git_log,PermissionLevel.READ),
 Tool('git_diff','Show Git changes.',{'type':'object','properties':{'repo':{'type':'string'},'staged':{'type':'boolean'}},'required':['repo']},git_diff,PermissionLevel.READ),
 Tool('git_command','Run Git arguments in a repository. Mutating/publishing commands are elevated dynamically.',{'type':'object','properties':{'repo':{'type':'string'},'arguments':{'type':'array','items':{'type':'string'}}},'required':['repo','arguments']},git_command,PermissionLevel.READ,classify),
]
