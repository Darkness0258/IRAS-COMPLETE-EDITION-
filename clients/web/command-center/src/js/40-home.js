/* ==========================================================================
   Home: presence, pipeline, live activity, screen peek, command bar, chips
   ========================================================================== */
"use strict";

(function () {
  /* ---------- copy for each state ---------- */
  const COPY = {
    idle:      { label: "Ready",                  cap: () => `Say “${settings.wake || "IRAS"}” or press Space to talk.`, say: "IRAS is ready" },
    listening: { label: "Listening",              cap: () => "Go ahead. I’m listening.",                                 say: "IRAS is listening" },
    thinking:  { label: "Thinking",               cap: () => "Working out what to do…",                                  say: "IRAS is thinking" },
    speaking:  { label: "Speaking",               cap: () => "",                                                         say: "IRAS is speaking" },
    acting:    { label: "Working on your screen", cap: () => "",                                                         say: "IRAS is working on your screen" },
    approval:  { label: "Needs your approval",    cap: () => "",                                                         say: "IRAS needs your approval" },
  };

  const elLabel = $("#voiceStateLabel");
  const elCap = $("#stateCaption");
  const pipeline = $("#pipeline");
  const heard = $("#heard");
  const heardText = $("#heardText");
  const heardIcon = $("#heardIcon");
  let capOverride = "";

  IRAS.setCaption = function (text) {
    capOverride = text || "";
    renderCaption();
  };
  function renderCaption() {
    const base = COPY[S.ui].cap();
    const text = capOverride || base;
    if (elCap.textContent !== text) elCap.textContent = text;
  }

  function renderHeard() {
    const on = !!S.heard && ["listening", "thinking", "speaking", "approval"].includes(S.ui);
    heard.classList.toggle("is-on", on);
    heardText.textContent = S.heard || "";
    heardText.classList.toggle("is-live", S.ui === "listening");
    heardIcon.innerHTML = icon(S.heardVia === "voice" ? "mic" : "keyboard", "i-sm");
  }

  function renderPipeline() {
    const ui = S.ui;
    let active = null, done = -1;
    if (ui === "listening") { active = "listen"; }
    else if (ui === "thinking") { active = "understand"; done = 0; }
    else if (ui === "approval") { active = "approve"; done = 1; }
    else if (ui === "acting" || ui === "speaking") { active = "act"; done = 2; }
    $$(".step", pipeline).forEach((li, i) => {
      const key = li.dataset.step;
      li.classList.toggle("is-active", key === active);
      li.classList.toggle("is-done", i <= done);
      if (key === active) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
  }

  function renderState(prev) {
    const c = COPY[S.ui];
    if (elLabel.textContent !== c.label) {
      elLabel.textContent = c.label;
      if (prev && !IRAS.env.reduceMotion && elLabel.animate) {
        elLabel.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: "cubic-bezier(.2,0,0,1)" });
      }
    }
    renderCaption();
    renderPipeline();
    renderHeard();
    const mic = $$("[data-act='mic']");
    mic.forEach((b) => {
      b.setAttribute("aria-pressed", S.ui === "listening" ? "true" : "false");
      b.setAttribute("aria-label", S.ui === "listening" ? "Stop listening" : "Talk to IRAS");
    });
    $("#stopBtn").hidden = S.ui === "idle";
    $("#voicePresence").setAttribute("aria-label", c.label);
  }

  bus.on("ui", (e) => {
    capOverride = "";
    if (e.to === "idle") S.heard = "";
    if (e.to === "approval") IRAS.setCaption(S.pending ? S.pending.title : "");
    renderState(e.from);
    IRAS.announce(e.to === "approval" && S.pending ? `${COPY.approval.say}: ${S.pending.title}. ${S.authority === "critical" ? "Critical action." : "System action."}` : COPY[e.to].say);
  });
  bus.on("partial_transcript", (e) => { S.heard = e.text; S.heardVia = "voice"; renderHeard(); });
  bus.on("submit", (e) => { S.heard = e.text; S.heardVia = e.via === "voice" ? "voice" : "text"; renderHeard(); });
  bus.on("caption", (e) => IRAS.setCaption(e.text));

  /* the sentence IRAS is saying, or the tail of the reply as it streams */
  let tokenTail = "";
  bus.on("submit", () => { tokenTail = ""; });
  bus.on("token", (e) => {
    tokenTail = (tokenTail + e.text).slice(-140);
    if (S.ui === "thinking") IRAS.setCaption(tokenTail.replace(/[#*`>_-]+/g, "").replace(/\s+/g, " ").trim());
  });
  bus.on("tts_start", (e) => { if (e.text) IRAS.setCaption(e.text); });
  bus.on("tool_start", (e) => { if (e.title && S.ui !== "approval") IRAS.setCaption(e.title); });

  /* ---------- prompts (also the demo entry points) ---------- */
  const PROMPTS = [
    { icon: "music", text: "Play something calm on Spotify" },
    { icon: "mail", text: "Summarize my unread emails" },
    { icon: "bug", text: "/code fix the failing test" },
    { icon: "package", text: "Install VS Code" },
    { icon: "trash-2", text: "Delete old build folders" },
  ];
  function renderPrompts() {
    const host = $("#promptGrid");
    host.innerHTML = PROMPTS.map((p) => `<button type="button" class="prompt${p.tour ? " is-tour" : ""}" data-text="${esc(p.text)}"${p.tour ? " data-tour" : ""}>${icon(p.icon, "i-sm")}<span>${esc(p.text)}</span></button>`).join("");
    host.addEventListener("click", (e) => {
      const b = e.target.closest(".prompt");
      if (!b) return;
      if (b.hasAttribute("data-tour")) IRAS.sim.tour(); else IRAS.run(b.dataset.text, { via: "text" });
    });
  }
  IRAS.PROMPTS = PROMPTS;

  /* ---------- live activity ---------- */
  const liveList = $("#liveList");
  const rows = new Map();
  let liveFilter = "all";
  const FILTERS = { all: () => true, tool: (it) => it.kind !== "agent", agent: (it) => it.kind === "agent" };

  function iconFor(it) {
    if (it.status === "running") return "loader-circle";
    if (it.kind === "approval") return it.authority === "critical" ? "shield-alert" : "shield";
    if (it.kind === "agent") return ({ code: "bug", research: "flask-conical", install: "package" })[(it.payload && it.payload.agent)] || "workflow";
    if (it.kind === "system") return it.tags && it.tags.includes("sync") ? "cloud" : "cpu";
    const t = (it.payload && it.payload.tool) || "";
    if (t.startsWith("spotify")) return "music";
    if (t.startsWith("mail")) return "mail";
    if (t.startsWith("calendar")) return "calendar";
    if (t.startsWith("fs.delete")) return "trash-2";
    if (t.startsWith("fs")) return "folder";
    if (t.startsWith("winget")) return "package";
    if (t.startsWith("whatsapp")) return "message-square";
    if (t.startsWith("browser")) return "globe";
    if (t.startsWith("apps")) return "monitor";
    return "zap";
  }
  const STATUS_TEXT = (it) => ({ running: "Running…", done: it.ms ? "Done in " + fmtDur(it.ms) : "Done", failed: "Failed", denied: "Denied", waiting: "Waiting for you" })[it.status] || "";

  function fillRow(li, it) {
    li.dataset.status = it.status;
    li.dataset.kind = it.kind;
    const lvl = it.authority === "critical" ? "crit" : it.authority === "system" ? "warn" : "";
    const badge = lvl ? `<span class="badge ${lvl}">${icon(lvl === "crit" ? "shield-alert" : "shield", "i-sm")}${lvl === "crit" ? "Critical" : "System action"}</span>` : "";
    li.innerHTML =
      `<span class="item-ico">${icon(iconFor(it))}</span>` +
      `<div class="item-body"><div class="item-top"><strong class="item-title">${esc(it.title)}</strong><time class="item-time">${fmtTime(it.ts)}</time></div>` +
      (it.detail ? `<p class="item-detail">${esc(it.detail)}</p>` : "") +
      `<div class="item-meta">${badge}<span class="item-status">${esc(STATUS_TEXT(it))}</span></div>` +
      (it.status === "running" ? `<div class="bar thin indet" aria-hidden="true"><i></i></div>` : "") + `</div>`;
  }
  function buildRow(it, n) {
    const li = document.createElement("li");
    li.className = "item is-new";
    li.dataset.id = it.id;
    li.style.setProperty("--n", n || 0);
    fillRow(li, it);
    rows.set(it.id, li);
    return li;
  }
  function trimLive() {
    while (liveList.children.length > 40) { const last = liveList.lastElementChild; rows.delete(last.dataset.id); last.remove(); }
  }
  function renderLiveAll() {
    liveList.innerHTML = "";
    rows.clear();
    const items = audit.items.filter(FILTERS[liveFilter]).slice(0, 40);
    items.forEach((it, n) => liveList.appendChild(buildRow(it, Math.min(n, 8))));
    if (!items.length) liveList.innerHTML = `<li class="empty">${icon("activity")}<strong>Nothing here yet</strong><span>Ask IRAS to do something and each step shows up here.</span></li>`;
    $("#liveCount").textContent = items.length ? `Showing the latest ${items.length}` : "No activity yet";
  }
  function updateLatest() {
    const it = audit.items[0];
    const el = $("#liveLatest");
    if (el) el.textContent = it ? `${it.title}. ${STATUS_TEXT(it)}` : "Nothing yet";
  }
  bus.on("audit:add", updateLatest);
  bus.on("audit:update", updateLatest);
  bus.on("audit:add", (e) => {
    if (!FILTERS[liveFilter](e.item)) return;
    const empty = liveList.querySelector(".empty");
    if (empty) empty.remove();
    liveList.prepend(buildRow(e.item, 0));
    trimLive();
  });
  bus.on("audit:update", (e) => {
    const li = rows.get(e.item.id);
    if (li) fillRow(li, e.item);
  });
  $$("input[name='liveFilter']").forEach((r) => r.addEventListener("change", () => { liveFilter = r.value; renderLiveAll(); }));
  IRAS.renderLive = renderLiveAll;

  /* phones: live activity is a sheet that opens upward */
  const live = $("#livePanel");
  const liveToggle = $("#liveToggle");
  liveToggle.addEventListener("click", () => {
    const open = live.classList.toggle("is-open");
    liveToggle.setAttribute("aria-expanded", String(open));
    liveToggle.setAttribute("aria-label", open ? "Show less live activity" : "Show more live activity");
    liveToggle.innerHTML = icon(open ? "chevron-down" : "chevron-up", "i-sm");
  });

  /* ---------- screen peek: the area IRAS is controlling ---------- */
  const peekScreen = $("#peekScreen");
  const peekApp = $("#peekApp");
  const peekStep = $("#peekStep");
  const peekDots = $("#peekDots");
  const peekCard = $("#screenPeek");
  const LAYOUTS = {
    music: {
      els: [
        ["pk", 0, 0, 100, 9], ["pk dot", 3, 2.6, 3, 4.2], ["pk hi", 22, 2.4, 30, 4.4],
        ["pk", 0, 9, 21, 91], ["pk hi", 3, 14, 15, 3.2], ["pk", 3, 21, 12, 3], ["pk", 3, 27, 14, 3], ["pk", 3, 33, 10, 3],
        ["pk text", 26, 20, 22, 3], ["pk", 26, 27, 30, 7, "search"],
        ["pk", 26, 40, 68, 9, "row1"], ["pk hi", 27, 41.5, 6, 6], ["pk text", 36, 42.5, 24, 2.4], ["pk", 36, 46, 14, 2],
        ["pk", 26, 51, 68, 9, "row2"], ["pk hi", 27, 52.5, 6, 6], ["pk text", 36, 53.5, 18, 2.4], ["pk", 36, 57, 12, 2],
        ["pk", 26, 62, 68, 9, "row3"], ["pk hi", 27, 63.5, 6, 6], ["pk text", 36, 64.5, 28, 2.4], ["pk", 36, 68, 10, 2],
        ["pk", 21, 86, 79, 14], ["pk accent", 56, 88.5, 7, 9, "play"], ["pk", 26, 92, 22, 2.4],
      ],
      targets: { search: [26, 27, 30, 7], row1: [26, 40, 68, 9], row2: [26, 51, 68, 9], row3: [26, 62, 68, 9], play: [56, 88.5, 7, 9] },
    },
    terminal: {
      els: [
        ["pk", 0, 0, 100, 10], ["pk dot", 3, 3.2, 2.6, 4], ["pk dot", 7, 3.2, 2.6, 4], ["pk dot", 11, 3.2, 2.6, 4],
        ["pk text", 6, 18, 38, 3, "line1"], ["pk text", 6, 27, 52, 3], ["pk text", 6, 36, 30, 3, "line2"],
        ["pk text", 6, 49, 46, 3], ["pk text", 6, 58, 24, 3], ["pk text", 6, 67, 60, 3, "line3"],
        ["pk accent", 6, 80, 3, 6, "prompt"], ["pk text", 11, 82, 18, 3],
      ],
      targets: { line1: [5, 16, 42, 7], line2: [5, 34, 34, 7], line3: [5, 65, 64, 7], prompt: [5, 78, 40, 10] },
    },
    files: {
      els: [
        ["pk", 0, 0, 100, 10], ["pk text", 4, 4.2, 26, 2.6],
        ["pk", 4, 18, 28, 24, "dir1"], ["pk hi", 8, 22, 8, 7], ["pk text", 8, 34, 18, 2.4],
        ["pk", 36, 18, 28, 24, "dir2"], ["pk hi", 40, 22, 8, 7], ["pk text", 40, 34, 16, 2.4],
        ["pk", 68, 18, 28, 24, "dir3"], ["pk hi", 72, 22, 8, 7], ["pk text", 72, 34, 20, 2.4],
        ["pk", 4, 52, 28, 24], ["pk hi", 8, 56, 8, 7], ["pk text", 8, 68, 14, 2.4],
        ["pk", 36, 52, 28, 24], ["pk hi", 40, 56, 8, 7], ["pk text", 40, 68, 18, 2.4],
        ["pk accent", 74, 86, 22, 9, "confirm"],
      ],
      targets: { dir1: [4, 18, 28, 24], dir2: [36, 18, 28, 24], dir3: [68, 18, 28, 24], confirm: [74, 86, 22, 9] },
    },
  };
  let peekSpec = null, peekIdx = 0;

  function buildPeek(spec) {
    const L = LAYOUTS[spec.layout] || LAYOUTS.music;
    peekScreen.innerHTML =
      L.els.map(([cls, x, y, w, h]) => `<i class="${cls.split(" ").map((c) => c).join(" ")}" style="left:${x}%;top:${y}%;width:${w}%;height:${h}%"></i>`).join("") +
      `<svg class="pk-hl" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect id="peekHl" x="0" y="0" width="1" height="1" style="transform:translate(0px,0px) scale(0,0)"/></svg>` +
      `<span class="pk-cursor" id="peekCursor" aria-hidden="true">${icon("mouse-pointer-2", "i-sm")}</span><span class="pk-scan" aria-hidden="true"></span>`;
    peekApp.textContent = spec.app;
    peekDots.innerHTML = spec.steps.map(() => "<li></li>").join("");
  }
  function peekGo(i) {
    if (!peekSpec) return;
    const L = LAYOUTS[peekSpec.layout] || LAYOUTS.music;
    const step = peekSpec.steps[clamp(i, 0, peekSpec.steps.length - 1)];
    peekIdx = i;
    peekStep.textContent = step.label;
    $$("li", peekDots).forEach((d, n) => { d.className = n < i ? "done" : n === i ? "now" : ""; });
    const t = L.targets[step.target];
    const hl = $("#peekHl");
    const cur = $("#peekCursor");
    if (t && hl) {
      hl.style.transform = `translate(${t[0]}px, ${t[1]}px) scale(${t[2]}, ${t[3]})`;
      const r = peekScreen.getBoundingClientRect();
      if (cur) cur.style.transform = `translate(${((t[0] + t[2] * .62) / 100) * r.width}px, ${((t[1] + t[3] * .6) / 100) * r.height}px)`;
    }
    IRAS.setCaption(step.label);
  }
  IRAS.peek = {
    show(spec) { peekSpec = spec; buildPeek(spec); peekCard.setAttribute("aria-hidden", "false"); requestAnimationFrame(() => peekGo(0)); },
    step(i) { peekGo(i); },
    hide() { peekCard.setAttribute("aria-hidden", "true"); peekSpec = null; },
  };
  bus.on("tool_start", (e) => { if (e.screen) IRAS.peek.show(e.screen); });
  bus.on("peek_step", (e) => IRAS.peek.step(e.i));
  bus.on("peek_show", (e) => IRAS.peek.show(e.spec));
  bus.on("peek_hide", () => IRAS.peek.hide());
  bus.on("tool_end", (e) => { if (peekSpec && e.screen !== false) IRAS.peek.hide(); });
  bus.on("ui", (e) => { if (e.to === "idle") IRAS.peek.hide(); });

  /* ---------- command bar ---------- */
  function composerHTML() {
    return `<form class="composer glass" autocomplete="off" data-form>
      <button type="button" class="btn-icon plain" data-act="palette" aria-label="Open commands" title="Commands (Ctrl+K)">${icon("command")}</button>
      <input class="msg" type="text" placeholder="Ask IRAS, or type /code, /research, /install" aria-label="Message IRAS" enterkeyhint="send" spellcheck="false">
      <button type="button" class="mic-btn" data-act="mic" aria-label="Talk to IRAS" aria-pressed="false" title="Talk (Space)">${icon("mic", "i-lg")}</button>
      <button type="submit" class="btn-icon send-btn" aria-label="Send" disabled>${icon("arrow-up")}</button>
    </form>
    <p class="composer-hints"><span><kbd>Space</kbd> talk</span><span><kbd>Ctrl</kbd><kbd>K</kbd> commands</span><span><kbd>Esc</kbd> stop</span></p>`;
  }
  function mountComposers() {
    $$("[data-composer]").forEach((host) => {
      host.innerHTML = composerHTML();
      const form = $("[data-form]", host), input = $(".msg", host), send = $(".send-btn", host);
      input.addEventListener("input", () => { send.disabled = !input.value.trim(); });
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = ""; send.disabled = true;
        IRAS.run(text, { via: "text" });
      });
      $("[data-act='mic']", host).addEventListener("click", () => IRAS.toggleMic());
      $("[data-act='palette']", host).addEventListener("click", () => IRAS.openPalette && IRAS.openPalette());
    });
  }
  IRAS.focusComposer = () => {
    const host = $(`[data-composer="${IRAS.view() === "chat" ? "chat" : "home"}"] .msg`);
    if (host) host.focus();
  };

  /* One entry point for everything the person asks, typed or spoken. */
  IRAS.run = function (text, { via = "text" } = {}) {
    text = String(text || "").trim();
    if (!text) return;
    if (IRAS.view() !== "home" && IRAS.view() !== "chat") IRAS.go("home");
    if (S.busy && S.ui !== "speaking") { toast("IRAS is busy. Press Stop to cancel the current task.", { icon: "info" }); return; }
    if (S.ui === "speaking") { IRAS.voice.stopSpeaking(); IRAS.sim.cancel(); bus.emit("cancel"); }
    S.heard = text; S.heardVia = via === "voice" ? "voice" : "text";
    bus.emit("submit", { text, via });
    if (settings.source === "live" && IRAS.live) IRAS.live.send(text, { via }); else IRAS.sim.route(text, { via });
  };

  IRAS.toggleMic = function () {
    if (S.busy && S.ui !== "speaking" && S.ui !== "listening") { toast("IRAS is busy. Press Stop to cancel the current task.", { icon: "info" }); return; }
    IRAS.voice.toggle();
  };

  IRAS.stopAll = function () {
    if (S.ui === "idle") return;
    IRAS.sim.cancel();
    if (IRAS.voice) IRAS.voice.stopSpeaking();
    if (IRAS.live) IRAS.live.cancel();
    if (S.ui === "approval" && S.pending) IRAS.resolveApproval("deny", "button");
    bus.emit("cancel");
    audit.add({ kind: "system", status: "done", title: "You stopped IRAS", detail: "Everything that was running was cancelled.", tags: ["stop"] });
    toast("Stopped. Nothing else will run.", { icon: "square" });
  };
  $("#stopBtn").addEventListener("click", () => IRAS.stopAll());
  $("#orbHit").addEventListener("click", () => IRAS.toggleMic());

  /* ---------- status chips and popovers ---------- */
  const chip = { prov: $("#chipProvider"), mic: $("#chipMic"), cam: $("#chipCam"), sync: $("#chipSync") };
  const setIcon = (btn, name) => { const old = btn.querySelector("svg"); const tmp = document.createElement("span"); tmp.innerHTML = icon(name, "i-sm"); old.replaceWith(tmp.firstChild); };

  function renderChips() {
    $("#chipProviderText").textContent = S.provider.active;
    chip.prov.classList.toggle("is-failover", !!S.provider.justSwitched);
    chip.prov.setAttribute("aria-label", `AI provider: ${S.provider.active}. Open details.`);
    const mic = S.mic;
    chip.mic.setAttribute("aria-pressed", String(mic === "on"));
    setIcon(chip.mic, mic === "on" ? "mic" : "mic-off");
    $("#chipMicText").textContent = mic === "on" ? "Mic on" : mic === "blocked" ? "Mic blocked" : "Mic off";
    chip.mic.title = mic === "blocked" ? "The browser blocked the microphone. Allow it in the address bar to use your voice." : mic === "on" ? "Turn the microphone off" : "Turn the microphone on";
    setIcon(chip.cam, S.cam === "on" ? "camera" : "camera-off");
    $("#chipCamText").textContent = S.cam === "on" ? "Camera on" : "Camera off";
    chip.cam.title = "Camera is only used when you set up Face ID";
    const sy = S.sync;
    setIcon(chip.sync, sy.state === "syncing" ? "refresh-cw" : sy.state === "offline" ? "cloud-off" : "cloud");
    $("#chipSyncText").textContent = sy.state === "syncing" ? "Syncing…" : sy.state === "offline" ? "Offline" : "Synced";
    chip.sync.setAttribute("aria-label", `Sync: ${sy.state === "synced" ? "synced " + relTime(sy.at) : sy.state}. Open details.`);
  }
  bus.on("mic", renderChips);
  bus.on("cam", renderChips);
  bus.on("setting", (e) => { if (e.key === "wake") renderCaption(); });
  bus.on("sync", (e) => { S.sync = { state: e.state, at: e.state === "synced" ? Date.now() : S.sync.at }; renderChips(); });
  bus.on("provider", (e) => {
    if (!e.active) return;
    S.provider.justSwitched = !!e.failover;
    renderChips();
    if (e.failover) setTimeout(() => { S.provider.justSwitched = false; renderChips(); }, 6000);
  });
  chip.mic.addEventListener("click", async () => {
    if (settings.source === "live") { toast("The microphone is used by the voice screen in the classic client.", { icon: "mic" }); return; }
    if (S.mic === "on") { IRAS.audio.stop(); toast("Microphone off. Nothing is being heard.", { icon: "mic-off" }); return; }
    const ok = await IRAS.audio.start();
    toast(ok ? "Microphone on. The orb now reacts to your voice. Audio stays in this page." : "The microphone is blocked. The orb will use demo levels.", { icon: ok ? "mic" : "mic-off" });
  });
  chip.cam.addEventListener("click", () => IRAS.go("identity"));

  const pops = { prov: $("#popProvider"), sync: $("#popSync") };
  function closePops() {
    Object.entries(pops).forEach(([k, p]) => { p.hidden = true; chip[k].setAttribute("aria-expanded", "false"); });
  }
  function popRows() {
    const route = [S.provider.active, ...S.provider.fallbacks.filter((n) => n !== S.provider.active)];
    pops.prov.innerHTML = `<p class="pop-title">AI providers</p>` +
      route.map((n, i) => `<div class="pop-row"><span class="dot ${i === 0 ? "on" : ""}" aria-hidden="true"></span><span class="grow">${esc(n)}<small>${i === 0 ? "In use right now" : i === route.length - 1 ? "Runs on this PC, works offline" : "Ready as a backup"}</small></span>${i === 0 ? '<span class="badge accent">Active</span>' : ""}</div>`).join("") +
      `<p class="hint">IRAS tries them in this order and switches by itself when one is slow or down.${S.provider.note ? " Last switch: " + esc(S.provider.note) + "." : ""}</p>`;
    const rows2 = [["Windows PC", "Just now", "laptop"], ["Android phone", "4 min ago", "smartphone"], ["This browser tab", "Live", "globe"]];
    pops.sync.innerHTML = `<p class="pop-title">Sync across your devices</p>` +
      rows2.map(([n, t, ic]) => `<div class="pop-row">${icon(ic, "i-sm")}<span class="grow">${esc(n)}<small>${esc(t)}</small></span><span class="dot on" aria-hidden="true"></span></div>`).join("") +
      `<p class="hint">Memory and conversations stay in step through your own cloud.${settings.source === "demo" ? " This preview shows sample data." : ""}</p>`;
  }
  Object.entries(chip).filter(([k]) => k === "prov" || k === "sync").forEach(([k, btn]) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = !pops[k].hidden;
      closePops();
      if (!wasOpen) { popRows(); pops[k].hidden = false; btn.setAttribute("aria-expanded", "true"); }
    });
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".popover")) closePops(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePops(); });

  /* ---------- boot ---------- */
  IRAS.initHome = function () {
    renderPrompts();
    mountComposers();
    renderChips();
    renderState(null);
    renderLiveAll();
    updateLatest();
  };
})();
