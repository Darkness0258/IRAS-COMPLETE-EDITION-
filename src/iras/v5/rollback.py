from __future__ import annotations
import json
from pathlib import Path
import subprocess
from typing import Any
from .common import SQLiteDB,new_id,utc_now

class RollbackTimeline:
    def __init__(self,db:SQLiteDB):
        self.db=db; self.db.execute("""CREATE TABLE IF NOT EXISTS v5_rollback_timeline(
          checkpoint_id TEXT PRIMARY KEY,project_root TEXT NOT NULL,git_head TEXT NOT NULL,
          status_porcelain TEXT NOT NULL,label TEXT NOT NULL,created_at TEXT NOT NULL,metadata_json TEXT NOT NULL)""")
    @staticmethod
    def _git(root:Path,*args:str)->str:
        p=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,shell=False,timeout=60)
        if p.returncode!=0: raise RuntimeError(p.stderr.strip() or p.stdout.strip()); return p.stdout.strip()
        return p.stdout.strip()
    def capture(self,project_root:str|Path,label:str="checkpoint",metadata:dict[str,Any]|None=None)->dict[str,Any]:
        root=Path(project_root).resolve(); head=self._git(root,"rev-parse","HEAD"); status=self._git(root,"status","--porcelain"); cid=new_id("rb_"); self.db.execute("INSERT INTO v5_rollback_timeline VALUES(?,?,?,?,?,?,?)",(cid,str(root),head,status,label[:160],utc_now(),json.dumps(metadata or {},ensure_ascii=False))); return self.get(cid)
    def get(self,cid:str):
        r=self.db.execute("SELECT * FROM v5_rollback_timeline WHERE checkpoint_id=?",(cid,),fetch="one")
        if r:r["metadata"]=json.loads(r.pop("metadata_json"))
        return r
    def list(self,project_root:str|Path|None=None,limit:int=50):
        if project_root: rows=self.db.execute("SELECT checkpoint_id FROM v5_rollback_timeline WHERE project_root=? ORDER BY created_at DESC LIMIT ?",(str(Path(project_root).resolve()),limit),fetch="all") or []
        else: rows=self.db.execute("SELECT checkpoint_id FROM v5_rollback_timeline ORDER BY created_at DESC LIMIT ?",(limit,),fetch="all") or []
        return [self.get(r["checkpoint_id"]) for r in rows]
    def preview(self,cid:str)->dict[str,Any]:
        row=self.get(cid)
        if not row:raise KeyError(cid)
        root=Path(row["project_root"]); current=self._git(root,"rev-parse","HEAD"); diff=self._git(root,"diff","--stat",row["git_head"],"--") if current==row["git_head"] else "HEAD changed; automatic restore would be refused."
        return {"checkpoint":row,"current_head":current,"head_matches":current==row["git_head"],"working_tree":self._git(root,"status","--porcelain"),"diff_stat":diff}
    def restore_tracked(self,cid:str,*,approved:bool=False)->dict[str,Any]:
        if not approved:raise PermissionError("Rollback requires explicit approval.")
        row=self.get(cid)
        if not row:raise KeyError(cid)
        root=Path(row["project_root"]); current=self._git(root,"rev-parse","HEAD")
        if current!=row["git_head"]:raise RuntimeError("HEAD changed since checkpoint; refusing automatic restore.")
        self._git(root,"restore","--source",row["git_head"],"--staged","--worktree","--","."); return {"restored":True,"checkpoint_id":cid,"head":current,"untracked_preserved":True}
