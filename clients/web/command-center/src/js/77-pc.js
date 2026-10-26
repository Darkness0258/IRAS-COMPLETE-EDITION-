/* ==========================================================================
   Your PC: the old page's remote tools, in the new screen.

     GET    /v1/devices                  which of your computers is online
     GET    /v1/remote/policy            the highest session this server allows, and what each action needs
     POST   /v1/remote/sessions          start a session   { device_id, mode, ttl_seconds, scopes }
     DELETE /v1/remote/sessions/{id}     end it
     POST   /v1/remote/invoke            one action on the PC. Sent with the session token only.

   The same rules as the old page:
   - A session is the only way in. You start it here, you can see it, and you can end it.
   - Look only < Control < Full. Your server's limit and the PC's own rules still have the last word.
   - The session token stays in this window (sessionStorage), under the key the old page uses.
   - Master Control can only be turned on at the PC. Nothing here can do it.
   - Nothing from your PC stays on screen after you leave this screen or end the session.
   ========================================================================== */
"use strict";

(function () {
  const KEY = "iras-remote-session";
  /* what each session level can reach: 0 READ, 2 SYSTEM_ACTION, 3 CRITICAL */
  const MODES = {
    read_only: { name: "Look only", rank: 0, can: "see the screen and read files and settings, but change nothing" },
    control: { name: "Control", rank: 2, can: "see the screen, open apps, type, click and write files" },
    full: { name: "Full", rank: 3, can: "do everything, including running commands, deleting files, installing programs and powering off" },
  };
  const LEVELS = { READ: 0, SAFE_ACTION: 1, SYSTEM_ACTION: 2, CRITICAL: 3 };
  const MODE_FOR = { READ: "read_only", SAFE_ACTION: "control", SYSTEM_ACTION: "control", CRITICAL: "full" };
  const LEVEL_WORD = { READ: "Look only", SAFE_ACTION: "Control", SYSTEM_ACTION: "Control", CRITICAL: "Full" };
  const MASTER_COMMAND = "iras --master-enable 30";

  let policy = null;        // { cap, modes, actions } from the server. null if the server is older: it still decides.
  let device = null;        // the online PC
  let working = false;      // a start, direct action or Master step is running
  let shotBusy = false;     // a screen picture is on its way
  let shotFails = 0;
  let tickId = 0, autoId = 0;
  let pending = null;       // the question that is open: a function that takes true or false

  const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const server = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const nowSec = () => Date.now() / 1000;
  const span = (sec) => {
    const m = Math.max(1, Math.round(sec / 60));
    if (m < 60) return m + (m === 1 ? " minute" : " minutes");
    const h = Math.round((m / 60) * 10) / 10;
    return h + (h === 1 ? " hour" : " hours");
  };
  const left = (s) => {
    const rem = Number(s.expires_at || 0) - nowSec();
    return rem < 60 ? "under 1 min left" : Math.ceil(rem / 60) + " min left";
  };
  const log = (title, detail) => { try { audit.add({ kind: "system", status: "done", title, detail, tags: ["remote", "pc"] }); } catch (e) { /* the log is a bonus */ } };

  /* ---------- the session ---------- */
  function readSession() {
    try {
      const v = JSON.parse(sessionStorage.getItem(KEY) || "null");
      return v && v.session_id && v.session_token ? v : null;
    } catch (e) { return null; }
  }

  function keepSession(s) {
    try {
      if (s) sessionStorage.setItem("iras-remote-session", JSON.stringify(s));
      else sessionStorage.removeItem(KEY);
    } catch (e) { /* a private window may refuse storage */ }
  }

  function activeSession() {
    const s = readSession();
    if (!s) return null;
    if (Number(s.expires_at || 0) && nowSec() >= Number(s.expires_at)) { keepSession(null); return null; }
    return s;
  }

  const isMaster = (s) => !!s && (s.scopes || []).map((x) => String(x).toLowerCase()).includes("master");
  const rankOf = (s) => (MODES[s.mode] ? MODES[s.mode].rank : 0);

  /* Turn the server's words into plain ones, and say what to do next. */
  function plain(message) {
    const m = String(message || "");
    if (/remote-session cap is/i.test(m)) return m + " To allow more, set IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL on your server (2 is Control, 3 is Full) and redeploy.";
    if (/invalid, expired, or revoked/i.test(m)) return "The session ended. Start a new one.";
    const need = /does not authorize (\w+) actions/i.exec(m);
    if (need) return "This session cannot do that. It needs " + (LEVEL_WORD[need[1]] || need[1]) + ". End this session and start a new one with more power, if your server allows it.";
    return m;
  }

  const hint = (t) => { $("#pcHint").textContent = t || ""; };

  /* ---------- asking you first ---------- */
  function askYou({ level = "system", title, body, bullets = [], confirm = "Allow" }) {
    const dlg = $("#pcAskDlg");
    if (pending) pending(false);
    return new Promise((resolve) => {
      dlg.dataset.level = level;
      $("#pcAskLevel").innerHTML = level === "critical" ? `${icon("shield-alert", "i-sm")}Critical. Be sure` : `${icon("shield", "i-sm")}Needs your OK`;
      $("#pcAskIcon").innerHTML = icon(level === "critical" ? "shield-alert" : "shield", "i-lg");
      $("#pcAskTitle").textContent = title;
      $("#pcAskDetail").textContent = body;
      $("#pcAskEffects").innerHTML = bullets.map((b) => `<li>${icon("circle-dot", "i-sm")}<span>${esc(b)}</span></li>`).join("");
      $("#pcAskOk").querySelector("span").textContent = confirm;
      pending = (v) => { pending = null; IRAS.closeDialog(dlg); resolve(v); };
      IRAS.openDialog(dlg);
      $("#pcAskNo").focus();  // the safe answer has the focus
    });
  }

  /* ---------- finding the PC and the server's limit ---------- */
  async function findDevice() {
    const r = await IRAS.api("/v1/devices");
    const all = (r && r.devices) || [];
    const online = all.filter((d) => d.online);
    device = online.find((d) => /windows/i.test(String(d.platform || ""))) || online[0] || null;
    renderDevice();
    return device;
  }

  async function loadPolicy() {
    try { policy = await IRAS.api("/v1/remote/policy"); } catch (e) { policy = null; }
    applyPolicy();
  }

  function applyPolicy() {
    $$('#pcModes input[name="pcMode"]').forEach((input) => {
      const allowed = !policy || !policy.modes || policy.modes[input.value] !== false;
      input.disabled = !allowed;
      const small = input.closest(".pc-mode").querySelector("small");
      if (!small.dataset.base) small.dataset.base = small.textContent;
      small.textContent = allowed ? small.dataset.base : "Your server does not allow this (its limit is " + (LEVEL_WORD[policy.cap] || policy.cap) + "). " + small.dataset.base;
      if (!allowed && input.checked) $('#pcModes input[value="read_only"]').checked = true;
    });
    $("#directActions").innerHTML = ((policy && policy.actions) || []).map((a) => `<option value="${esc(a.name)}"></option>`).join("");
    renderLevel();
  }

  function renderDevice() {
    $("#pcDevice").textContent = device ? device.display_name + " is online." : "No paired PC is online. Open the IRAS app on your Windows PC.";
  }

  async function refreshDevice() {
    try { await findDevice(); } catch (e) { device = null; $("#pcDevice").textContent = plain(e.message); }
  }

  /* ---------- starting and ending ---------- */
  async function startSession({ mode = "read_only", ttl = 1800, scopes = ["windows"], ask = true, master = false } = {}) {
    if (!device) await findDevice();
    if (!device) throw new Error("No paired IRAS computer is online. Open the IRAS app on your Windows PC.");
    if (policy && policy.modes && policy.modes[mode] === false) {
      throw new Error("Your server does not allow " + MODES[mode].name + " sessions (its limit is " + (LEVEL_WORD[policy.cap] || policy.cap) + "). To allow more, set IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL on your server (2 is Control, 3 is Full) and redeploy.");
    }
    if (ask) {
      const yes = await askYou(master ? {
        level: "critical",
        title: "Attach a Master session?",
        body: "This browser will carry Full authority from the PC's active Master Control into chat and direct actions. Critical tools may run without asking you each time. The PC's own rules still apply.",
        bullets: ["PC: " + device.display_name, "Level: Full, with Master", "Ends by itself after " + span(ttl)],
        confirm: "Attach",
      } : {
        level: mode === "full" ? "critical" : "system",
        title: "Start a " + MODES[mode].name + " session?",
        body: "For " + span(ttl) + ", this browser will be able to " + MODES[mode].can + " on " + device.display_name + ". The PC's own rules still have the last word, and you can end it at any time.",
        bullets: ["PC: " + device.display_name, "Level: " + MODES[mode].name, "Ends by itself after " + span(ttl)],
        confirm: "Start session",
      });
      if (!yes) return null;
    }
    const s = await IRAS.api("/v1/remote/sessions", json({ device_id: device.device_id, mode, ttl_seconds: ttl, scopes }));
    keepSession(s);
    tickOn();
    render();
    announce("Session started. " + MODES[s.mode].name + ".");
    log("Started a " + MODES[s.mode].name + " session" + (master ? " (Master)" : ""), s.device_name || device.display_name);
    return s;
  }

  async function endSession(quiet) {
    const s = readSession();
    if (!s) return;
    keepSession(null);          // gone from this window first, whatever the server says
    stopAuto();
    clearPrivate();
    render();
    try {
      await IRAS.api("/v1/remote/sessions/" + encodeURIComponent(s.session_id), { method: "DELETE" });
      if (!quiet) toast("Session ended.", { icon: "shield-check" });
    } catch (e) {
      toast("The session is gone from this window, but the server could not confirm it. It ends by itself when its time is up.", { icon: "triangle-alert", timeout: 8000 });
    }
    announce("Session ended.");
    log("Ended a " + (MODES[s.mode] ? MODES[s.mode].name : "remote") + " session" + (isMaster(s) ? " (Master)" : ""), s.device_name || "");
  }

  /* ---------- one action on the PC ---------- */
  async function invokeRemoteAction(action, args = {}, timeout = 45) {
    const active = activeSession();
    if (!active) throw new Error("There is no session. Start one first.");
    if (!server()) throw new Error("Add your server address in Settings first.");
    const ctl = new AbortController();
    const cut = setTimeout(() => ctl.abort(), (timeout + 15) * 1000);
    try {
      const r = await fetch(server() + "/v1/remote/invoke", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-ID": "web", "X-IRAS-Remote-Token": active.session_token },
        body: JSON.stringify({ session_id: active.session_id, action, arguments: args || {}, timeout }),
        signal: ctl.signal,
      });
      let j = null;
      try { j = await r.json(); } catch (e) { /* no body */ }
      if (!r.ok) {
        if (r.status === 401) { keepSession(null); stopAuto(); render(); }  // the session ended on the server
        throw new Error(plain((j && typeof j.detail === "string" && j.detail) || "The server answered " + r.status + "."));
      }
      return (j && j.result) || {};
    } catch (e) {
      if (e && e.name === "AbortError") throw new Error("The PC took too long to answer.");
      throw e;
    } finally { clearTimeout(cut); }
  }

  /* ---------- the screen ---------- */
  const SAFE_IMAGE = /^image\/(jpeg|png|webp)$/;

  function clearShot() {
    const img = $("#screenImg");
    img.removeAttribute("src");
    img.hidden = true;
    $("#screenEmpty").hidden = false;
    $("#screenInfo").textContent = "";
  }

  function clearPrivate() {
    clearShot();
    $("#directOut").textContent = "Ready.";
  }

  async function showScreen() {
    if (shotBusy) return;
    shotBusy = true;
    $("#screenButton").disabled = true;
    try {
      let s = activeSession();
      if (!s) {
        s = await startSession({ mode: "read_only", ttl: 1800 });
        if (!s) { $("#screenInfo").textContent = "Cancelled. Nothing was sent."; return; }
      }
      $("#screenInfo").textContent = "Getting the picture…";
      const r = await invokeRemoteAction("screen_preview", { max_width: 1200, quality: 62 }, 45);
      if (!r.base64) throw new Error("The PC sent no picture.");
      const mime = SAFE_IMAGE.test(String(r.mime || "")) ? r.mime : "image/jpeg";
      const img = $("#screenImg");
      img.src = "data:" + mime + ";base64," + r.base64;
      img.hidden = false;
      $("#screenEmpty").hidden = true;
      $("#screenInfo").textContent = "Updated " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + (r.source_width ? " · your screen is " + r.source_width + "×" + r.source_height : "");
      shotFails = 0;
    } catch (e) {
      $("#screenInfo").textContent = plain(e.message);
      if (++shotFails >= 3) { stopAuto(); toast("Stopped refreshing the screen after 3 errors.", { icon: "triangle-alert" }); }
    } finally {
      shotBusy = false;
      $("#screenButton").disabled = false;
    }
  }

  function stopAuto() {
    clearInterval(autoId);
    autoId = 0;
    $("#screenAuto").checked = false;
  }

  function startAuto() {
    clearInterval(autoId);
    shotFails = 0;
    autoId = setInterval(() => {
      if (document.hidden || IRAS.view() !== "pc" || !activeSession()) { if (!activeSession()) stopAuto(); return; }
      showScreen();
    }, 5000);
    showScreen();
  }

  /* ---------- direct action ---------- */
  function needFor(action) {
    if (!policy || !Array.isArray(policy.actions)) return null;
    const row = policy.actions.find((a) => a.name === action);
    return row ? { level: row.level, varies: !!row.varies } : { level: "CRITICAL", unknown: true };
  }

  function renderLevel() {
    const b = $("#directLevel"), action = $("#directAction").value.trim(), need = action ? needFor(action) : null;
    if (!action) { b.className = "badge"; b.textContent = "Type an action"; return; }
    if (!need) { b.className = "badge"; b.textContent = "Level unknown"; return; }
    if (need.unknown) { b.className = "badge crit"; b.textContent = "Not a known action"; return; }
    const word = LEVEL_WORD[need.level];
    b.className = "badge " + (need.level === "CRITICAL" ? "crit" : need.level === "READ" ? "accent" : "warn");
    b.textContent = "Needs " + word + (need.varies ? " or more" : "");
    b.title = need.varies ? "This one depends on its arguments. The server decides." : "";
  }

  function parseArgs() {
    const raw = $("#directArgs").value.trim();
    if (!raw) return {};
    let args;
    try { args = JSON.parse(raw); } catch (e) { throw new Error("The arguments are not valid JSON. " + e.message); }
    if (!args || Array.isArray(args) || typeof args !== "object") throw new Error('The arguments must be a JSON object, like {"path": "C:\\\\Users"}.');
    return args;
  }

  /* long text (a picture, a big file) would freeze the page, so it is cut */
  const show = (v) => {
    const t = JSON.stringify(v, (k, x) => (typeof x === "string" && x.length > 1500 ? x.slice(0, 200) + "… (" + x.length + " characters)" : x), 2) || "";
    return t.length > 20000 ? t.slice(0, 20000) + "\n… (cut)" : t;
  };

  async function runDirectAction() {
    const action = $("#directAction").value.trim();
    if (!action) throw new Error("Type the name of an action first.");
    const args = parseArgs();
    const need = needFor(action);
    if (need && need.unknown) throw new Error("I do not know an action called \"" + action + "\". Choose one from the list.");
    let s = activeSession();
    if (!s) {
      s = await startSession({ mode: need ? MODE_FOR[need.level] : "read_only", ttl: 1800 });
      if (!s) { $("#directOut").textContent = "Cancelled. Nothing was sent."; return; }
    } else if (need && !need.varies && rankOf(s) < LEVELS[need.level]) {
      throw new Error("\"" + action + "\" needs " + LEVEL_WORD[need.level] + ", and this session is " + MODES[s.mode].name + ". End it and start a new one with more power.");
    }
    if (need && need.level === "CRITICAL") {
      const yes = await askYou({
        level: "critical",
        title: "Run a critical action?",
        body: "This can change or remove things on your PC, and it cannot be undone from here.",
        bullets: ["Action: " + action, "Arguments: " + (JSON.stringify(args).slice(0, 160) || "{}")],
        confirm: "Run it",
      });
      if (!yes) { $("#directOut").textContent = "Cancelled. Nothing was sent."; return; }
    }
    $("#directOut").textContent = "Running…";
    const result = await invokeRemoteAction(action, args, 60);
    $("#directOut").textContent = show(result);
    log("Ran the PC action " + action, "Direct action");
  }

  /* ---------- Master Control ---------- */
  const remainingOf = (m) => (m.persistent || !Number(m.expires_at || 0) ? null : Math.max(0, Number(m.expires_at) - nowSec()));

  /* Reads the PC's own Master file through a short Look-only session, as the old page does. */
  async function localMasterStatus() {
    let temporary = false;
    if (!activeSession()) {
      const made = await startSession({ mode: "read_only", ttl: 300, ask: false });
      if (!made) throw new Error("Could not start a Look-only session to check the PC.");
      temporary = true;
    }
    try {
      const info = (await invokeRemoteAction("system_info", {}, 30)) || {};
      const user = String(info.user || "").trim();
      if (!user) return { enabled: false, unknown: true, reason: "The PC did not say which Windows user is signed in." };
      let raw;
      try {
        raw = await invokeRemoteAction("read_text", { path: "C:\\Users\\" + user + "\\.iras\\master_control.json", max_chars: 12000 }, 30);
      } catch (e) {
        if (/not found|no such file|does not exist|cannot find|not exist/i.test(e.message)) return { enabled: false };
        return { enabled: false, unknown: true, reason: e.message };
      }
      let data = {};
      try { data = JSON.parse(String(raw.text || raw.content || "{}")); } catch (e) { data = {}; }
      if (data.enabled && !data.persistent && Number(data.expires_at || 0) > 0 && nowSec() >= Number(data.expires_at)) data.enabled = false;
      return data;
    } finally {
      if (temporary && !isMaster(activeSession())) await endSession(true);
    }
  }

  function renderMaster(local) {
    const on = !!local.enabled, rem = remainingOf(local);
    $("#masterLocalState").textContent = local.unknown ? "Unknown" : on ? "ON · " + (local.persistent ? "persistent" : rem == null ? "—" : Math.max(0, Math.ceil(rem / 60)) + " min") : "OFF";
    $("#masterAutonomyState").textContent = on ? (local.autonomous ? "CRITICAL autonomous" : "interactive only") : "—";
    const b = $("#masterBadge");
    b.className = "badge" + (on ? " crit" : "");
    b.textContent = local.unknown ? "Could not check" : on ? "PC: ON" : "PC: OFF";
    $("#masterOut").textContent = local.unknown
      ? "I could not read the PC's Master Control file. " + (local.reason || "") + "\n\nIf the PC is on, check that IRAS may read the .iras folder in your user folder."
      : on
        ? "Local owner elevation is active. Shell: " + !!local.allow_shell + " · Power: " + !!local.allow_power + " · Autonomous: " + !!local.autonomous + ".\n\nAttach a Master session to let this browser carry FULL remote authority into chat and direct actions."
        : "Master Control is OFF on the Windows PC. For safety, web/mobile cannot turn it on remotely. On the PC run:\n\n  " + MASTER_COMMAND + "\n\nThen come back here and press Check the PC, then Attach Master Session.";
  }

  async function checkMaster() {
    $("#masterOut").textContent = "Checking the Windows owner-control state…";
    const local = await localMasterStatus();
    renderMaster(local);
    return local;
  }

  async function attachMaster() {
    if (policy && policy.modes && policy.modes.full === false) {
      throw new Error("Your server does not allow Full sessions (its limit is " + (LEVEL_WORD[policy.cap] || policy.cap) + "), and a Master session is Full. Set IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL=3 on your server and redeploy first.");
    }
    const local = await checkMaster();
    if (!local.enabled) throw new Error("Turn Master Control on at the PC first: " + MASTER_COMMAND);
    const rem = remainingOf(local);
    const ttl = Math.max(60, Math.min(Math.floor(rem == null ? 1800 : rem), 12 * 60 * 60));
    const old = activeSession();
    const s = await startSession({ mode: "full", ttl, scopes: ["windows", "master"], master: true });
    if (!s) return;
    if (old) { /* the new session replaced the old one for this window; the old one ends by itself */
      try { await IRAS.api("/v1/remote/sessions/" + encodeURIComponent(old.session_id), { method: "DELETE" }); } catch (e) { /* it expires anyway */ }
    }
    $("#masterOut").textContent = "A Master session is attached to this browser. It ends when the PC's Master time ends, or when you press End web Master session.";
  }

  async function detachMaster() {
    if (isMaster(activeSession())) await endSession(true);
    $("#masterOut").textContent = "The web Master session ended. The PC's own Master state did not change.";
    toast("Web Master session ended.", { icon: "shield-check" });
  }

  /* ---------- drawing ---------- */
  function lock() {
    ["#pcStart", "#screenButton", "#runDirect", "#masterRefresh", "#masterEnable"].forEach((sel) => { const b = $(sel); if (b) b.disabled = working || (sel === "#screenButton" && shotBusy); });
  }

  function render() {
    const s = activeSession(), master = isMaster(s);
    const badge = $("#pcBadge");
    if (s) {
      const rank = rankOf(s);
      badge.className = "badge " + (rank >= 3 ? "crit" : rank >= 2 ? "warn" : "accent");
      badge.textContent = MODES[s.mode].name + (master ? " · Master" : "") + " · " + left(s);
    } else { badge.className = "badge"; badge.textContent = "No session"; }
    $("#pcStart").hidden = !!s;
    $("#pcEnd").hidden = !s;
    $("#pcModes").disabled = !!s;
    $("#pcTtl").disabled = !!s;
    $("#masterCloudState").textContent = master ? "ON · " + String(s.max_permission || "CRITICAL") : "OFF";
    $("#masterEnable").hidden = master;
    $("#masterDisable").hidden = !master;
    const chip = $("#chipPc");
    chip.hidden = !s;
    if (s) {
      chip.className = "chip pc-live";
      chip.dataset.rank = String(rankOf(s));
      $("#chipPcText").textContent = "PC · " + MODES[s.mode].name + (master ? " · Master" : "");
      chip.title = "A remote session is open (" + left(s) + "). Open the PC screen to end it.";
    }
    lock();
  }

  function tickOn() {
    if (tickId) return;
    tickId = setInterval(() => {
      const s = readSession();
      if (!s) { clearInterval(tickId); tickId = 0; return; }
      if (!activeSession()) {  // its time ran out
        clearInterval(tickId); tickId = 0; stopAuto(); clearPrivate(); render();
        toast("The remote session ended. Its time was up.", { icon: "clock" });
        return;
      }
      render();
    }, 15000);
  }

  /* ---------- the screen comes and goes ---------- */
  function enter() {
    render();
    if (activeSession()) tickOn();
    refreshDevice();
    loadPolicy();
  }

  function leave() {
    stopAuto();
    clearPrivate();
  }

  const run = (fn, onError) => async () => {
    if (working) return;
    working = true; lock();
    try { await fn(); } catch (e) { onError(plain(e.message || "That did not work.")); } finally { working = false; lock(); render(); }
  };

  async function copy(text, done) {
    try { await navigator.clipboard.writeText(text); toast(done, { icon: "check" }); }
    catch (e) { toast("Could not copy. The command is: " + text, { icon: "triangle-alert", timeout: 9000 }); }
  }

  IRAS.initPc = function () {
    $("#pcStart").addEventListener("click", run(async () => {
      hint("");
      const mode = ($('#pcModes input[name="pcMode"]:checked') || {}).value || "read_only";
      await startSession({ mode, ttl: Number($("#pcTtl").value) || 1800 });
    }, hint));
    $("#pcEnd").addEventListener("click", () => endSession(false));
    $("#pcRescan").addEventListener("click", async () => { $("#pcDevice").textContent = "Looking…"; await refreshDevice(); });
    $("#screenButton").addEventListener("click", showScreen);
    $("#screenAuto").addEventListener("change", (e) => { if (e.target.checked) startAuto(); else stopAuto(); });
    $("#runDirect").addEventListener("click", run(runDirectAction, (m) => { $("#directOut").textContent = "Error: " + m; }));
    $("#directAction").addEventListener("input", renderLevel);
    $("#masterRefresh").addEventListener("click", run(checkMaster, (m) => { $("#masterOut").textContent = "Master status error: " + m; }));
    $("#masterEnable").addEventListener("click", run(attachMaster, (m) => { $("#masterOut").textContent = "Master error: " + m; }));
    $("#masterDisable").addEventListener("click", () => detachMaster());
    $("#masterCopy").addEventListener("click", () => copy(MASTER_COMMAND, "Copied. Paste it in a terminal on your PC."));
    $("#chipPc").addEventListener("click", () => IRAS.go("pc"));

    const dlg = $("#pcAskDlg");
    $("#pcAskNo").addEventListener("click", () => { if (pending) pending(false); });
    $("#pcAskOk").addEventListener("click", () => { if (pending) pending(true); });
    dlg.addEventListener("cancel", () => { if (pending) pending(false); });  // Esc means no
    dlg.addEventListener("close", () => { if (pending) pending(false); });   // closed any other way also means no

    bus.on("view", (e) => { if (e.view === "pc") enter(); else leave(); });
    bus.on("visibility", (e) => { if (e.hidden) { clearInterval(autoId); autoId = 0; $("#screenAuto").checked = false; } });
    render();
    if (activeSession()) tickOn();
  };
})();
