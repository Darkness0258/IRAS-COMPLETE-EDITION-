/* ==========================================================================
   Voice: she listens to you and answers in her own voice.

   Listening  the browser's speech recognition (Chrome, Edge, Safari).
   Speaking   POST /v1/tts on your server, so she keeps the voice you set there.

   She speaks when you spoke to her, or when "Speak replies" is on.
   ========================================================================== */
"use strict";

(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  let rec = null, said = "", reply = "", viaVoice = false, player = null, playId = 0, ctx = null;

  const voice = (IRAS.voice = { supported: !!SR });

  /* ---------- listening ---------- */
  voice.toggle = function () {
    if (rec) { rec.stop(); return; }                 // second tap: stop and send what she heard
    if (S.ui === "speaking") voice.stopSpeaking();   // you spoke over her
    if (!SR) { toast("This browser cannot listen. Use Chrome, Edge or Safari, or type.", { icon: "mic-off", timeout: 7000 }); return; }
    rec = new SR();
    rec.lang = settings.voiceLang || navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    said = "";
    rec.onstart = () => bus.emit("wake", { via: "mic" });
    rec.onresult = (ev) => {
      let t = "", fin = false;
      for (let i = ev.resultIndex; i < ev.results.length; i++) { t += ev.results[i][0].transcript; if (ev.results[i].isFinal) fin = true; }
      said = t.trim();
      bus.emit("partial_transcript", { text: said, final: fin });
    };
    rec.onerror = (ev) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") toast("The microphone is blocked. Allow it for this site, then try again.", { icon: "mic-off", timeout: 8000 });
      else if (ev.error !== "no-speech" && ev.error !== "aborted") toast("I could not hear you (" + ev.error + ").", { icon: "mic-off" });
    };
    rec.onend = () => {
      rec = null;
      if (said) {
        S.heard = said; S.heardVia = "voice"; viaVoice = true; reply = "";
        bus.emit("speech_end", { text: said });
        IRAS.live.send(said, { via: "voice" });
      } else if (S.ui === "listening") bus.emit("cancel");
    };
    try { rec.start(); } catch (e) { rec = null; bus.emit("cancel"); }
  };

  /* ---------- speaking ---------- */
  const clean = (t) => String(t || "").replace(/```[\s\S]*?```/g, " ").replace(/[*_`#>|~]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 900);

  function meter(el) {   // lets the orb move with her voice
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === "suspended") ctx.resume();
      const an = ctx.createAnalyser(); an.fftSize = 256;
      const src = ctx.createMediaElementSource(el); src.connect(an); an.connect(ctx.destination);
      const buf = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        if (el !== player) return;
        an.getByteFrequencyData(buf);
        let sum = 0; for (let i = 0; i < buf.length; i++) sum += buf[i];
        bus.emit("audio_level", { source: "tts", level: Math.min(1, sum / buf.length / 110) });
        setTimeout(tick, 50);
      };
      tick();
    } catch (e) { /* the orb stays calm; the sound still plays */ }
  }

  voice.speak = async function (raw) {
    const text = clean(raw);
    if (!text || !base()) return;
    const id = ++playId;
    try {
      const r = await fetch(base() + "/v1/tts", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json", "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}),
        body: JSON.stringify({ text }),
      });
      if (!r.ok) throw new Error("The server answered " + r.status + ".");
      const blob = await r.blob();
      if (id !== playId) return;   // you cut her off while she was getting ready
      const url = URL.createObjectURL(blob);
      const el = (player = new Audio(url));
      el.onended = el.onerror = () => { URL.revokeObjectURL(url); if (el === player) { player = null; bus.emit("tts_end", {}); } };
      bus.emit("tts_start", { text });
      meter(el);
      await el.play();
    } catch (err) {
      player = null; bus.emit("tts_end", {});
      toast("I could not speak that. " + (err.message || ""), { icon: "cloud-off", timeout: 6000 });
    }
  };

  voice.stopSpeaking = function () {
    playId++;
    if (player) { player.pause(); player = null; }
    if (S.ui === "speaking") bus.emit("tts_end", {});
  };

  bus.on("submit", () => { reply = ""; viaVoice = false; });
  bus.on("token", (e) => { reply += (e && e.text) || ""; });
  bus.on("done", () => { if (viaVoice || settings.speakReplies) voice.speak(reply); viaVoice = false; });
})();
