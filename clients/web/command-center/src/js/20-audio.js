/* ==========================================================================
   Audio levels. The orb is voice-reactive: it reads S.level.mic while you
   talk and S.level.tts while IRAS speaks.

   Real microphone: Web Audio API AnalyserNode. Audio never leaves the page.
   Demo fallback:   a speech-shaped envelope (words and gaps), so the orb
                    still moves when there is no microphone or no permission.
   ========================================================================== */
"use strict";

(function () {
  const audio = { ctx: null, an: null, stream: null, src: null, buf: null, raf: 0, on: false };
  IRAS.audio = audio;

  function setLevel(source, v) {
    v = clamp(v, 0, 1);
    S.level[source] = v;
    bus.emit("audio_level", { source, level: v });
  }
  audio.setLevel = setLevel;

  audio.start = async function () {
    if (audio.on) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      S.mic = "blocked"; bus.emit("mic", { state: "blocked", reason: "unsupported" });
      return false;
    }
    try {
      audio.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      const AC = window.AudioContext || window.webkitAudioContext;
      audio.ctx = new AC();
      if (audio.ctx.state === "suspended") await audio.ctx.resume();
      audio.an = audio.ctx.createAnalyser();
      audio.an.fftSize = 1024;
      audio.an.smoothingTimeConstant = .5;
      audio.src = audio.ctx.createMediaStreamSource(audio.stream);
      audio.src.connect(audio.an);
      audio.buf = new Uint8Array(audio.an.fftSize);
      audio.on = true;
      S.mic = "on";
      bus.emit("mic", { state: "on" });
      audio.loop();
      return true;
    } catch (e) {
      S.mic = "blocked";
      bus.emit("mic", { state: "blocked", reason: e && e.name });
      return false;
    }
  };

  audio.stop = function () {
    cancelAnimationFrame(audio.raf);
    audio.on = false;
    if (audio.stream) audio.stream.getTracks().forEach((t) => t.stop());
    if (audio.ctx) audio.ctx.close().catch(() => {});
    audio.stream = audio.ctx = audio.an = audio.src = null;
    S.mic = "off";
    setLevel("mic", 0);
    bus.emit("mic", { state: "off" });
  };

  audio.loop = function () {
    if (!audio.on) return;
    audio.raf = requestAnimationFrame(audio.loop);
    if (document.hidden || !audio.an) return;
    audio.an.getByteTimeDomainData(audio.buf);
    let sum = 0;
    for (let i = 0; i < audio.buf.length; i++) { const v = (audio.buf[i] - 128) / 128; sum += v * v; }
    const rms = Math.sqrt(sum / audio.buf.length);
    setLevel("mic", clamp((rms - .012) * 9, 0, 1));
  };

  /* A level shaped like speech: words of 160-420ms with short gaps. */
  audio.envelope = function (source, ms, signal) {
    return new Promise((resolve) => {
      const t0 = performance.now();
      let wordEnd = 0, gapEnd = 0, amp = 0;
      const iv = setInterval(() => {
        const t = performance.now() - t0;
        if ((signal && signal.aborted) || t >= ms) { clearInterval(iv); setLevel(source, 0); resolve(); return; }
        if (t >= gapEnd && t >= wordEnd) { amp = rand(.4, .95); wordEnd = t + rand(160, 420); gapEnd = wordEnd + rand(50, 150); }
        const w = t < wordEnd ? (.7 + .3 * Math.sin(t / 38)) * amp : 0;
        setLevel(source, w * (.85 + .15 * Math.random()));
      }, 33);
      if (signal) signal.addEventListener("abort", () => { clearInterval(iv); setLevel(source, 0); resolve(); }, { once: true });
    });
  };
})();
