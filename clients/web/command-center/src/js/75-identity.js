/* ==========================================================================
   Identity: Face ID and Voice ID enrollment (preview).

   Honest by design: the face mesh is an animated stand-in, not tracking.
   With the camera on, the mesh is hidden and only the progress ring shows.
   The microphone level is real when you allow it. Nothing is recorded.
   ========================================================================== */
"use strict";

(function () {
  const KEY = "iras-cc-identity";
  const ident = Object.assign({ face: false, voice: false }, store.get(KEY, {}));
  const fCanvas = $("#faceCanvas"), vCanvas = $("#voiceCanvas"), stage = $("#faceStage"), video = $("#faceVideo");
  let fg, vg, fw = 0, vw = 0, vh = 0, dpr = 1, raf = 0, last = 0, time = 0, col = {};
  let faceCtl = null, voiceCtl = null;

  const STEPS = [
    { label: "Look straight", prompt: "Look straight at the screen", yaw: 0, ms: 2300 },
    { label: "Turn left", prompt: "Slowly turn your head to the left", yaw: -.5, ms: 2500 },
    { label: "Turn right", prompt: "Now slowly to the right", yaw: .5, ms: 2500 },
    { label: "Blink twice", prompt: "Look straight and blink twice", yaw: 0, ms: 2300 },
  ];
  const PHRASES = ["Hey IRAS, it is me.", "Play something calm.", "Yes, I approve this."];
  const face = { running: false, step: -1, stepAt: 0, progress: 0, yaw: 0, target: 0, done: ident.face, cam: false, stream: null };
  const voice = { running: false, step: -1, done: ident.voice, levels: new Array(96).fill(0), quality: ident.voice ? 96 : 0, acc: 0 };

  function readColors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    col = { accent: v("--accent"), fill: v("--accent-fill"), line: v("--line"), text: v("--text"), muted: v("--muted"), bg: v("--surface-solid") };
  }

  /* ---------- a stand-in face mesh: points in 3D, joined to their nearest neighbours ---------- */
  const pts = [], links = [];
  (function build() {
    const add = (x, y, z, g) => pts.push({ x, y, z, g });
    for (let i = 0; i < 34; i++) { const a = (i / 34) * Math.PI * 2 + Math.PI / 2; add(Math.cos(a) * 84, Math.sin(a) * 108 - 6, 34 - Math.abs(Math.cos(a)) * 80, "oval"); }
    for (const s of [-1, 1]) for (let i = 0; i < 5; i++) { const t = i / 4; add(s * (14 + t * 34), -46 - 7 * Math.sin(t * Math.PI), 36 - t * 8, "brow"); }
    for (const s of [-1, 1]) for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2; add(s * 34 + Math.cos(a) * 15, -24 + Math.sin(a) * 6.5, 36, s < 0 ? "eyeL" : "eyeR"); }
    for (let i = 0; i < 6; i++) { const t = i / 5; add(0, -20 + t * 40, 38 + t * 26, "nose"); }
    add(-11, 30, 48, "nose"); add(11, 30, 48, "nose"); add(-6, 34, 54, "nose"); add(6, 34, 54, "nose");
    for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; add(Math.cos(a) * 25, 62 + Math.sin(a) * 8.5 * (Math.sin(a) > 0 ? 1.3 : .8), 36 - Math.abs(Math.cos(a)) * 10, "mouth"); }
    for (const s of [-1, 1]) { add(s * 52, 20, 14, "cheek"); add(s * 58, 46, 4, "cheek"); add(s * 30, 80, 14, "cheek"); }
    for (let i = 0; i < 5; i++) add(-40 + i * 20, -78 + Math.abs(i - 2) * 5, 22, "forehead");
    add(0, 98, 24, "chin");
    const seen = new Set();
    pts.forEach((p, i) => {
      const near = pts.map((q, j) => [j, Math.hypot(p.x - q.x, p.y - q.y, (p.z - q.z) * .5)]).filter(([j, d]) => j !== i && d < 52).sort((a, b) => a[1] - b[1]).slice(0, 3);
      near.forEach(([j]) => { const k = i < j ? i + "-" + j : j + "-" + i; if (!seen.has(k)) { seen.add(k); links.push([i, j]); } });
    });
  })();

  /* ---------- face drawing ---------- */
  function drawFace(dt) {
    if (!fg || !fw) return;
    const W = fw, cx = W / 2, cy = W / 2, sc = (W / 340) * 1.14;
    const still = IRAS.env.reduceMotion;
    fg.clearRect(0, 0, W, W);

    face.yaw = still ? face.target : face.yaw + (face.target - face.yaw) * (1 - Math.exp(-dt * 4.5));
    const total = STEPS.length;
    let want = face.done ? 1 : 0;
    if (face.running && face.step >= 0) want = (face.step + clamp((performance.now() - face.stepAt) / STEPS[face.step].ms, 0, 1)) / total;
    face.progress += (want - face.progress) * (still ? 1 : 1 - Math.exp(-dt * 6));

    /* progress ring: 48 small arcs */
    const R = W * .455, N = 48, gap = .045;
    fg.lineWidth = Math.max(4, W * .016); fg.lineCap = "round";
    for (let i = 0; i < N; i++) {
      const a0 = (i / N) * Math.PI * 2 - Math.PI / 2 + gap / 2, a1 = ((i + 1) / N) * Math.PI * 2 - Math.PI / 2 - gap / 2;
      const on = i < Math.round(face.progress * N);
      fg.strokeStyle = on ? col.accent : col.line;
      fg.globalAlpha = on ? 1 : .8;
      fg.beginPath(); fg.arc(cx, cy, R, a0, a1); fg.stroke();
    }
    fg.globalAlpha = 1;

    fg.save();
    fg.beginPath(); fg.arc(cx, cy, R * .93, 0, Math.PI * 2); fg.clip();
    if (face.cam) {
      fg.strokeStyle = col.accent; fg.globalAlpha = .55; fg.lineWidth = 2; fg.setLineDash([6, 6]);
      fg.beginPath(); fg.ellipse(cx, cy, W * .27, W * .35, 0, 0, Math.PI * 2); fg.stroke();
      fg.setLineDash([]); fg.globalAlpha = 1;
    } else {
      const cyaw = Math.cos(face.yaw), syaw = Math.sin(face.yaw);
      const bob = still ? 0 : Math.sin(time * 1.3) * 2;
      const blink = face.running && face.step === 3 ? Math.pow(Math.max(0, Math.sin(time * 5.4)), 10) : 0;
      const scan = still ? 2 : Math.sin(time * 1.7) * 105;
      const P = pts.map((p) => {
        let y = p.y;
        if (p.g === "eyeL" || p.g === "eyeR") y = -24 + (p.y + 24) * (1 - .92 * blink);
        const x = p.x * cyaw + p.z * syaw, z = -p.x * syaw + p.z * cyaw, k = 1 / (1 - z / 520);
        return { sx: cx + x * k * sc, sy: cy + (y + bob) * k * sc, z, oy: y };
      });
      const dim = face.done && !face.running ? .45 : 1;
      fg.lineWidth = 1;
      for (const [i, j] of links) {
        const a = P[i], b = P[j];
        const near = Math.max(0, 1 - Math.abs((a.oy + b.oy) / 2 - scan) / 34);
        fg.strokeStyle = col.accent;
        fg.globalAlpha = (.2 + .6 * near) * dim * (face.running ? 1 : .8);
        fg.beginPath(); fg.moveTo(a.sx, a.sy); fg.lineTo(b.sx, b.sy); fg.stroke();
      }
      for (const p of P) {
        const near = Math.max(0, 1 - Math.abs(p.oy - scan) / 30);
        fg.fillStyle = col.accent;
        fg.globalAlpha = (.55 + .45 * near) * dim;
        fg.beginPath(); fg.arc(p.sx, p.sy, (1.5 + near * 1.6) * Math.max(.8, sc), 0, Math.PI * 2); fg.fill();
      }
      if (face.running && !still) {
        const y = cy + scan * sc;
        const g2 = fg.createLinearGradient(0, y - 22 * sc, 0, y + 4);
        g2.addColorStop(0, "transparent"); g2.addColorStop(1, col.accent);
        fg.globalAlpha = .22; fg.fillStyle = g2;
        fg.fillRect(cx - W * .32, y - 22 * sc, W * .64, 26 * sc);
      }
      fg.globalAlpha = 1;
    }
    fg.restore();

    if (face.done && !face.running) {
      fg.strokeStyle = col.accent; fg.lineWidth = Math.max(5, W * .022); fg.lineCap = "round"; fg.lineJoin = "round";
      fg.beginPath(); fg.moveTo(cx - W * .1, cy + W * .01); fg.lineTo(cx - W * .02, cy + W * .09); fg.lineTo(cx + W * .12, cy - W * .07); fg.stroke();
    }
  }

  /* ---------- voice drawing ---------- */
  function drawVoice(dt) {
    if (!vg || !vw) return;
    vg.clearRect(0, 0, vw, vh);
    const L = voice.levels, n = L.length, mid = vh / 2, bw = vw / n;
    for (let i = 0; i < n; i++) {
      const v = L[i];
      const idle = voice.running ? 0 : (IRAS.env.reduceMotion ? .02 : .03 + .02 * Math.sin(time * 1.4 + i * .35));
      const h = Math.max(3, (Math.max(v, idle) * (vh * .42)) * 2);
      vg.fillStyle = col.accent;
      vg.globalAlpha = .35 + .65 * (i / n);
      const x = i * bw + bw * .2, w = Math.max(2, bw * .6);
      vg.beginPath();
      vg.roundRect ? vg.roundRect(x, mid - h / 2, w, h, w / 2) : vg.rect(x, mid - h / 2, w, h);
      vg.fill();
    }
    vg.globalAlpha = 1;
  }

  /* ---------- loop ---------- */
  let vAcc = 0;
  function frame(ts) {
    raf = requestAnimationFrame(frame);
    const still = IRAS.env.reduceMotion;
    const minDt = still ? 120 : 0;
    const raw = ts - last;
    if (raw < minDt) return;
    last = ts;
    const dt = Math.min(.1, raw / 1000);
    if (!still) time += dt;
    vAcc += raw;
    if (vAcc >= 33) { vAcc = 0; voice.levels.push(S.level.mic); voice.levels.shift(); }
    drawFace(dt);
    drawVoice(dt);
  }
  function start() { if (!raf && IRAS.view() === "identity" && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); } }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  function sizeCanvases() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const fr = stage.getBoundingClientRect();
    if (fr.width) { fw = Math.round(fr.width); fCanvas.width = fCanvas.height = fw * dpr; fg = fCanvas.getContext("2d"); fg.setTransform(dpr, 0, 0, dpr, 0, 0); }
    const vr = vCanvas.parentElement.getBoundingClientRect();
    if (vr.width) { vw = Math.round(vr.width); vh = Math.round(vr.height); vCanvas.width = vw * dpr; vCanvas.height = vh * dpr; vg = vCanvas.getContext("2d"); vg.setTransform(dpr, 0, 0, dpr, 0, 0); }
    readColors();
    drawFace(0); drawVoice(0);
  }

  /* ---------- UI bits ---------- */
  const badge = (el, done) => { el.className = "badge" + (done ? " accent" : ""); el.innerHTML = done ? `${icon("check", "i-sm")}Ready (preview)` : "Not set up"; };
  const listHTML = (items, step, doneAll) => items.map((t, i) => {
    const s = doneAll || i < step ? "done" : i === step ? "now" : "todo";
    return `<li data-s="${s}">${icon(s === "done" ? "check" : s === "now" ? "loader-circle" : "circle-dot", "i-sm")}<span>${esc(t)}</span></li>`;
  }).join("");
  function renderFace() {
    $("#faceSteps").innerHTML = listHTML(STEPS.map((s) => s.label), face.step, face.done && !face.running);
    badge($("#faceBadge"), face.done);
    $("#faceStart").innerHTML = `${icon(face.running ? "square" : "play", "i-sm")}<span>${face.running ? "Stop" : face.done ? "Do it again" : "Start Face ID"}</span>`;
  }
  function renderVoice() {
    $("#phraseList").innerHTML = PHRASES.map((t, i) => {
      const s = voice.done && !voice.running || i < voice.step ? "done" : i === voice.step ? "now" : "todo";
      return `<li data-s="${s}">${icon(s === "done" ? "check" : s === "now" ? "loader-circle" : "circle-dot", "i-sm")}<span>“${esc(t)}”</span></li>`;
    }).join("");
    badge($("#voiceBadge"), voice.done);
    const q = Math.round(voice.quality);
    $("#voiceBar").style.setProperty("--p", String(q / 100));
    $("#voiceBar").setAttribute("aria-valuenow", String(q));
    $("#voicePct").textContent = q + "%";
    $("#voiceStart").innerHTML = `${icon(voice.running ? "square" : "play", "i-sm")}<span>${voice.running ? "Stop" : voice.done ? "Do it again" : "Start Voice ID"}</span>`;
  }

  /* ---------- flows ---------- */
  async function runFace() {
    if (face.running) { faceCtl && faceCtl.abort(); return; }
    faceCtl = new AbortController();
    const signal = faceCtl.signal;
    face.running = true; face.done = false; face.progress = 0; face.step = 0;
    try {
      for (let i = 0; i < STEPS.length; i++) {
        face.step = i; face.stepAt = performance.now(); face.target = STEPS[i].yaw;
        $("#facePrompt").textContent = STEPS[i].prompt;
        renderFace();
        await sleep(STEPS[i].ms, signal);
      }
      face.done = true; ident.face = true; store.set(KEY, ident);
      $("#facePrompt").textContent = "Face ID is ready. In the full app IRAS now checks it is you before big actions.";
      toast("Face ID is ready (preview).", { icon: "scan-face" });
    } catch (e) {
      if (!(e && e.name === "AbortError")) console.error(e);
      $("#facePrompt").textContent = "Stopped. Press start when you are ready.";
    } finally {
      face.running = false; face.step = -1; face.target = 0; faceCtl = null;
      renderFace();
    }
  }

  async function runVoice() {
    if (voice.running) { voiceCtl && voiceCtl.abort(); return; }
    voiceCtl = new AbortController();
    const signal = voiceCtl.signal;
    voice.running = true; voice.done = false; voice.quality = 0;
    const real = $("#voiceMicToggle").checked;
    try {
      if (real && !IRAS.audio.on) {
        const ok = await IRAS.audio.start();
        if (!ok) { toast("The microphone is blocked, so the demo uses a practice voice.", { icon: "mic-off", timeout: 6000 }); $("#voiceMicToggle").checked = false; }
      }
      const live = $("#voiceMicToggle").checked && IRAS.audio.on;
      const gains = [38, 71, 96];
      for (let i = 0; i < PHRASES.length; i++) {
        voice.step = i;
        $("#voicePrompt").textContent = `Say it out loud: “${PHRASES[i]}”`;
        renderVoice();
        if (live) {
          let heard = 0, t = 0;
          while (heard < 1100) {
            await sleep(100, signal); t += 100;
            if (S.level.mic > .14) heard += 100;
            if (t > 14000) { $("#voicePrompt").textContent = "I could not hear you. Move closer and try this line again."; t = 0; }
          }
        } else {
          await IRAS.audio.envelope("mic", 2400, signal);
          await sleep(250, signal);
        }
        voice.quality = gains[i];
        renderVoice();
      }
      voice.done = true; ident.voice = true; store.set(KEY, ident);
      $("#voicePrompt").textContent = "Voice ID is ready. You can now approve big actions by voice.";
      toast("Voice ID is ready (preview).", { icon: "audio-lines" });
    } catch (e) {
      if (!(e && e.name === "AbortError")) console.error(e);
      $("#voicePrompt").textContent = "Stopped. Press start when you are ready.";
      if (!voice.done) voice.quality = 0;
    } finally {
      voice.running = false; voice.step = -1; voiceCtl = null;
      IRAS.audio.setLevel("mic", IRAS.audio.on ? S.level.mic : 0);
      renderVoice();
    }
  }

  async function camOn() {
    try {
      face.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 640 } }, audio: false });
      video.srcObject = face.stream;
      await video.play();
      video.hidden = false; face.cam = true; S.cam = "on";
      bus.emit("cam", { state: "on" });
      $("#facePrompt").textContent = "Camera on. The ring fills as you follow the steps.";
    } catch (e) {
      $("#faceCamToggle").checked = false;
      toast("The camera is blocked or missing, so the demo keeps the animated preview.", { icon: "camera-off", timeout: 6000 });
    }
  }
  function camOff() {
    if (face.stream) face.stream.getTracks().forEach((t) => t.stop());
    face.stream = null; video.srcObject = null; video.hidden = true; face.cam = false; S.cam = "off";
    bus.emit("cam", { state: "off" });
  }

  IRAS.initIdentity = function () {
    readColors();
    renderFace(); renderVoice();
    $("#faceStart").addEventListener("click", runFace);
    $("#voiceStart").addEventListener("click", runVoice);
    $("#faceCamToggle").addEventListener("change", (e) => { if (e.target.checked) camOn(); else camOff(); });
    $("#voiceMicToggle").checked = false;
    new ResizeObserver(() => { if (IRAS.view() === "identity") sizeCanvases(); }).observe(stage);
    bus.on("view", (e) => {
      if (e.view === "identity") { sizeCanvases(); start(); }
      else {
        stop();
        faceCtl && faceCtl.abort(); voiceCtl && voiceCtl.abort();
        if (face.cam) { camOff(); $("#faceCamToggle").checked = false; }
      }
    });
    bus.on("visibility", (e) => { if (e.hidden) stop(); else start(); });
    bus.on("appearance", () => { readColors(); drawFace(0); drawVoice(0); });
  };
})();
