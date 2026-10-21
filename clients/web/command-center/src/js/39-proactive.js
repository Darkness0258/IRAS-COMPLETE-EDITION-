/* ==========================================================================
   Her own notices: things IRAS saw or finished without being asked.

     GET /v1/v5/notifications     { notifications: [{ notification_id, title, body, severity, ... }] }

   Each new notice shows as a message, goes into Activity, and is spoken
   when "Speak replies" is on. The first check shows at most 3, so an old
   backlog does not flood the screen.
   ========================================================================== */
"use strict";

(function () {
  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  const seen = new Set();
  let first = true;

  function show(n) {
    const bad = /error|critical|warn/i.test(String(n.severity || ""));
    const body = String(n.body || "").slice(0, 240);
    audit.add({ kind: "system", status: "done", title: String(n.title || "IRAS noticed something"), detail: body, tags: ["her own"], payload: { notice: n } });
    toast(String(n.title || "IRAS noticed something") + (body ? ": " + body.slice(0, 110) : ""), { icon: bad ? "shield-alert" : "info", timeout: 9000 });
    if (settings.speakReplies && IRAS.voice) IRAS.voice.speak((n.title || "") + ". " + body);
  }

  async function pull() {
    if (document.hidden || settings.source !== "live" || !base() || !IRAS.live.ok) return;
    try {
      const r = await fetch(base() + "/v1/v5/notifications", { headers: Object.assign({ "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}) });
      if (!r.ok) return;
      const list = (await r.json()).notifications || [];
      const fresh = list.filter((n) => n && n.notification_id && !n.read && !seen.has(n.notification_id));
      list.forEach((n) => n && seen.add(n.notification_id));
      (first ? fresh.slice(0, 3) : fresh.slice(0, 5)).reverse().forEach(show);
      first = false;
    } catch (e) { /* the next check tries again */ }
  }

  setInterval(pull, 30000);
  bus.on("sync", (e) => { if (e.state === "synced") pull(); });
})();
