/* ==========================================================================
   Settings
   ========================================================================== */
"use strict";

(function () {
  const radios = (name) => $$(`input[name="${name}"]`);
  const setRadio = (name, val) => radios(name).forEach((r) => { r.checked = r.value === val; });

  function reflect() {
    setRadio("theme", settings.theme);
    setRadio("skin", settings.skin);
    setRadio("perf", settings.perf);
    setRadio("source", settings.source);
    $("#setMotion").checked = settings.motion === "reduce";
    $("#voiceProfile").value = settings.voiceProfile;
    $("#voiceMood").value = settings.mood;
    $("#language").value = settings.language;
    $("#wake").value = settings.wake;
    $("#setSpeak").checked = !!settings.speakReplies;
    $("#setRealMic").checked = !!settings.realMic;
    $("#server").value = settings.server || "";
    $("#token").value = store.sget("iras-api-token", "");
    $("#liveFields").hidden = settings.source !== "live";
  }

  IRAS.initSettings = function () {
    reflect();

    radios("theme").forEach((r) => r.addEventListener("change", () => setSetting("theme", r.value)));
    radios("skin").forEach((r) => r.addEventListener("change", () => setSetting("skin", r.value)));
    radios("perf").forEach((r) => r.addEventListener("change", () => {
      setSetting("perf", r.value);
      toast(r.value === "lite" ? "Performance mode on. No blur, no particles, no loops." : r.value === "full" ? "Full effects on." : "Auto. I will switch if this device struggles.", { icon: "gauge" });
    }));
    $("#setMotion").addEventListener("change", (e) => setSetting("motion", e.target.checked ? "reduce" : "system"));

    $("#voiceProfile").addEventListener("change", (e) => setSetting("voiceProfile", e.target.value));
    $("#voiceMood").addEventListener("change", (e) => setSetting("mood", e.target.value));
    $("#language").addEventListener("change", (e) => setSetting("language", e.target.value));
    $("#wake").addEventListener("change", (e) => setSetting("wake", e.target.value.trim() || "IRAS"));
    $("#setSpeak").addEventListener("change", (e) => setSetting("speakReplies", e.target.checked));
    $("#setRealMic").addEventListener("change", (e) => {
      setSetting("realMic", e.target.checked);
      if (!e.target.checked && IRAS.audio.on) IRAS.audio.stop();
    });

    radios("source").forEach((r) => r.addEventListener("change", () => {
      setSetting("source", r.value);
      $("#liveFields").hidden = r.value !== "live";
      IRAS.applySource();
      toast(r.value === "live" ? "Live mode. Messages go to your server." : "Demo mode. Sample data again.", { icon: r.value === "live" ? "server" : "flask-conical" });
    }));
    $("#server").addEventListener("change", (e) => { setSetting("server", e.target.value.trim()); if (settings.source === "live") IRAS.live.connect(); });
    $("#token").addEventListener("change", (e) => { store.sset("iras-api-token", e.target.value.trim()); if (settings.source === "live") IRAS.live.connect(); });

    $("#connTest").addEventListener("click", async () => {
      const st = $("#connStatus");
      setSetting("server", $("#server").value.trim(), { silent: true });
      store.sset("iras-api-token", $("#token").value.trim());
      st.textContent = "Checking…";
      const res = await IRAS.live.test();
      st.textContent = res.message;
      toast(res.ok ? "Connected." : res.partial ? "Reached the server, but the token was refused." : "Could not connect.", { icon: res.ok ? "check" : "cloud-off" });
    });

    /* the classic web client keeps its own config; offer to reuse it */
    try {
      const c = JSON.parse(localStorage.getItem("iras-config") || "null");
      if (c && (c.server || c.voiceProfile)) $("#connImport").hidden = false;
    } catch (e) { /* ignore */ }
    $("#connImport").addEventListener("click", () => {
      try {
        const c = JSON.parse(localStorage.getItem("iras-config") || "{}");
        if (c.server) settings.server = c.server;
        if (c.wakeWord) settings.wake = c.wakeWord;
        if (c.language) settings.language = c.language;
        if (c.voiceProfile) settings.voiceProfile = c.voiceProfile;
        if (c.voiceMood) settings.mood = c.voiceMood;
        saveSettings(); reflect();
        toast("Imported from the classic web app. The token is still tab-only, so type it again if needed.", { icon: "download", timeout: 6500 });
      } catch (e) { toast("Could not read the classic settings.", { icon: "info" }); }
    });

    $("#resetSettings").addEventListener("click", () => {
      Object.keys(settings).forEach((k) => delete settings[k]);
      Object.assign(settings, DEFAULTS);
      saveSettings();
      IRAS.env.autoLite = false;
      applyAppearance();
      reflect();
      IRAS.applySource();
      toast("Settings are back to the defaults.", { icon: "rotate-ccw" });
    });

    /* keep the form in step when something else changes a setting (palette, theme button) */
    bus.on("setting", () => reflect());
  };
})();
