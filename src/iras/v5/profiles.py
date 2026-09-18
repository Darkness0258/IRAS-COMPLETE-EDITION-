from __future__ import annotations
import json
from typing import Any
from .common import SQLiteDB,new_id,utc_now

class ProfileStore:
    def __init__(self,db:SQLiteDB):
        self.db=db; self.db.execute("""CREATE TABLE IF NOT EXISTS v5_profiles(
          profile_id TEXT PRIMARY KEY,name TEXT NOT NULL,permissions_json TEXT NOT NULL,
          memory_namespace TEXT NOT NULL,created_at TEXT NOT NULL,enabled INTEGER NOT NULL)""")
    def create(self,name:str,permissions:list[str]|None=None)->dict[str,Any]:
        pid=new_id("usr_"); ns="profile:"+pid; self.db.execute("INSERT INTO v5_profiles VALUES(?,?,?,?,?,1)",(pid,name[:120],json.dumps(permissions or ["read"]),ns,utc_now())); return self.get(pid)
    def get(self,pid:str):
        r=self.db.execute("SELECT * FROM v5_profiles WHERE profile_id=?",(pid,),fetch="one")
        if r:r["permissions"]=json.loads(r.pop("permissions_json"));r["enabled"]=bool(r["enabled"])
        return r
    def list(self):
        rows=self.db.execute("SELECT profile_id FROM v5_profiles ORDER BY created_at",fetch="all") or []; return [self.get(r["profile_id"]) for r in rows]
    def update(self,pid:str,*,name:str|None=None,permissions:list[str]|None=None,enabled:bool|None=None):
        r=self.get(pid)
        if not r:raise KeyError(pid)
        self.db.execute("UPDATE v5_profiles SET name=?,permissions_json=?,enabled=? WHERE profile_id=?",((name or r["name"])[:120],json.dumps(permissions if permissions is not None else r["permissions"]),int(r["enabled"] if enabled is None else enabled),pid));return self.get(pid)
    def upsert_snapshot(self,snapshot:dict[str,Any])->dict[str,Any]:
        pid=str(snapshot.get("profile_id") or "").strip()
        if not pid: raise ValueError("profile_id is required")
        name=str(snapshot.get("name") or "Profile")[:120]
        permissions=[str(x)[:80] for x in list(snapshot.get("permissions") or ["read"])]
        namespace=str(snapshot.get("memory_namespace") or ("profile:"+pid))[:200]
        created_at=str(snapshot.get("created_at") or utc_now())
        enabled=bool(snapshot.get("enabled",True))
        self.db.execute("""INSERT INTO v5_profiles(profile_id,name,permissions_json,memory_namespace,created_at,enabled)
          VALUES(?,?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET
          name=excluded.name,permissions_json=excluded.permissions_json,memory_namespace=excluded.memory_namespace,
          enabled=excluded.enabled""",(pid,name,json.dumps(permissions),namespace,created_at,int(enabled)))
        return self.get(pid)

    def allows(self,pid:str,permission:str)->bool:
        r=self.get(pid); return bool(r and r["enabled"] and ("*" in r["permissions"] or permission in r["permissions"]))
