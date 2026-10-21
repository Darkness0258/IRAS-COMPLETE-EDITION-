/* ==========================================================================
   Memory: a map you can drag, search and click, and a plain list for
   keyboards and screen readers. Facts IRAS learned wait for your review.
   ========================================================================== */
"use strict";

(function () {
  const canvas = $("#graph");
  const wrap = $("#graphWrap");
  let g, W = 0, H = 0, dpr = 1;
  let nodes = [], edges = [];
  let alpha = 0, raf = 0;
  let hover = null, selected = null, drag = null, query = "";
  let col = {};
  const R_BY = { you: 20, device: 15, project: 14, service: 13, model: 12, preference: 11 };
  const KIND = { you: "You", device: "Device", service: "App or service", project: "Project", model: "AI model", preference: "Preference" };
  const KIND_ICON = { you: "user", device: "laptop", service: "link", project: "folder", model: "cpu", preference: "sparkles" };

  function readColors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    col = { accent: v("--accent"), fill: v("--accent-fill"), text: v("--text"), muted: v("--muted"), bg: v("--surface-solid"), line: v("--line"), soft: v("--accent-soft"), onAccent: v("--on-accent") };
  }

  /* ---------- data: the real memory on your server ---------- */
  const YOU = { id: "you", label: "You", type: "you", detail: "Everything on this map was saved for you." };
  const TYPE_BY_KIND = { project: "project", device: "device", service: "service", app: "service", tool: "service", model: "model" };
  let searched = false, newest = 0;
  const mk = (n, i, count) => { const a = (i / count) * Math.PI * 2; return Object.assign({}, n, { x: Math.cos(a) * 160 + rand(-20, 20), y: Math.sin(a) * 120 + rand(-20, 20), vx: 0, vy: 0, r: R_BY[n.type] || 12, pinned: false }); };
  const api = (path, opts = {}) => {
    const b = String(settings.server || "").trim().replace(/\/+$/, ""), tk = store.sget("iras-api-token", "");
    if (!b) return Promise.reject(new Error("Add your server address in Settings first."));
    return fetch(b + path, Object.assign({}, opts, { headers: Object.assign({ "X-Device-ID": "web" }, tk ? { Authorization: "Bearer " + tk } : {}, opts.headers || {}) }))
      .then((r) => { if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "The server refused the access token." : "The server answered " + r.status + "."); return r.json(); });
  };
  async function loadReal(q) {
    searched = !!q;
    try {
      const list = (await api("/v1/v5/memory/search?limit=60&q=" + encodeURIComponent(q || ""))).memories || [];
      const you = mk(YOU, 0, list.length + 1);
      const mems = list.map((m, i) => { const t = String(m.text || ""); return mk({ id: m.memory_id, label: t.length > 34 ? t.slice(0, 33) + "…" : t, type: TYPE_BY_KIND[String(m.kind || "").toLowerCase()] || "preference", detail: t + (m.source ? " (from " + m.source + ")" : "") }, i + 1, list.length + 1); });
      nodes = [you].concat(mems);
      edges = mems.map((n) => ({ a: you, b: n }));
      if (!q) newest = list.reduce((t, m) => Math.max(t, Date.parse(m.created_at) || 0), 0);
      selected = null; hover = null;
      settle(300);
      $("#memStatus").textContent = !list.length && !q ? "Nothing is saved yet. Add something on the right." : "";
    } catch (err) { $("#memStatus").textContent = "Could not read memory. " + err.message; }
    renderStats(); renderCard(); renderList(); if (q) setStatus(); reheat(.6);
  }
  async function forgetReal(id) {
    const n = nodes.find((x) => x.id === id);
    if (!n) return;
    try {
      await api("/v1/v5/memory/" + encodeURIComponent(id), { method: "DELETE" });
      nodes = nodes.filter((x) => x !== n); edges = edges.filter((x) => x.a !== n && x.b !== n);
      selected = null; hover = null;
      renderCard(); renderList(); renderStats(); reheat(.5);
      toast("Forgot “" + n.label + "”.", { icon: "trash-2" });
    } catch (err) { toast("Could not forget it. " + err.message, { icon: "cloud-off", timeout: 7000 }); }
  }
  async function addReal() {
    const box = $("#memNew"), text = box.value.trim();
    if (!text) { toast("Write what IRAS should remember first.", { icon: "info" }); box.focus(); return; }
    try {
      await api("/v1/v5/memory", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, namespace: "default", kind: "note", source: "web" }) });
      box.value = "";
      toast("Saved to memory.", { icon: "check" });
      loadReal("");
    } catch (err) { toast("Could not save it. " + err.message, { icon: "cloud-off", timeout: 7000 }); }
  }

  /* ---------- layout ---------- */
  function tick(a) {
    for (let i = 0; i < nodes.length; i++) {
      const p = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const q = nodes[j];
        let dx = p.x - q.x, dy = p.y - q.y;
        const d2 = dx * dx + dy * dy + .01;
        const d = Math.sqrt(d2);
        const f = (12000 * a) / d2;
        dx /= d; dy /= d;
        const fx = dx * Math.min(f, 14), fy = dy * Math.min(f, 14);
        if (!p.pinned) { p.vx += fx; p.vy += fy; }
        if (!q.pinned) { q.vx -= fx; q.vy -= fy; }
      }
    }
    for (const e of edges) {
      const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = 124 + (e.a.type === "you" || e.b.type === "you" ? 16 : 0);
      const f = (d - L) * .045 * a;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      if (!e.a.pinned) { e.a.vx += fx; e.a.vy += fy; }
      if (!e.b.pinned) { e.b.vx -= fx; e.b.vy -= fy; }
    }
    for (const n of nodes) {
      if (n.pinned) { n.vx = n.vy = 0; continue; }
      n.vx += -n.x * .0035 * a; n.vy += -n.y * .006 * a;
      n.vx *= .82; n.vy *= .82;
      n.x += n.vx; n.y += n.vy;
    }
  }
  function settle(iter) { for (let i = 0; i < iter; i++) tick(Math.max(.05, 1 - i / iter)); }

  /* world to screen: fit the whole map with a margin */
  let view = { s: 1, ox: 0, oy: 0 };
  function fit() {
    if (!nodes.length || !W) return;
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (const n of nodes) { x0 = Math.min(x0, n.x - 60); x1 = Math.max(x1, n.x + 60); y0 = Math.min(y0, n.y - 34); y1 = Math.max(y1, n.y + 40); }
    const s = Math.min(W / (x1 - x0), (H - 28) / (y1 - y0), 2.2);
    view = { s, ox: W / 2 - ((x0 + x1) / 2) * s, oy: (H - 22) / 2 - ((y0 + y1) / 2) * s };
  }
  const toScreen = (n) => [n.x * view.s + view.ox, n.y * view.s + view.oy];
  const toWorld = (px, py) => [(px - view.ox) / view.s, (py - view.oy) / view.s];

  /* ---------- drawing ---------- */
  function shape(n, x, y, r) {
    g.beginPath();
    switch (n.type) {
      case "device": { const s = r * 1.55, rad = 5; g.roundRect ? g.roundRect(x - s / 2, y - s / 2, s, s, rad) : g.rect(x - s / 2, y - s / 2, s, s); break; }
      case "project": { for (let i = 0; i < 6; i++) { const a = (Math.PI / 3) * i - Math.PI / 6; const px = x + Math.cos(a) * r * 1.1, py = y + Math.sin(a) * r * 1.1; i ? g.lineTo(px, py) : g.moveTo(px, py); } g.closePath(); break; }
      case "preference": { g.moveTo(x, y - r * 1.15); g.lineTo(x + r * 1.15, y); g.lineTo(x, y + r * 1.15); g.lineTo(x - r * 1.15, y); g.closePath(); break; }
      default: g.arc(x, y, r, 0, Math.PI * 2);
    }
  }
  const matches = (n) => !query || searched || (n.label + " " + (n.detail || "")).toLowerCase().includes(query);
  const connected = (n, m) => edges.some((e) => (e.a === n && e.b === m) || (e.a === m && e.b === n));

  function draw() {
    if (!g || !W) return;
    g.clearRect(0, 0, W, H);
    const focus = drag || hover || selected;
    for (const e of edges) {
      const [x1, y1] = toScreen(e.a), [x2, y2] = toScreen(e.b);
      const on = focus && (e.a === focus || e.b === focus);
      const hit = query && matches(e.a) && matches(e.b);
      g.strokeStyle = on || hit ? col.accent : col.line;
      g.globalAlpha = on || hit ? .9 : query ? .25 : .75;
      g.lineWidth = on || hit ? 2 : 1.2;
      g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    }
    g.globalAlpha = 1;
    g.textAlign = "center"; g.textBaseline = "top";
    g.font = `500 12px "Instrument Sans", "Segoe UI", system-ui, sans-serif`;
    for (const n of nodes) {
      const [x, y] = toScreen(n);
      const r = n.r * Math.min(1.25, Math.max(.8, view.s));
      const dim = query ? !matches(n) : focus && n !== focus && !connected(n, focus);
      g.globalAlpha = dim ? .28 : 1;
      if (n === selected || (query && matches(n))) { g.fillStyle = col.soft; g.beginPath(); g.arc(x, y, r + 9, 0, Math.PI * 2); g.fill(); }
      shape(n, x, y, r);
      if (n.type === "you") { g.fillStyle = col.fill; g.fill(); g.lineWidth = 2; g.strokeStyle = col.bg; g.stroke(); }
      else if (n.type === "device" || n.type === "project") { g.fillStyle = col.soft; g.fill(); g.lineWidth = 1.8; g.strokeStyle = col.accent; g.stroke(); }
      else { g.fillStyle = col.bg; g.fill(); g.lineWidth = 1.8; g.strokeStyle = n === selected || n === hover ? col.accent : col.muted; g.stroke(); }
      if (n.type === "model") { g.beginPath(); g.arc(x, y, r * .45, 0, Math.PI * 2); g.fillStyle = col.accent; g.fill(); }
      if (n === selected) { g.lineWidth = 2.5; g.strokeStyle = col.accent; shape(n, x, y, r + 4); g.stroke(); }
      const label = n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label;
      g.lineWidth = 4; g.strokeStyle = col.bg; g.lineJoin = "round";
      g.strokeText(label, x, y + r + 6);
      g.fillStyle = col.text; g.fillText(label, x, y + r + 6);
    }
    g.globalAlpha = 1;
  }

  function loop() {
    raf = 0;
    if (IRAS.view() !== "memory" || document.hidden) return;
    if (alpha > .02 || drag) { tick(Math.max(alpha, drag ? .3 : 0)); alpha *= .965; fit(); draw(); raf = requestAnimationFrame(loop); }
    else draw();
  }
  function reheat(a = .5) { alpha = Math.max(alpha, a); if (!raf) raf = requestAnimationFrame(loop); }

  function resize() {
    const r = wrap.getBoundingClientRect();
    if (!r.width) return;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.round(r.width); H = Math.round(r.height);
    canvas.width = W * dpr; canvas.height = H * dpr;
    g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    fit(); draw();
  }

  /* ---------- pointer ---------- */
  function pick(px, py) {
    let best = null, bd = 1e9;
    for (const n of nodes) {
      const [x, y] = toScreen(n);
      const d = Math.hypot(px - x, py - y);
      if (d < n.r * Math.min(1.25, Math.max(.8, view.s)) + 8 && d < bd) { best = n; bd = d; }
    }
    return best;
  }
  const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  let moved = 0, downAt = null;
  canvas.addEventListener("pointerdown", (e) => {
    const [px, py] = local(e);
    const n = pick(px, py);
    downAt = [px, py]; moved = 0;
    if (n) { drag = n; n.pinned = true; canvas.setPointerCapture(e.pointerId); canvas.classList.add("is-drag"); reheat(.3); }
  });
  canvas.addEventListener("pointermove", (e) => {
    const [px, py] = local(e);
    if (drag) {
      moved = Math.hypot(px - downAt[0], py - downAt[1]);
      const [wx, wy] = toWorld(px, py);
      drag.x = wx; drag.y = wy;
      return;
    }
    const n = pick(px, py);
    if (n !== hover) { hover = n; canvas.classList.toggle("is-hover", !!n); draw(); }
  });
  const up = () => {
    if (!drag) return;
    const n = drag;
    drag = null;
    canvas.classList.remove("is-drag");
    if (moved < 5) select(n.id); else n.pinned = false;
    if (moved < 5) n.pinned = false;
    reheat(.2);
  };
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", up);
  canvas.addEventListener("pointerleave", () => { if (!drag && hover) { hover = null; canvas.classList.remove("is-hover"); draw(); } });

  /* ---------- selection, card, list ---------- */
  function select(id) {
    selected = nodes.find((n) => n.id === id) || null;
    renderCard();
    renderList();
    draw();
  }
  function renderCard() {
    const card = $("#nodeCard");
    const n = selected;
    if (!n) { card.innerHTML = `<h2 class="h3" id="nodeTitle">Nothing selected</h2><p class="muted">Click something on the map, or pick it from the list, to see what IRAS knows and how it is connected.</p>`; return; }
    const links = edges.filter((e) => e.a === n || e.b === n).map((e) => (e.a === n ? e.b : e.a));
    card.innerHTML = `<div class="node-head"><span class="ico-tile">${icon(KIND_ICON[n.type])}</span><div><h2 id="nodeTitle">${esc(n.label)}</h2><div class="node-kind">${KIND[n.type]}</div></div></div>
      <p>${esc(n.detail || "")}</p>
      ${links.length ? `<div><p class="label">Connected to</p><div class="links">${links.map((l) => `<button type="button" class="link-chip" data-go="${esc(l.id)}">${esc(l.label)}</button>`).join("")}</div></div>` : ""}
      ${n.type === "you" ? "" : `<div><button type="button" class="btn sm" data-forget="${esc(n.id)}">${icon("trash-2", "i-sm")}<span>Forget this</span></button></div>`}`;
  }
  function renderList() {
    const host = $("#memList");
    const groups = {};
    nodes.filter(matches).forEach((n) => (groups[n.type] = groups[n.type] || []).push(n));
    const order = ["you", "device", "service", "project", "model", "preference"];
    host.innerHTML = order.filter((t) => groups[t]).map((t) => `<div class="mem-group"><h3>${KIND[t]}${groups[t].length > 1 && t !== "you" ? "s" : ""}</h3>` +
      groups[t].map((n) => `<button type="button" class="mem-item" data-go="${esc(n.id)}" aria-pressed="${selected === n}">${icon(KIND_ICON[t], "i-sm")}<div><strong>${esc(n.label)}</strong><span>${esc(n.detail || "")}</span></div></button>`).join("") + `</div>`).join("") || `<p class="muted">Nothing matches.</p>`;
  }

  function renderStats() {
    const n = Math.max(0, nodes.length - 1);
    $("#memStats").innerHTML = [
      ["Things remembered", String(n), n >= 60 ? "the latest 60 are shown" : "facts, habits and notes", "brain"],
      ["Newest", newest ? relTime(newest) : "none yet", "when it was saved", "clock"],
      ["Saved in", ($("#chipStoreText") || {}).textContent || "Unknown", "see the top bar", "cloud"],
    ].map(([l, v, sub, ic]) => `<div class="stat"><div class="stat-label">${icon(ic, "i-sm")}${l}</div><div class="stat-num num">${esc(v)}</div><div class="stat-sub">${sub}</div></div>`).join("");
  }

  function setStatus() {
    const el = $("#memStatus");
    if (!query) { el.textContent = ""; return; }
    const m = nodes.filter((n) => n.type !== "you" && matches(n));
    el.textContent = m.length ? `${m.length} ${m.length === 1 ? "memory matches" : "memories match"}: ${m.slice(0, 4).map((n) => n.label).join(", ")}${m.length > 4 ? "…" : ""}` : "Nothing in memory matches that.";
  }

  /* ---------- events ---------- */
  document.addEventListener("click", (e) => {
    if (IRAS.view() !== "memory") return;
    const go = e.target.closest("[data-go]");
    if (go) { select(go.dataset.go); return; }
    const forget = e.target.closest("[data-forget]");
    if (forget) forgetReal(forget.dataset.forget);
  });
  let timer = 0;
  $("#memSearch").addEventListener("input", (e) => {
    query = e.target.value.trim().toLowerCase(); setStatus(); renderList(); draw();
    clearTimeout(timer); timer = setTimeout(() => loadReal(e.target.value.trim()), 350);
  });
  $$("input[name='memView']").forEach((r) => r.addEventListener("change", () => {
    const list = r.value === "list";
    $("#graphWrap").hidden = list; $("#memList").hidden = !list;
    if (!list) { resize(); reheat(.1); }
  }));
  $("#graphReset").addEventListener("click", () => { nodes.forEach((n) => { n.pinned = false; }); reheat(.9); });

  IRAS.initMemory = function () {
    readColors();
    nodes = [mk(YOU, 0, 1)]; edges = [];
    renderStats(); renderCard(); renderList();
    $("#memAdd").addEventListener("click", addReal);
    $("#graphLegend").innerHTML = [["circle", "You, apps"], ["square", "Devices"], ["hex", "Projects"], ["diamond", "Preferences"]].map(([s, t]) => {
      const shapeSvg = s === "circle" ? '<circle cx="8" cy="8" r="5.5"/>' : s === "square" ? '<rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/>' : s === "hex" ? '<path d="M8 1.5l5.6 3.2v6.6L8 14.5l-5.6-3.2V4.7z"/>' : '<path d="M8 1.5l6.5 6.5L8 14.5 1.5 8z"/>';
      return `<li><svg viewBox="0 0 16 16">${shapeSvg}</svg>${t}</li>`;
    }).join("");
    new ResizeObserver(() => { if (IRAS.view() === "memory") resize(); }).observe(wrap);
    bus.on("view", (e) => { if (e.view === "memory") { readColors(); resize(); renderStats(); loadReal(query); if (!IRAS.env.reduceMotion) { alpha = .15; } loop(); } });
    bus.on("appearance", () => { readColors(); draw(); });
  };
})();
