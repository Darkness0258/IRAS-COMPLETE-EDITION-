/* ==========================================================================
   Right now: what is going on around her, for the person who is here.

     GET /v1/right-now?person_id=&via=&guest=&tz=&offset=     the facts (see src/iras/right_now.py)

   One set of facts. This card shows them on Home, and the chat sends her the same request
   with each message ({ tz, offset }), so the server writes her lines from the same facts.
   The switch is in Settings: off means no card, and she gets nothing.

     IRAS.rightNow.enabled()    true unless the switch is off
     IRAS.rightNow.forChat()    what the chat adds to a message: { tz, offset }, or undefined when the switch is off
     IRAS.rightNow.refresh(f)   ask the server now (f = true skips the short wait)

   The facts belong to one person. The server only answers for who we ask about, and this card
   never shows facts that were asked for somebody else: after Who is here changes, the private
   rows say "Checking" until the answer for the new person arrives.
   ========================================================================== */
"use strict";

(function () {
  const FRESH = 15000;   // asked again no sooner than this, when Home is shown again
  const EVERY = 60000;   // while Home is on screen, it asks the server this often
  const TICK = 20000;    // and it redraws this often, so "in 12 min" stays right between answers
  const HOW = { face: "known by face", voice: "known by voice", chosen: "picked by hand" };

  let facts = null, askedFor = "", failed = false, at = 0, pending = null, again = false, open = false;
  let link = "";   // how the link to the server is doing: "" (not tried yet), "syncing", "synced" or "offline"

  /* ---------- what the page knows without the server ---------- */
  const enabled = () => settings.rightNow !== false;
  const zone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { return ""; } };
  const offset = () => String(-new Date().getTimezoneOffset());   // minutes east of UTC
  const forChat = () => (enabled() ? { tz: zone(), offset: Number(offset()) } : undefined);
  const connected = () => settings.source === "live" && !!String(settings.server || "").trim() && !!(IRAS.live && IRAS.live.ok);
  const anyone = () => !!(IRAS.people && IRAS.people.all().length);

  /* who is here, as a short key: facts asked for one person are never shown for another */
  function key() {
    const w = IRAS.who && IRAS.who.current();
    return !w ? "none" : w.kind === "guest" ? "guest" : "p:" + String(w.person_id || "");
  }

  function query() {
    const w = IRAS.who && IRAS.who.forChat();
    const p = new URLSearchParams();
    if (w && w.guest) p.set("guest", "1");
    else if (w && w.person_id) { p.set("person_id", w.person_id); p.set("via", w.via || "chosen"); }
    const z = zone();
    if (z) p.set("tz", z);
    p.set("offset", offset());
    return p.toString();
  }

  /* ---------- words ---------- */
  const part = (h) => (h >= 5 && h < 12 ? "Morning" : h >= 12 && h < 17 ? "Afternoon" : h >= 17 && h < 21 ? "Evening" : "Night");
  const clockText = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const dateText = (d) => d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
  function dayText(d, now) {
    const a = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const b = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const gap = Math.round((b - a) / 864e5);
    return gap === 0 ? "" : gap === 1 ? "tomorrow" : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  }
  function inText(ms) {
    const m = Math.floor(ms / 6e4);
    if (m <= 0) return "now";
    if (m < 60) return "in " + m + " min";
    const h = Math.floor(m / 60), r = m % 60;
    if (h < 24) return "in " + h + " h" + (r ? " " + r + " min" : "");
    const d = Math.floor(h / 24);
    return "in " + d + (d === 1 ? " day" : " days");
  }
  const when = (iso, now) => {
    const d = new Date(iso);
    if (isNaN(d)) return { rel: "", clock: "" };
    const day = dayText(d, now);
    return { rel: inText(d - now), clock: clockText(d) + (day ? " " + day : "") };
  };

  /* ---------- the rows ---------- */
  const text = (main, sub) => ({ main: esc(main), sub: sub ? esc(sub) : "" });

  function timeRow(now) {
    return { kind: "time", ic: now.getHours() >= 5 && now.getHours() < 18 ? "sun" : "moon", label: "Time", main: esc(part(now.getHours()) + " · " + clockText(now)), sub: esc(dateText(now)) };
  }

  function whoRow() {
    const w = IRAS.who && IRAS.who.current();
    if (w && w.kind === "guest") return { kind: "who", ic: "shield", label: "Who is here", main: "A guest", sub: "Your private things stay hidden", who: true };
    if (w && w.kind === "person") return { kind: "who", ic: "user", label: "Who is here", main: esc(w.name || "Someone"), sub: esc(HOW[w.via] || ""), who: true };
    return { kind: "who", ic: "users", label: "Who is here", main: "No one picked", sub: anyone() ? "Showing what is shared with everyone" : "Tap to say who is here", who: true };
  }

  /* the two rows that come from the server */
  function state(kind) {
    const w = IRAS.who && IRAS.who.current();
    if (w && w.kind === "guest") return { text: text("Hidden for a guest") };
    if (!connected()) {   // still trying (start-up) is not the same as not connected
      const trying = settings.source === "live" && !!String(settings.server || "").trim() && (link === "" || link === "syncing");
      return trying ? { text: text("Checking…"), busy: true } : { text: text("Not connected", "Connect to your server in Settings.") };
    }
    if (failed) return { text: text("Could not load this", "It will try again in a minute.") };
    if (!facts || askedFor !== key()) return { text: text("Checking…"), busy: true };
    return { facts: facts[kind] || {} };
  }

  function eventRow(now) {
    const row = { kind: "event", ic: "calendar", label: "Next event" };
    const s = state("calendar");
    if (!s.facts) return Object.assign(row, s.text || {}, { ic: s.text && s.text.main === "Hidden for a guest" ? "lock" : row.ic });
    const c = s.facts;
    if (c.state === "none") return Object.assign(row, { main: "No calendar yet", sub: '<a class="link-btn" href="#/agents">Add one</a>' });
    if (c.state === "slow" || c.state === "unavailable") return Object.assign(row, text("Could not read the calendar", "It will try again."));
    if (!c.event) return Object.assign(row, text("Nothing in the next 7 days"));
    const t = when(c.event.start, now);
    return Object.assign(row, { main: esc(c.event.title), sub: esc([t.rel, t.clock].filter(Boolean).join(" · ")) });
  }

  function remindersRow(now) {
    const row = { kind: "reminders", ic: "bell", label: "Reminders due" };
    const s = state("reminders");
    if (!s.facts) return Object.assign(row, s.text || {}, { ic: s.text && s.text.main === "Hidden for a guest" ? "lock" : row.ic });
    const r = s.facts;
    if (r.state === "unavailable") return Object.assign(row, text("Could not read the reminders", "It will try again."));
    const items = r.items || [];
    if (!items.length) return Object.assign(row, text("Nothing due in the next " + Number(r.hours || 4) + " hours"));
    const lines = items.map((i) => {
      const t = when(i.due, now);
      const tag = anyone() && i.for === "everyone" ? ' <span class="rn-tag">for everyone</span>' : "";
      return `<span class="rn-line"><span class="rn-what">${esc(i.text)}</span> <span class="rn-when">${esc(t.rel)}</span>${tag}</span>`;
    });
    if (r.more) lines.push(`<span class="rn-line rn-more">and ${Number(r.more)} more</span>`);
    return Object.assign(row, { main: lines.join(""), lines: true });
  }

  /* one short line for a phone, where the card is folded */
  function summary(now) {
    const w = IRAS.who && IRAS.who.current();
    const base = part(now.getHours()) + " · " + clockText(now);
    if (!connected() || failed || !facts || askedFor !== key() || (w && w.kind === "guest")) return base;
    const first = ((facts.reminders || {}).items || [])[0];
    if (first) return first.text + " · " + when(first.due, now).rel;
    const ev = (facts.calendar || {}).event;
    if (ev) return ev.title + " · " + when(ev.start, now).rel;
    return base;
  }

  const rowHtml = (r) => {
    const inner = `<span class="rn-ic">${icon(r.ic)}</span><span class="rn-txt"><span class="rn-label">${esc(r.label)}</span><span class="rn-main${r.lines ? " is-lines" : ""}">${r.main || ""}</span>${r.sub ? `<span class="rn-sub">${r.sub}</span>` : ""}</span>`;
    return r.who
      ? `<li class="rn-row is-${r.kind}"><button class="rn-hit" type="button" data-who-open aria-haspopup="dialog">${inner}</button></li>`
      : `<li class="rn-row is-${r.kind}">${inner}</li>`;
  };

  function render() {
    const el = $("#rightNow");
    if (!el) return;
    el.hidden = !enabled();
    const opener = $("#rnOpen");
    if (opener) opener.hidden = !enabled();
    if (!enabled()) { if (open) fold(false); return; }
    const now = new Date();
    const rows = [timeRow(now), whoRow(), eventRow(now), remindersRow(now)];
    el.setAttribute("aria-busy", pending ? "true" : "false");
    $("#rnBody").innerHTML = rows.map(rowHtml).join("");
    $("#rnSummary").textContent = summary(now);
  }

  /* ---------- asking the server ---------- */
  function refresh(force) {
    if (!enabled()) return Promise.resolve();
    if (!connected()) { facts = null; failed = false; render(); return Promise.resolve(); }
    if (pending) { again = true; return pending; }
    if (!force && facts && askedFor === key() && Date.now() - at < FRESH) return Promise.resolve();
    const mine = key();
    pending = IRAS.api("/v1/right-now?" + query())
      .then((j) => { facts = j; askedFor = mine; failed = false; at = Date.now(); })
      .catch(() => { facts = null; failed = true; at = Date.now(); })   // an older server has no such route: the card still shows the time and who
      .then(() => { pending = null; render(); if (again) { again = false; refresh(true); } });
    render();
    return pending;
  }

  /* ---------- the folded card on a phone ---------- */
  function fold(on) {
    const el = $("#rightNow"), btn = $("#rnToggle"), opener = $("#rnOpen");
    if (!el || !btn) return;
    open = !!on;
    if (opener) opener.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { const lt = $("#liveToggle"); if (lt && lt.getAttribute("aria-expanded") === "true") lt.click(); }   // one sheet at a time
    el.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.setAttribute("aria-label", open ? "Show less of Right now" : "Show more of Right now");
    $("svg use", btn).setAttribute("href", open ? "#i-chevron-down" : "#i-chevron-up");
  }

  IRAS.rightNow = { enabled, forChat, refresh, render, query };

  IRAS.initRightNow = function () {
    $("#rnToggle").addEventListener("click", () => fold(!open));
    $("#rnOpen").addEventListener("click", (e) => { e.stopPropagation(); fold(!open); if (open) $("#rnToggle").focus(); });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !open) return;
      const opener = $("#rnOpen"), short = opener && opener.offsetParent !== null;
      fold(false);
      (short ? opener : $("#rnToggle")).focus();   // back to the button that opened it
    });
    document.addEventListener("click", (e) => { if (open && !e.target.closest("#rightNow, #rnOpen")) fold(false); });
    bus.on("who", () => { render(); refresh(true); });
    bus.on("people", render);
    bus.on("sync", (e) => { link = e.state || ""; render(); refresh(true); });
    bus.on("view", (e) => { if (e.view === "home") { render(); refresh(); } else if (open) fold(false); });
    bus.on("setting", (e) => { if (e.key === "rightNow" || e.key === "source" || e.key === "server") { render(); refresh(true); } });
    setInterval(() => { if (!document.hidden && IRAS.view() === "home") render(); }, TICK);
    setInterval(() => { if (!document.hidden && IRAS.view() === "home") refresh(); }, EVERY);
    render();
    refresh();
  };
})();
