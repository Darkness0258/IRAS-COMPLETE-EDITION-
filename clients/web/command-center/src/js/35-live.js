/* ==========================================================================
   Live source (experimental).

   Talks to a real IRAS server with the endpoints the classic web client
   already uses:

     GET  /health                 service, version
     GET  /v1/providers/status    active_provider, fallback_order
     POST /v1/chat/stream         Server-Sent Events: start, queued, token, done, error

   It translates those into the same bus events the demo emits, so no screen
   changes. The access token lives in sessionStorage under the same key the
   classic client uses, and is never written to localStorage.
   ========================================================================== */
"use strict";

(function () {
  const live = { ctrl: null, ok: false };
  IRAS.live = live;

  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  const headers = (extra = {}) => Object.assign({ "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}, extra);
  const rawGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const rawSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };
  const clientId = () => { let v = rawGet("iras-cloud-client-id"); if (!v) { v = uid("web"); rawSet("iras-cloud-client-id", v); } return v; };
  const threadId = () => rawGet("iras-cloud-thread-id") || "";
  const BRAND = { gemini: "Gemini", openrouter: "OpenRouter", cerebras: "Cerebras", groq: "Groq", ollama: "Ollama", openai: "OpenAI", anthropic: "Anthropic", mistral: "Mistral", deepseek: "DeepSeek", nvidia: "NVIDIA", github: "GitHub", huggingface: "Hugging Face", together: "Together", xai: "xAI" };
  const pretty = (n) => { const k = String(n || "").toLowerCase().replace(/[^a-z0-9]/g, ""); return BRAND[k] || String(n || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); };

  live.test = async function () {
    const b = base();
    if (!b) return { ok: false, message: "Add your server address first." };
    try {
      const r = await fetch(b + "/health", { headers: headers() });
      if (!r.ok) return { ok: false, message: `The server answered ${r.status}.` };
      const j = await r.json().catch(() => ({}));
      let provider = null, note = "";
      try {
        const pr = await fetch(b + "/v1/providers/status", { headers: headers() });
        if (pr.ok) provider = await pr.json();
        else if (pr.status === 401 || pr.status === 403) note = " The access token was refused, so chat will not work yet.";
      } catch (e) { /* provider status is optional */ }
      return { ok: !note, partial: !!note, message: `Reached ${j.service || "IRAS"}${j.version ? " " + j.version : ""}.${note}`, provider };
    } catch (e) {
      return { ok: false, message: "Could not reach the server. Check the address, and that the server allows this page (CORS)." };
    }
  };

  live.connect = async function () {
    if (settings.source !== "live") return { ok: false };
    bus.emit("sync", { state: "syncing" });
    const res = await live.test();
    live.ok = !!res.ok;
    bus.emit("sync", { state: res.ok || res.partial ? "synced" : "offline" });
    live.checkStorage();
    if (res.provider) {
      const p = res.provider;
      const active = pretty(p.active_provider || (p.providers || []).find((x) => x.active)?.name);
      if (active) {
        S.provider.fallbacks = (p.fallback_order || []).map(pretty).filter((n) => n !== active);
        bus.emit("provider", { active });
      }
    }
    return res;
  };

  live.cancel = function () { if (live.ctrl) { live.ctrl.abort(); live.ctrl = null; } };

  /* one chat turn over Server-Sent Events */
  live.send = async function (text) {
    const b = base();
    if (!b) {
      toast("Add your server address in Settings first.", { icon: "server", action: { label: "Open settings", fn: () => IRAS.go("settings") }, timeout: 7000 });
      bus.emit("cancel", {});
      return;
    }
    live.cancel();
    const ctrl = new AbortController();
    live.ctrl = ctrl;
    const t0 = performance.now();
    const item = audit.add({ kind: "tool", status: "running", title: "Sent your message to IRAS", detail: text.slice(0, 120), tags: ["chat"], payload: { tool: "chat.stream", args: { chars: text.length } } });
    let done = null;
    const handle = (raw) => {
      let ev = "message";
      const data = [];
      raw.split("\n").forEach((line) => {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      });
      if (!data.length) return;
      let d = {};
      try { d = JSON.parse(data.join("\n")); } catch (e) { d = { text: data.join("\n") }; }
      if (ev === "start") { if (d.thread_id) rawSet("iras-cloud-thread-id", d.thread_id); bus.emit("caption", { text: "IRAS is working on it…" }); }
      else if (ev === "queued") bus.emit("caption", { text: `Waiting in line, ${((d.waited_ms || 0) / 1000).toFixed(1)} s…` });
      else if (ev === "token") bus.emit("token", { text: d.text || "" });
      else if (ev === "done") { done = d; if (d.thread_id) rawSet("iras-cloud-thread-id", d.thread_id); }
      else if (ev === "error") throw new Error(d.message || "The server reported an error.");
    };
    try {
      const res = await fetch(b + "/v1/chat/stream", {
        method: "POST",
        headers: headers({ "Content-Type": "application/json", Accept: "text/event-stream" }),
        body: JSON.stringify({ message: text, device_id: "web", client_id: clientId(), thread_id: threadId(), turn_id: uid("turn") }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error(res.status === 401 || res.status === 403 ? "The server refused the access token." : `The server answered ${res.status}.`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done: fin } = await reader.read();
        if (fin) break;
        buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) { const raw = buf.slice(0, i); buf = buf.slice(i + 2); handle(raw); }
      }
      if (buf.trim()) handle(buf);
      const ms = Math.round(performance.now() - t0);
      audit.update(item.id, { status: "done", ms, detail: text.slice(0, 120) });
      bus.emit("done", { timing_ms: ms });
      if (done && done.execution_mode === "authorization_required") {
        toast("This request needs your approval. It opens here in a moment.", { icon: "shield", timeout: 6000 });
        setTimeout(() => IRAS.pollApprovals && IRAS.pollApprovals(), 700);
      }
    } catch (err) {
      if (err && err.name === "AbortError") { audit.update(item.id, { status: "failed", detail: "Stopped by you" }); return; }
      const msg = err && err.message && err.message !== "Failed to fetch" ? err.message : "Could not reach the server.";
      audit.update(item.id, { status: "failed", detail: msg });
      bus.emit("error", { message: msg });
      toast(msg, { icon: "cloud-off", timeout: 7000 });
    } finally {
      if (live.ctrl === ctrl) live.ctrl = null;
    }
  };

  /* where is memory saved: a cloud database (shared) or only on this server? */
  live.checkStorage = async function () {
    const chip = $("#chipStore"), txt = $("#chipStoreText");
    if (!chip || !txt) return;
    const show = (label, tip, warn) => { txt.textContent = label; chip.title = tip; chip.classList.toggle("chip-demo", !!warn); };
    try {
      const r = await fetch(base() + "/ready", { headers: headers() });
      const j = await r.json();
      if (j.database === "postgres" && j.database_ok !== false) show("Cloud database", "Memory is saved in your cloud database and shared between your devices.", false);
      else show("Local only", String(j.database_help || "Memory is kept on this server only. It is lost when the server restarts and is not shared between devices.").slice(0, 220), true);
    } catch (e) { show("Storage unknown", "Could not read the server status.", true); }
  };

  /* switch between sample data and the real server */
  IRAS.applySource = function () {
    const on = settings.source === "live";
    document.body.dataset.source = on ? "live" : "demo";
    if (IRAS.sim) IRAS.sim.cancel();
    live.cancel();
    audit.items.length = 0;
    audit.byId.clear();
    if (!on) IRAS.seedAudit();
    bus.emit("audit:reset", {});
    if (IRAS.renderLive) IRAS.renderLive();
    if (on) live.connect();
    else { S.provider.active = "Gemini"; S.provider.fallbacks = ["OpenRouter", "Cerebras", "Groq", "Ollama (this PC)"]; bus.emit("provider", { active: "Gemini" }); bus.emit("sync", { state: "synced" }); }
  };

  IRAS.initLive = function () {
    /* pick up the classic client's server address the first time */
    if (!settings.server) {
      try {
        const c = JSON.parse(rawGet("iras-config") || "null");
        if (c && c.server) settings.server = c.server;
      } catch (e) { /* ignore */ }
    }
    /* served by IRAS itself: use the same address, nothing to type */
    if (!settings.server && /^https?:$/.test(location.protocol)) settings.server = location.origin;
    settings.source = "live";
    saveSettings();
    IRAS.applySource();
    setInterval(() => { if (!document.hidden) live.checkStorage(); }, 60000);
  };
})();
