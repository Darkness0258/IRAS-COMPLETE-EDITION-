/* ==========================================================================
   Identity: real Face ID.

     GET    /v1/identity/status          is Face ID ready on the server
     GET    /v1/identity/people          who she knows
     POST   /v1/identity/face/enroll     { name, image }   one picture of one person
     POST   /v1/identity/face/verify     { image, frames } who is this
     DELETE /v1/identity/people/{id}     forget a person

   The camera is only on while you are on this screen. Pictures go to your
   server for one check and are thrown away. Only numbers are kept.
   ========================================================================== */
"use strict";

(function () {
  let stream = null, busy = false;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const say = (t) => { $("#facePrompt").textContent = t; };
  const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const STEPS = ["Look straight at the camera.", "Turn a little to the left.", "Turn a little to the right.", "Look straight again.", "Tilt your head a little."];

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

  async function refresh() {
    try {
      const [s, p] = await Promise.all([IRAS.api("/v1/identity/status"), IRAS.api("/v1/identity/people")]);
      const people = p.people || [];
      const badge = $("#faceBadge");
      badge.className = "badge" + (people.length ? " accent" : "");
      badge.textContent = people.length ? people.length + (people.length === 1 ? " person" : " people") : "Not set up";
      $("#faceHint").textContent = !s.available ? s.reason : s.models_ready ? "" : "The first picture downloads the face models (15 MB). It can take a minute.";
      $("#faceList").innerHTML = people.map((x) =>
        `<li style="display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid rgba(127,127,127,.25)"><span class="grow"><strong>${esc(x.name)}</strong> <span class="muted">${x.faces} picture${x.faces === 1 ? "" : "s"}</span></span>` +
        `<button type="button" class="btn-icon sm" data-forget="${esc(x.person_id)}" aria-label="Forget ${esc(x.name)}" title="Forget">${icon("trash-2", "i-sm")}</button></li>`).join("");
    } catch (e) {
      $("#faceHint").textContent = e.message || "Cannot reach your server.";
    }
  }

  async function enroll() {
    const name = $("#faceName").value.trim();
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

  IRAS.initIdentity = function () {
    $("#faceCam").addEventListener("click", () => { if (stream) stopCam(); else startCam(); });
    $("#faceEnroll").addEventListener("click", enroll);
    $("#faceCheck").addEventListener("click", check);
    $("#faceList").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-forget]");
      if (!b || !window.confirm("Forget this person? Every faceprint of them is deleted.")) return;
      try { await IRAS.api("/v1/identity/people/" + encodeURIComponent(b.dataset.forget), { method: "DELETE" }); toast("Forgotten.", { icon: "trash-2" }); }
      catch (x) { toast("Could not forget them. " + (x.message || ""), { icon: "cloud-off", timeout: 7000 }); }
      refresh();
    });
    bus.on("view", (e) => { if (e.view === "identity") refresh(); else if (stream) stopCam(); });
    bus.on("visibility", (e) => { if (e.hidden && stream) stopCam(); });
  };
})();
