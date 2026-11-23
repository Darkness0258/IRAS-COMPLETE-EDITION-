/* ==========================================================================
   Voice check while you talk: she works out whose voice it is, by herself.

   While she listens in voice chat, this page records the same few seconds
   (the browser's speech recognition does not hand out the sound) and sends
   them to your server, the same way the "Who is speaking?" button does:

     POST /v1/identity/voice/verify    { audio }   ->   { verdict, match, closest, ... }

   What the answer does:

     match     a clear match: "Who is here" becomes that person (voice).
     other     "nobody I know". Only when she has heard it twice in a row, and only
               when the person set now has a taught voice, she stops using that
               person's name ("Who is here?" again). One "other" changes nothing:
               when someone else talks at the same time, your own voice can look strange.
     anything else (not sure, too little speech)   nothing changes.
     Guest mode is never changed by a voice. It stays until you clear it.

   She never makes you wait long. If the server has not answered after about 2 seconds
   she answers you anyway, and the answer is used for your next turn. The sound lives in
   memory for a moment, goes to your server once, and is dropped. Nothing is saved here.
   It is a hint for how she talks, like the rest of "Who is here". It is not a login,
   and it never approves anything.

   It is off in the Android app (the app listens with the phone's own speech recognizer,
   which does not share the microphone), when nobody has a taught voice, and when you
   switch it off in Settings. On a phone browser it starts off, because on some phones
   listening and recording together do not work. If the microphone cannot be shared, or gives
   no sound twice in a row, it turns itself off for this window and says so.

     IRAS.autoid.begin()           she starts to listen (call it inside your tap)
     IRAS.autoid.end(heard)        she stopped listening. Returns a promise that settles in
                                   about 2 seconds at most, or null when there is nothing to wait for
     IRAS.autoid.listenFailed(e)   the speech recognition failed (e is its error name)
     IRAS.autoid.enabled()         is it switched on (Settings)
     IRAS.autoid.available()       { ok, why }
     IRAS.autoid.hint()            one sentence for Settings and Check everything
     IRAS.autoid.state()           what it is doing now, for tests
   ========================================================================== */
"use strict";

(function () {
  const MAX_S = 12;          // keep at most this many seconds of the talk (the server uses up to 10 seconds of speech)
  const EARLY_S = 3.5;       // ask once as soon as this much was heard, so the answer is often ready when you stop
  const VOICED_S = 2.0;      // ...and only when this much of it was louder than a whisper
  const MIN_S = 1.8;         // a shorter clip is not worth sending
  const WAIT_MS = 1800;      // the longest she makes you wait for the answer
  const QUIET = 0.004;       // under this the microphone heard nothing (the same line as the Voice ID screen)
  const LOUD = 0.012;        // a block louder than this counts as voice
  const STRIKES = 2;         // "nobody I know" this many times in a row before she stops using a name
  const STRIKE_MS = 10 * 60 * 1000;   // ...and an old "nobody I know" is forgotten after this
  const PAUSE_MS = 2 * 60 * 1000;     // after a server problem she does not try again for this long

  const AC = window.AudioContext || window.webkitAudioContext;
  const ua = () => String(navigator.userAgent || "");
  const onPhone = () => /Android|iPhone|iPad|iPod|Mobile/i.test(ua()) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua()));

  let cap = null;            // the recording that runs while she listens
  let job = null;            // the question that is out to the server now: { my, done, t0 }
  let off = "";              // why it turned itself off for this window (empty: it did not)
  let pausedUntil = 0, pausedWhy = "";
  let strikes = 0, strikeFor = "", strikeAt = 0;
  let rev = 0, mineDepth = 0;   // rev counts changes of "Who is here" that were not hers
  let quietTurns = 0, busyTurns = 0;
  let last = null;           // what the last check found

  /* ---------- is it on, and can it work here ---------- */
  function enabled() {
    const v = settings.autoWho;
    return v === null || v === undefined ? !onPhone() : !!v;
  }

  function available() {
    if (window.IRASNative) return { ok: false, why: "The Android app listens with the phone's own speech recognizer, which does not share the microphone." };
    if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return { ok: false, why: "This browser cannot record sound for the check." };
    if (settings.source !== "live") return { ok: false, why: "It needs your own server, not the demo." };
    if (off) return { ok: false, why: off };
    if (Date.now() < pausedUntil) return { ok: false, why: pausedWhy };
    return { ok: true, why: "" };
  }

  function hint() {
    if (!enabled()) return "Off. She learns who is speaking only when you press “Who is speaking?” or pick a person.";
    const a = available();
    if (!a.ok) return "On, but it cannot work now. " + a.why;
    if (!IRAS.people || !IRAS.people.withVoice()) return "On. Teach her a voice on the Identity screen first, then she can tell who is speaking.";
    return "On. While you talk to her, she checks whose voice it is and sets Who is here by herself.";
  }

  /* ---------- sound helpers (the same as the Voice ID screen) ---------- */
  function joinChunks(chunks) {
    let n = 0;
    for (const c of chunks) n += c.length;
    const out = new Float32Array(n);
    let at = 0;
    for (const c of chunks) { out.set(c, at); at += c.length; }
    return out;
  }

  function wavBlob(samples, rate) {   // 16-bit mono WAV, which is all the server needs to read
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

  async function to16k(samples, rate) {   // the model listens at 16 000 samples a second; this also makes the upload smaller
    if (rate === 16000) return samples;
    try {
      const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const job2 = new Offline(1, Math.max(1, Math.ceil((samples.length * 16000) / rate)), 16000);
      const buffer = job2.createBuffer(1, samples.length, rate);
      buffer.getChannelData(0).set(samples);
      const source = job2.createBufferSource();
      source.buffer = buffer; source.connect(job2.destination); source.start();
      return (await job2.startRendering()).getChannelData(0);
    } catch (e) { return null; }
  }

  /* ---------- the extra recording ---------- */
  function release(my) {   // microphone off, header chip back. The sound already heard is kept.
    if (!my || !my.open) return;
    my.open = false;
    clearTimeout(my.timer);
    try { if (my.node) my.node.onaudioprocess = null; } catch (e) { /* already gone */ }
    try { if (my.src) my.src.disconnect(); if (my.node) my.node.disconnect(); if (my.mute) my.mute.disconnect(); } catch (e) { /* already apart */ }
    try { if (my.stream) my.stream.getTracks().forEach((t) => t.stop()); } catch (e) { /* already stopped */ }
    try { my.ctx.close().catch(() => {}); } catch (e) { /* already closed */ }
    if (my.micWas !== null) {
      if (my.micWas !== "on" && S.mic === "on") { S.mic = my.micWas; bus.emit("mic", { state: my.micWas }); }   // if it was on already, leave it
      my.micWas = null;
    }
  }

  function drop() {   // forget a talk: microphone off, sound gone
    if (!cap) return;
    release(cap);
    cap.chunks = [];
    cap = null;
  }

  function heard(my, x) {
    if (!my.open) return;
    let sum = 0;
    for (let i = 0; i < x.length; i++) sum += x[i] * x[i];
    const rms = Math.sqrt(sum / x.length);
    if (rms > my.peak) my.peak = rms;
    if (my.n < MAX_S * my.rate) {
      my.chunks.push(new Float32Array(x));   // a copy: the browser reuses its buffer
      my.n += x.length;
      if (rms > LOUD) my.voiced += x.length;
    }
    if (!my.early && my.n >= EARLY_S * my.rate && my.voiced >= VOICED_S * my.rate) { my.early = true; ask(my); }
  }

  function opened(my, stream) {
    if (cap !== my || !my.open) { stream.getTracks().forEach((t) => t.stop()); try { my.ctx.close().catch(() => {}); } catch (e) { /* closed */ } return; }   // she stopped listening before the microphone opened
    my.stream = stream;
    busyTurns = 0;
    try {
      if (my.ctx.state === "suspended") my.ctx.resume();
      my.src = my.ctx.createMediaStreamSource(stream);
      my.node = my.ctx.createScriptProcessor(4096, 1, 1);
      my.mute = my.ctx.createGain();
      my.mute.gain.value = 0;   // the processor only runs while joined to the output, and she must not play you back
      my.node.onaudioprocess = (e) => heard(my, e.inputBuffer.getChannelData(0));
      my.src.connect(my.node); my.node.connect(my.mute); my.mute.connect(my.ctx.destination);
    } catch (e) { release(my); return; }
    my.micWas = S.mic;   // the header chip tells the truth while she records
    if (S.mic !== "on") { S.mic = "on"; bus.emit("mic", { state: "on" }); }
  }

  function refused(my, err) {
    if (cap === my) release(my);
    const name = String((err && err.name) || "");
    if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") {   // speech recognition holds the microphone alone
      busyTurns++;
      if (busyTurns >= 2) turnOff("On this device the microphone cannot be shared with speech recognition.", true);
    }
    // a blocked microphone is already told to you by the speech recognition itself
  }

  function turnOff(why, tell) {
    off = why;
    drop();
    if (tell) toast("I turned the voice check off for now. " + why + " Voice chat still works. Settings has the switch.", { icon: "audio-lines", timeout: 9000 });
  }

  function begin() {
    drop();   // a talk from an earlier turn is gone
    if (!enabled() || !available().ok || !(IRAS.live && IRAS.live.ok)) return;
    if (job) return;   // the last question is still out: do not pile up on a small server
    if (!IRAS.people) return;
    const here = IRAS.who && IRAS.who.current();
    if (here && here.kind === "guest") return;   // a voice never changes guest mode, so there is nothing to find out
    if (!IRAS.people.withVoice()) { IRAS.people.load(); return; }   // no taught voice (or the list is not here yet): nothing to compare with
    let ctx;
    try { ctx = new AC(); } catch (e) { return; }   // made inside your tap, so the browser lets it run
    const my = (cap = { ctx, rate: ctx.sampleRate, stream: null, src: null, node: null, mute: null, chunks: [], n: 0, peak: 0, voiced: 0, open: true, early: false, asked: 0, unheard: false, saw: false, micWas: null, rev: 0, timer: 0 });
    my.timer = setTimeout(() => release(my), (MAX_S + 5) * 1000);   // never leave the microphone on
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true } })
      .then((stream) => opened(my, stream), (err) => refused(my, err));
  }

  /* ---------- asking the server ---------- */
  function ask(my) {
    if (job || my.asked >= 2) return null;
    const samples = joinChunks(my.chunks);   // copied now; what is sent never changes later
    if (my.peak < QUIET || samples.length < MIN_S * my.rate) return null;
    my.asked++;
    my.rev = rev;
    const t0 = performance.now();
    const done = (async () => {
      let answer = null;
      try {
        const small = await to16k(samples, my.rate);
        const audio = await dataUrl(wavBlob(small || samples, small ? 16000 : my.rate));
        answer = await IRAS.api("/v1/identity/voice/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio }) });
      } catch (err) { problem(err); return; }
      outcome(answer, my, Math.round(performance.now() - t0));
    })();
    const mine = (job = { my, done, t0 });
    done.then(() => { if (job === mine) job = null; });
    return mine;
  }

  function verdictOf(r) {   // an older server does not say it: work it out from the old answer
    const v = String((r && r.verdict) || "");
    if (v) return v;
    return r && r.match ? "match" : r && r.heard ? "unsure" : "unheard";
  }

  const pct = (x) => Math.round(Math.max(0, Math.min(1, Number(x) || 0)) * 100) + "%";

  function record(r, v, ms) {   // one line in Activity, so you can see what she heard
    const c = r && r.closest, m = r && r.match;
    const says = {
      match: m ? "It sounded like " + m.name + " (" + pct(m.score) + " sure)." : "It matched someone she knows.",
      other: "It sounded like nobody she knows" + (c ? " (best match " + pct(c.score) + ")." : "."),
      unsure: "Not sure whose voice it was" + (c ? " (closest: " + c.name + ", " + pct(c.score) + ")." : "."),
      unheard: "Too little speech to tell" + (r && r.speech !== undefined ? " (" + (Number(r.speech) || 0).toFixed(1) + " seconds of speech)." : "."),
      nobody: "She does not know any voice yet.",
    };
    audit.add({ kind: "tool", status: "done", title: "Checked who is speaking", detail: says[v] || "She could not tell.", tags: ["voice id"], ms, payload: { tool: "identity.voice.verify", args: { seconds: r && r.seconds } } });
  }

  function outcome(r, my, ms) {
    const v = verdictOf(r);
    last = { at: Date.now(), verdict: v, name: r && r.match ? r.match.name : "", score: r && r.match ? r.match.score : r && r.closest ? r.closest.score : 0 };
    record(r, v, ms);
    if (v === "unheard") my.unheard = true;
    if (my.rev !== rev) return;   // you changed who is here while she was checking: what you did is newer
    if (v === "match" && r.match && r.match.person_id) adopt(r.match);
    else if (v === "other") strange();
  }

  function problem(err) {
    const say = String((err && err.message) || "It did not answer.");
    pausedUntil = Date.now() + PAUSE_MS;
    pausedWhy = "The last check failed (" + say.slice(0, 120) + "). She tries again in a couple of minutes.";
    audit.add({ kind: "tool", status: "failed", title: "Could not check who is speaking", detail: say.slice(0, 200), tags: ["voice id"], payload: { tool: "identity.voice.verify" } });
  }

  /* ---------- using the answer ---------- */
  function mine(fn) { mineDepth++; try { fn(); } finally { mineDepth--; } }   // her own changes to Who is here are not "yours"

  function adopt(m) {
    const who = IRAS.who, cur = who && who.current();
    if (!who || (cur && cur.kind === "guest")) return;   // a guest stays a guest: a voice never switches that off
    strikes = 0; strikeFor = "";
    const same = !!(cur && cur.kind === "person" && cur.person_id === m.person_id);
    mine(() => who.set({ person_id: m.person_id, name: m.name }, "voice", m.score));
    if (!same) toast(cur && cur.kind === "person" ? "I hear " + m.name + " now, not " + cur.name + "." : "I know your voice, " + m.name + ".", { icon: "audio-lines" });
  }

  function strange() {   // a voice that is nobody she knows
    const who = IRAS.who, cur = who && who.current();
    if (!cur || cur.kind !== "person") { strikes = 0; strikeFor = ""; return; }   // nobody to stop using; a guest stays a guest
    if (!IRAS.people.voices(cur.person_id)) return;   // she never learned this person's voice, so a strange voice says nothing about them
    if (strikeFor !== cur.person_id || Date.now() - strikeAt > STRIKE_MS) { strikes = 0; strikeFor = cur.person_id; }
    strikes++; strikeAt = Date.now();
    if (strikes < STRIKES) return;
    strikes = 0; strikeFor = "";
    mine(() => who.clear());
    toast("That did not sound like " + cur.name + ", twice in a row. I stopped using the name. Tap “Who is here?” to set it again.", { icon: "users", timeout: 9000 });
  }

  /* ---------- the end of a talk ---------- */
  function end(heardSomething) {
    const my = cap;
    if (!my) return null;
    cap = null;
    release(my);   // the microphone is let go at once, whatever happens next
    if (!heardSomething) { my.chunks = []; return null; }   // nothing was said: the sound is dropped
    if (my.peak < QUIET) {   // she was listening, but this page's recording got no sound at all
      my.chunks = [];
      if (my.stream) {   // the microphone did open (when it never opened, that is told by refused(), not here)
        quietTurns++;
        if (quietTurns >= 2) turnOff("The microphone gave no sound to the check while she was listening.", true);
      }
      return null;
    }
    quietTurns = 0;
    let wait = null;
    if (job && job.my === my) wait = job;                       // the early question is still out
    else if (my.asked === 0 || my.unheard) wait = ask(my);      // not asked yet, or the early clip had too little speech
    my.chunks = [];   // the sound now lives only in the question that was sent; nothing is kept here
    if (!wait) return null;
    const left = Math.max(250, WAIT_MS - (performance.now() - wait.t0));
    return new Promise((resolve) => {
      let over = false;
      const finish = () => { if (over) return; over = true; clearTimeout(t1); clearTimeout(t2); resolve(); };
      const t1 = setTimeout(finish, left);
      const t2 = setTimeout(() => { if (!over) bus.emit("caption", { text: "Checking who is speaking…" }); }, 350);
      wait.done.then(finish, finish);
    });
  }

  function listenFailed(code) {
    if (cap && cap.open && code === "audio-capture") turnOff("Listening stopped while the check was recording, so the two cannot run together here.", true);
  }

  /* ---------- keeping the microphone honest ---------- */
  bus.on("ui", (e) => {
    if (!cap) return;
    if (e.to === "listening") cap.saw = true;
    else if (cap.saw && cap.open) release(cap);   // she is no longer listening, so neither is the check
  });
  bus.on("cancel", () => { if (cap && cap.open) release(cap); });
  bus.on("visibility", (e) => { if (e.hidden && cap) release(cap); });
  bus.on("who", () => { if (!mineDepth) rev++; });
  window.addEventListener("pagehide", drop);

  IRAS.autoid = {
    begin, end, listenFailed, enabled, available, hint,
    state: () => ({ enabled: enabled(), available: available(), recording: !!(cap && cap.open), streaming: !!(cap && cap.stream), seconds: cap ? Math.round((cap.n / cap.rate) * 100) / 100 : 0, asking: !!job, strikes, off, last }),
  };

  IRAS.initAutoId = function () {   // the list of people (and who has a voice) is ready before the first talk
    const warm = () => { if (enabled() && IRAS.people && settings.source === "live") IRAS.people.load(); };
    bus.on("sync", (e) => { if (e.state === "synced") warm(); });
    bus.on("setting", (e) => { if (e.key === "autoWho") { off = ""; pausedUntil = 0; warm(); } });
  };
})();
