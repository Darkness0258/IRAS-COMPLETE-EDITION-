from __future__ import annotations
from datetime import datetime,timezone,timedelta
class AutomationStore:
    def __init__(self,memory): self.m=memory
    def add(self,next_run,prompt,interval_seconds=None):
        with self.m._lock,self.m._conn() as c:
            cur=c.execute('INSERT INTO schedules(created,next_run,interval_seconds,prompt,enabled) VALUES(?,?,?,?,1)',(self.m._now(),next_run,interval_seconds,prompt)); return cur.lastrowid
    def list(self):
        with self.m._lock,self.m._conn() as c: return [dict(r) for r in c.execute('SELECT * FROM schedules ORDER BY next_run').fetchall()]
    def cancel(self,id):
        with self.m._lock,self.m._conn() as c: c.execute('UPDATE schedules SET enabled=0 WHERE id=?',(id,)); return {'cancelled':id}
    def due(self,now=None):
        now=now or datetime.now(timezone.utc).isoformat()
        with self.m._lock,self.m._conn() as c: return [dict(r) for r in c.execute('SELECT * FROM schedules WHERE enabled=1 AND next_run<=? ORDER BY next_run',(now,)).fetchall()]
    def finish(self,row,result):
        with self.m._lock,self.m._conn() as c:
            if row['interval_seconds']:
                nxt=(datetime.now(timezone.utc)+timedelta(seconds=row['interval_seconds'])).isoformat(); c.execute('UPDATE schedules SET next_run=?,last_result=? WHERE id=?',(nxt,result,row['id']))
            else: c.execute('UPDATE schedules SET enabled=0,last_result=? WHERE id=?',(result,row['id']))
