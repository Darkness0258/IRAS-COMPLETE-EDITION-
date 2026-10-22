/* ==========================================================================
   Voice: she listens to you and answers in her own voice.

   Listening  the browser's speech recognition (Chrome, Edge, Safari).
   Speaking   POST /v1/tts on your server, one sentence at a time. She starts
              talking after the first sentence, while the rest is still being
              written, and the next sentence is ready before the last one ends.
              If the server cannot make her voice, you see the reason. The page
              never swaps in a robot voice on its own.

   She speaks when you spoke to her, or when "Speak replies" is on.
   ========================================================================== */
"use strict";

(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const base = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const token = () => store.sget("iras-api-token", "");
  const voice = (IRAS.voice = { supported: !!SR || !!(window.IRASNative) });
  let rec = null, said = "";

  /* ---------- listening ---------- */
  const native = () => { try { return !!(window.IRASNative && window.IRASNative.canListen()); } catch (e) { return false; } };
  let nativeOn = false;

  function finishHeard() {
    if (said) {
      S.heard = said; S.heardVia = "voice";
      begin(true);
      bus.emit("speech_end", { text: said });
      IRAS.live.send(said, { via: "voice" });
    } else if (S.ui === "listening") bus.emit("cancel");
  }

  function startNative() {   // inside the Android app, which has no browser speech recognition
    said = ""; nativeOn = true;
    window.IRASNativeSpeech = {
      event(e) {
        if (e.type === "partial" || e.type === "final") { said = e.text; bus.emit("partial_transcript", { text: said, final: e.type === "final" }); }
        else if (e.type === "error" && e.text !== "6" && e.text !== "7") toast("I could not hear you (code " + e.text + ").", { icon: "mic-off" });
        else if (e.type === "end") { nativeOn = false; finishHeard(); }
      },
    };
    bus.emit("wake", { via: "mic" });
    window.IRASNative.listen(settings.voiceLang || navigator.language || "en-US");
  }
  voice.toggle = function () {
    if (nativeOn) { window.IRASNative.stop(); return; }
    if (rec) { rec.stop(); return; }                 // second tap: stop and send what she heard
    if (S.ui === "speaking") voice.stopSpeaking();   // you spoke over her
    if (native()) { startNative(); return; }
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
    rec.onend = () => { rec = null; finishHeard(); };
    try { rec.start(); } catch (e) { rec = null; bus.emit("cancel"); }
  };

  /* ---------- speaking: a queue of sentences ---------- */
  let sess = 0, spoken = 0, cut = false, buf = "", inCode = false, queue = [], busy = false, done = true, started = false, failed = false, wanted = false, player = null, endNow = null, ctx = null;

  async function fetchAudio(text) {
    const r = await fetch(base() + "/v1/tts", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json", "X-Device-ID": "web" }, token() ? { Authorization: "Bearer " + token() } : {}),
      body: JSON.stringify({ text, mood: settings.voiceMood || "warm", voice_gender: "female", voice_profile: settings.voiceProfile || "iras_human" }),
    });
    if (!r.ok) {
      let d = ""; try { d = (await r.json()).detail; } catch (e) { /* no body */ }
      throw new Error(typeof d === "string" && d ? d : "The server answered " + r.status + ".");
    }
    return { blob: await r.blob(), voice: r.headers.get("X-IRAS-Voice") || "", fallback: r.headers.get("X-IRAS-Voice-Fallback") === "true", note: r.headers.get("X-IRAS-Voice-Note") || "" };
  }

  function meter(el) {   // lets the orb move with her voice
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === "suspended") ctx.resume();
      const an = ctx.createAnalyser(); an.fftSize = 256;
      const src = ctx.createMediaElementSource(el); src.connect(an); an.connect(ctx.destination);
      const data = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        if (el !== player) return;
        an.getByteFrequencyData(data);
        let sum = 0; for (let i = 0; i < data.length; i++) sum += data[i];
        bus.emit("audio_level", { source: "tts", level: Math.min(1, sum / data.length / 110) });
        setTimeout(tick, 50);
      };
      tick();
    } catch (e) { /* the orb stays calm; the sound still plays */ }
  }

  function play(blob) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(blob), el = new Audio(url);
      player = el;
      const end = () => { URL.revokeObjectURL(url); if (player === el) player = null; endNow = null; resolve(); };
      endNow = end; el.onended = end; el.onerror = end;
      if (!started) { started = true; bus.emit("tts_start", { text: "" }); }
      meter(el);
      el.play().catch(end);
    });
  }

  async function pump() {
    if (busy) return;
    const item = queue.shift();
    if (!item) { if (done && started) { started = false; bus.emit("tts_end", {}); } return; }
    if (item.my !== sess) return pump();
    busy = true;
    try {
      const a = await item.p;
      if (item.my === sess) await play(a.blob);
    } catch (err) {
      if (!failed && item.my === sess) { failed = true; toast("I could not speak. " + (err.message || ""), { icon: "cloud-off", timeout: 12000 }); }
    }
    busy = false;
    pump();
  }

  function enqueue(text) {
    const t = text.trim();
    if (!t) return;
    const p = fetchAudio(t);
    p.catch(() => { /* shown when its turn comes */ });
    queue.push({ p, my: sess });
    pump();
  }

  function begin(want) {   // a new answer starts: forget the old one
    sess++; spoken = 0; cut = false; buf = ""; inCode = false; queue = []; done = false; failed = false; wanted = want;
  }

  const MAX_SPOKEN = 380;   // about 3 or 4 sentences; the rest stays on screen
  const TAILS = ["The rest is on your screen.", "I put the details on your screen.", "You can read the rest there."];
  const minChunk = () => (/^gemini_/.test(settings.voiceProfile || "") ? 110 : 28);
  const BOUND = /[.!?…]["')\]]*(?=\s|$)/g;
  function flush(final) {
    for (;;) {
      let cut = -1;
      BOUND.lastIndex = 0;
      for (let m; (m = BOUND.exec(buf)); ) { if (m.index + m[0].length >= minChunk()) { cut = m.index + m[0].length; break; } }
      if (cut < 0 && final && buf.trim()) cut = buf.length;
      if (cut < 0) return;
      const chunk = buf.slice(0, cut); buf = buf.slice(cut);
      const fences = (chunk.match(/```/g) || []).length;
      const skip = inCode || fences > 0;   // code stays on screen, she does not read it
      if (fences % 2) inCode = !inCode;
      if (!skip) { if (spoken >= MAX_SPOKEN) cut = true; else { spoken += chunk.length; enqueue(chunk); } }
    }
  }

  voice.stopSpeaking = function () {
    sess++; queue = []; buf = ""; done = true;
    if (player) { try { player.pause(); } catch (e) { /* already stopped */ } }
    if (endNow) endNow();
    if (started) { started = false; bus.emit("tts_end", {}); }
  };

  voice.speak = function (raw) {   // one-off lines, such as her own notices
    if (started || busy || !base()) return;
    begin(true); done = true;
    enqueue(String(raw || ""));
  };

  voice.test = async function () {
    if (!base()) { toast("Add your server address in Settings first.", { icon: "cloud-off" }); return; }
    voice.stopSpeaking();
    toast("Asking your server for her voice…", { icon: "info", timeout: 3000 });
    try {
      const a = await fetchAudio("Hi, it's me. Can you hear me clearly? This is how I sound.");
      toast(a.note ? a.note + " She used a backup voice: " + a.voice : a.fallback ? "She used a backup voice: " + a.voice : "Her voice works: " + (a.voice || "default"), { icon: a.note || a.fallback ? "info" : "check", timeout: a.note ? 20000 : 7000 });
      begin(true); done = true;
      queue.push({ p: Promise.resolve(a), my: sess });
      pump();
    } catch (err) {
      toast("Her voice failed: " + (err.message || "unknown error") + " If it mentions 403 or a handshake, the voice service may be refusing your Render server.", { icon: "cloud-off", timeout: 20000 });
    }
  };
  document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest("#voiceTest")) voice.test(); });

  bus.on("submit", () => begin(!!settings.speakReplies));
  bus.on("token", (e) => { if (wanted && !done) { buf += (e && e.text) || ""; flush(false); } });
  bus.on("done", () => {
    if (wanted) { flush(true); if (cut) enqueue(TAILS[Math.floor(Math.random() * TAILS.length)]); }
    done = true; pump();
  });
})();
