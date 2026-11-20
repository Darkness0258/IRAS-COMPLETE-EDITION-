/* ==========================================================================
   Her own notices: things IRAS saw or finished without being asked.

     GET /v1/v5/notifications     { notifications: [{ notification_id, title, body, severity, ... }] }

   Each new notice shows as a message, goes into Activity, and is spoken
   when "Speak replies" is on. The first check shows at most 3, so an old
   backlog does not flood the screen.

   A private reminder is titled "Reminder for <name>". Its text is shown and
   spoken only when Who is here is that person, or nobody. For anyone else,
   or a guest, the screen shows only "A private reminder for <name> is due".
   The text of that reminder is never kept here: only its id, so it is shown in
   full the next time the right person is here.
   ========================================================================== */
"use strict";

(function () {
  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  const seen = new Set();     // notices that were handled
  const masked = new Set();   // private notices we only announced (ids only, no text)
  let first = true, timer = 0;

  /* ---------- private reminders ---------- */
  const PRIVATE = /^reminder for (.+)$/i;
  const norm = (t) => String(t || "").trim().replace(/\s+/g, " ").toLowerCase();
  const ownerOf = (n) => { const m = PRIVATE.exec(String(n.title || "").trim()); return m ? m[1].trim() : ""; };

  function mayRead(name) {
    const w = IRAS.who && IRAS.who.current();
    if (!w) return true;                                      // nobody in particular
    if (w.kind !== "person") return false;                    // a guest
    return norm(name) !== "someone" && norm(w.name) === norm(name);   // "someone": the server could not name the owner, so only "nobody" may read it
  }
  const hiddenFrom = (n) => { const o = ownerOf(n); return !!o && !mayRead(o); };

  function showPrivate(name) {
    const line = "A private reminder for " + name + " is due";
    audit.add({ kind: "system", status: "done", title: line, detail: "", tags: ["her own", "private"], payload: { private: true } });
    toast(line, { icon: "shield", timeout: 9000 });   // not spoken, and no text
  }

  function show(n) {
    const bad = /error|critical|warn/i.test(String(n.severity || ""));
    const body = String(n.body || "").slice(0, 240);
    audit.add({ kind: "system", status: "done", title: String(n.title || "IRAS noticed something"), detail: body, tags: ["her own"], payload: { notice: n } });
    toast(String(n.title || "IRAS noticed something") + (body ? ": " + body.slice(0, 110) : ""), { icon: bad ? "shield-alert" : "info", timeout: 9000 });
    const reminder = /^reminder/i.test(String(n.title || ""));
    if ((settings.speakReplies || reminder) && IRAS.voice) IRAS.voice.speak(reminder ? "Hey, quick reminder. " + body : (n.title || "") + ". " + body);
  }

  async function pull() {
    if (document.hidden || settings.source !== "live" || !base() || !IRAS.live.ok) return;
    try {
      const r = await fetch(base() + "/v1/v5/notifications", { headers: Object.assign({ "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}) });
      if (!r.ok) return;
      const list = (await r.json()).notifications || [];
      const fresh = [], hidden = [];
      list.forEach((n) => {
        if (!n || !n.notification_id || n.read) return;
        if (hiddenFrom(n)) { if (!masked.has(n.notification_id)) hidden.push({ id: n.notification_id, name: ownerOf(n) }); return; }
        if (!seen.has(n.notification_id)) fresh.push(n);
      });
      // Everything counts as seen, except a private reminder that this person may not read yet.
      list.forEach((n) => { if (n && n.notification_id && !hiddenFrom(n)) seen.add(n.notification_id); });
      hidden.forEach((h) => masked.add(h.id));
      const most = first ? 3 : 5;
      fresh.slice(0, most).reverse().forEach(show);
      hidden.slice(0, most).reverse().forEach((h) => showPrivate(h.name));
      first = false;
    } catch (e) { /* the next check tries again */ }
  }

  setInterval(pull, 20000);
  bus.on("sync", (e) => { if (e.state === "synced") pull(); });
  // When Who is here changes, a private reminder that was waiting can be shown to the right person.
  bus.on("who", () => { clearTimeout(timer); timer = setTimeout(pull, 500); });
})();
