/* ==========================================================================
   Check everything: one button that tests what a test day needs.

   Each line is a real question to your server or your browser, and each answer says in plain
   words what is wrong and what to do. Nothing is changed. It makes one tiny speech request
   (it plays no sound) and never shows or copies your access token.

     GET  /health                 is the server awake
     GET  /ready                  is the database really connected (no token needed)
     GET  /v1/providers/status    does the server accept your token, and is an AI ready
     POST /v1/tts                 can she really speak (one short word, not played)
     GET  /v1/identity/status     Face ID and Voice ID
     GET  /v1/calendar/status     and /v1/calendar/events   your calendar link
     GET  /v1/devices             is your PC online     GET /v1/remote/policy   how far a session may go

   IRAS.check.run() / IRAS.check.report()
   ========================================================================== */
"use strict";

(function () {
  const server = () => String(settings.server || "").trim().replace(/\/+$/, "");
  const hostOf = (u) => { try { return new URL(u).host; } catch (e) { return u; } };
  const upText = (s) => { const m = Math.round(Number(s) / 60); return m < 1 ? "under a minute" : m < 90 ? m + " min" : Math.round(m / 60) + " hours"; };
  const timed = (promise, ms) => new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("It took too long to answer.")), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
  const ok = (say, fix) => ({ state: "ok", say, fix: fix || "" });
  const warn = (say, fix) => ({ state: "warn", say, fix: fix || "" });
  const fail = (say, fix) => ({ state: "fail", say, fix: fix || "" });
  const skip = (say) => ({ state: "skip", say, fix: "" });
  const ICON = { wait: "loader-circle", ok: "circle-check", warn: "triangle-alert", fail: "circle-alert", skip: "circle-dot" };
  const WORD = { wait: "Checking", ok: "OK", warn: "Look at this", fail: "Problem", skip: "Skipped" };
  const TAG = { ok: "OK", warn: "WARN", fail: "FAIL", skip: "SKIP" };

  /* what a failed call usually means, in words you can act on */
  function tokenFix(message) {
    if (/refused|invalid iras access/i.test(message)) return "Copy the value of IRAS_API_TOKEN from Render (Environment) into Access token above, then press Test connection.";
    if (/not configured/i.test(message)) return "Add IRAS_API_TOKEN in Render, under Environment, and let it redeploy.";
    return "Look at the Render logs for the error.";
  }

  /* ---------- the checks ---------- */
  const CHECKS = [
    { id: "server", name: "Server", run: async (ctx) => {
      const base = server();
      if (!base) { ctx.down = true; return fail("No server address is set.", "Type your server address in Connection above, for example https://iras-cloud.onrender.com."); }
      let r;
      try { r = await timed(fetch(base + "/health"), 70000); }
      catch (e) { ctx.down = true; return fail("Could not reach " + hostOf(base) + ".", "On Render, open the dashboard and check the service is running. A sleeping service takes about a minute to wake, so try again. Also check the address above."); }
      if (!r.ok) { ctx.down = true; return fail("The server answered " + r.status + ".", "Open the Render logs and look for the error."); }
      const j = await r.json().catch(() => ({}));
      return ok((j.service || "IRAS Cloud") + " " + (j.version || "") + " is running" + (j.uptime_seconds != null ? ", up " + upText(j.uptime_seconds) : "") + ".");
    } },

    { id: "token", name: "Access token", needsServer: true, run: async (ctx) => {
      try { await providers(ctx); return ok("The server accepted your token."); }
      catch (e) { ctx.tokenBad = true; return fail(e.message, tokenFix(e.message)); }
    } },

    { id: "ai", name: "AI", needsToken: true, run: async (ctx) => {
      const p = await providers(ctx);
      const rows = p.providers || [];
      const ready = rows.filter((x) => x.ready).map((x) => x.name);
      if (!p.configured_count && !rows.length) return fail("No AI provider has a key.", "Add an AI key in Render, under Environment (for example GEMINI_API_KEY), and redeploy.");
      if (p.available_count > 0) return ok(ready.join(", ") + " is ready" + (p.active_model ? " (" + p.active_model + ")" : "") + ".");
      return warn("A provider is set up but none has answered yet.", "Send one message in Chat. If it still fails, check the key in Render.");
    } },

    { id: "database", name: "Database", needsServer: true, run: async () => {
      const r = await timed(fetch(server() + "/ready"), 25000);
      if (!r.ok) return warn("The server did not give its database status (it answered " + r.status + ").", "Deploy the latest version, then check again.");
      const j = await r.json();
      const help = String(j.database_help || "");
      if (j.database === "sqlite-fallback") return fail("The server could not reach your database, so it is using temporary storage.", (help ? help + " " : "") + "Anything saved now is lost when Render restarts. Check DATABASE_URL in Render.");
      if (j.database === "postgres" && j.database_ok) return ok("Your database (Postgres, for example Supabase) is connected.");
      if (j.database === "postgres") return fail("The database is set up but not answering.", help || "Check DATABASE_URL in Render.");
      return warn("No database is set, so the server uses temporary local storage.", "On Render, memory, people and calendars are lost on every restart. Add your Supabase connection as DATABASE_URL.");
    } },

    { id: "voice", name: "Her voice", needsToken: true, run: async () => {
      const profile = settings.voiceProfile || "iras_human";
      const headers = { "Content-Type": "application/json", "X-Device-ID": "web" };
      const t = store.sget("iras-api-token", "");
      if (t) headers.Authorization = "Bearer " + t;
      const r = await timed(fetch(server() + "/v1/tts", { method: "POST", headers, body: JSON.stringify({ text: "Checking my voice.", mood: settings.voiceMood || "warm", voice_gender: "female", voice_profile: profile }) }), 45000);
      if (!r.ok) {
        let d = ""; try { d = (await r.json()).detail; } catch (e) { /* no body */ }
        return fail(typeof d === "string" && d ? d : "The server answered " + r.status + ".", "Look at the Render logs. Check GEMINI_API_KEY if you chose a Gemini voice.");
      }
      const used = r.headers.get("X-IRAS-Voice") || "", note = r.headers.get("X-IRAS-Voice-Note") || "";
      const size = (await r.blob()).size;
      if (size < 500) return fail("The server sent no sound.", "Look at the Render logs.");
      if (/^gemini_/.test(profile) && !/^gemini:/.test(used)) return warn("Gemini did not answer, so she used the older voice (" + (used || "unknown") + ").", (note ? "Reason: " + note + ". " : "") + "Check GEMINI_API_KEY in Render.");
      return ok((used || "A voice") + " answered (" + Math.max(1, Math.round(size / 1024)) + " KB). Press \"Test her voice\" above to listen.");
    } },

    { id: "face", name: "Face ID", needsToken: true, run: async (ctx) => {
      const s = await identity(ctx);
      if (!s.available) return fail("Not available. " + (s.reason || ""), "These need numpy, onnxruntime and OpenCV on the server. Look at the Render build log for the install step.");
      return s.models_ready ? ok("Ready. " + (s.people || 0) + " " + ((s.people || 0) === 1 ? "person is" : "people are") + " known.") : warn("Ready, but the face models are not downloaded yet.", "The first picture downloads about 15 MB. After each Render restart it downloads again.");
    } },

    { id: "voiceid", name: "Voice ID", needsToken: true, run: async (ctx) => {
      const s = await identity(ctx);
      if (!s.voice) return warn("The server does not know Voice ID yet.", "Deploy the latest update.");
      if (!s.voice.available) return fail("Not available. " + (s.voice.reason || ""), "It needs numpy and onnxruntime on the server. Look at the Render build log.");
      return s.voice.models_ready ? ok("Ready.") : warn("Ready, but the voice model is not downloaded yet.", "The first recording downloads about 26 MB. After each Render restart it downloads again.");
    } },

    { id: "calendar", name: "Calendar", needsToken: true, run: async () => {
      const s = await IRAS.api("/v1/calendar/status");
      if (!s.available) return fail("Not available. " + (s.reason || ""), "Look at the Render build log and the server logs.");
      const feeds = s.feeds || [];
      if (!feeds.length) return warn("No calendar is linked yet.", "Open Agents, then Calendar, and paste your private iCal link.");
      const bad = feeds.find((f) => f.last_error);
      const e = await IRAS.api("/v1/calendar/events?days=7");
      const problems = e.problems || [];
      if (problems.length) return warn("Could not read your calendar: " + String(problems[0].message || problems[0]).slice(0, 160), "Use the private iCal address from your calendar's settings, not the page link. Then add it again.");
      if (bad) return warn("The last sync of " + (bad.name || "a calendar") + " failed: " + String(bad.last_error).slice(0, 140), "Press sync in Agents, Calendar. If it keeps failing, add the link again.");
      return ok("Read " + (e.events || []).length + " " + ((e.events || []).length === 1 ? "event" : "events") + " in the next 7 days from " + feeds.length + " " + (feeds.length === 1 ? "calendar" : "calendars") + ".");
    } },

    { id: "pc", name: "Your PC", needsToken: true, run: async () => {
      const r = await IRAS.api("/v1/devices");
      const online = ((r && r.devices) || []).filter((d) => d.online);
      let limit = "";
      try { const p = await IRAS.api("/v1/remote/policy"); limit = " Your server allows sessions up to " + ({ READ: "Look only", SAFE_ACTION: "Control", SYSTEM_ACTION: "Control", CRITICAL: "Full" }[p.cap] || p.cap) + "."; } catch (e) { /* an older server: fine */ }
      if (!online.length) return warn("No paired PC is online." + limit, "Turn the PC on and open the IRAS Windows app. Then check again.");
      return ok(online.map((d) => d.display_name).join(", ") + (online.length === 1 ? " is" : " are") + " online." + limit);
    } },

    { id: "mic", name: "Microphone", browser: true, run: () => media("microphone", "the microphone") },
    { id: "cam", name: "Camera", browser: true, run: () => media("camera", "the camera") },
    { id: "listen", name: "Listening", browser: true, run: async () => {
      if (window.SpeechRecognition || window.webkitSpeechRecognition || window.IRASNative) return ok("This browser or app can turn your speech into text.");
      return warn("This browser cannot turn speech into text.", "Use Chrome or Edge, or the Android app. You can still type.");
    } },
  ];

  /* one call, shared by the lines that need it */
  const providers = (ctx) => ctx.providers || (ctx.providers = timed(IRAS.api("/v1/providers/status"), 25000));
  const identity = (ctx) => ctx.identity || (ctx.identity = timed(IRAS.api("/v1/identity/status"), 25000));

  async function media(name, words) {
    if (!window.isSecureContext) return fail("This page is not on https, so the browser blocks " + words + ".", "Open the site with https:// (a Render address already is).");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return fail("This browser cannot use " + words + ".", "Use a current Chrome, Edge or Safari.");
    let state = "unknown";
    try { state = (await navigator.permissions.query({ name })).state; } catch (e) { /* some browsers do not say */ }
    if (state === "denied") return fail("The browser has blocked " + words + " for this site.", "Click the lock icon next to the address, allow it, and reload the page.");
    return ok(state === "granted" ? "It is allowed." : "The browser will ask you the first time you use it.");
  }

  /* ---------- drawing ---------- */
  let results = {}, running = false;

  function row(c, res) {
    const r = res || { state: "wait", say: "Checking…", fix: "" };
    return `<li class="check-row" data-state="${r.state}" data-check="${c.id}">` +
      `<span class="check-ico" aria-hidden="true">${icon(ICON[r.state], "i-sm")}</span>` +
      `<div class="check-body"><strong>${esc(c.name)}</strong><span class="check-state"> ${WORD[r.state]}.</span> <span class="check-say">${esc(r.say)}</span>` +
      (r.fix ? `<span class="check-fix">What to do: ${esc(r.fix)}</span>` : "") + `</div></li>`;
  }

  function draw() {
    $("#checkList").innerHTML = CHECKS.map((c) => row(c, results[c.id])).join("");
  }

  function summary() {
    const all = CHECKS.map((c) => results[c.id]).filter(Boolean);
    const n = (s) => all.filter((r) => r.state === s).length;
    const problems = n("fail"), warns = n("warn");
    const first = CHECKS.find((c) => results[c.id] && results[c.id].state === "fail") || CHECKS.find((c) => results[c.id] && results[c.id].state === "warn");
    const el = $("#checkSummary");
    el.dataset.state = problems ? "fail" : warns ? "warn" : "ok";
    el.textContent = problems || warns
      ? [problems ? problems + (problems === 1 ? " problem" : " problems") : "", warns ? warns + (warns === 1 ? " thing to look at" : " things to look at") : ""].filter(Boolean).join(" and ") + ". Start with: " + first.name + "."
      : "Everything checked is working.";
  }

  function report() {
    const lines = ["IRAS check, " + new Date().toLocaleString(), "Server: " + (hostOf(server()) || "(none)"), "Browser: " + String(navigator.userAgent || "").slice(0, 120), ""];
    CHECKS.forEach((c) => {
      const r = results[c.id];
      if (!r) return;
      lines.push("[" + (TAG[r.state] || "?") + "] " + c.name + ": " + r.say + (r.fix ? "  -> " + r.fix : ""));
    });
    const all = CHECKS.map((c) => results[c.id]).filter(Boolean);
    lines.push("", "Summary: " + all.filter((r) => r.state === "ok").length + " ok, " + all.filter((r) => r.state === "warn").length + " to look at, " + all.filter((r) => r.state === "fail").length + " problems.");
    return lines.join("\n");
  }

  /* ---------- running ---------- */
  async function settle(c, ctx) {
    let res;
    if (c.needsServer && ctx.down) res = skip("Skipped: the server could not be reached.");
    else if (c.needsToken && (ctx.down || ctx.tokenBad)) res = skip(ctx.down ? "Skipped: the server could not be reached." : "Skipped: fix the access token first.");
    else {
      try { res = await c.run(ctx); }
      catch (e) { res = fail(String((e && e.message) || "It did not answer."), /token|refused/i.test(String(e && e.message)) ? tokenFix(String(e.message)) : "Look at the Render logs, then check again."); }
    }
    results[c.id] = res;
    const li = $(`#checkList [data-check="${c.id}"]`);
    if (li) li.outerHTML = row(c, res);
    const done = Object.keys(results).length;
    if (done < CHECKS.length) $("#checkSummary").textContent = "Checking… " + done + " of " + CHECKS.length + " done.";
  }

  async function run() {
    if (running) return;
    running = true; results = {};
    $("#checkRun").disabled = true;
    $("#checkRun").querySelector("span").textContent = "Checking…";
    $("#checkCopy").hidden = true;
    $("#checkSummary").dataset.state = "";
    $("#checkSummary").textContent = "Checking… 0 of " + CHECKS.length + " done.";
    draw();
    const ctx = { down: false, tokenBad: false };
    try {
      await settle(CHECKS[0], ctx);            // the server first: it may be waking up
      await settle(CHECKS[1], ctx);            // then the token
      await Promise.all(CHECKS.slice(2).map((c) => settle(c, ctx)));
      summary();
      $("#checkCopy").hidden = false;
      announce($("#checkSummary").textContent);
    } finally {
      running = false;
      $("#checkRun").disabled = false;
      $("#checkRun").querySelector("span").textContent = "Run checks again";
    }
  }

  IRAS.check = { run, report };

  IRAS.initCheck = function () {
    $("#checkRun").addEventListener("click", run);
    $("#checkCopy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(report()); toast("Copied. Paste it to me.", { icon: "check" }); }
      catch (e) { toast("Could not copy. Select the lines and copy them.", { icon: "triangle-alert", timeout: 6000 }); }
    });
  };
})();
