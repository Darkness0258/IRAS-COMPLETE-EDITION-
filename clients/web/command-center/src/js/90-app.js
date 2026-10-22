/* ==========================================================================
   App boot, command palette, keyboard
   ========================================================================== */
"use strict";

(function () {
  /* ---------- command palette ---------- */
  const dlg = $("#paletteDlg");
  const input = $("#palInput");
  const list = $("#palList");
  let items = [], shown = [], sel = 0;

  function build() {
    const goto = (v, label, ic) => ({ group: "Go to", label, icon: ic, kw: v, run: () => IRAS.go(v) });
    const perfOn = IRAS.env.perf === "lite";
    items = [
      goto("home", "Home", "house"), goto("chat", "Conversation", "message-square"), goto("agents", "Agents and routines", "workflow"),
      goto("activity", "Activity and audit log", "activity"), goto("memory", "Memory", "share-2"), goto("identity", "Face ID and Voice ID", "scan-face"), goto("settings", "Settings", "settings"),


      { group: "Look and feel", label: "Dark theme", icon: "moon", kw: "appearance", run: () => setSetting("theme", "dark") },
      { group: "Look and feel", label: "Light theme", icon: "sun", kw: "appearance", run: () => setSetting("theme", "light") },
      { group: "Look and feel", label: "Follow my system theme", icon: "monitor", kw: "auto appearance", run: () => setSetting("theme", "auto") },
      { group: "Look and feel", label: "Cobalt skin (blue)", icon: "palette", kw: "color", run: () => setSetting("skin", "cobalt") },
      { group: "Look and feel", label: "Neon skin (green)", icon: "palette", kw: "color", run: () => setSetting("skin", "neon") },
      { group: "Look and feel", label: perfOn ? "Turn Performance mode off" : "Turn Performance mode on", icon: "gauge", kw: "fast blur battery", run: () => setSetting("perf", perfOn ? "full" : "lite") },

      { group: "Safety", label: "Stop everything", icon: "square", hint: "Esc", kw: "cancel emergency", run: () => IRAS.stopAll() },
    ];
  }

  function filter() {
    const q = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    shown = items.filter((it) => { const hay = (it.label + " " + it.group + " " + (it.kw || "")).toLowerCase(); return q.every((w) => hay.includes(w)); });
    shown.sort((a, b) => (q.length ? (b.label.toLowerCase().startsWith(q[0]) ? 1 : 0) - (a.label.toLowerCase().startsWith(q[0]) ? 1 : 0) : 0));
    sel = 0;
    render();
  }
  function render() {
    if (!shown.length) { list.innerHTML = `<li class="pal-empty">No command matches “${esc(input.value)}”.</li>`; input.removeAttribute("aria-activedescendant"); return; }
    let lastGroup = "", html = "";
    shown.forEach((it, i) => {
      if (!input.value.trim() && it.group !== lastGroup) { html += `<li class="pal-group" role="presentation">${esc(it.group)}</li>`; lastGroup = it.group; }
      html += `<li class="pal-item" role="option" id="pal-${i}" data-i="${i}" aria-selected="${i === sel}">${icon(it.icon)}<span class="grow">${esc(it.label)}</span>${it.hint ? `<kbd>${esc(it.hint)}</kbd>` : ""}</li>`;
    });
    list.innerHTML = html;
    input.setAttribute("aria-activedescendant", "pal-" + sel);
    const cur = $("#pal-" + sel);
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    const it = shown[i];
    if (!it) return;
    IRAS.closeDialog(dlg);
    setTimeout(() => it.run(), 30);
  }
  IRAS.openPalette = function () {
    if ($("#approvalDlg").open) return;
    build();
    input.value = "";
    filter();
    IRAS.openDialog(dlg);
    input.focus();
  };
  input.addEventListener("input", filter);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); render(); }
    else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
  });
  list.addEventListener("click", (e) => { const li = e.target.closest(".pal-item"); if (li) choose(Number(li.dataset.i)); });
  list.addEventListener("pointermove", (e) => { const li = e.target.closest(".pal-item"); if (li && Number(li.dataset.i) !== sel) { sel = Number(li.dataset.i); $$(".pal-item", list).forEach((n) => n.setAttribute("aria-selected", String(Number(n.dataset.i) === sel))); } });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) IRAS.closeDialog(dlg); });
  $("#paletteBtn").addEventListener("click", () => IRAS.openPalette());

  /* ---------- theme button ---------- */
  $("#themeBtn").addEventListener("click", () => setSetting("theme", IRAS.env.theme === "dark" ? "light" : "dark"));

  /* ---------- keyboard ---------- */
  const INTERACTIVE = "button, input, textarea, select, summary, label, [contenteditable], [role='button'], [role='switch'], [role='checkbox'], [role='radio'], [role='tab'], [role='option'], [role='slider']";
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if (dlg.open) IRAS.closeDialog(dlg); else IRAS.openPalette(); return; }
    if (document.querySelector("dialog[open]")) return;
    if (e.key === "Escape") { if (S.busy) IRAS.stopAll(); return; }
    const t = e.target;
    const typing = t && t.closest && t.closest("input, textarea, select, [contenteditable]");
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey) { e.preventDefault(); IRAS.focusComposer(); return; }
    if (e.code === "Space" && !e.repeat && !e.ctrlKey && !e.metaKey && !e.altKey && !(t && t.closest && t.closest(INTERACTIVE))) {
      if (["home", "chat"].includes(IRAS.view())) { e.preventDefault(); IRAS.toggleMic(); }
    }
  });

  /* ---------- Performance mode: Auto notices a struggling device ---------- */
  IRAS.onSlow = function (avg) {
    if (IRAS.env.autoLite || settings.perf !== "auto") return;
    IRAS.env.autoLite = true;
    applyAppearance();
    toast("This device is working hard, so I switched to Performance mode.", {
      icon: "gauge", timeout: 10000,
      action: { label: "Undo", fn: () => setSetting("perf", "full") },
    });
  };

  /* ---------- boot ---------- */
  function boot() {
    document.documentElement.dataset.hidden = document.hidden ? "1" : "0";
    applyAppearance(true);
    IRAS.initHome();
    ["initChat", "initAgents", "initActivity", "initMemory", "initIdentity", "initSettings", "initLive"].forEach((fn) => { try { if (IRAS[fn]) IRAS[fn](); } catch (e) { console.error("[IRAS] " + fn + " failed", e); } });
    routeFromHash(true);
    IRAS.initOrb();
    document.body.dataset.ready = "1";
    setTimeout(() => { document.body.classList.add("intro-done"); }, 1800);
    bus.emit("ready", {});
  }
  boot();
})();
