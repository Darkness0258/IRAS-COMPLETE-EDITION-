/* ==========================================================================
   Agents: real runs, and the things she does on her own.

     Runs       GET/POST /v1/orchestration/runs, pause / resume / retry per run
     Routines   /v1/v5/schedules   (she runs a prompt on a timer)
     Goals      /v1/v5/goals
     Watching   /v1/v5/monitors    (she checks a website and tells you)
   ========================================================================== */
"use strict";

(function () {
  const AGENTS = [
    { id: "code", name: "Code agent", cmd: "/code", ic: "bug", desc: "Reads your project, writes a fix, runs the tests, and repairs what still fails.", sample: "/code fix the failing test" },
    { id: "research", name: "Research agent", cmd: "/research", ic: "flask-conical", desc: "Plans, searches, reads and cross-checks, then writes a short brief with sources.", sample: "/research local speech-to-text on low-end laptops" },
    { id: "install", name: "Install agent", cmd: "/install", ic: "package", desc: "Finds software from the official source, asks you first, installs it and checks it opens.", sample: "Install VS Code" },
  ];
  const runList = $("#runList");
  let sched = [], goals = [], mons = [], lastSig = "", visible = false;

  const low = (v) => String(v == null ? "" : v).toLowerCase();
  const stateOf = (x) => {
    const s = low(x && (x.status || x.state));
    if (/fail|error|cancel|abort/.test(s)) return "failed";
    if (/complete|done|success|finish/.test(s)) return "done";
    if (/pause/.test(s)) return "paused";
    if (/pend|queue|wait|ready/.test(s)) return "pending";
    return "running";
  };
  const when = (iso) => { const t = Date.parse(iso); return t ? fmtTime(t) : "not yet"; };
  const err = (e, what) => toast(what + " " + (e.message || ""), { icon: "cloud-off", timeout: 8000 });
  const empty = (t, s) => `<div class="empty surface">${icon("workflow")}<strong>${t}</strong><span>${s}</span></div>`;

  /* ---------- reminders: read a time like "in 10 minutes", "at 5pm", "tomorrow at 9" ---------- */
  function parseWhen(input) {
    const s = String(input || "").toLowerCase().trim();
    let m = s.match(/^(?:in\s+)?(\d+(?:\.\d+)?|an?|half an)\s*(minutes?|mins?|m|hours?|hrs?|h|days?|d)\b/);
    if (m) {
      const n = /^an?$/.test(m[1]) ? 1 : m[1] === "half an" ? 0.5 : parseFloat(m[1]);
      return new Date(Date.now() + n * (m[2][0] === "m" ? 60e3 : m[2][0] === "h" ? 3600e3 : 86400e3));
    }
    const tomorrow = /\btomorrow\b/.test(s);
    m = s.match(/(?:\bat\s+)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$/);
    if (m && (/\bat\b/.test(s) || m[2] || m[3])) {
      let h = +m[1]; const min = +(m[2] || 0);
      if (m[3] === "pm" && h < 12) h += 12;
      if (m[3] === "am" && h === 12) h = 0;
      if (h > 23 || min > 59) return null;
      const d = new Date(); d.setHours(h, min, 0, 0);
      if (tomorrow) d.setDate(d.getDate() + 1); else if (d <= new Date()) d.setDate(d.getDate() + 1);
      return d;
    }
    if (tomorrow) { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); return d; }
    return null;
  }

  /* ---------- runs ---------- */
  function stepHTML(s) {
    const ic = s.status === "done" ? "check" : s.status === "running" ? "loader-circle" : s.status === "failed" ? "circle-alert" : "circle-dot";
    return `<li class="stp" data-status="${s.status}"><span class="stp-node">${icon(ic, "i-sm")}</span><div><div class="stp-label">${esc(s.label)}</div>${s.detail ? `<div class="stp-detail">${esc(s.detail)}</div>` : ""}</div></li>`;
  }
  function runHTML(r) {
    const st = stateOf(r), tasks = r.tasks || r.nodes || r.steps || [];
    const p = st === "done" ? 1 : tasks.length ? tasks.filter((t) => stateOf(t) === "done").length / tasks.length : 0;
    const badge = { running: `<span class="badge accent">${icon("loader-circle", "i-sm")}Running</span>`, failed: `<span class="badge">Failed</span>`, paused: `<span class="badge">Paused</span>`, pending: `<span class="badge">Waiting</span>`, done: `<span class="badge accent">${icon("check", "i-sm")}Done</span>` }[st];
    const steps = tasks.map((t) => { const s = stateOf(t); return stepHTML({ status: s === "paused" ? "pending" : s, label: t.title || t.name || t.role || t.task_id || t.id || "Step", detail: String(t.error || t.summary || "").slice(0, 160) }); }).join("");
    const note = String(r.error || r.summary || (typeof r.result === "string" ? r.result : "") || "").slice(0, 300);
    const id = esc(r.run_id || r.id);
    const acts = st === "running" ? `<button type="button" class="btn sm" data-act="pause" data-id="${id}">Pause</button>` : st === "paused" ? `<button type="button" class="btn sm" data-act="resume" data-id="${id}">Resume</button>` : st === "failed" ? `<button type="button" class="btn sm" data-act="retry" data-id="${id}">Try again</button>` : "";
    return `<article class="run" aria-label="${esc(r.objective || "Task")}"><div class="run-head"><span class="ico-tile">${icon("workflow")}</span><div class="grow"><div class="run-title">${esc(String(r.objective || r.goal || r.title || "Task").slice(0, 140))}</div><div class="run-sub">Started ${esc(when(r.created_at || r.started_at))}</div></div>${badge}</div>` +
      `<div class="bar" style="--p:${p}" role="progressbar" aria-label="Progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(p * 100)}"><i></i></div>` +
      (steps ? `<ol class="steps">${steps}</ol>` : "") + (note && st !== "running" ? `<p class="muted">${esc(note)}</p>` : "") + (acts ? `<div class="tile-foot">${acts}</div>` : "") + `</article>`;
  }
  async function pullRuns() {
    try {
      const list = (await IRAS.api("/v1/orchestration/runs?limit=15")).runs || [];
      const sig = JSON.stringify(list);
      if (sig === lastSig) return;
      lastSig = sig;
      runList.innerHTML = list.length ? list.map(runHTML).join("") : empty("No runs yet", "Press New task and describe what she should do. Its steps appear here.");
    } catch (e) { runList.innerHTML = empty("Cannot reach your server", e.message || "Check the address in Settings."); lastSig = ""; }
  }

  /* ---------- routines, goals, watching ---------- */
  const sw = (attr, id, name, on) => `<label class="switch"><input type="checkbox" role="switch" ${attr}="${esc(id)}" aria-label="${esc(name)}" ${on ? "checked" : ""}><span class="track"></span></label>`;
  const del = (attr, id, name) => `<button type="button" class="btn-icon sm" ${attr}="${esc(id)}" aria-label="Delete ${esc(name)}" title="Delete">${icon("trash-2", "i-sm")}</button>`;
  const none = (t) => `<p class="muted" style="padding:12px">${t}</p>`;

  function renderSide() {
    $("#routineList").innerHTML = sched.length ? sched.map((j) => {
      const on = j.enabled && !j.paused, s = j.interval_seconds;
      const every = s ? "Every " + (s >= 3600 ? Math.round(s / 360) / 10 + " h" : Math.max(1, Math.round(s / 60)) + " min") : "Once";
      return `<div class="routine${on ? "" : " is-off"}"><div><div class="rt-name">${esc(j.name)}</div><div class="rt-desc">${esc(String(j.prompt).replace(/^\[reminder\]\s*/i, "Reminder: "))}</div></div><div class="rt-actions">${del("data-del-job", j.job_id, j.name)}${sw("data-job", j.job_id, j.name, on)}</div><div class="rt-meta"><span>${icon("clock", "i-sm")}${every}</span><span>${icon("history", "i-sm")}Last: ${esc(j.last_run ? when(j.last_run) : "not yet")}</span></div></div>`;
    }).join("") : none("Nothing yet. Add a routine and she does it on her own.");
    $("#goalList").innerHTML = goals.length ? goals.map((g) => {
      const pr = Number(g.progress) || 0, pc = Math.round(pr <= 1 ? pr * 100 : pr);
      return `<div class="routine"><div><div class="rt-name">${esc(g.title)}</div><div class="rt-desc">${esc(g.level || "goal")}, ${pc}% done</div></div></div>`;
    }).join("") : none("No goals yet. Add one and she works toward it.");
    $("#monitorList").innerHTML = mons.length ? mons.map((m) => {
      const on = m.enabled !== false && !m.paused;
      const health = m.last_healthy == null ? "not checked yet" : m.last_healthy ? "healthy" : "problem: " + String(m.last_error || "no answer").slice(0, 60);
      return `<div class="routine${on ? "" : " is-off"}"><div><div class="rt-name">${esc(m.name)}</div><div class="rt-desc">${esc(m.kind || "website")}, ${esc(health)}</div></div><div class="rt-actions"><button type="button" class="btn-icon sm" data-check-mon="${esc(m.monitor_id)}" aria-label="Check ${esc(m.name)} now" title="Check now">${icon("play", "i-sm")}</button>${del("data-del-mon", m.monitor_id, m.name)}${sw("data-mon", m.monitor_id, m.name, on)}</div></div>`;
    }).join("") : none("Nothing watched yet. Add a website and she tells you if it breaks.");
    const on = sched.filter((j) => j.enabled && !j.paused).length;
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const today = audit.items.filter((i) => i.ts >= start.getTime()).length;
    const waiting = audit.items.filter((i) => i.status === "waiting").length;
    $("#agentStats").innerHTML = [
      ["Routines on", `${on}`, `of ${sched.length} set up`, "repeat-2"],
      ["Watching", `${mons.filter((m) => m.enabled !== false && !m.paused).length}`, `of ${mons.length} sites`, "list-checks"],
      ["Actions today", `${today}`, "all in Activity", "history"],
      ["Waiting for you", `${waiting}`, waiting ? "open the approval to decide" : "nothing needs you", "shield"],
    ].map(([l, n, sub, ic]) => `<div class="stat"><div class="stat-label">${icon(ic, "i-sm")}${l}</div><div class="stat-num num">${n}</div><div class="stat-sub">${sub}</div></div>`).join("");
  }
  async function pullSide() {
    try {
      const [a, b, c] = await Promise.all([IRAS.api("/v1/v5/schedules"), IRAS.api("/v1/v5/goals"), IRAS.api("/v1/v5/monitors")]);
      sched = (a.schedules || []).filter((j) => !(/^\[reminder\]/i.test(String(j.prompt)) && !j.enabled)); goals = b.goals || []; mons = c.monitors || [];
    } catch (e) { /* the lists keep what they had */ }
    renderSide();
  }
  const refresh = () => { pullRuns(); pullSide(); };

  /* ---------- actions ---------- */
  const post = (path, body) => IRAS.api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const ask = (q, d) => { const v = window.prompt(q, d || ""); return v == null ? "" : v.trim(); };

  IRAS.initAgents = function () {
    $("#agentTiles").innerHTML = AGENTS.map((a) => `
      <article class="agent-tile"><span class="ico-tile">${icon(a.ic)}</span><h2>${a.name}</h2><p>${a.desc}</p>
        <div class="tile-foot"><code>${a.cmd}</code><button type="button" class="btn sm" data-sample="${esc(a.sample)}">${icon("play", "i-sm")}<span>Try it</span></button></div></article>`).join("");
    $("#agentTiles").addEventListener("click", (e) => { const b = e.target.closest("[data-sample]"); if (b) IRAS.run(b.dataset.sample); });
    runList.innerHTML = empty("No runs yet", "Press New task and describe what she should do. Its steps appear here.");
    renderSide();

    $("#newTask").addEventListener("click", async () => {
      const objective = ask("What should IRAS do? Describe the goal in one or two sentences.");
      if (!objective) return;
      try { await post("/v1/orchestration/runs", { objective }); toast("Started. Watch the steps below.", { icon: "check" }); lastSig = ""; refresh(); } catch (e) { err(e, "Could not start it."); }
    });
    runList.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      try { await post("/v1/orchestration/runs/" + encodeURIComponent(b.dataset.id) + "/" + b.dataset.act); lastSig = ""; pullRuns(); } catch (x) { err(x, "Could not do that."); }
    });
    $("#addRoutine").addEventListener("click", async () => {
      const prompt = ask("What should IRAS do on her own? For example: Check my email and tell me what is urgent.");
      if (!prompt) return;
      const mins = Number(ask("How often, in minutes? 60 means every hour. Leave empty to run once.", "60"));
      const body = { name: prompt.length > 40 ? prompt.slice(0, 39) + "…" : prompt, prompt };
      if (mins > 0) body.interval_seconds = Math.round(mins * 60);
      try { await post("/v1/v5/schedules", body); toast("Routine added.", { icon: "check" }); pullSide(); } catch (e) { err(e, "Could not add it."); }
    });
    $("#addReminder").addEventListener("click", async () => {
      const text = ask("What should she remind you about?");
      if (!text) return;
      const at = parseWhen(ask("When? For example: in 10 minutes, at 5pm, tomorrow at 9.", "in 10 minutes"));
      if (!at) { toast("I could not understand that time. Try: in 10 minutes, at 5pm, or tomorrow at 9.", { icon: "info", timeout: 8000 }); return; }
      try {
        await post("/v1/v5/schedules", { name: "Reminder: " + text.slice(0, 60), prompt: "[reminder] " + text, next_run: at.toISOString().replace(/\.\d{3}Z$/, "+00:00") });
        toast("Okay. I will remind you at " + fmtTime(at.getTime()) + ".", { icon: "check" });
        pullSide();
      } catch (e) { err(e, "Could not set it."); }
    });
    $("#addGoal").addEventListener("click", async () => {
      const title = ask("What goal should IRAS work toward?");
      if (!title) return;
      try { await post("/v1/v5/goals", { title }); toast("Goal added.", { icon: "check" }); pullSide(); } catch (e) { err(e, "Could not add it."); }
    });
    $("#addMonitor").addEventListener("click", async () => {
      const url = ask("Which website should she watch? Paste the full address, starting with https://");
      if (!url) return;
      try { await post("/v1/v5/monitors", { name: url.replace(/^https?:\/\//, "").slice(0, 40), kind: "website", config: { url } }); toast("Now watching it.", { icon: "check" }); pullSide(); } catch (e) { err(e, "Could not add it."); }
    });
    $("#routineList").addEventListener("change", async (e) => {
      const t = e.target.closest("[data-job]");
      if (!t) return;
      try { await post("/v1/v5/schedules/" + encodeURIComponent(t.dataset.job) + (t.checked ? "/resume" : "/pause")); toast(t.checked ? "Routine is on." : "Routine is paused.", { icon: t.checked ? "check" : "pause" }); } catch (x) { t.checked = !t.checked; err(x, "Could not change it."); }
      pullSide();
    });
    $("#routineList").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-del-job]");
      if (!b || !window.confirm("Delete this routine?")) return;
      try { await IRAS.api("/v1/v5/schedules/" + encodeURIComponent(b.dataset.delJob), { method: "DELETE" }); } catch (x) { err(x, "Could not delete it."); }
      pullSide();
    });
    $("#monitorList").addEventListener("change", async (e) => {
      const t = e.target.closest("[data-mon]");
      if (!t) return;
      try { await post("/v1/v5/monitors/" + encodeURIComponent(t.dataset.mon) + (t.checked ? "/resume" : "/pause")); } catch (x) { t.checked = !t.checked; err(x, "Could not change it."); }
      pullSide();
    });
    $("#monitorList").addEventListener("click", async (e) => {
      const c = e.target.closest("[data-check-mon]"), d = e.target.closest("[data-del-mon]");
      try {
        if (c) { await post("/v1/v5/monitors/" + encodeURIComponent(c.dataset.checkMon) + "/check"); toast("Checked.", { icon: "check" }); }
        else if (d && window.confirm("Stop watching this?")) await IRAS.api("/v1/v5/monitors/" + encodeURIComponent(d.dataset.delMon), { method: "DELETE" });
      } catch (x) { err(x, "Could not do that."); }
      if (c || d) pullSide();
    });

    bus.on("view", (e) => { visible = e.view === "agents"; if (visible) { lastSig = ""; refresh(); } });
    bus.on("audit:add", () => { if (visible) renderSide(); });
    setInterval(() => { if (visible && !document.hidden) refresh(); }, 5000);
  };
})();
