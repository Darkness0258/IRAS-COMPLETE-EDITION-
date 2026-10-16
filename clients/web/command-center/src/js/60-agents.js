/* ==========================================================================
   Agents: tiles, run timelines, routines
   ========================================================================== */
"use strict";

(function () {
  const AGENTS = [
    { id: "code", name: "Code agent", cmd: "/code", ic: "bug", desc: "Reads your project, writes a fix, runs the tests, and repairs what still fails.", sample: "/code fix the failing test" },
    { id: "research", name: "Research agent", cmd: "/research", ic: "flask-conical", desc: "Plans, searches, reads and cross-checks, then writes a short brief with sources.", sample: "/research local speech-to-text on low-end laptops" },
    { id: "install", name: "Install agent", cmd: "/install", ic: "package", desc: "Finds software from the official source, asks you first, installs it and checks it opens.", sample: "Install VS Code" },
  ];
  const PLAN = {
    code: [["inspect", "Inspect"], ["implement", "Implement"], ["test", "Test"], ["repair", "Repair"], ["retest", "Re-test"], ["review", "Review"]],
    research: [["plan", "Plan"], ["search", "Search"], ["read", "Read"], ["check", "Cross-check"], ["write", "Write"]],
  };
  const runList = $("#runList");
  const cards = new Map();

  function stepHTML(s) {
    const ic = s.status === "done" ? "check" : s.status === "running" ? "loader-circle" : s.status === "failed" ? "circle-alert" : "circle-dot";
    const badge = s.status === "failed" ? `<span class="badge plain">Failed, then fixed</span>` : "";
    return `<li class="stp" data-status="${s.status}"><span class="stp-node">${icon(ic, "i-sm")}</span><div><div class="stp-label">${esc(s.label)}${badge}</div>${s.detail ? `<div class="stp-detail">${esc(s.detail)}</div>` : ""}</div></li>`;
  }
  function cardHTML(it) {
    const a = (it.payload && it.payload.agent) || "code";
    const info = AGENTS.find((x) => x.id === a) || AGENTS[0];
    const seen = new Map(((it.payload && it.payload.steps) || []).map((s) => [s.id, s]));
    const steps = (PLAN[a] || []).map(([id, label]) => seen.get(id) || { id, label, status: "pending", detail: "" });
    const badge = it.status === "running" ? `<span class="badge accent">${icon("loader-circle", "i-sm")}Running</span>` : it.status === "failed" ? `<span class="badge">Failed</span>` : `<span class="badge accent">${icon("check", "i-sm")}Done</span>`;
    const p = it.status === "running" ? (it.payload.progress || 0) : 1;
    return `<div class="run-head"><span class="ico-tile">${icon(info.ic)}</span><div class="grow"><div class="run-title">${esc(it.title)}</div><div class="run-sub">${esc(info.name)}, started ${esc(fmtTime(it.ts))}${it.status !== "running" && it.ms ? ", took " + esc(fmtDur(it.ms)) : ""}</div></div>${badge}</div>` +
      `<div class="bar" style="--p:${p}" role="progressbar" aria-label="Progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(p * 100)}"><i></i></div>` +
      `<ol class="steps">${steps.map(stepHTML).join("")}</ol>` +
      (it.detail && it.status !== "running" ? `<p class="muted">${esc(it.detail)}</p>` : "");
  }
  function upsert(it) {
    if (it.kind !== "agent") return;
    let el = cards.get(it.id);
    if (!el) { el = document.createElement("article"); el.className = "run"; el.setAttribute("aria-label", it.title); cards.set(it.id, el); const empty = $(".empty", runList); if (empty) empty.remove(); runList.prepend(el); }
    el.innerHTML = cardHTML(it);
  }

  function renderStats() {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const today = audit.items.filter((i) => i.ts >= start.getTime()).length;
    const waiting = audit.items.filter((i) => i.status === "waiting").length;
    const times = audit.items.filter((i) => i.kind === "tool" && i.status === "done" && i.ms);
    const avg = times.length ? times.reduce((a, b) => a + b.ms, 0) / times.length : 0;
    const on = IRAS.data.routines.filter((r) => r.on).length;
    $("#agentStats").innerHTML = [
      ["Routines on", `${on}`, `of ${IRAS.data.routines.length} set up`, "repeat-2"],
      ["Actions today", `${today}`, "all in the audit log", "list-checks"],
      ["Waiting for you", `${waiting}`, waiting ? "open the approval to decide" : "nothing needs you", "shield"],
      ["Average action", avg ? fmtDur(avg) : "none yet", "from finished tools", "timer"],
    ].map(([l, n, sub, ic]) => `<div class="stat"><div class="stat-label">${icon(ic, "i-sm")}${l}</div><div class="stat-num num">${n}</div><div class="stat-sub">${sub}</div></div>`).join("");
  }

  function renderRoutines() {
    $("#routineList").innerHTML = IRAS.data.routines.map((r) => `
      <div class="routine${r.on ? "" : " is-off"}" data-id="${r.id}">
        <div><div class="rt-name">${esc(r.name)}</div><div class="rt-desc">${esc(r.desc)}</div></div>
        <div class="rt-actions">
          <button type="button" class="btn-icon sm" data-run="${r.id}" aria-label="Run ${esc(r.name)} now" title="Run now">${icon("play", "i-sm")}</button>
          <label class="switch"><input type="checkbox" role="switch" data-toggle="${r.id}" aria-label="${esc(r.name)}" ${r.on ? "checked" : ""}><span class="track"></span></label>
        </div>
        <div class="rt-meta"><span>${icon("clock", "i-sm")}${esc(r.when)}</span><span>${icon("history", "i-sm")}Last: ${esc(r.last)}</span><span>${icon("layers", "i-sm")}${esc(r.tools.join(", "))}</span></div>
      </div>`).join("");
  }

  IRAS.initAgents = function () {
    $("#agentTiles").innerHTML = AGENTS.map((a) => `
      <article class="agent-tile"><span class="ico-tile">${icon(a.ic)}</span><h2>${a.name}</h2><p>${a.desc}</p>
        <div class="tile-foot"><code>${a.cmd}</code><button type="button" class="btn sm" data-sample="${esc(a.sample)}">${icon("play", "i-sm")}<span>Try it</span></button></div></article>`).join("");
    $("#agentTiles").addEventListener("click", (e) => { const b = e.target.closest("[data-sample]"); if (b) IRAS.run(b.dataset.sample); });

    const runs = audit.items.filter((i) => i.kind === "agent");
    if (!runs.length) runList.innerHTML = `<div class="empty surface">${icon("workflow")}<strong>No runs yet</strong><span>Try one of the agents above and its steps appear here.</span></div>`;
    runs.slice().reverse().forEach(upsert);
    renderRoutines();
    renderStats();

    $("#routineList").addEventListener("change", (e) => {
      const t = e.target.closest("[data-toggle]");
      if (!t) return;
      const r = IRAS.data.routines.find((x) => x.id === t.dataset.toggle);
      r.on = t.checked;
      t.closest(".routine").classList.toggle("is-off", !r.on);
      toast(`${r.name} is ${r.on ? "on" : "off"}.`, { icon: r.on ? "check" : "pause" });
      renderStats();
    });
    $("#routineList").addEventListener("click", (e) => {
      const b = e.target.closest("[data-run]");
      if (!b) return;
      const r = IRAS.data.routines.find((x) => x.id === b.dataset.run);
      const it = audit.add({ kind: "tool", status: "running", title: `Running “${r.name}” now`, detail: r.desc, tags: ["routine"], payload: { tool: "routine.run", args: { id: r.id } } });
      setTimeout(() => audit.update(it.id, { status: "done", ms: 1800, title: `Ran “${r.name}” now`, payload: Object.assign({}, it.payload, { ok: true }) }), 1800);
    });
    $("#newTask").addEventListener("click", () => {
      IRAS.go("home");
      setTimeout(() => { const inp = $('[data-composer="home"] .msg'); if (inp) { inp.value = "/"; inp.dispatchEvent(new Event("input")); inp.focus(); } }, 60);
    });

    bus.on("audit:reset", () => {
      cards.clear();
      runList.innerHTML = `<div class="empty surface">${icon("workflow")}<strong>No runs yet</strong><span>Try one of the agents above and its steps appear here.</span></div>`;
      audit.items.filter((i) => i.kind === "agent").slice().reverse().forEach(upsert);
      renderStats();
    });
    bus.on("audit:add", (e) => { upsert(e.item); renderStats(); });
    bus.on("audit:update", (e) => { upsert(e.item); renderStats(); });
  };
})();
