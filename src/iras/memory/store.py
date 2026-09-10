from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, threading

class MemoryStore:
    def __init__(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True); self.path=path; self._lock=threading.RLock(); self._init()
    def _conn(self):
        c=sqlite3.connect(self.path, timeout=15); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with self._conn() as c:
            c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, UNIQUE(key))')
            c.execute('CREATE TABLE IF NOT EXISTS schedules(id INTEGER PRIMARY KEY, created TEXT NOT NULL, next_run TEXT NOT NULL, interval_seconds INTEGER, prompt TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_result TEXT)')
    def add_message(self,role,content):
        with self._lock,self._conn() as c: c.execute('INSERT INTO messages(ts,role,content) VALUES(?,?,?)',(self._now(),role,content))
    def recent_messages(self,limit=20):
        with self._lock,self._conn() as c:
            rows=c.execute('SELECT role,content FROM messages ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]
    def remember(self,key,value):
        with self._lock,self._conn() as c:
            c.execute('INSERT INTO facts(ts,key,value) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET ts=excluded.ts,value=excluded.value',(self._now(),key,value))
    def get_fact(self,key,default=None):
        with self._lock,self._conn() as c:
            row=c.execute('SELECT value FROM facts WHERE key=?',(key,)).fetchone()
        return row['value'] if row else default
    def search_facts(self,query,limit=10):
        q=f'%{query}%'
        with self._lock,self._conn() as c:
            rows=c.execute('SELECT key,value,ts FROM facts WHERE key LIKE ? OR value LIKE ? ORDER BY id DESC LIMIT ?',(q,q,limit)).fetchall()
        return [dict(r) for r in rows]
    def all_facts(self,limit=100):
        with self._lock,self._conn() as c: rows=c.execute('SELECT key,value,ts FROM facts ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
        return [dict(r) for r in rows]
    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
