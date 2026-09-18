from __future__ import annotations

import json
from typing import Any

from .common import SQLiteDB, new_id, utc_now


class MobileCompanionHub:
    """Persistent mobile control plane for events, approvals and device state."""

    def __init__(self, db: SQLiteDB):
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_mobile_devices(
            mobile_id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,
            created_at TEXT NOT NULL,last_seen TEXT NOT NULL,enabled INTEGER NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_mobile_events(
            event_id TEXT PRIMARY KEY,mobile_id TEXT,kind TEXT NOT NULL,payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_mobile_event_deliveries(
            event_id TEXT NOT NULL,mobile_id TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0,
            delivered_at TEXT,PRIMARY KEY(event_id,mobile_id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_mobile_approvals(
            approval_id TEXT PRIMARY KEY,mobile_id TEXT,kind TEXT NOT NULL,payload_json TEXT NOT NULL,
            status TEXT NOT NULL,created_at TEXT NOT NULL,resolved_at TEXT,resolution_note TEXT)""")

    def register(self,name:str,platform:str="android")->dict[str,Any]:
        mid=new_id("mob_"); now=utc_now()
        self.db.execute("INSERT INTO v5_mobile_devices VALUES(?,?,?,?,?,1)",(mid,name[:120],platform[:40],now,now))
        return {"mobile_id":mid,"name":name,"platform":platform,"created_at":now}

    def list_devices(self)->list[dict[str,Any]]:
        rows=self.db.execute("SELECT * FROM v5_mobile_devices ORDER BY created_at",fetch="all") or []
        for r in rows: r["enabled"]=bool(r["enabled"])
        return rows

    def heartbeat(self,mobile_id:str)->None:
        self.db.execute("UPDATE v5_mobile_devices SET last_seen=? WHERE mobile_id=?",(utc_now(),mobile_id))

    def set_enabled(self,mobile_id:str,enabled:bool)->None:
        self.db.execute("UPDATE v5_mobile_devices SET enabled=? WHERE mobile_id=?",(int(bool(enabled)),mobile_id))

    def _ensure_delivery(self,event_id:str,mobile_id:str)->None:
        self.db.execute(
            "INSERT INTO v5_mobile_event_deliveries(event_id,mobile_id,delivered,delivered_at) VALUES(?,?,0,NULL) ON CONFLICT(event_id,mobile_id) DO NOTHING",
            (event_id,mobile_id),
        )

    def _refresh_legacy_delivered(self,event_id:str)->None:
        pending=self.db.execute(
            "SELECT COUNT(*) AS n FROM v5_mobile_event_deliveries WHERE event_id=? AND delivered=0",
            (event_id,),fetch="one"
        ) or {"n":0}
        total=self.db.execute(
            "SELECT COUNT(*) AS n FROM v5_mobile_event_deliveries WHERE event_id=?",
            (event_id,),fetch="one"
        ) or {"n":0}
        if int(total["n"]) > 0 and int(pending["n"]) == 0:
            self.db.execute("UPDATE v5_mobile_events SET delivered=1 WHERE event_id=?",(event_id,))

    def push_event(self,kind:str,payload:dict[str,Any],mobile_id:str|None=None)->str:
        eid=new_id("mevt_")
        self.db.execute("INSERT INTO v5_mobile_events VALUES(?,?,?,?,?,0)",(eid,mobile_id,kind,json.dumps(payload,ensure_ascii=False),utc_now()))
        if mobile_id:
            self._ensure_delivery(eid,mobile_id)
        else:
            devices=self.db.execute("SELECT mobile_id FROM v5_mobile_devices WHERE enabled=1",fetch="all") or []
            for device in devices:
                self._ensure_delivery(eid,device["mobile_id"])
        return eid

    def pending(self,mobile_id:str,limit:int=100)->list[dict[str,Any]]:
        # Materialize delivery state for legacy/pre-registration events without
        # allowing one device's ACK to consume a broadcast for every device.
        eligible=self.db.execute(
            "SELECT event_id FROM v5_mobile_events WHERE delivered=0 AND (mobile_id IS NULL OR mobile_id=?)",
            (mobile_id,),fetch="all"
        ) or []
        for row in eligible:
            self._ensure_delivery(row["event_id"],mobile_id)
        rows=self.db.execute(
            """SELECT e.* FROM v5_mobile_events e
               JOIN v5_mobile_event_deliveries d ON d.event_id=e.event_id
               WHERE d.mobile_id=? AND d.delivered=0
               ORDER BY e.created_at LIMIT ?""",
            (mobile_id,max(1,min(int(limit),500))),fetch="all"
        ) or []
        for r in rows: r["payload"]=json.loads(r.pop("payload_json"))
        return rows

    def acknowledge(self,event_id:str,mobile_id:str|None=None)->None:
        now=utc_now()
        if mobile_id is None:
            # Backward-compatible legacy ACK: acknowledge the event everywhere.
            self.db.execute(
                "UPDATE v5_mobile_event_deliveries SET delivered=1,delivered_at=? WHERE event_id=?",
                (now,event_id),
            )
            self.db.execute("UPDATE v5_mobile_events SET delivered=1 WHERE event_id=?",(event_id,))
            return
        self._ensure_delivery(event_id,mobile_id)
        self.db.execute(
            "UPDATE v5_mobile_event_deliveries SET delivered=1,delivered_at=? WHERE event_id=? AND mobile_id=?",
            (now,event_id,mobile_id),
        )
        self._refresh_legacy_delivered(event_id)

    def request_approval(self,kind:str,payload:dict[str,Any],*,mobile_id:str|None=None)->dict[str,Any]:
        aid=new_id("mappr_"); now=utc_now()
        self.db.execute("INSERT INTO v5_mobile_approvals VALUES(?,?,?,?,?,?,?,?)",(aid,mobile_id,kind,json.dumps(payload,ensure_ascii=False),"pending",now,None,""))
        self.push_event("approval.requested",{"approval_id":aid,"kind":kind,"payload":payload},mobile_id)
        return self.get_approval(aid) or {}

    def get_approval(self,approval_id:str)->dict[str,Any]|None:
        row=self.db.execute("SELECT * FROM v5_mobile_approvals WHERE approval_id=?",(approval_id,),fetch="one")
        if row: row["payload"]=json.loads(row.pop("payload_json"))
        return row

    def resolve_approval(self,approval_id:str,*,approved:bool,note:str="")->dict[str,Any]:
        row=self.get_approval(approval_id)
        if not row: raise KeyError(approval_id)
        if row["status"]!="pending": return row
        status="approved" if approved else "denied"
        self.db.execute("UPDATE v5_mobile_approvals SET status=?,resolved_at=?,resolution_note=? WHERE approval_id=?",(status,utc_now(),note[:2000],approval_id))
        self.push_event("approval.resolved",{"approval_id":approval_id,"status":status},row.get("mobile_id"))
        return self.get_approval(approval_id) or {}

    def approvals(self,*,status:str|None=None,limit:int=100)->list[dict[str,Any]]:
        if status:
            rows=self.db.execute("SELECT approval_id FROM v5_mobile_approvals WHERE status=? ORDER BY created_at DESC LIMIT ?",(status,max(1,min(int(limit),500))),fetch="all") or []
        else:
            rows=self.db.execute("SELECT approval_id FROM v5_mobile_approvals ORDER BY created_at DESC LIMIT ?",(max(1,min(int(limit),500)),),fetch="all") or []
        return [self.get_approval(r["approval_id"]) for r in rows]
