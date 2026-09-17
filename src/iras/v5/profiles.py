from __future__ import annotations
import json
from typing import Any
from .common import SQLiteDB,new_id,utc_now


class ProfileStore:
    def __init__(self,db:SQLiteDB):
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_profiles(
          profile_id TEXT PRIMARY KEY,name TEXT NOT NULL,permissions_json TEXT NOT NULL,
          memory_namespace TEXT NOT NULL,created_at TEXT NOT NULL,enabled INTEGER NOT NULL)""")
    def create(self,name:str,permissions:list[str]|None=None)->dict[str,Any]:
        pid=new_id("usr_"); ns="profile:"+pid
        self.db.execute("INSERT INTO v5_profiles VALUES(?,?,?,?,?,1)",(pid,name[:120],json.dumps(permissions or ["read"]),ns,utc_now()))
        return self.get(pid)
    def get(self,pid:str):
        row=self.db.execute("SELECT * FROM v5_profiles WHERE profile_id=?",(pid,),fetch="one")
        if row: row["permissions"]=json.loads(row.pop("permissions_json")); row["enabled"]=bool(row["enabled"])
        return row
    def list(self):
        rows=self.db.execute("SELECT profile_id FROM v5_profiles ORDER BY created_at",fetch="all") or []
        return [self.get(r["profile_id"]) for r in rows]
