/* ==========================================================================
   Activity: the audit log. A timeline, an inspector, and an export.
   ========================================================================== */
"use strict";

(function () {
  const list = $("#actList");
  const insp = $("#inspector");
  let filter = "all";
  let query = "";
  let selected = null;

  const FILTERS = {
    all: () => true,
    tool: (i) => i.kind === "tool",
    agent: (i) => i.kind === "agent",
    approval: (i) => i.kind === "approval" || i.authority !== "none",
    system: (i) => i.kind === "system",
  };
  const REVERSIBLE = { "winget.install": "Uninstall it", "spotify.play": "Stop playback", "apps.open": "Close the app" };
  const levelName = (a) => (a === "critical" ? "Critical" : a === "system" ? "System action" : "None");
  const iconOf = (it) => {
    if (it.status === "running") return "loader-circle";
    if (it.kind === "approval") return it.authority === "critical" ? "shield-alert" : "shield";
    if (it.kind === "agent") return "workflow";
    if (it.kind === "system") return it.tags && it.tags.includes("sync") ? "cloud" : "cpu";
    const t = (it.payload && it.payload.tool) || "";
    return t.startsWith("spotify") ? "music" : t.startsWith("mail") ? "mail" : t.startsWith("winget") ? "package" : t.startsWith("whatsapp") ? "message-square" : t.startsWith("apps") ? "monitor" : t.startsWith("fs") ? "folder" : "zap";
  };
  const statusBadge = (it) => {
    switch (it.status) {
      case "running": return `<span class="badge accent">${icon("loader-circle", "i-sm")}Running</span>`;
      case "waiting": return `<span class="badge ${it.authority === "critical" ? "crit" : "warn"}">${icon("shield", "i-sm")}Waiting for you</span>`;
      case "denied": return `<span class="badge ${it.authority === "critical" ? "crit" : "warn"}">${icon("shield", "i-sm")}Denied</span>`;
      case "failed": return `<span class="badge">${icon("circle-alert", "i-sm")}Failed</span>`;
      default: return `<span class="badge accent">${icon("check", "i-sm")}${it.ms ? "Done in " + esc(fmtDur(it.ms)) : "Done"}</span>`;
    }
  };

  function visible() {
    const q = query.trim().toLowerCase();
    return audit.items.filter(FILTERS[filter]).filter((i) => !q || (i.title + " " + i.detail + " " + (i.tags || []).join(" ")).toLowerCase().includes(q));
  }

  function dayLabel(ts) {
    const d = new Date(ts), n = new Date();
    const same = (a, b) => a.toDateString() === b.toDateString();
    const y = new Date(n); y.setDate(n.getDate() - 1);
    return same(d, n) ? "Today" : same(d, y) ? "Yesterday" : d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short" });
  }

  function renderList() {
    const items = visible();
    if (!items.length) {
      list.innerHTML = `<li class="empty surface">${icon("search")}<strong>Nothing matches</strong><span>Try a different word or show everything.</span></li>`;
      $("#actCount").textContent = "";
      return;
    }
    let html = "", lastDay = "";
    items.forEach((it) => {
      const day = dayLabel(it.ts);
      if (day !== lastDay) { html += `<li class="tl-day" aria-hidden="true">${esc(day)}</li>`; lastDay = day; }
      const authBadge = it.authority === "critical" ? `<span class="badge crit">${icon("shield-alert", "i-sm")}Critical</span>` : it.authority === "system" ? `<span class="badge warn">${icon("shield", "i-sm")}System action</span>` : "";
      const tags = (it.tags || []).map((t) => `<code>${esc(t)}</code>`).join("");
      html += `<li class="tl" data-id="${esc(it.id)}" data-status="${it.status}" data-level="${it.authority}">
        <div class="tl-time"><time>${esc(fmtTime(it.ts))}</time><span>${esc(relTime(it.ts))}</span></div>
        <span class="tl-node" aria-hidden="true">${icon(iconOf(it), "i-sm")}</span>
        <button type="button" class="tl-card" aria-pressed="${selected === it.id}" data-id="${esc(it.id)}">
          <div class="tl-top"><strong>${esc(it.title)}</strong>${statusBadge(it)}</div>
          ${it.detail ? `<p class="tl-detail">${esc(it.detail)}</p>` : ""}
          ${authBadge || tags ? `<div class="tl-tags">${authBadge}${tags}</div>` : ""}
        </button></li>`;
    });
    list.innerHTML = html;
    $("#actCount").textContent = `Showing ${items.length} of ${audit.items.length} events`;
  }

  function checksFor(it) {
    const out = ["Secrets were removed from this log"];
    if (it.kind === "tool") out.push("Stayed inside the apps and folders you allowed");
    if (it.kind === "agent") out.push("Checked its own changes before it finished");
    if (it.authority === "system") out.push(it.status === "denied" ? "Asked you first, and you said no" : "Asked you first");
    else if (it.authority === "critical") out.push(it.status === "denied" ? "Needed your voice. Nothing changed" : "Needed your voice before it ran");
    else if (it.kind === "tool") out.push("No approval needed for this kind of action");
    if (it.status === "failed") out.push("Stopped when something failed");
    return out;
  }

  function payloadJSON(it) {
    const p = {
      id: it.id, time: new Date(it.ts).toISOString(), kind: it.kind, status: it.status, authority: it.authority,
      duration_ms: it.ms || undefined,
    };
    if (it.payload) Object.assign(p, it.payload);
    return JSON.stringify(p, null, 2);
  }

  function renderInspector() {
    const it = audit.byId.get(selected);
    if (!it) { insp.innerHTML = `<div class="empty">${icon("list-checks")}<strong>Pick an event</strong><span>Its details, safety checks and raw data show up here.</span></div>`; return; }
    const tool = it.payload && it.payload.tool;
    const undo = REVERSIBLE[tool];
    insp.innerHTML = `
      <div class="insp-head"><div><h2>${esc(it.title)}</h2><div class="insp-id">${esc(it.id)}</div></div>${statusBadge(it)}</div>
      <dl class="facts">
        <div><dt>When</dt><dd>${esc(dayLabel(it.ts))}, ${esc(fmtTime(it.ts))}</dd></div>
        <div><dt>Took</dt><dd>${it.ms ? esc(fmtDur(it.ms)) : "Instant"}</dd></div>
        <div><dt>Authority</dt><dd>${esc(levelName(it.authority))}</dd></div>
        <div><dt>${it.kind === "agent" ? "Agent" : "Tool"}</dt><dd class="mono">${esc(tool || (it.payload && it.payload.agent) || it.kind)}</dd></div>
      </dl>
      <h3 class="insp-sub">Safety checks</h3>
      <ul class="checks">${checksFor(it).map((c) => `<li>${icon("shield-check")}<span>${esc(c)}</span></li>`).join("")}</ul>
      <h3 class="insp-sub">Details</h3>
      <pre class="json" tabindex="0" aria-label="Raw details">${esc(payloadJSON(it))}</pre>
      <div class="insp-actions">
        <button type="button" class="btn" id="undoBtn" ${undo && it.status === "done" ? "" : "disabled"}>${icon("undo-2", "i-sm")}<span>${undo ? esc(undo) : "Can’t be undone"}</span></button>
        <button type="button" class="btn" id="copyJson">${icon("copy", "i-sm")}<span>Copy details</span></button>
      </div>
      ${undo && it.status === "done" ? `<p class="insp-note">Undo is a preview here. It adds a new line to the log instead of changing your PC.</p>` : ""}`;
  }

  function renderStats() {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const today = audit.items.filter((i) => i.ts >= start.getTime());
    const asked = audit.items.filter((i) => i.authority !== "none").length;
    const denied = audit.items.filter((i) => i.status === "denied").length;
    const times = audit.items.filter((i) => i.kind === "tool" && i.status === "done" && i.ms);
    const avg = times.length ? times.reduce((a, b) => a + b.ms, 0) / times.length : 0;
    $("#activityStats").innerHTML = [
      ["Actions today", `${today.length}`, "every one is listed below", "list-checks"],
      ["Asked you first", `${asked}`, "system or critical actions", "shield"],
      ["Denied or expired", `${denied}`, "nothing ran", "octagon-x"],
      ["Average action", avg ? fmtDur(avg) : "none yet", "from finished tools", "timer"],
    ].map(([l, n, sub, ic]) => `<div class="stat"><div class="stat-label">${icon(ic, "i-sm")}${l}</div><div class="stat-num num">${n}</div><div class="stat-sub">${sub}</div></div>`).join("");
  }

  function refresh() { renderList(); renderInspector(); renderStats(); }

  list.addEventListener("click", (e) => {
    const b = e.target.closest(".tl-card");
    if (!b) return;
    selected = b.dataset.id;
    $$(".tl-card", list).forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.id === selected)));
    renderInspector();
    if (window.matchMedia("(max-width: 1180px)").matches) insp.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  insp.addEventListener("click", async (e) => {
    if (e.target.closest("#copyJson")) {
      const ok = await IRAS.copyText($(".json", insp).textContent);
      toast(ok ? "Details copied." : "Couldn’t copy.", { icon: ok ? "copy" : "info" });
    }
    if (e.target.closest("#undoBtn")) {
      const it = audit.byId.get(selected);
      if (!it) return;
      audit.add({ kind: "system", status: "done", title: `Undid: ${it.title}`, detail: "Preview only. Nothing on your PC changed.", tags: ["undo"], payload: { undone: it.id } });
      toast("Undone. Added to the log.", { icon: "undo-2" });
    }
  });
  $$("input[name='actFilter']").forEach((r) => r.addEventListener("change", () => { filter = r.value; renderList(); }));
  $("#actSearch").addEventListener("input", (e) => { query = e.target.value; renderList(); });

  $("#exportLog").addEventListener("click", () => {
    const rows = audit.items.map((it) => ({ id: it.id, time: new Date(it.ts).toISOString(), kind: it.kind, status: it.status, authority: it.authority, title: it.title, detail: it.detail, tags: it.tags, duration_ms: it.ms || null, data: it.payload || null }));
    const blob = new Blob([JSON.stringify({ exported: new Date().toISOString(), source: settings.source, events: rows }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `iras-activity-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast("Log exported as a JSON file.", { icon: "download" });
  });

  IRAS.initActivity = function () {
    selected = audit.items[0] ? audit.items[0].id : null;
    refresh();
    let t = 0;
    const later = () => { clearTimeout(t); t = setTimeout(() => { if (IRAS.view() === "activity" || !selected) refresh(); else renderStats(); }, 120); };
    const badge = () => {
      const n = audit.items.filter((i) => i.status === "waiting").length;
      const b = $("#navBadgeActivity");
      b.hidden = !n; b.textContent = n; b.setAttribute("aria-label", `${n} waiting for you`);
    };
    bus.on("audit:add", (e) => { if (!selected) selected = e.item.id; later(); badge(); });
    bus.on("audit:update", () => { later(); badge(); });
    bus.on("audit:reset", () => { selected = audit.items[0] ? audit.items[0].id : null; refresh(); badge(); });
    bus.on("view", (e) => { if (e.view === "activity") refresh(); });
    IRAS.selectActivity = (id) => { selected = id; refresh(); };
    setInterval(() => { if (IRAS.view() === "activity" && !document.hidden) renderList(); }, 60000);
  };
})();
