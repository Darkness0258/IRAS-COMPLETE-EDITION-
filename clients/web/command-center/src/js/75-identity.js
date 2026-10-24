/* ==========================================================================
   Identity: real Face ID and real Voice ID.

     GET    /v1/identity/status                     is each one ready on the server
     GET    /v1/identity/people                     who she knows
     POST   /v1/identity/face/enroll    { name, image }   one picture of one person
     POST   /v1/identity/face/verify    { image, frames } who is this
     POST   /v1/identity/voice/enroll   { name, audio }   one recording of one person
     POST   /v1/identity/voice/verify   { audio }         who is speaking
     DELETE /v1/identity/people/{id}/face               forget a face
     DELETE /v1/identity/people/{id}/voice              forget a voice

   The camera and the microphone are only on while you teach or check, and only
   while you are on this screen. Pictures and recordings go to your server for one
   check and are thrown away. Only numbers are kept. Neither one replaces an approval.
   ========================================================================== */
"use strict";

(function () {
  let stream = null, busy = false;       // camera, and "a teach or check is running"
  let ear = null, stopRecording = null;  // microphone, and a way to end a recording early
  let micBefore = null;                  // what the header "Mic" chip said before Voice ID turned it on
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const say = (t) => { $("#facePrompt").textContent = t; };
  const hear = (t) => { $("#voicePrompt").textContent = t; };
  const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const STEPS = ["Look straight at the camera.", "Turn a little to the left.", "Turn a little to the right.", "Look straight again.", "Tilt your head a little."];
  const LINES = [
    "Hello IRAS, it is me. Please remember my voice, so you know when I am the one talking.",
    "The quick brown fox jumps over the lazy dog, then runs along the river to the old bridge.",
    "Today is a good day to start something new. Tell me what is on my list, and what to do first.",
  ];
  const CLIP_MS = 8000, CHECK_MS = 6000;  // how long each recording lasts
  const QUIET = 0.004;                    // below this the microphone heard nothing (about -48 dB)

  /* the name field on each card: if one is empty, use what is written in the other */
  function nameFrom(own, other) {
    const a = $(own), b = $(other), v = a.value.trim() || b.value.trim();
    if (v && !a.value.trim()) a.value = v;
    return v;
  }

  /* ---------- Face ID ---------- */
  function setCam(on) { S.cam = on ? "on" : "off"; bus.emit("cam", { state: on ? "on" : "off" }); }

  async function startCam() {
    if (stream) return true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    } catch (e) {
      say("I cannot use the camera. Allow it for this site, then try again.");
      return false;
    }
    const v = $("#faceVideo");
    v.srcObject = stream;
    await v.play().catch(() => {});
    setCam(true);
    $("#faceCam span").textContent = "Stop camera";
    say("Camera is on.");
    return true;
  }

  function stopCam() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    $("#faceVideo").srcObject = null;
    setCam(false);
    $("#faceCam span").textContent = "Start camera";
  }

  function snap() {
    const v = $("#faceVideo"), c = document.createElement("canvas");
    const w = Math.min(640, v.videoWidth || 640), h = Math.round((w * (v.videoHeight || 480)) / (v.videoWidth || 640));
    c.width = w; c.height = h;
    c.getContext("2d").drawImage(v, 0, 0, w, h);
    return c.toDataURL("image/jpeg", 0.85);
  }

  async function enroll() {
    const name = nameFrom("#faceName", "#voiceName");
    if (!name) { say("Write your name first."); $("#faceName").focus(); return; }
    if (busy) return;
    busy = true;
    try {
      if (!(await startCam())) return;
      let good = 0;
      for (let i = 0; i < STEPS.length; i++) {
        say(STEPS[i] + " (" + (i + 1) + " of " + STEPS.length + ")");
        await sleep(1500);
        try { await IRAS.api("/v1/identity/face/enroll", json({ name, image: snap() })); good++; }
        catch (e) { say(e.message); await sleep(1500); }
      }
      if (good >= 3) {
        say("Done. I know your face now, " + name + ".");
        if (IRAS.voice) IRAS.voice.speak("Okay " + name + ". I will remember you.");
      } else say("I only got " + good + " good pictures. Try again in better light.");
    } finally { busy = false; refresh(); }
  }

  async function check() {
    if (busy) return;
    busy = true;
    try {
      if (!(await startCam())) return;
      say("Turn your head slowly left and right.");
      const frames = [];
      for (let i = 0; i < 5; i++) { await sleep(500); frames.push(snap()); }
      const r = await IRAS.api("/v1/identity/face/verify", json({ image: frames[2], frames }));
      const live = r.liveness && r.liveness.checked ? (r.liveness.passed ? " I saw you turn your head." : " I did not see you turn your head, so I cannot rule out a photo.") : "";
      if (!r.faces) say("I cannot see a face.");
      else if (r.match) {
        say("It is " + r.match.name + " (" + Math.round(r.match.score * 100) + "% sure)." + live);
        if (IRAS.voice) IRAS.voice.speak("Hey " + r.match.name + ". It is you.");
      } else say((r.message || "I do not know you.") + live);
    } catch (e) { say(e.message || "That did not work."); }
    finally { busy = false; }
  }

  /* ---------- Voice ID: recording ---------- */
  function level(v) { $("#voiceLevel").style.setProperty("--p", String(clamp(v * 7, 0, 1))); }
  function clock(t) { $("#voiceTime").textContent = t || "\u00a0"; }

  function drawLines(state) {
    $("#voiceLines").innerHTML = LINES.map((t, i) => {
      const s = state[i] || "";
      return `<li data-s="${s}">${icon(s === "done" ? "circle-check" : s === "now" ? "loader-circle" : "circle-dot", "i-sm")}<span>${esc(t)}</span></li>`;
    }).join("");
  }

  /* Opens the microphone. The sound context is made first, straight from your tap,
     because some phones only allow that. */
  async function openEar() {
    if (ear) return true;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      hear("This browser cannot record sound. Use Chrome, Edge or Safari.");
      return false;
    }
    const ctx = new AC();
    try { if (ctx.state === "suspended") await ctx.resume(); } catch (e) { /* the first recording tries again */ }
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
      ear = { ctx, mic };
      micBefore = S.mic;  // the header chip tells the truth while she records
      S.mic = "on"; bus.emit("mic", { state: "on" });
      return true;
    } catch (e) {
      ctx.close().catch(() => {});
      hear(e && e.name === "NotReadableError"
        ? "The microphone is busy. Close whatever else is using it, then try again."
        : "I cannot use the microphone. Allow it for this site, then try again.");
      return false;
    }
  }

  function closeEar() {
    if (!ear) return;
    const { ctx, mic } = ear;
    ear = null;
    mic.getTracks().forEach((t) => t.stop());
    ctx.close().catch(() => {});
    level(0); clock("");
    if (micBefore !== null) {
      if (micBefore !== "on") { S.mic = micBefore; bus.emit("mic", { state: micBefore }); }  // if it was on already, leave it
      micBefore = null;
    }
  }

  function joinChunks(chunks) {
    let n = 0;
    for (const c of chunks) n += c.length;
    const out = new Float32Array(n);
    let at = 0;
    for (const c of chunks) { out.set(c, at); at += c.length; }
    return out;
  }

  /* Records for `ms` milliseconds. Resolves with { samples, rate, peak }.
     (A script processor is old but works in every browser and in the Android web view.) */
  async function recordClip(ms) {
    const { ctx, mic } = ear;
    if (ctx.state === "suspended") { try { await ctx.resume(); } catch (e) { /* try anyway */ } }
    return new Promise((resolve, reject) => {
      const chunks = [], src = ctx.createMediaStreamSource(mic), node = ctx.createScriptProcessor(4096, 1, 1), mute = ctx.createGain();
      mute.gain.value = 0;  // the processor only runs while connected to the output, and she must not play you back
      let peak = 0, over = false;
      const t0 = performance.now();
      const finish = (err) => {
        if (over) return;
        over = true;
        clearInterval(tick);
        node.onaudioprocess = null;
        try { src.disconnect(); node.disconnect(); mute.disconnect(); } catch (e) { /* already apart */ }
        stopRecording = null; level(0); clock("");
        if (err) reject(err); else resolve({ samples: joinChunks(chunks), rate: ctx.sampleRate, peak });
      };
      node.onaudioprocess = (e) => {
        const x = e.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(x));  // a copy: the browser reuses its buffer
        let sum = 0;
        for (let i = 0; i < x.length; i++) sum += x[i] * x[i];
        const rms = Math.sqrt(sum / x.length);
        if (rms > peak) peak = rms;
        level(rms);
      };
      const tick = setInterval(() => {
        const left = Math.max(0, ms - (performance.now() - t0));
        clock(Math.ceil(left / 1000) + " s");
        if (left <= 0) finish();
      }, 100);
      stopRecording = () => finish(Object.assign(new Error("stopped"), { stopped: true }));
      src.connect(node); node.connect(mute); mute.connect(ctx.destination);
    });
  }

  /* ---------- Voice ID: sending ---------- */
  /* 16-bit mono WAV, which is all the server needs to read. */
  function wavBlob(samples, rate) {
    const n = samples.length, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    const text = (at, s) => { for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i)); };
    text(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); text(8, "WAVE"); text(12, "fmt ");
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    text(36, "data"); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buf], { type: "audio/wav" });
  }

  function dataUrl(blob) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(r.error || new Error("Could not prepare the recording."));
      r.readAsDataURL(blob);
    });
  }

  /* The model listens at 16 000 samples a second. The browser records at 44 100 or 48 000,
     so it is brought down here, which also makes the upload three times smaller.
     If the browser cannot do that, the server does it. */
  async function to16k(samples, rate) {
    if (rate === 16000) return samples;
    try {
      const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const job = new Offline(1, Math.max(1, Math.ceil((samples.length * 16000) / rate)), 16000);
      const buffer = job.createBuffer(1, samples.length, rate);
      buffer.getChannelData(0).set(samples);
      const source = job.createBufferSource();
      source.buffer = buffer; source.connect(job.destination); source.start();
      return (await job.startRendering()).getChannelData(0);
    } catch (e) { return null; }
  }

  async function pack(clip) {
    const small = await to16k(clip.samples, clip.rate);
    return dataUrl(wavBlob(small || clip.samples, small ? 16000 : clip.rate));
  }

  const NO_SOUND = "I heard no sound. Check that your microphone is on and not muted.";
  const failed = (e) => hear((e && e.message) || "That did not work.");

  /* ---------- Voice ID: teaching and checking ---------- */
  async function teachVoice() {
    const name = nameFrom("#voiceName", "#faceName");
    if (!name) { hear("Write your name first."); $("#voiceName").focus(); return; }
    if (busy) return;
    busy = true;
    const state = LINES.map(() => "");
    try {
      if (!(await openEar())) return;
      let good = 0;
      for (let i = 0; i < LINES.length; i++) {
        state[i] = "now"; drawLines(state);
        hear("Line " + (i + 1) + " of " + LINES.length + ": say it out loud. Keep talking until the time ends.");
        try {
          const clip = await recordClip(CLIP_MS);
          if (clip.peak < QUIET) throw new Error(NO_SOUND);
          hear("Checking…");
          await IRAS.api("/v1/identity/voice/enroll", json({ name, audio: await pack(clip) }));
          good++; state[i] = "done";
        } catch (e) {
          state[i] = "";
          if (e && e.stopped) return;  // you left this screen
          failed(e);
          drawLines(state);
          await sleep(2500);
        }
        drawLines(state);
      }
      closeEar();
      if (good >= 2) {
        hear("Done. I know your voice now, " + name + ".");
        if (IRAS.voice) IRAS.voice.speak("Okay " + name + ". I will remember your voice.");
      } else hear("I only got " + good + " good recording" + (good === 1 ? "" : "s") + ". Try again in a quiet place, close to the microphone.");
    } finally { closeEar(); busy = false; refresh(); }
  }

  async function checkVoice() {
    if (busy) return;
    busy = true;
    try {
      if (!(await openEar())) return;
      hear("Say anything for a few seconds. Talk the way you normally do.");
      let r;
      try {
        const clip = await recordClip(CHECK_MS);
        closeEar();
        if (clip.peak < QUIET) throw new Error(NO_SOUND);
        hear("Checking…");
        r = await IRAS.api("/v1/identity/voice/verify", json({ audio: await pack(clip) }));
      } catch (e) {
        if (!(e && e.stopped)) failed(e);
        return;
      }
      if (!r.heard) hear(r.message);
      else if (r.match) {
        hear("It is " + r.match.name + " (" + Math.round(r.match.score * 100) + "% sure).");
        if (IRAS.voice) IRAS.voice.speak("Hey " + r.match.name + ". I know your voice.");
      } else {
        hear((r.message || "I do not know you.") + (r.closest ? " The closest voice I know is " + r.closest.name + " (" + Math.round(r.closest.score * 100) + "%)." : ""));
      }
    } finally { closeEar(); busy = false; }
  }

  /* ---------- who she knows ---------- */
  function badge(sel, count) {
    const b = $(sel);
    b.className = "badge" + (count ? " accent" : "");
    b.textContent = count ? count + (count === 1 ? " person" : " people") : "Not set up";
  }

  function row(x, count, noun, attr) {
    return `<li class="id-row"><span class="grow"><strong>${esc(x.name)}</strong> <span class="muted">${count} ${noun}${count === 1 ? "" : "s"}</span></span>` +
      `<button type="button" class="btn-icon sm" ${attr}="${esc(x.person_id)}" aria-label="Forget ${esc(x.name)}" title="Forget">${icon("trash-2", "i-sm")}</button></li>`;
  }

  async function refresh() {
    try {
      const [s, p] = await Promise.all([IRAS.api("/v1/identity/status"), IRAS.api("/v1/identity/people")]);
      const people = p.people || [], v = s.voice || {};
      const withFace = people.filter((x) => x.faces > 0), withVoice = people.filter((x) => x.voices > 0);
      badge("#faceBadge", withFace.length);
      badge("#voiceBadge", withVoice.length);
      $("#faceHint").textContent = !s.available ? s.reason : s.models_ready ? "" : "The first picture downloads the face models (15 MB). It can take a minute.";
      $("#voiceHint").textContent = v.available === false ? v.reason : v.models_ready === false ? "The first recording downloads the voice model (26 MB). It can take a minute." : "";
      $("#faceList").innerHTML = withFace.map((x) => row(x, x.faces, "picture", "data-forget")).join("");
      $("#voiceList").innerHTML = withVoice.map((x) => row(x, x.voices, "recording", "data-forget-voice")).join("");
    } catch (e) {
      const m = e.message || "Cannot reach your server.";
      $("#faceHint").textContent = m;
      $("#voiceHint").textContent = m;
    }
  }

  async function forget(id, what, ask) {
    if (!window.confirm(ask)) return;
    try { await IRAS.api("/v1/identity/people/" + encodeURIComponent(id) + "/" + what, { method: "DELETE" }); toast("Forgotten.", { icon: "trash-2" }); }
    catch (x) { toast("Could not forget them. " + (x.message || ""), { icon: "cloud-off", timeout: 7000 }); }
    refresh();
  }

  IRAS.initIdentity = function () {
    drawLines(LINES.map(() => ""));
    $("#faceCam").addEventListener("click", () => { if (stream) stopCam(); else startCam(); });
    $("#faceEnroll").addEventListener("click", enroll);
    $("#faceCheck").addEventListener("click", check);
    $("#voiceEnroll").addEventListener("click", teachVoice);
    $("#voiceCheck").addEventListener("click", checkVoice);
    $("#faceList").addEventListener("click", (e) => {
      const b = e.target.closest("[data-forget]");
      if (b) forget(b.dataset.forget, "face", "Forget this face? Every faceprint of them is deleted.");
    });
    $("#voiceList").addEventListener("click", (e) => {
      const b = e.target.closest("[data-forget-voice]");
      if (b) forget(b.dataset.forgetVoice, "voice", "Forget this voice? Every voiceprint of them is deleted.");
    });
    bus.on("view", (e) => {
      if (e.view === "identity") { refresh(); return; }
      if (stream) stopCam();
      if (stopRecording) stopRecording();
    });
    bus.on("visibility", (e) => {
      if (!e.hidden) return;
      if (stream) stopCam();
      if (stopRecording) stopRecording();
    });
  };
})();
