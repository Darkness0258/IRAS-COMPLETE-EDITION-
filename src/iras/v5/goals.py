from __future__ import annotations
import json
from typing import Any
from .common import SQLiteDB,new_id,utc_now

class GoalHierarchy:
    LEVELS=("goal","project","milestone","job","task")
    def __init__(self,db:SQLiteDB):
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_goals(
          item_id TEXT PRIMARY KEY,parent_id TEXT,level TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL,
          progress REAL NOT NULL,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_goal_dependencies(
          item_id TEXT NOT NULL,depends_on TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(item_id,depends_on))""")
    def add(self,title:str,*,level:str="goal",parent_id:str|None=None,metadata:dict[str,Any]|None=None)->dict[str,Any]:
        if level not in self.LEVELS: raise ValueError("Invalid goal level")
        if parent_id:
            p=self.get(parent_id)
            if not p: raise KeyError(parent_id)
            if self.LEVELS.index(level)<=self.LEVELS.index(p["level"]): raise ValueError("Child goal level must be below parent level")
        iid=new_id("goal_"); now=utc_now(); self.db.execute("INSERT INTO v5_goals VALUES(?,?,?,?,?,?,?,?,?)",(iid,parent_id,level,title[:240],"planned",0.0,json.dumps(metadata or {},ensure_ascii=False),now,now)); return self.get(iid)
    def get(self,iid:str):
        r=self.db.execute("SELECT * FROM v5_goals WHERE item_id=?",(iid,),fetch="one")
        if r:
            r["metadata"]=json.loads(r.pop("metadata_json")); r["dependencies"]=[x["depends_on"] for x in (self.db.execute("SELECT depends_on FROM v5_goal_dependencies WHERE item_id=?",(iid,),fetch="all") or [])]
        return r
    def add_dependency(self,item_id:str,depends_on:str)->None:
        if item_id==depends_on: raise ValueError("Goal item cannot depend on itself")
        if not self.get(item_id) or not self.get(depends_on): raise KeyError("Unknown goal item")
        self.db.execute("INSERT INTO v5_goal_dependencies(item_id,depends_on,created_at) VALUES(?,?,?) ON CONFLICT(item_id,depends_on) DO NOTHING",(item_id,depends_on,utc_now()))
    def ready(self,item_id:str)->bool:
        deps=self.get(item_id)["dependencies"]
        return all((self.get(d) or {}).get("status") in {"done","completed","succeeded"} for d in deps)
    def update(self,iid:str,*,status:str|None=None,progress:float|None=None)->dict[str,Any]:
        row=self.get(iid)
        if not row: raise KeyError(iid)
        status=status or row["status"]; progress=row["progress"] if progress is None else max(0,min(1,float(progress)))
        self.db.execute("UPDATE v5_goals SET status=?,progress=?,updated_at=? WHERE item_id=?",(status,progress,utc_now(),iid)); self._rollup(row.get("parent_id")); return self.get(iid)
    def _rollup(self,parent_id:str|None)->None:
        if not parent_id:return
        children=self.children(parent_id)
        if children:
            progress=sum(float(c["progress"]) for c in children)/len(children); done=all(c["status"] in {"done","completed","succeeded"} for c in children); status="completed" if done else "active"
            self.db.execute("UPDATE v5_goals SET progress=?,status=?,updated_at=? WHERE item_id=?",(progress,status,utc_now(),parent_id))
            p=self.get(parent_id); self._rollup(p.get("parent_id") if p else None)
    def children(self,iid:str):
        rows=self.db.execute("SELECT item_id FROM v5_goals WHERE parent_id=? ORDER BY created_at",(iid,),fetch="all") or []; return [self.get(r["item_id"]) for r in rows]
    def tree(self,root_id:str)->dict[str,Any]:
        root=self.get(root_id)
        if not root: raise KeyError(root_id)
        return {**root,"children":[self.tree(c["item_id"]) for c in self.children(root_id)]}
    def next_actions(self,limit:int=20)->list[dict[str,Any]]:
        rows=self.db.execute("SELECT item_id FROM v5_goals WHERE level IN ('job','task') AND status IN ('planned','active') ORDER BY created_at LIMIT ?",(max(1,min(int(limit),100)),),fetch="all") or []
        return [self.get(r["item_id"]) for r in rows if self.ready(r["item_id"])]
