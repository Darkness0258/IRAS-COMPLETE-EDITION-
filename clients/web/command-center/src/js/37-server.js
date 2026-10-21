/* ==========================================================================
   Real server data: approvals and the activity log.

     GET  /v1/v5/mobile/approvals?status=pending   approvals that wait for you
     POST /v1/v5/mobile/approvals/{id}              { approved, note }
     GET  /v1/v5/audit                              recent operations

   An approval opens the same overlay as before. Your choice goes to the server.
   If the time runs out nothing is sent, and the request stays pending.
   ========================================================================== */
"use strict";

(function () {
  const live = IRAS.live;
  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  const hdr = (extra = {}) => Object.assign({ "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}, extra);
  const ready = () => settings.source === "live" && base() && live.ok;
  const human = (s) => { const t = String(s || "request").replace(/[._-]+/g, " ").trim(); return t.charAt(0).toUpperCase() + t.slice(1); };
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); };

  /* ---------- approvals ---------- */
  const shown = new Set();   // approvals already put in front of you
  const open = new Map();    // overlay id -> approval row
  let current = null;        // the one on screen now

  function ask(a) {
    const p = a.payload || {};
    const text = p.summary || p.description || p.command || p.action || p.path || "";
    current = a.approval_id;
    open.set(a.approval_id, a);
    bus.emit("approval_request", {
      id: a.approval_id,
      authority: "system",
      title: human(a.kind),
      detail: text ? String(text).slice(0, 240) : "IRAS is asking before it acts.",
      effects: Object.entries(p).slice(0, 4).map(([k, v]) => ({ icon: "circle-dot", text: (k + ": " + (typeof v === "string" ? v : JSON.stringify(v))).slice(0, 140) })),
      approveLabel: "Approve",
      expires_ms: 120000,
    });
  }

  async function pollApprovals() {
    if (!ready() || document.hidden || current) return;
    try {
      const r = await fetch(base() + "/v1/v5/mobile/approvals?status=pending", { headers: hdr() });
      if (!r.ok) return;
      const list = (await r.json()).approvals || [];
      const next = list.find((a) => a && a.approval_id && !shown.has(a.approval_id));
      if (next) { shown.add(next.approval_id); ask(next); }
    } catch (e) { /* the next check tries again */ }
  }
  IRAS.pollApprovals = pollApprovals;

  bus.on("approval_result", async (e) => {
    const a = open.get(e.id);
    if (!a) return;   // not an approval from the server
    open.delete(e.id);
    current = null;
    if (e.decision === "expired") {
      toast("An approval is still waiting: " + human(a.kind), { icon: "shield", timeout: 12000, action: { label: "Review", fn: () => { shown.delete(e.id); pollApprovals(); } } });
      return;
    }
    const approved = e.decision === "approve";
    try {
      const r = await fetch(base() + "/v1/v5/mobile/approvals/" + encodeURIComponent(e.id), {
        method: "POST",
        headers: hdr({ "Content-Type": "application/json" }),
        body: JSON.stringify({ approved, note: "Decided in the web app (" + (e.via || "button") + ")" }),
      });
      if (!r.ok) throw new Error("The server answered " + r.status + ".");
      toast(approved ? "Approved. IRAS can go ahead." : "Denied. IRAS will not do it.", { icon: approved ? "shield-check" : "shield-alert" });
    } catch (err) {
      shown.delete(e.id);   // ask again at the next check
      toast("Your answer did not reach the server. " + (err.message || ""), { icon: "cloud-off", timeout: 8000 });
    }
    setTimeout(pollApprovals, 500);
  });

  /* ---------- activity ---------- */
  const seen = new Set();
  bus.on("audit:reset", () => seen.clear());

  async function pullAudit() {
    if (!ready() || document.hidden) return;
    try {
      const r = await fetch(base() + "/v1/v5/audit", { headers: hdr() });
      if (!r.ok) return;
      ((await r.json()).recent || []).forEach((x) => {
        const id = "srv_" + hash(JSON.stringify(x));
        if (seen.has(id)) return;
        seen.add(id);
        const t = x.ts ?? x.time ?? x.timestamp ?? x.at;
        const when = typeof t === "number" ? (t < 1e12 ? t * 1000 : t) : (Date.parse(t) || Date.now());
        const name = x.name || x.event || "server";
        audit.add({
          id, ts: when, kind: "tool", status: x.ok === false || x.error ? "failed" : "done",
          title: human(name), detail: String(x.error || x.detail || x.message || "").slice(0, 160),
          tags: [String(name)], ms: Number(x.duration_ms || x.ms || 0) || 0, payload: { tool: name, result: x },
        });
      });
    } catch (e) { /* the next check tries again */ }
  }

  /* ---------- when to look ---------- */
  setInterval(pollApprovals, 5000);
  setInterval(pullAudit, 30000);
  bus.on("done", () => { setTimeout(pollApprovals, 800); setTimeout(pullAudit, 1500); });
  bus.on("sync", (e) => { if (e.state === "synced") { pollApprovals(); pullAudit(); } });
})();
