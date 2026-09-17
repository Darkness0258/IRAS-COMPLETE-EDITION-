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
    def add(self,title:str,*,level:str="goal",parent_id:str|None=None,metadata:dict[str,Any]|None=None)->dict[str,Any]:
        if level not in self.LEVELS: raise ValueError("Invalid goal level")
        if parent_id:
            parent=self.get(parent_id)
            if not parent: raise KeyError(parent_id)
            if self.LEVELS.index(level)<=self.LEVELS.index(parent["level"]): raise ValueError("Child goal level must be below parent level")
        iid=new_id("goal_"); now=utc_now()
        self.db.execute("INSERT INTO v5_goals VALUES(?,?,?,?,?,?,?,?,?)",(iid,parent_id,level,title[:240],"planned",0.0,json.dumps(metadata or {},ensure_ascii=False),now,now))
        return self.get(iid)
    def get(self,iid:str):
        row=self.db.execute("SELECT * FROM v5_goals WHERE item_id=?",(iid,),fetch="one")
        if row: row["metadata"]=json.loads(row.pop("metadata_json"))
        return row
    def update(self,iid:str,*,status:str|None=None,progress:float|None=None)->dict[str,Any]:
        row=self.get(iid)
        if not row: raise KeyError(iid)
        status=status or row["status"]; progress=row["progress"] if progress is None else max(0,min(1,float(progress)))
        self.db.execute("UPDATE v5_goals SET status=?,progress=?,updated_at=? WHERE item_id=?",(status,progress,utc_now(),iid)); return self.get(iid)
    def children(self,iid:str):
        rows=self.db.execute("SELECT item_id FROM v5_goals WHERE parent_id=? ORDER BY created_at",(iid,),fetch="all") or []
        return [self.get(r["item_id"]) for r in rows]
    def tree(self,root_id:str)->dict[str,Any]:
        root=self.get(root_id)
        if not root: raise KeyError(root_id)
        return {**root,"children":[self.tree(c["item_id"]) for c in self.children(root_id)]}
