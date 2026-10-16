/* ==========================================================================
   Approval overlay: the authority gate.

   SYSTEM_ACTION  amber, asks first
   CRITICAL       red, a voice phrase and a 9 second window

   Color is never alone: every level has an icon and a word. Esc means deny.
   Nothing here decides anything. It shows a request and reports your choice.
   ========================================================================== */
"use strict";

(function () {
  const dlg = $("#approvalDlg");
  const ringProg = $("#apProgress");
  const ringIcon = $("#apIcon");
  const level = $("#apLevel");
  const title = $("#apTitle");
  const detail = $("#apDetail");
  const effects = $("#apEffects");
  const voice = $("#apVoice");
  const phrase = $("#apPhrase");
  const bars = $$(".ap-bars i", dlg);
  const timer = $("#apTimer");
  const approveText = $("#apApproveText");
  let req = null, t0 = 0, raf = 0, tm = 0, said5 = false, said2 = false;

  /* the orb reads this every frame to draw its countdown ring */
  IRAS.approvalFrac = () => {
    if (!req) return 1;
    return clamp(1 - (performance.now() - t0) / req.expires_ms, 0, 1);
  };

  bus.on("approval_request", (e) => {
    IRAS.closeDialog($("#paletteDlg"));
    req = e; t0 = performance.now(); said5 = said2 = false;
    const crit = e.authority === "critical";
    dlg.dataset.level = crit ? "critical" : "system";
    level.innerHTML = crit ? `${icon("shield-alert", "i-sm")}Critical action. Needs your voice` : `${icon("shield", "i-sm")}System action. Needs your OK`;
    ringIcon.innerHTML = icon(crit ? "shield-alert" : "shield", "i-lg");
    title.textContent = e.title;
    detail.textContent = e.detail || "";
    effects.innerHTML = (e.effects || []).map((x) => `<li>${icon(x.icon || "circle-alert")}<span>${x.html || esc(x.text)}</span></li>`).join("");
    voice.hidden = !e.phrase;
    phrase.textContent = e.phrase || "";
    approveText.textContent = e.approveLabel || "Approve";
    ringProg.style.strokeDashoffset = "0";
    bars.forEach((b) => b.style.setProperty("--lv", ".18"));
    IRAS.openDialog(dlg);
    clearTimeout(tm);
    tm = setTimeout(() => resolve("expired", "timeout"), e.expires_ms);
    loop();
  });

  function loop() {
    cancelAnimationFrame(raf);
    const tick = () => {
      if (!req) return;
      const frac = IRAS.approvalFrac();
      ringProg.style.strokeDashoffset = String(100 * (1 - frac));
      const left = Math.ceil((frac * req.expires_ms) / 1000);
      const txt = `<strong>${left}s</strong> left`;
      if (timer.innerHTML !== txt) timer.innerHTML = txt;
      if (left <= 5 && !said5 && req.expires_ms > 6000) { said5 = true; IRAS.announce("5 seconds left to decide"); }
      if (left <= 2 && !said2) { said2 = true; IRAS.announce("2 seconds left"); }
      raf = requestAnimationFrame(tick);
    };
    tick();
  }

  /* the bars move with your voice, so you can see IRAS is listening for the phrase */
  bus.on("audio_level", (e) => {
    if (!req || e.source !== "mic" || !dlg.open) return;
    const t = performance.now() / 120;
    bars.forEach((b, i) => b.style.setProperty("--lv", String(clamp(.16 + e.level * (.55 + .45 * Math.sin(t + i * 1.3)), .12, 1))));
  });

  function resolve(decision, via) {
    if (!req) return;
    const r = req;
    req = null;
    clearTimeout(tm);
    cancelAnimationFrame(raf);
    IRAS.closeDialog(dlg);
    bus.emit("approval_result", { id: r.id, decision, via: via || "button" });
  }
  IRAS.resolveApproval = resolve;

  $("#apDeny").addEventListener("click", () => resolve("deny", "button"));
  $("#apApprove").addEventListener("click", () => resolve("approve", "button"));
  /* Esc is a decision: deny. The dialog can never be dismissed into a limbo state. */
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); resolve("deny", "escape"); });
})();
