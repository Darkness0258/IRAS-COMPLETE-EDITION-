/* ==========================================================================
   Sample data for the demo. A live backend replaces all of this.
   ========================================================================== */
"use strict";

(function () {
  const data = (IRAS.data = {});

  /* ---------- audit history ---------- */
  IRAS.seedAudit = function () {
    if (audit.items.length) return;
    const m = 60e3, h = 60 * m, now = Date.now();
    const done = (arr) => arr.map(([id, label, detail]) => ({ id, label, status: "done", detail }));
    const seeds = [
      { ago: 7 * h + 20 * m, kind: "system", title: "Memory synced to your cloud", detail: "212 facts across 3 devices", tags: ["sync"], ms: 2400, payload: { facts: 212, devices: 3 } },
      { ago: 5 * h + 40 * m, kind: "tool", title: "Opened Chrome on your dashboard", detail: "Window focused, page loaded", tags: ["apps.open"], ms: 1100, payload: { tool: "apps.open", args: { app: "chrome", url: "http://localhost:8000/app/" }, result: { ok: true, window: "Chrome" } } },
      { ago: 4 * h + 55 * m, kind: "tool", authority: "system", title: "Sent a WhatsApp message to Family group", detail: "“Reaching home in 20 minutes”", tags: ["whatsapp.send"], ms: 2300, payload: { tool: "whatsapp.send", args: { to: "Family group", chars: 29 }, result: { ok: true, delivered: true } } },
      { ago: 3 * h + 30 * m, kind: "agent", title: "Research: local speech-to-text on low-end laptops", detail: "9 sources read, 1-page brief ready", tags: ["/research"], ms: 118000, payload: { agent: "research", progress: 1, steps: done([["plan", "Plan", "Four questions: speed, accuracy, memory, license."], ["search", "Search", "Found 14 pages. Kept the 9 best."], ["read", "Read", "Read 9 sources and took notes."], ["check", "Cross-check", "Two sources disagreed. Checked the benchmarks."], ["write", "Write", "One-page brief with sources."]]) } },
      { ago: 2 * h + 12 * m, kind: "tool", authority: "system", title: "Installed Git", detail: "Checked afterwards: git --version works", tags: ["winget.install"], ms: 41000, payload: { tool: "winget.install", args: { id: "Git.Git", source: "winget" }, result: { ok: true, version_check: "passed" } } },
      { ago: 1 * h + 45 * m, kind: "approval", authority: "critical", status: "denied", title: "Approval expired. Nothing changed", detail: "Delete 2 folders in D:\\temp", tags: ["approval"], ms: 9000, payload: { request: "ap_seed", decision: "expired", via: "timeout", effects: [{ text: "D:\\temp\\cache-a" }, { text: "D:\\temp\\cache-b" }] } },
      { ago: 1 * h + 20 * m, kind: "system", title: "Switched AI provider to OpenRouter", detail: "Gemini took longer than 4 seconds", tags: ["failover"], ms: 0, payload: { from: "Gemini", to: "OpenRouter", reason: "Gemini took longer than 4 seconds" } },
      { ago: 52 * m, kind: "tool", title: "Played “Calm Piano” on Spotify", detail: "Checked afterwards: music is playing", tags: ["spotify.play"], ms: 5100, payload: { tool: "spotify.play", args: { query: "calm piano" }, result: { playing: true } } },
      { ago: 34 * m, kind: "tool", title: "Read 3 unread emails", detail: "Newest: weekly team update", tags: ["mail.read"], ms: 900, payload: { tool: "mail.read", args: { folder: "inbox", unread: true }, result: { unread: 3 } } },
      { ago: 18 * m, kind: "agent", title: "Fix the failing test in iras-core", detail: "2 files changed, all 42 tests pass", tags: ["/code"], ms: 96000, payload: { agent: "code", progress: 1, steps: [
        { id: "inspect", label: "Inspect", status: "done", detail: "Read router.py and test_router.py." },
        { id: "implement", label: "Implement", status: "done", detail: "Added the fallback when the first provider times out." },
        { id: "test", label: "Test", status: "failed", detail: "1 failed, 41 passed." },
        { id: "repair", label: "Repair", status: "done", detail: "Changed 2 lines so the retry limit still applies." },
        { id: "retest", label: "Re-test", status: "done", detail: "42 passed." },
        { id: "review", label: "Review", status: "done", detail: "No secrets, no unrelated edits." },
      ] } },
    ];
    seeds.forEach((s) => {
      const { ago, ...rest } = s;
      audit.add(Object.assign({ status: "done" }, rest, { ts: now - ago }));
    });
  };

  /* ---------- routines ---------- */
  data.routines = [
    { id: "brief", name: "Morning briefing", desc: "Reads your calendar and unread email, then tells you the day in three minutes.", when: "Weekdays at 8:00", last: "Today, 8:00. Took 3.4 s", tools: ["Calendar", "Email"], on: true },
    { id: "backup", name: "Nightly project backup", desc: "Copies D:\\projects to your cloud drive and checks the copy opens.", when: "Every night at 00:00", last: "Last night. Took 4 min", tools: ["Files", "Cloud drive"], on: true },
    { id: "ci", name: "Watch failing builds", desc: "Checks your repos for failing tests and tells you the first thing to look at.", when: "Every 30 minutes", last: "14 min ago", tools: ["GitHub"], on: true },
    { id: "price", name: "Price watch", desc: "Checks a product page and tells you when the price drops.", when: "Every 6 hours", last: "2 hours ago", tools: ["Browser"], on: true },
    { id: "tidy", name: "Tidy the Downloads folder", desc: "Sorts files by type. Always asks before it deletes anything.", when: "Sundays at 10:00", last: "Last Sunday", tools: ["Files"], on: false },
  ];

  /* ---------- memory graph ---------- */
  data.graph = {
    nodes: [
      { id: "you", label: "You", type: "you", detail: "The owner of this IRAS." },
      { id: "pc", label: "Windows laptop", type: "device", detail: "Runs the IRAS core. Four cores and no strong GPU, so IRAS keeps models light here." },
      { id: "phone", label: "Android phone", type: "device", detail: "Remote control and push approvals." },
      { id: "web", label: "This web app", type: "device", detail: "Installed as an app on your devices." },
      { id: "core", label: "IRAS core", type: "project", detail: "The brain: router, memory, agents and tools." },
      { id: "cloud", label: "Cloud sync", type: "service", detail: "Keeps memory and chats in step across devices." },
      { id: "db", label: "Postgres", type: "service", detail: "Stores memory and conversations in your own cloud." },
      { id: "spotify", app: true, label: "Spotify", type: "service", detail: "Used 14 times this week, mostly after 9 pm." },
      { id: "whatsapp", app: true, label: "WhatsApp", type: "service", detail: "Messages are sent only after you approve." },
      { id: "calendar", app: true, label: "Calendar", type: "service", detail: "Read only. Used for your morning briefing." },
      { id: "mail", app: true, label: "Email", type: "service", detail: "Read only. IRAS drafts, you send." },
      { id: "gemini", label: "Gemini", type: "model", detail: "The main AI provider." },
      { id: "openrouter", label: "OpenRouter", type: "model", detail: "First backup when Gemini is slow." },
      { id: "ollama", label: "Ollama", type: "model", detail: "Runs on this PC. Works with no internet." },
      { id: "p-urdu", label: "Roman Urdu when I speak", type: "preference", detail: "You like replies in Roman Urdu when you talk and English when you type." },
      { id: "p-calm", label: "Calm music in the evening", type: "preference", detail: "Seen 6 times." },
      { id: "p-quiet", label: "Quiet hours 23:00 to 07:00", type: "preference", detail: "No spoken replies in this window." },
      { id: "p-short", label: "Short answers", type: "preference", detail: "Keep replies brief unless you ask for more." },
      { id: "voice", label: "Voice: iras_human", type: "preference", detail: "The voice profile IRAS speaks with." },
      { id: "proj", label: "D:\\projects", type: "project", detail: "Your main workspace. Backed up every night." },
      { id: "brief", label: "Morning briefing", type: "project", detail: "Weekdays at 8:00." },
    ],
    edges: [
      ["you", "pc"], ["you", "phone"], ["you", "web"], ["pc", "core"], ["phone", "core"], ["web", "core"],
      ["core", "cloud"], ["cloud", "db"], ["core", "gemini"], ["core", "openrouter"], ["core", "ollama"],
      ["you", "p-urdu"], ["you", "p-calm"], ["p-calm", "spotify"], ["you", "p-quiet"], ["you", "p-short"], ["you", "voice"],
      ["you", "proj"], ["pc", "proj"], ["core", "spotify"], ["core", "whatsapp"], ["core", "calendar"], ["core", "mail"],
      ["you", "brief"], ["brief", "calendar"], ["brief", "mail"], ["ollama", "pc"],
    ],
  };

  /* ---------- facts waiting for review ---------- */
  data.facts = [
    { id: "f1", text: "You usually ask for music after 9 pm.", source: "Seen 6 times in Spotify requests", conf: 92, use: "IRAS picks calmer playlists in the evening." },
    { id: "f2", text: "You like replies in Roman Urdu when you speak, English when you type.", source: "Seen 11 times", conf: 88, use: "IRAS answers in the language you used." },
    { id: "f3", text: "D:\\projects is your main workspace.", source: "Seen in 24 file requests", conf: 97, use: "IRAS looks there first when you say “my project”." },
    { id: "f4", text: "You approve installs with a tap but want to say deletes out loud.", source: "Your last 5 approvals", conf: 81, use: "IRAS asks for your voice on deletes." },
  ];
})();
