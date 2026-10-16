/* ==========================================================================
   Demo director.

   Every scenario below only emits events on the bus, exactly like a live
   backend would. The UI cannot tell the difference. To go live, replace this
   file with a source that calls IRAS.ingest(event). See EVENTS.md.
   ========================================================================== */
"use strict";

(function () {
  const sim = { running: false, utter: 0 };
  IRAS.sim = sim;
  let ctl = null;

  const aborted = (signal) => signal && signal.aborted;
  const check = (signal) => { if (aborted(signal)) throw new DOMException("Aborted", "AbortError"); };

  sim.cancel = function () {
    if (ctl) { ctl.abort(); ctl = null; }
    sim.running = false;
    IRAS.audio.setLevel("tts", 0);
    if (!IRAS.audio.on) IRAS.audio.setLevel("mic", 0);
  };

  async function run(fn) {
    if (ctl) ctl.abort();
    ctl = new AbortController();
    const signal = ctl.signal;
    sim.running = true;
    const c = { signal, wait: (ms) => sleep(ms, signal) };
    try { await fn(c); }
    catch (err) {
      if (!(err && err.name === "AbortError")) {
        console.error(err);
        bus.emit("error", { message: String(err && err.message || err) });
        toast("Something went wrong in the demo. Try again.", { icon: "info" });
      }
    } finally {
      if (ctl && ctl.signal === signal) { ctl = null; sim.running = false; }
    }
  }

  /* ---------- building blocks ---------- */
  async function stream(text, c, speed = 1) {
    const parts = text.match(/\S+\s*|\s+/g) || [];
    for (const p of parts) { bus.emit("token", { text: p }); await c.wait(rand(22, 52) / speed); }
  }
  async function speak(text, c) {
    bus.emit("tts_start", { text });
    await IRAS.audio.envelope("tts", clamp(text.length * 52, 1500, 6500), c.signal);
    check(c.signal);
    bus.emit("tts_end", {});
  }
  function waitApproval(id, c) {
    return new Promise((resolve) => {
      const off = bus.on("approval_result", (e) => { if (e.id === id) { off(); resolve(e.decision); } });
      c.signal.addEventListener("abort", () => { off(); resolve("cancel"); }, { once: true });
    });
  }
  async function tool(c, spec, ms, end = {}) {
    const id = uid("t");
    bus.emit("tool_start", Object.assign({ id, authority: "none" }, spec));
    await c.wait(ms);
    bus.emit("tool_end", Object.assign({ id, ok: true, ms }, end));
    return id;
  }
  /* the reply: streamed into chat, spoken if the request was spoken */
  async function reply(text, c, via, spoken) {
    const t0 = performance.now();
    bus.emit("state", { state: "thinking" });
    await c.wait(260);
    await stream(text, c);
    if (via === "voice" && IRAS.settings.speakReplies) await speak(spoken || text.replace(/[*_`#>-]/g, "").replace(/\s+/g, " ").slice(0, 160), c);
    bus.emit("done", { timing_ms: Math.round(performance.now() - t0) });
    afterSync();
  }
  function afterSync() {
    bus.emit("sync", { state: "syncing" });
    setTimeout(() => bus.emit("sync", { state: "synced" }), 1400);
  }
  const isUr = (t) => /\b(chala|bata|kholo|karo|mera|meri|aaj|kya|kuch|hai|nahi|pe)\b/i.test(t);

  /* ---------- scenarios ---------- */
  const scenarios = {
    async spotify(c, text, via) {
      const ur = isUr(text);
      await c.wait(750);
      bus.emit("tool_start", {
        id: "t_spotify", tool: "spotify.play", title: "Opening Spotify", detail: "Looking for calm music", authority: "none",
        screen: { layout: "music", app: "Spotify", steps: [
          { label: "Opening Spotify", target: "search" },
          { label: "Typing “calm” in the search box", target: "search" },
          { label: "Choosing the first playlist", target: "row1" },
          { label: "Pressing play", target: "play" },
          { label: "Checking that music is playing", target: "play" },
        ] },
      });
      bus.emit("state", { state: "acting" });
      for (let i = 0; i < 5; i++) { bus.emit("peek_step", { i }); await c.wait(i === 0 ? 900 : 1050); }
      bus.emit("tool_end", { id: "t_spotify", ok: true, ms: 5100, title: "Played “Calm Piano” on Spotify", detail: "Checked afterwards: music is playing", result: { playing: true, playlist: "Calm Piano" } });
      await reply(ur ? "Theek hai, Spotify pe **Calm Piano** laga di hai." : "Playing **Calm Piano** on Spotify. I checked that the music started.", c, via, ur ? "Theek hai, Spotify pe Calm Piano laga di hai." : "Playing Calm Piano on Spotify.");
    },

    async emails(c, text, via) {
      await c.wait(600);
      await tool(c, { tool: "mail.read", title: "Reading your unread emails", detail: "Mailbox: inbox, unread only" }, 1200, { title: "Read 3 unread emails", detail: "Newest: weekly team update", result: { unread: 3 } });
      await reply(
        "You have **3 unread emails**:\n\n1. **Weekly team update** from Sarah. The Q3 roadmap changed and your review is due Friday.\n2. **Invoice #2041** from your hosting provider. Payment is due in 5 days.\n3. **Newsletter**. Nothing needs action.\n\nWant me to draft a reply to Sarah?",
        c, via, "You have three unread emails. The most important one is Sarah's team update. Your review is due Friday."
      );
    },

    async calendar(c, text, via) {
      const ur = isUr(text);
      await c.wait(600);
      await tool(c, { tool: "calendar.read", title: "Checking your calendar", detail: "Today, all calendars" }, 1000, { title: "Read today’s calendar", detail: "3 events" });
      await reply(
        ur
          ? "Aaj aapke **3 kaam** hain:\n\n- 10:30 Design review, 45 minute\n- 14:00 Android build team ke saath call\n- 18:30 Gym\n\nDesign review 40 minute mein shuru hoga. Notes maine laga diye hain."
          : "Today you have **3 things**:\n\n- 10:30 Design review, 45 minutes\n- 14:00 Call with the Android build team\n- 18:30 Gym\n\nYour design review starts in 40 minutes. I attached the briefing notes.",
        c, via, ur ? "Aaj aapke teen kaam hain. Design review 40 minute mein shuru hoga." : "You have three things today. Your design review starts in 40 minutes."
      );
    },

    async install(c, text, via) {
      await c.wait(600);
      await tool(c, { tool: "winget.search", title: "Searching WinGet for VS Code", detail: "Only the official source" }, 1100, { title: "Found Visual Studio Code", detail: "Microsoft.VisualStudioCode from winget" });
      const id = uid("ap");
      bus.emit("approval_request", {
        id, authority: "system", title: "Install Visual Studio Code", expires_ms: 30000, approveLabel: "Approve install",
        detail: "IRAS wants to install software on this PC with WinGet.",
        effects: [
          { icon: "download", text: "Downloads about 95 MB from the official WinGet source" },
          { icon: "hard-drive-download", html: "Installs for your user only, in <code>AppData\\Local\\Programs</code>" },
          { icon: "undo-2", text: "You can remove it later from Windows Settings" },
        ],
      });
      if (sim.auto) autoDecide(id, "approve", 4200, false);
      const decision = await waitApproval(id, c);
      check(c.signal);
      if (decision !== "approve") { await reply("Okay, I won’t install it. Nothing changed on your PC.", c, via, "Okay, I won't install it."); return; }
      bus.emit("state", { state: "thinking" });
      bus.emit("tool_start", {
        id: "t_inst", tool: "winget.install", title: "Installing Visual Studio Code", detail: "winget install Microsoft.VisualStudioCode", authority: "system",
        screen: { layout: "terminal", app: "Terminal", steps: [
          { label: "Downloading the installer", target: "line1" },
          { label: "Checking the file is genuine", target: "line2" },
          { label: "Installing for your user", target: "line3" },
          { label: "Opening it to make sure it works", target: "prompt" },
        ] },
      });
      bus.emit("state", { state: "acting" });
      for (let i = 0; i < 4; i++) { bus.emit("peek_step", { i }); await c.wait(1150); }
      bus.emit("tool_end", { id: "t_inst", ok: true, ms: 4600, title: "Installed Visual Studio Code", detail: "Checked afterwards: it opens", result: { installed: true } });
      await reply("**Visual Studio Code** is installed, and I checked that it opens. You can remove it any time from Windows Settings.", c, via, "Visual Studio Code is installed.");
    },

    async delete(c, text, via) {
      await c.wait(600);
      await tool(c, { tool: "fs.scan", title: "Looking in D:\\projects", detail: "Finding folders named old-builds" }, 1100, { title: "Found 3 folders", detail: "2.4 GB in total" });
      const id = uid("ap");
      bus.emit("approval_request", {
        id, authority: "critical", title: "Delete 3 folders in D:\\projects", expires_ms: 9000, approveLabel: "Approve and delete", phrase: "Approve delete",
        detail: "These folders hold about 2.4 GB. Deleted files skip the Recycle Bin.",
        effects: [
          { icon: "folder", html: "<code>D:\\projects\\old-builds\\v1</code>" },
          { icon: "folder", html: "<code>D:\\projects\\old-builds\\v2</code>" },
          { icon: "folder", html: "<code>D:\\projects\\old-builds\\v3</code>" },
          { icon: "triangle-alert", text: "This can’t be undone" },
        ],
      });
      if (sim.auto) autoDecide(id, "approve", 5200, true);
      const decision = await waitApproval(id, c);
      check(c.signal);
      if (decision !== "approve") {
        await reply(decision === "expired" ? "Time ran out, so I didn’t delete anything." : "No problem. I didn’t delete anything.", c, via, decision === "expired" ? "Time ran out, so I didn't delete anything." : "No problem. I didn't delete anything.");
        return;
      }
      bus.emit("state", { state: "thinking" });
      bus.emit("tool_start", {
        id: "t_del", tool: "fs.delete", title: "Deleting 3 folders", detail: "D:\\projects\\old-builds", authority: "critical",
        screen: { layout: "files", app: "File Explorer", steps: [
          { label: "Opening D:\\projects", target: "dir1" },
          { label: "Selecting the old build folders", target: "dir2" },
          { label: "Deleting them", target: "dir3" },
          { label: "Checking they are gone", target: "dir1" },
        ] },
      });
      bus.emit("state", { state: "acting" });
      for (let i = 0; i < 4; i++) { bus.emit("peek_step", { i }); await c.wait(1000); }
      bus.emit("tool_end", { id: "t_del", ok: true, ms: 4100, title: "Deleted 3 folders", detail: "Freed 2.4 GB", result: { freed_gb: 2.4 } });
      await reply("Done. I deleted **3 folders** and freed **2.4 GB**.", c, via, "Done. I deleted three folders and freed two point four gigabytes.");
    },

    async code(c, text, via) {
      const run = uid("r"), title = "Fix the failing test in iras-core";
      bus.emit("state", { state: "acting" });
      bus.emit("peek_show", { spec: { layout: "terminal", app: "Terminal in iras-core", steps: [
        { label: "Reading the code and the failing test", target: "line1" },
        { label: "Writing the fix", target: "line2" },
        { label: "Running the tests", target: "line3" },
        { label: "Fixing what still fails", target: "line2" },
        { label: "Running the tests again", target: "line3" },
        { label: "Reviewing my own changes", target: "prompt" },
      ] } });
      const steps = [
        { id: "inspect", label: "Inspect", detail: "Read router.py and test_router.py. The test expects a fallback provider.", ms: 1500 },
        { id: "implement", label: "Implement", detail: "Added the fallback when the first provider times out.", ms: 1700 },
        { id: "test", label: "Test", detail: "1 failed, 41 passed. The new fallback skips the retry limit.", ms: 1500, fail: true },
        { id: "repair", label: "Repair", detail: "Changed 2 lines so the retry limit still applies.", ms: 1400 },
        { id: "retest", label: "Re-test", detail: "42 passed.", ms: 1500 },
        { id: "review", label: "Review", detail: "Checked the diff: no secrets, no unrelated edits.", ms: 1200 },
      ];
      for (let i = 0; i < steps.length; i++) {
        const s = steps[i];
        bus.emit("peek_step", { i });
        bus.emit("agent_step", { run, agent: "code", title, step: { id: s.id, label: s.label }, status: "running", stepStatus: "running", detail: s.detail, index: i, total: steps.length });
        await c.wait(s.ms);
        bus.emit("agent_step", { run, agent: "code", title, step: { id: s.id, label: s.label }, status: s.fail ? "failed" : "done", stepStatus: s.fail ? "failed" : "done", detail: s.detail, index: i, total: steps.length, final: i === steps.length - 1, summary: "2 files changed, all 42 tests pass" });
      }
      bus.emit("peek_hide", {});
      await reply(
        "Fixed. The test failed once, so I repaired my change and ran everything again. **All 42 tests pass.**\n\n```diff\n--- a/src/iras/router.py\n+++ b/src/iras/router.py\n@@ def route(request):\n-    return providers[0].send(request)\n+    for provider in providers:\n+        try:\n+            return provider.send(request, timeout=4)\n+        except TimeoutError:\n+            continue\n+    raise AllProvidersDown()\n```\n\nI changed 2 files. Want me to open the diff?",
        c, via, "Fixed. All forty-two tests pass."
      );
    },

    async research(c, text, via) {
      const run = uid("r"), title = "Research: local speech-to-text on low-end laptops";
      bus.emit("state", { state: "thinking" });
      const steps = [
        { id: "plan", label: "Plan", detail: "Four questions: speed, accuracy, memory, license.", ms: 1100 },
        { id: "search", label: "Search", detail: "Found 14 pages. Kept the 9 best.", ms: 1500 },
        { id: "read", label: "Read", detail: "Read 9 sources and took notes.", ms: 1700 },
        { id: "check", label: "Cross-check", detail: "Two sources disagreed on memory use. I checked the benchmarks.", ms: 1400 },
        { id: "write", label: "Write", detail: "One-page brief with sources.", ms: 1100 },
      ];
      for (let i = 0; i < steps.length; i++) {
        const s = steps[i];
        bus.emit("agent_step", { run, agent: "research", title, step: { id: s.id, label: s.label }, status: "running", stepStatus: "running", detail: s.detail, index: i, total: steps.length });
        IRAS.setCaption(s.label + ": " + s.detail);
        await c.wait(s.ms);
        bus.emit("agent_step", { run, agent: "research", title, step: { id: s.id, label: s.label }, status: "done", stepStatus: "done", detail: s.detail, index: i, total: steps.length, final: i === steps.length - 1, summary: "9 sources read, 1-page brief ready" });
      }
      await reply(
        "Here is the short version, from **9 sources**:\n\n- **Whisper small (int8)** is the best balance on a 4-core laptop. About 1.4x faster than real time.\n- **Vosk** is the lightest, but it makes more mistakes with accents.\n- On a laptop with no good GPU, run speech-to-text on the CPU and keep the model in memory.\n\nI saved the full brief with links. Want me to compare two models side by side?",
        c, via, "Here is the short version. Whisper small is the best balance on your laptop."
      );
    },

    async failover(c) {
      bus.emit("state", { state: "thinking" });
      IRAS.setCaption("Gemini is slow. Trying the next provider…");
      await c.wait(1300);
      bus.emit("provider", { active: "OpenRouter", failover: true, reason: "Gemini took longer than 4 seconds" });
      toast("Switched to OpenRouter because Gemini was slow.", { icon: "cpu" });
      await c.wait(900);
      bus.emit("done", {});
    },

    async help(c, text, via) {
      await c.wait(500);
      await reply(
        "I can do a few things in this preview:\n\n- **Open and use apps**, like Spotify, and watch the screen as I work\n- **Read** your email and calendar\n- **Install** software, but only after you approve\n- **Delete** files, but only with your voice or a clear OK\n- **/code** to fix tests, **/research** to write a brief\n\nTry one of the suggestions under the orb.",
        c, via
      );
    },

    async fallback(c, text, via) {
      await c.wait(600);
      await reply("I’m a demo, so I only know a few tasks. Try **Play something calm on Spotify**, **Summarize my unread emails**, **Install VS Code** or **Delete old build folders**, or type **/code** or **/research**.", c, via);
    },
  };

  function pick(text) {
    const t = text.toLowerCase();
    if (/^\/code\b|fix.*test|failing test/.test(t)) return "code";
    if (/^\/research\b|research|brief on/.test(t)) return "research";
    if (/^\/install\b|install|winget/.test(t)) return "install";
    if (/delete|remove|clean up|old build|wipe/.test(t)) return "delete";
    if (/spotify|music|song|gaana|chala|\bplay\b/.test(t)) return "spotify";
    if (/e-?mail|inbox/.test(t)) return "emails";
    if (/calendar|schedule|agenda|meeting|\baaj\b|\btoday\b/.test(t)) return "calendar";
    if (/failover|switch provider/.test(t)) return "failover";
    if (/\bhelp\b|what can you do|kya kar/.test(t)) return "help";
    return "fallback";
  }

  /* in the guided demo, the approval decides itself so the tour keeps moving */
  function autoDecide(id, decision, afterMs, speakIt) {
    setTimeout(async () => {
      if (!S.pending || S.pending.id !== id) return;
      if (speakIt && !IRAS.audio.on) await IRAS.audio.envelope("mic", 1600, null);
      if (S.pending && S.pending.id === id) IRAS.resolveApproval(decision, speakIt ? "voice" : "button");
    }, afterMs);
  }

  sim.route = function (text, { via = "text" } = {}) {
    const name = pick(text);
    return run((c) => scenarios[name](c, text, via));
  };
  sim.play = function (name, via = "text") {
    return run((c) => scenarios[name](c, name, via));
  };

  /* ---------- voice: listening follows your real microphone when allowed ---------- */
  const UTTERANCES = ["Spotify pe kuch calm chala do", "Summarize my unread emails", "Install VS Code", "Delete the old build folders", "What is on my schedule today"];

  sim.voice = function (forced) {
    return run(async (c) => {
      const text = forced || UTTERANCES[sim.utter++ % UTTERANCES.length];
      const words = text.split(" ");
      bus.emit("wake", { via: "button" });
      S.heard = ""; S.heardVia = "voice";
      let real = IRAS.audio.on;
      if (!real && IRAS.settings.realMic && S.mic !== "blocked") {
        real = await IRAS.audio.start();
        if (!real) toast("The microphone is blocked, so the orb uses demo levels. You can allow it in the address bar.", { icon: "mic-off", timeout: 6500 });
      }
      check(c.signal);

      if (real) {
        /* follow the real voice: start when you speak, finish when you stop */
        let spoke = 0, quiet = 0, shown = 0, t = 0, started = false;
        while (t < 11000) {
          await c.wait(100); t += 100;
          const lv = S.level.mic;
          if (lv > .14) { spoke += 100; quiet = 0; started = true; } else if (started) quiet += 100;
          if (spoke > 250 && shown < words.length && (spoke / 100) % 3 === 0) { shown++; bus.emit("partial_transcript", { text: words.slice(0, shown).join(" "), final: false }); }
          if (!started && t >= 6000) { bus.emit("cancel", {}); toast("I didn’t hear anything. Press the mic and try again.", { icon: "ear" }); return; }
          if (started && ((quiet >= 1100 && spoke >= 500) || quiet >= 2500)) break;
        }
        bus.emit("partial_transcript", { text, final: true });
        await c.wait(250);
      } else {
        const dur = Math.max(1800, words.length * 340);
        const env = IRAS.audio.envelope("mic", dur + 200, c.signal);
        for (let i = 1; i <= words.length; i++) {
          await c.wait(dur / words.length);
          bus.emit("partial_transcript", { text: words.slice(0, i).join(" "), final: i === words.length });
        }
        await env;
        await c.wait(250);
      }
      check(c.signal);
      bus.emit("speech_end", { text });
      S.heard = text; S.heardVia = "voice";
      await scenarios[pick(text)](c, text, "voice");
    });
  };

  /* ---------- the guided tour ---------- */
  sim.tour = function () {
    if (S.busy) { toast("Press Stop first, then start the guided demo.", { icon: "info" }); return; }
    IRAS.go("home");
    sim.auto = true;
    run(async (c) => {
      toast("Guided demo. Watch the orb, the pipeline and the live activity.", { icon: "circle-play", timeout: 5200 });
      const steps = [
        ["voice", "Spotify pe kuch calm chala do"],
        ["text", "Summarize my unread emails"],
        ["voice", "Delete the old build folders"],
        ["text", "/code fix the failing test"],
      ];
      for (const [mode, text] of steps) {
        check(c.signal);
        await c.wait(900);
        if (mode === "voice") {
          bus.emit("wake", { via: "tour" });
          S.heard = ""; S.heardVia = "voice";
          const words = text.split(" "), dur = Math.max(1800, words.length * 340);
          const env = IRAS.audio.envelope("mic", dur + 200, c.signal);
          for (let i = 1; i <= words.length; i++) { await c.wait(dur / words.length); bus.emit("partial_transcript", { text: words.slice(0, i).join(" "), final: i === words.length }); }
          await env; await c.wait(250);
          bus.emit("speech_end", { text });
          S.heard = text;
          await scenarios[pick(text)](c, text, "voice");
        } else {
          S.heard = text; S.heardVia = "text";
          bus.emit("submit", { text, via: "text" });
          await scenarios[pick(text)](c, text, "text");
        }
        await c.wait(1100);
      }
    }).finally(() => { sim.auto = false; });
  };
})();
