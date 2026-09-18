from __future__ import annotations

from dataclasses import dataclass,asdict
from pathlib import Path
import json,re,subprocess
from typing import Any
from .common import new_id,utc_now

_BRANCH=re.compile(r"[^A-Za-z0-9._/-]+")

@dataclass
class CodingWorkspace:
    workspace_id:str
    repo:str
    path:str
    branch:str
    base_ref:str
    created_at:str
    status:str="active"

class CodingWorkspaceManager:
    """Persistent isolated Git worktrees for coding agents.

    Workspaces never auto-merge. Merge execution requires an explicit approved flag
    and refuses dirty destination repositories.
    """
    def __init__(self,root:str|Path):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True); self.index=self.root/"workspaces.json"
        if not self.index.exists(): self.index.write_text("{}",encoding="utf-8")

    @staticmethod
    def _git(repo:Path,*args:str,timeout:int=60)->str:
        p=subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,timeout=timeout,shell=False)
        if p.returncode!=0: raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f"git exited {p.returncode}")
        return p.stdout.strip()

    def _load(self)->dict[str,dict[str,Any]]:
        try:return json.loads(self.index.read_text(encoding="utf-8"))
        except Exception:return {}
    def _save(self,data:dict[str,dict[str,Any]])->None:
        tmp=self.index.with_suffix(".tmp"); tmp.write_text(json.dumps(data,indent=2),encoding="utf-8"); tmp.replace(self.index)
    def _record(self,ws:CodingWorkspace)->None:
        data=self._load(); data[ws.workspace_id]=asdict(ws); self._save(data)
    def get(self,workspace_id:str)->CodingWorkspace:
        row=self._load().get(workspace_id)
        if not row: raise KeyError(workspace_id)
        return CodingWorkspace(**row)
    def list(self)->list[dict[str,Any]]: return list(self._load().values())

    def create(self,repo:str|Path,*,name:str,base_ref:str="HEAD")->CodingWorkspace:
        repo=Path(repo).resolve(); self._git(repo,"rev-parse","--git-dir")
        wid=new_id("ws_")[:15]; safe=_BRANCH.sub("-",name.strip().lower()).strip("-./") or "task"; branch=f"iras/{safe}-{wid[-6:]}"; path=self.root/wid
        self._git(repo,"worktree","add","-b",branch,str(path),base_ref,timeout=120)
        ws=CodingWorkspace(wid,str(repo),str(path),branch,base_ref,utc_now()); self._record(ws); return ws

    def status(self,workspace:CodingWorkspace|str)->str:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; return self._git(Path(ws.path),"status","--short")
    def diff(self,workspace:CodingWorkspace|str,*,staged:bool=False)->str:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; args=["diff"]+(["--cached"] if staged else [])+["--"]; return self._git(Path(ws.path),*args)
    def commits(self,workspace:CodingWorkspace|str,limit:int=20)->list[str]:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; out=self._git(Path(ws.path),"log",f"-{max(1,min(int(limit),100))}","--oneline","--decorate"); return out.splitlines() if out else []
    def run_tests(self,workspace:CodingWorkspace|str,args:list[str]|None=None,*,timeout:int=300)->dict[str,Any]:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; cmd=["python","-m","pytest",*(args or ["-q"])]
        p=subprocess.run(cmd,cwd=ws.path,capture_output=True,text=True,timeout=timeout,shell=False); return {"ok":p.returncode==0,"returncode":p.returncode,"stdout":p.stdout[-30000:],"stderr":p.stderr[-15000:]}
    def commit(self,workspace:CodingWorkspace|str,message:str)->dict[str,Any]:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace
        path=Path(ws.path)
        if not self._git(path,"status","--porcelain"):
            return {"committed":False,"reason":"clean","head":self._git(path,"rev-parse","HEAD")}
        self._git(path,"add","--all")
        self._git(path,"commit","-m",str(message or "IRAS workspace update")[:240],timeout=120)
        return {"committed":True,"head":self._git(path,"rev-parse","HEAD"),"status":self.status(ws)}

    def merge_plan(self,workspace:CodingWorkspace|str)->dict[str,str]:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; return {"repo":ws.repo,"branch":ws.branch,"command":f"git -C {ws.repo} merge --no-ff {ws.branch}"}
    def merge(self,workspace:CodingWorkspace|str,*,approved:bool=False)->dict[str,Any]:
        if not approved: raise PermissionError("Workspace merge requires explicit approval.")
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; repo=Path(ws.repo)
        if self._git(repo,"status","--porcelain"): raise RuntimeError("Destination repository is dirty; refusing merge.")
        before=self._git(repo,"rev-parse","HEAD"); self._git(repo,"merge","--no-ff",ws.branch,"-m",f"Merge IRAS workspace {ws.workspace_id}",timeout=180); after=self._git(repo,"rev-parse","HEAD")
        data=self._load(); data[ws.workspace_id]["status"]="merged"; self._save(data); return {"merged":True,"before":before,"after":after,"branch":ws.branch}
    def remove(self,workspace:CodingWorkspace|str,*,delete_branch:bool=False)->None:
        ws=self.get(workspace) if isinstance(workspace,str) else workspace; repo=Path(ws.repo)
        self._git(repo,"worktree","remove","--force",ws.path,timeout=120)
        if delete_branch:
            try:self._git(repo,"branch","-D",ws.branch)
            except Exception:pass
        data=self._load(); data[ws.workspace_id]["status"]="removed"; self._save(data)
