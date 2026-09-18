from __future__ import annotations

import json,math,re
from collections import Counter
from datetime import datetime,timezone
from typing import Any
from .common import SQLiteDB,new_id,utc_now

_TOKEN=re.compile(r"[A-Za-z0-9_\-]{2,}")
def _tokens(text:str)->Counter: return Counter(t.lower() for t in _TOKEN.findall(text))
def _similarity(a:Counter,b:Counter)->float:
    if not a or not b:return 0.0
    dot=sum(v*b.get(k,0) for k,v in a.items()); na=math.sqrt(sum(v*v for v in a.values())); nb=math.sqrt(sum(v*v for v in b.values())); return dot/(na*nb) if na and nb else 0.0

class SemanticMemory:
    """Durable searchable memory with namespaces, provenance and expiry controls."""
    def __init__(self,db:SQLiteDB):
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_semantic_memory(
            memory_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,namespace TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,metadata_json TEXT NOT NULL)""")
        for spec in ("expires_at TEXT","source TEXT","updated_at TEXT"):
            try:self.db.execute(f"ALTER TABLE v5_semantic_memory ADD COLUMN {spec}")
            except Exception:pass

    def remember(self,text:str,*,namespace:str="default",kind:str="note",metadata:dict[str,Any]|None=None,source:str="user",expires_at:str|None=None)->str:
        mid=new_id("mem_"); now=utc_now()
        self.db.execute("INSERT INTO v5_semantic_memory(memory_id,created_at,namespace,kind,text,metadata_json,expires_at,source,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(mid,now,namespace[:160],kind[:80],text[:50000],json.dumps(metadata or {},ensure_ascii=False),expires_at,source[:240],now)); return mid

    def forget(self,memory_id:str)->None:self.db.execute("DELETE FROM v5_semantic_memory WHERE memory_id=?",(memory_id,))
    def purge_expired(self)->int:
        before=len(self.db.execute("SELECT memory_id FROM v5_semantic_memory",fetch="all") or []); self.db.execute("DELETE FROM v5_semantic_memory WHERE expires_at IS NOT NULL AND expires_at<=?",(utc_now(),)); after=len(self.db.execute("SELECT memory_id FROM v5_semantic_memory",fetch="all") or []); return before-after

    def export_namespace(self,namespace:str)->list[dict[str,Any]]:
        rows=self.db.execute("SELECT * FROM v5_semantic_memory WHERE namespace=? ORDER BY created_at",(namespace,),fetch="all") or []
        for row in rows:
            row["metadata"]=json.loads(row.pop("metadata_json") or "{}")
        return rows

    def import_rows(self,rows:list[dict[str,Any]],*,namespace:str|None=None)->int:
        count=0
        for raw in rows[:10000]:
            row=dict(raw or {})
            mid=str(row.get("memory_id") or new_id("mem_"))
            ns=str(namespace or row.get("namespace") or "default")[:160]
            metadata=dict(row.get("metadata") or {})
            now=utc_now()
            self.db.execute("""INSERT INTO v5_semantic_memory(memory_id,created_at,namespace,kind,text,metadata_json,expires_at,source,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(memory_id) DO UPDATE SET
              namespace=excluded.namespace,kind=excluded.kind,text=excluded.text,metadata_json=excluded.metadata_json,
              expires_at=excluded.expires_at,source=excluded.source,updated_at=excluded.updated_at""",
              (mid,str(row.get("created_at") or now),ns,str(row.get("kind") or "note")[:80],str(row.get("text") or "")[:50000],
               json.dumps(metadata,ensure_ascii=False),row.get("expires_at"),str(row.get("source") or "sync")[:240],str(row.get("updated_at") or now)))
            count+=1
        return count

    def search(self,query:str,*,namespace:str|None=None,limit:int=10)->list[dict[str,Any]]:
        self.purge_expired()
        rows=self.db.execute("SELECT * FROM v5_semantic_memory WHERE namespace=?",(namespace,),fetch="all") if namespace else self.db.execute("SELECT * FROM v5_semantic_memory",fetch="all")
        rows=rows or []; qv=_tokens(query); ranked=[]
        for row in rows:
            score=_similarity(qv,_tokens(row["text"]+" "+row["kind"]+" "+str(row.get("source") or "")))
            if score>0:
                row["metadata"]=json.loads(row.pop("metadata_json")); row["score"]=round(score,6); ranked.append(row)
        ranked.sort(key=lambda r:(r["score"],r["created_at"]),reverse=True); return ranked[:max(1,min(int(limit),100))]
