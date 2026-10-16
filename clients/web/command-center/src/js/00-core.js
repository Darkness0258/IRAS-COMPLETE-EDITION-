/* ==========================================================================
   IRAS Command Center · core
   The UI only renders state. It never guesses. Everything that changes the
   screen arrives as an event on one bus, and a small state machine decides
   which transitions are legal, so impossible states (listening while
   speaking) cannot happen.
   ========================================================================== */
"use strict";

const IRAS = (window.IRAS = window.IRAS || {});

/* ---------- helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const rand = (a, b) => a + Math.random() * (b - a);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "") => `<svg class="i ${cls}" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
const uid = (p = "id") => p + "_" + Math.random().toString(36).slice(2, 9);
const fmtTime = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const fmtDur = (ms) => (ms < 950 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(ms < 10000 ? 1 : 0) + " s");
const relTime = (ts) => {
  const d = Math.max(0, Date.now() - ts);
  if (d < 45e3) return "just now";
  if (d < 90e3) return "1 min ago";
  if (d < 3.6e6) return Math.round(d / 6e4) + " min ago";
  if (d < 5.4e6) return "1 hour ago";
  if (d < 864e5) return Math.round(d / 3.6e6) + " hours ago";
  return "yesterday";
};

/* a sleep that can be cancelled by an AbortSignal */
const sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    if (signal && signal.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const t = setTimeout(resolve, ms);
    if (signal) signal.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
  });

/* storage that never throws (file:// and private windows can block it) */
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  sget(k, d) { try { const v = sessionStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
  sset(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};

/* ---------- settings ---------- */
const SETTINGS_KEY = "iras-cc-settings";
const DEFAULTS = {
  theme: "auto",          // auto | dark | light
  skin: "cobalt",         // cobalt | neon
  perf: "auto",           // auto | full | lite
  motion: "system",       // system | reduce
  source: "demo",         // demo | live
  server: "",
  voiceProfile: "iras_human",
  mood: "warm",
  language: "roman-urdu",
  wake: "IRAS",
  realMic: true,
  speakReplies: true,
};
const settings = Object.assign({}, DEFAULTS, store.get(SETTINGS_KEY, {}));
const saveSettings = () => store.set(SETTINGS_KEY, settings);
IRAS.settings = settings;

/* ---------- event bus ---------- */
const bus = {
  handlers: new Map(),
  log: [],
  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
    return () => this.off(type, fn);
  },
  off(type, fn) {
    const list = this.handlers.get(type);
    if (list) this.handlers.set(type, list.filter((f) => f !== fn));
  },
  emit(type, data = {}) {
    const ev = Object.assign({ type, ts: Date.now() }, data);
    if (type !== "audio_level") { this.log.push(ev); if (this.log.length > 600) this.log.shift(); }
    for (const key of [type, "*"]) {
      const list = this.handlers.get(key);
      if (!list) continue;
      for (const fn of list.slice()) {
        try { fn(ev); } catch (err) { console.error("[IRAS] handler failed for", type, err); }
      }
    }
    return ev;
  },
};
IRAS.bus = bus;

/* The same function a live backend adapter calls for every event it receives. */
IRAS.ingest = (evt) => { if (evt && evt.type) bus.emit(evt.type, evt); };

/* ---------- view model ---------- */
const S = {
  ui: "idle",
  authority: null,          // "system" | "critical" while waiting for approval
  caption: "",
  heard: "",
  heardVia: "voice",
  level: { mic: 0, tts: 0 },
  provider: { active: "Gemini", fallbacks: ["OpenRouter", "Cerebras", "Groq", "Ollama (this PC)"], note: "" },
  mic: "off",               // off | on | blocked
  cam: "off",
  sync: { state: "synced", at: Date.now() - 2 * 60e3 },
  pending: null,            // current approval request
  busy: false,
};
IRAS.S = S;

/* ---------- state machine ---------- */
const ALLOWED = {
  idle:      ["listening", "thinking", "acting", "speaking", "approval"],
  listening: ["thinking", "idle", "approval"],
  thinking:  ["acting", "speaking", "approval", "idle", "listening"],
  acting:    ["thinking", "speaking", "approval", "idle"],
  speaking:  ["idle", "listening", "thinking", "approval"],
  approval:  ["acting", "thinking", "speaking", "idle"],
};
const fsm = {
  resumeTo: "thinking",
  to(next, meta = {}) {
    const prev = S.ui;
    if (next === prev) return true;
    if (!ALLOWED[prev] || !ALLOWED[prev].includes(next)) {
      console.warn(`[IRAS] blocked impossible transition ${prev} to ${next}`);
      bus.emit("invalid_transition", { from: prev, to: next });
      return false;
    }
    if (next === "approval") { this.resumeTo = prev === "idle" ? "thinking" : prev; }
    S.ui = next;
    S.busy = next !== "idle";
    document.body.dataset.uiState = next;
    if (next === "approval") document.body.dataset.authority = meta.authority || S.authority || "system";
    else delete document.body.dataset.authority;
    bus.emit("ui", { from: prev, to: next, meta });
    return true;
  },
};
IRAS.fsm = fsm;

/* the backend can say "state" directly; the machine still has the final word */
bus.on("state", (e) => fsm.to(e.state, e));
bus.on("wake", () => { fsm.to("listening"); });
bus.on("speech_end", () => { fsm.to("thinking"); });
bus.on("submit", () => { if (S.ui === "idle" || S.ui === "speaking" || S.ui === "listening") fsm.to("thinking"); });
bus.on("tts_start", () => { fsm.to("speaking"); });
bus.on("tts_end", () => { if (S.ui === "speaking") fsm.to("idle"); });
bus.on("done", () => { if (S.ui !== "approval") fsm.to("idle"); });
bus.on("error", () => { if (S.ui !== "idle") fsm.to("idle"); });
bus.on("cancel", () => { if (S.ui !== "idle") fsm.to("idle"); });
bus.on("approval_request", (e) => {
  S.pending = e;
  S.authority = e.authority === "critical" ? "critical" : "system";
  fsm.to("approval", { authority: S.authority });
});
bus.on("approval_result", (e) => {
  S.pending = null;
  S.authority = null;
  if (e.decision === "approve") fsm.to(fsm.resumeTo === "approval" ? "acting" : fsm.resumeTo);
  else fsm.to("idle");
});

/* ---------- announcer, toasts ---------- */
let lastAnnounce = "";
function announce(text) {
  const el = $("#announcer");
  if (!el || text === lastAnnounce) return;
  lastAnnounce = text;
  el.textContent = "";
  requestAnimationFrame(() => { el.textContent = text; });
}

function toast(message, opts = {}) {
  const host = $("#toasts");
  if (!host) return;
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.innerHTML = `${icon(opts.icon || "info", "i-sm")}<span>${esc(message)}</span>`;
  if (opts.action) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "toast-act";
    b.textContent = opts.action.label;
    b.addEventListener("click", () => { opts.action.fn(); dismiss(); });
    el.appendChild(b);
  }
  host.appendChild(el);
  while (host.children.length > 3) host.firstElementChild.remove();
  const dismiss = () => {
    if (!el.isConnected) return;
    el.classList.add("out");
    setTimeout(() => el.remove(), 220);
  };
  setTimeout(dismiss, opts.timeout || 4800);
}
IRAS.toast = toast;
IRAS.announce = announce;

/* ---------- appearance: theme, skin, performance, motion ---------- */
const mqLight = window.matchMedia("(prefers-color-scheme: light)");
const mqReduce = window.matchMedia("(prefers-reduced-motion: reduce)");
const env = { theme: "dark", skin: "cobalt", perf: "full", reduceMotion: false, autoLite: false };
IRAS.env = env;

function applyAppearance(silent) {
  const root = document.documentElement;
  env.theme = settings.theme === "auto" ? (mqLight.matches ? "light" : "dark") : settings.theme;
  env.skin = settings.skin === "neon" ? "neon" : "cobalt";
  env.perf = settings.perf === "lite" ? "lite" : settings.perf === "full" ? "full" : (env.autoLite ? "lite" : "full");
  env.reduceMotion = settings.motion === "reduce" || mqReduce.matches;
  root.dataset.theme = env.theme;
  root.dataset.skin = env.skin;
  root.dataset.perf = env.perf;
  if (settings.motion === "reduce") root.dataset.motion = "reduce"; else delete root.dataset.motion;
  const meta = $('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", env.theme === "light" ? "#EEF3FB" : "#04070F");
  const tb = $("#themeBtn");
  if (tb) tb.innerHTML = icon(env.theme === "light" ? "sun" : "moon");
  if (!silent) bus.emit("appearance", { ...env });
}
IRAS.applyAppearance = applyAppearance;
mqLight.addEventListener && mqLight.addEventListener("change", () => { if (settings.theme === "auto") applyAppearance(); });
mqReduce.addEventListener && mqReduce.addEventListener("change", () => applyAppearance());

function setSetting(key, value, { silent } = {}) {
  settings[key] = value;
  saveSettings();
  if (["theme", "skin", "perf", "motion"].includes(key)) {
    if (key === "perf") env.autoLite = false;
    applyAppearance();
  }
  if (!silent) bus.emit("setting", { key, value });
}
IRAS.setSetting = setSetting;

/* pause every loop while the window is hidden */
document.addEventListener("visibilitychange", () => {
  document.documentElement.dataset.hidden = document.hidden ? "1" : "0";
  bus.emit("visibility", { hidden: document.hidden });
});

/* ---------- audit store: one list that Live activity and Activity both render ---------- */
const audit = {
  items: [],
  byId: new Map(),
  add(item) {
    const it = Object.assign({ id: uid("act"), ts: Date.now(), kind: "tool", status: "done", authority: "none", title: "", detail: "", tags: [], ms: 0, payload: null }, item);
    this.items.unshift(it);
    this.byId.set(it.id, it);
    bus.emit("audit:add", { item: it });
    return it;
  },
  update(id, patch) {
    const it = this.byId.get(id);
    if (!it) return null;
    Object.assign(it, patch);
    bus.emit("audit:update", { item: it });
    return it;
  },
};
IRAS.audit = audit;

/* tool, agent, approval and provider events become audit rows */
bus.on("tool_start", (e) => {
  audit.add({
    id: e.id, kind: "tool", status: "running", authority: e.authority || "none",
    title: e.title || e.tool, detail: e.detail || "", tags: [e.tool].filter(Boolean),
    payload: { tool: e.tool, args: e.args || {} },
  });
});
bus.on("tool_end", (e) => {
  const it = audit.byId.get(e.id);
  if (!it) return;
  const payload = Object.assign({}, it.payload || {}, { ok: e.ok !== false, result: e.result || null });
  audit.update(e.id, {
    status: e.ok === false ? "failed" : "done",
    ms: e.ms || (Date.now() - it.ts),
    detail: e.detail || it.detail,
    title: e.title || it.title,
    payload,
  });
});
bus.on("agent_step", (e) => {
  const id = "run_" + e.run;
  let it = audit.byId.get(id);
  const label = e.step && e.step.label ? e.step.label : "";
  if (!it) {
    it = audit.add({ id, kind: "agent", status: "running", title: e.title || "Agent task", detail: label, tags: ["/" + e.agent], payload: { agent: e.agent, steps: [], progress: 0 } });
  }
  const steps = it.payload.steps;
  const sid = e.step && e.step.id;
  let st = steps.find((x) => x.id === sid);
  if (!st) { st = { id: sid, label, status: "running", detail: "" }; steps.push(st); }
  st.status = e.stepStatus || (e.status === "failed" ? "failed" : e.status === "done" ? "done" : "running");
  st.detail = e.detail || st.detail;
  if (e.total) it.payload.progress = clamp((e.index + (e.status === "running" ? .4 : 1)) / e.total, 0, 1);
  audit.update(id, {
    status: e.final ? (e.status === "failed" ? "failed" : "done") : "running",
    detail: e.final ? (e.summary || label) : label + "…",
    ms: Date.now() - it.ts,
  });
});
bus.on("approval_request", (e) => {
  audit.add({
    id: "ap_" + e.id, kind: "approval", status: "waiting", authority: e.authority,
    title: "Waiting for your approval", detail: e.title, tags: ["approval"], payload: { request: e.id, effects: e.effects || [] },
  });
});
bus.on("approval_result", (e) => {
  const it = audit.byId.get("ap_" + e.id);
  if (!it) return;
  const approved = e.decision === "approve";
  audit.update("ap_" + e.id, {
    status: approved ? "done" : "denied",
    title: approved ? "You approved this" : e.decision === "expired" ? "Approval expired. Nothing changed" : "You denied this",
    ms: Date.now() - it.ts,
    payload: Object.assign({}, it.payload, { decision: e.decision, via: e.via || "button" }),
  });
});
bus.on("provider", (e) => {
  if (e.active) {
    const from = S.provider.active;
    S.provider.active = e.active;
    S.provider.note = e.reason || "";
    if (e.failover) {
      audit.add({ kind: "system", status: "done", title: `Switched AI provider to ${e.active}`, detail: e.reason || `${from} was too slow`, tags: ["failover"], payload: { from, to: e.active, reason: e.reason || "" } });
    }
  }
});

/* ---------- router ---------- */
const VIEWS = ["home", "chat", "agents", "activity", "memory", "identity", "settings"];
const VIEW_TITLES = { home: "Home", chat: "Conversation", agents: "Agents", activity: "Activity", memory: "Memory", identity: "Identity", settings: "Settings" };
let currentView = null;

function showView(name, { first } = {}) {
  if (!VIEWS.includes(name)) name = "home";
  const changed = name !== currentView;
  currentView = name;
  $$(".view").forEach((sec) => {
    const on = sec.dataset.view === name;
    sec.hidden = !on;
    if (on && changed && !first && !env.reduceMotion) { sec.classList.remove("is-entering"); void sec.offsetWidth; sec.classList.add("is-entering"); }
  });
  $$(".nav-item").forEach((a) => {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const stage = $("#stage");
  if (stage) stage.dataset.view = name;
  const sub = $("#brandSub");
  if (sub) sub.textContent = name === "home" ? "Command Center" : VIEW_TITLES[name];
  document.title = (name === "home" ? "" : VIEW_TITLES[name] + " · ") + "IRAS Command Center";
  if (changed) { announce(VIEW_TITLES[name]); bus.emit("view", { view: name }); }
}
function routeFromHash(first) {
  const name = (location.hash || "").replace(/^#\/?/, "").split("?")[0] || "home";
  showView(name, { first });
}
window.addEventListener("hashchange", () => routeFromHash(false));
IRAS.go = (name) => { if (location.hash !== "#/" + name) location.hash = "#/" + name; else showView(name); };
IRAS.view = () => currentView;
IRAS.routeFromHash = routeFromHash;

/* dialogs: only the dialog blurs while one is open */
function openDialog(dlg) {
  if (!dlg || dlg.open) return;
  dlg.showModal();
  document.body.dataset.modal = "1";
}
function closeDialog(dlg) { if (dlg && dlg.open) dlg.close(); }
document.addEventListener("close", (e) => {
  if (e.target instanceof HTMLDialogElement && !$$("dialog[open]").length) delete document.body.dataset.modal;
}, true);
IRAS.openDialog = openDialog;
IRAS.closeDialog = closeDialog;
