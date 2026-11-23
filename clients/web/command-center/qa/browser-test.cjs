#!/usr/bin/env node
"use strict";
/* ==========================================================================
   Browser test: each person's own memory, calendar and reminders.

   It opens the real page in a real Chrome (puppeteer-core with @sparticuz/chromium),
   against the test server in qa/test_server.py, and checks the Memory, Identity and
   Agents screens, the private reminder notices, phone widths (360 to 412 px),
   accessibility (axe-core) and a fake microphone file. The "Voice check" sections test the new voice check
   while she listens: a fake speech recognizer, Chrome's fake microphone and a scripted server answer, so every
   case can be tried (a clear match, another person, "nobody I know", a slow server, Stop, guest mode, a microphone
   that gives no sound or cannot be shared, the Android app, a phone's browser). Try only those: QA_ONLY="voice check".

   1. Tools, in a folder OUTSIDE the project (so the page tests never read them):
        mkdir ~/iras-qa-tools && cd ~/iras-qa-tools
        npm init -y && npm i puppeteer-core @sparticuz/chromium axe-core
   2. Test server (writes a new token to the file; never prints it):
        python clients/web/command-center/qa/test_server.py --port 8765 --token-file /tmp/iras-qa-token
   3. The test:
        QA_NODE_DIR=~/iras-qa-tools IRAS_TOKEN_FILE=/tmp/iras-qa-token \
          node clients/web/command-center/qa/browser-test.cjs

   It creates people, memories, reminders and a calendar named "QA ..." and deletes them at
   the end. It only runs against a server on this computer (127.0.0.1 or localhost).
   Screenshots go to QA_SHOTS (default: the temp folder). The exit code is 1 if a check fails.
   ========================================================================== */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { createRequire } = require("module");

const BASE = (process.env.IRAS_URL || "http://127.0.0.1:8765").replace(/\/+$/, "");
const TOKEN = process.env.IRAS_TOKEN || (process.env.IRAS_TOKEN_FILE ? fs.readFileSync(process.env.IRAS_TOKEN_FILE, "utf8").trim() : "");
if (!TOKEN) { console.error("Give the access token with IRAS_TOKEN_FILE (a file) or IRAS_TOKEN."); process.exit(2); }
if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE) && process.env.QA_ALLOW_REMOTE !== "1") {
  console.error("This test writes data, so it only runs against a server on this computer. Start qa/test_server.py.");
  process.exit(2);
}

const SHOTS = process.env.QA_SHOTS || path.join(os.tmpdir(), "iras-qa-shots");
fs.mkdirSync(SHOTS, { recursive: true });
const MIC = path.join(os.tmpdir(), "iras-qa-fake-mic.wav");

const nodeRequire = createRequire(path.join(process.env.QA_NODE_DIR || __dirname, "noop.js"));
const puppeteer = nodeRequire("puppeteer-core");
const chromiumModule = nodeRequire("@sparticuz/chromium");
const chromium = chromiumModule.default || chromiumModule;
const AXE_SOURCE = fs.readFileSync(nodeRequire.resolve("axe-core/axe.min.js"), "utf8");

/* ---------- a tiny test kit ---------- */
const results = [];
const pageProblems = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail !== undefined ? "   [" + String(detail).slice(0, 300) + "]" : ""));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 8000, step = 100) {
  const t = Date.now();
  for (;;) {
    try { const v = await fn(); if (v) return v; } catch (e) { /* try again */ }
    if (Date.now() - t > ms) return false;
    await sleep(step);
  }
}
const ONLY = (process.env.QA_ONLY || "").toLowerCase().split(",").map((x) => x.trim()).filter(Boolean);   // for example QA_ONLY=private,phone
let lastPage = null;
async function section(name, fn) {
  if (ONLY.length && !ONLY.some((o) => name.toLowerCase().includes(o))) return;
  console.log("\n== " + name + " ==");
  try { await fn(); } catch (e) {
    check(name + ": the test itself stopped", false, (e && e.message || e).toString().split("\n")[0]);
    if (lastPage) {
      try { await lastPage.screenshot({ path: path.join(SHOTS, "stopped-" + name.replace(/\W+/g, "-") + ".png") }); } catch (x) { /* ignore */ }
      try { console.log("     page then: " + JSON.stringify(await lastPage.evaluate(() => ({ view: IRAS.view(), openDialogs: Array.from(document.querySelectorAll("dialog[open]")).map((d) => d.id), scrollY: Math.round(scrollY), width: innerWidth }))) + "  problems: " + JSON.stringify(pageProblems.slice(-4))); } catch (x) { /* the page is gone */ }
    }
  }
}

/* ---------- the server, through its own API ---------- */
async function api(method, p, body) {
  const r = await fetch(BASE + p, { method, headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) { /* not json */ }
  if (!r.ok) throw new Error(method + " " + p + " gave " + r.status + " " + String((data && data.detail) || text).slice(0, 120));
  return data;
}
const made = { people: [] };
async function makePerson(name) { const r = await api("POST", "/v1/identity/people", { name }); made.people.push(r.person.person_id); return r.person; }
const makeMemory = (text, namespace) => api("POST", "/v1/v5/memory", { text, namespace, kind: "note", source: "qa" });
async function mems(ns) { return (await api("GET", "/v1/v5/memory/search?limit=200&q=" + (ns ? "&namespace=" + encodeURIComponent(ns) : ""))).memories || []; }
const texts = (list) => list.map((m) => String(m.text));
async function jobs() { return (await api("GET", "/v1/v5/schedules")).schedules || []; }
async function feeds() { return (await api("GET", "/v1/calendar/status")).feeds || []; }

async function cleanup() {
  const tries = [
    async () => { for (const m of await mems("")) if (/^QA/.test(String(m.text))) await api("DELETE", "/v1/v5/memory/" + encodeURIComponent(m.memory_id)); },
    async () => { for (const j of await jobs()) if (/QA/.test(j.name + " " + j.prompt)) await api("DELETE", "/v1/v5/schedules/" + encodeURIComponent(j.job_id)); },
    async () => { for (const f of await feeds()) if (/^QA/.test(f.name)) await api("DELETE", "/v1/calendar/feeds/" + encodeURIComponent(f.feed_id)); },
    async () => { for (const id of made.people) await api("DELETE", "/v1/identity/people/" + encodeURIComponent(id)); },
  ];
  for (const t of tries) { try { await t(); } catch (e) { /* best effort */ } }
}

/* ---------- a fake microphone: 12 seconds of a voice-like sound ---------- */
function makeMicFile(file) {
  const rate = 16000, n = rate * 12, buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVE", 8); buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(rate, 24);
  buf.writeUInt32LE(rate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) {
    const t = i / rate, f0 = 120 + 25 * Math.sin(2 * Math.PI * 0.7 * t), ph = 2 * Math.PI * f0 * t;
    const env = 0.55 + 0.45 * Math.sin(2 * Math.PI * 3 * t);
    const s = env * (0.5 * Math.sin(ph) + 0.25 * Math.sin(2 * ph) + 0.15 * Math.sin(3 * ph) + 0.1 * Math.sin(5.1 * ph));
    buf.writeInt16LE(Math.round(s * 0.6 * 32767), 44 + i * 2);
  }
  fs.writeFileSync(file, buf);
}

/* ---------- the page ---------- */
const DESKTOP = { width: 1280, height: 900 };
const PHONES = [{ width: 360, height: 740 }, { width: 390, height: 844 }, { width: 412, height: 915 }];

async function openPage(browser, size, theme = "light", who = null, fakeNotices = false, before = []) {
  const ctx = await browser.createBrowserContext();
  try { await ctx.overridePermissions(BASE, ["microphone", "camera"]); } catch (e) { /* the fake-device flags cover it */ }
  const page = await ctx.newPage();
  lastPage = page;
  const phone = size.width < 600;
  await page.setViewport({ width: size.width, height: size.height, deviceScaleFactor: 1, isMobile: phone, hasTouch: phone });
  let fake = null;   // with fakeNotices, the page is given the list in fake.list instead of the server's
  if (fakeNotices) {
    fake = { list: [] };
    await page.setRequestInterception(true);
    page.on("request", (r) => {
      if (r.method() === "GET" && new URL(r.url()).pathname === "/v1/v5/notifications") r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ notifications: fake.list }) });
      else r.continue();
    });
  }
  page.on("pageerror", (e) => pageProblems.push("page error: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") pageProblems.push("console: " + m.text()); });
  page.on("response", (r) => { if (r.status() >= 400) pageProblems.push("HTTP " + r.status() + " " + r.request().method() + " " + new URL(r.url()).pathname); });
  await page.evaluateOnNewDocument((base, token, th, who) => {
    try {
      localStorage.setItem("iras-cc-settings", JSON.stringify({ theme: th, skin: "cobalt", perf: "lite", motion: "reduce", source: "live", server: base, realMic: true, speakReplies: false }));
      sessionStorage.setItem("iras-api-token", token);
      if (who) sessionStorage.setItem("iras-who", JSON.stringify({ kind: "person", person_id: who.person_id, name: who.name, via: "chosen", at: Date.now() }));
    } catch (e) { /* ignore */ }
    // Nothing is really spoken: from the first moment, what she would say is only written down.
    window.__spoken = [];
    window.IRAS = window.IRAS || {};
    let real = null;
    Object.defineProperty(window.IRAS, "voice", {
      configurable: true, enumerable: true,
      get() { return real; },
      set(v) { real = v; try { Object.defineProperty(v, "speak", { configurable: true, enumerable: true, get() { return (t) => { window.__spoken.push(String(t)); }; }, set() { /* keep ours */ } }); } catch (e) { /* ignore */ } },
    });
    // Every message box that appears is written down too, from the first moment.
    window.__toasts = [];
    // (The page keeps at most 3 boxes and removes older ones at once, so the box is read from the record, not from the page.)
    new MutationObserver((list) => list.forEach((m) => {
      if (!m.target || m.target.id !== "toasts") return;
      m.addedNodes.forEach((n) => { if (n.nodeType === 1) { const t = (n.textContent || "").trim(); if (t) window.__toasts.push(t); } });
    })).observe(document, { childList: true, subtree: true });
  }, BASE, TOKEN, theme, who ? { person_id: who.person_id, name: who.name } : null);
  for (const fn of [].concat(before)) await page.evaluateOnNewDocument(fn);   // for example a fake speech recognizer (see fakeSpeech)
  await page.goto(BASE + "/", { waitUntil: "load" });
  const live = await until(() => page.evaluate(() => typeof IRAS !== "undefined" && IRAS.live && IRAS.live.ok === true), 20000);
  if (!live) throw new Error("the page never reached the test server");
  return { page, ctx, fake };
}
async function go(page, view) {
  await page.bringToFront();
  await page.evaluate((v) => IRAS.go(v), view);
  await until(() => page.evaluate((v) => IRAS.view() === v, view));
  await sleep(250);
}
const setWho = (page, p) => page.evaluate((x) => IRAS.who.set(x, "chosen"), { person_id: p.person_id, name: p.name });
const guestOn = (page) => page.evaluate(() => IRAS.who.guest());
const nobody = (page) => page.evaluate(() => IRAS.who.clear());
const toasts = (page) => page.evaluate(() => window.__toasts.slice());
const spoken = (page) => page.evaluate(() => window.__spoken.slice());
function nextDialog(page, accept) {
  return new Promise((resolve) => page.once("dialog", async (d) => { const m = d.message(); await (accept ? d.accept() : d.dismiss()); resolve(m); }));
}
/* Press a button on a phone: bring it to the middle, wait until the page stops moving under it, then press. */
async function tap(page, sel) {
  await until(() => page.evaluate(() => document.querySelectorAll("#toasts > *").length === 0), 15000, 300);   // message boxes can cover a button on a small screen
  const place = () => page.$eval(sel, (e) => { e.scrollIntoView({ block: "center" }); const r = e.getBoundingClientRect(); return Math.round(r.top) + "," + Math.round(r.left); });
  let last = await place();
  for (let i = 0; i < 25; i++) {
    await sleep(250);
    const now = await place();
    if (now === last) break;
    last = now;
  }
  await page.click(sel);
}
async function shot(page, name) { try { await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } catch (e) { /* not important */ } }
const valueOf = (page, sel) => page.$eval(sel, (e) => e.value);
const innerText = (page, sel) => page.$eval(sel, (e) => e.innerText.replace(/\s+/g, " ").trim());
const options = (page, sel) => page.$$eval(sel + " option", (os) => os.map((o) => ({ value: o.value, label: o.textContent.trim() })));
const rows = (page) => page.$$eval("#memList .mem-item", (els) => els.map((e) => ({ text: e.innerText.replace(/\s+/g, " ").trim(), owner: ((e.querySelector(".badge.owner") || {}).textContent || "").trim() })));

async function axeRun(page, label, expect = []) {
  await page.evaluate(AXE_SOURCE);
  const found = await page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] }, resultTypes: ["violations"] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
  });
  const bad = found.filter((v) => !expect.includes(v.id));
  check("accessibility (axe): " + label, bad.length === 0, bad.map((v) => v.id + " [" + v.impact + "] " + v.nodes.join(" | ")).join("; "));
  return found;
}
const noSideways = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
const insideScreen = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1 && r.top >= 0 && r.bottom <= window.innerHeight + 1; });

/* ---------- the voice check while she listens: a fake speech recognizer, a watched microphone, a server we can script ---------- */
function fakeSpeech() {   // runs inside the page, before it loads: nothing is really listened to, the test says what she "heard"
  window.__sr = { starts: 0, stops: 0, last: null };
  class FakeSpeech {
    constructor() { window.__sr.last = this; this.on = false; }
    start() { window.__sr.starts++; this.on = true; setTimeout(() => this.onstart && this.onstart(), 20); }
    stop() { window.__sr.stops++; this.finish(); }
    abort() { this.finish(); }
    finish() { if (!this.on) return; this.on = false; setTimeout(() => this.onend && this.onend(), 20); }
    say(text) { const r = [{ transcript: text }]; r.isFinal = true; this.onresult && this.onresult({ resultIndex: 0, results: [r] }); }
  }
  window.SpeechRecognition = FakeSpeech;
}
function watchedMic() {   // runs inside the page: every microphone stream is written down, and the test can make it silent or busy
  window.__streams = []; window.__mic = "real"; window.__gum = 0;
  const md = navigator.mediaDevices, real = md.getUserMedia.bind(md);
  md.getUserMedia = async (c) => {
    window.__gum++;
    if (window.__mic === "busy") throw new DOMException("The microphone is in use.", "NotReadableError");
    if (window.__mic === "silent") { const dest = new AudioContext().createMediaStreamDestination(); window.__streams.push(dest.stream); return dest.stream; }
    const s = await real(c); window.__streams.push(s); return s;
  };
}
function androidApp() {   // runs inside the page: it looks like the Android app, which listens with the phone's own speech recognizer
  window.IRASNative = { canListen: () => true, listen() {}, stop() {}, reload() {}, openClassic() {} };
}
function phoneBrowser() {   // runs inside the page: a phone's browser says so in its name
  Object.defineProperty(navigator, "userAgent", { get: () => "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36" });
}

function parseWav(url) {   // what the server would receive: a 16-bit mono WAV in a data URL
  const m = /^data:audio\/wav;base64,(.+)$/.exec(url || "");
  if (!m) return null;
  const b = Buffer.from(m[1], "base64");
  if (b.length < 45 || b.toString("ascii", 0, 4) !== "RIFF" || b.toString("ascii", 8, 12) !== "WAVE") return null;
  const ch = b.readUInt16LE(22), rate = b.readUInt32LE(24), bits = b.readUInt16LE(34), bytes = b.readUInt32LE(40);
  let peak = 0;
  for (let i = 44; i + 1 < b.length; i += 2) peak = Math.max(peak, Math.abs(b.readInt16LE(i)) / 32768);
  return { ch, rate, bits, seconds: bytes / (rate * ch * (bits / 8)), peak, bytes: b.length };
}

/* Watches the voice-check call and the chat call of one page, and answers them from a script.
   The list of people comes from the test (with how many voices each has). Everything else goes to the real server. */
async function watchVoice(page, people) {
  const seen = { verify: [], chat: [] };
  const plan = { verify: [] };   // answers, used one by one: { body, delay }
  await page.setRequestInterception(true);
  page.on("request", async (r) => {
    const p = new URL(r.url()).pathname;
    if (r.method() === "GET" && p === "/v1/identity/people") return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ people }) });
    if (r.method() === "POST" && p === "/v1/identity/voice/verify") {
      const body = JSON.parse(r.postData() || "{}");
      body._auth = /^Bearer .+/.test(String(r.headers().authorization || ""));
      seen.verify.push(body);
      const next = plan.verify.shift() || { body: { heard: false, match: null, closest: null, speech: 0, seconds: 0, verdict: "unheard", message: "no answer planned" } };
      if (next.delay) await sleep(next.delay);
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(next.body) });
    }
    if (r.method() === "POST" && p === "/v1/chat/stream") {
      seen.chat.push(JSON.parse(r.postData() || "{}"));
      return r.respond({ status: 200, contentType: "text/event-stream", body: "event: start\ndata: {\"thread_id\":\"qa\"}\n\nevent: done\ndata: {}\n\n" });   // a reply with no words: there is nothing to read out loud
    }
    return r.continue();
  });
  await until(() => page.evaluate(() => IRAS.live.ok === true), 10000);   // she does nothing until the server is connected
  /* The page may already be loading the real list (then a new load is handed that same answer), so ask until it holds ours. */
  const voices = people.reduce((n, x) => n + x.voices, 0);
  const got = await until(async () => {
    await page.evaluate(() => IRAS.people.load(true));
    return page.evaluate((n, count) => IRAS.people.all().length === count && IRAS.people.all().reduce((a, x) => a + x.voices, 0) === n, voices, people.length);
  }, 10000, 150);
  if (!got) throw new Error("the page never received the scripted list of people");
  return { seen, plan };
}

const answerFor = (verdict, p, score = 0.8) => ({
  heard: verdict !== "unheard", speech: verdict === "unheard" ? 1.1 : 3.1, seconds: 3.3, verdict, message: "",
  match: verdict === "match" ? { person_id: p.person_id, name: p.name, score } : null,
  closest: verdict === "unheard" || !p ? null : { person_id: p.person_id, name: p.name, score: verdict === "match" ? score : verdict === "other" ? 0.12 : 0.41 },
});
const whoNow = (page) => page.evaluate(() => { const w = IRAS.who.current(); return w ? { kind: w.kind, id: w.person_id || "", name: w.name || "", via: w.via || "" } : null; });
const settleUi = (page) => until(() => page.evaluate(() => document.body.dataset.uiState === "idle"), 15000, 100);

/* One talk: she starts to listen, the person talks for talkMs, the fake recognizer "hears" the words, and the chat goes out. */
async function voiceTurn(page, kit, o = {}) {
  kit.plan.verify.length = 0;   // an answer that was planned but never asked for must not leak into this turn
  if (o.answer) kit.plan.verify.push({ body: o.answer, delay: o.delay || 0 });
  if (o.answers) o.answers.forEach((a) => kit.plan.verify.push(a));
  await settleUi(page);
  const was = { verify: kit.seen.verify.length, chat: kit.seen.chat.length, gum: await page.evaluate(() => window.__gum) };
  await page.evaluate(() => IRAS.voice.toggle());
  await sleep(o.talkMs || 2600);
  const whileTalking = kit.seen.verify.length - was.verify;
  await page.evaluate((t) => { window.__sr.last.say(t); window.__sr.last.stop(); }, o.say || "what is on my calendar today");
  const t0 = Date.now();
  const sent = await until(() => kit.seen.chat.length > was.chat, o.limit || 12000, 40);
  const waited = Date.now() - t0;
  return {
    sent, waited, whileTalking,
    asked: kit.seen.verify.length - was.verify,
    gum: (await page.evaluate(() => window.__gum)) - was.gum,
    chat: kit.seen.chat[kit.seen.chat.length - 1] || null,
    verify: kit.seen.verify[kit.seen.verify.length - 1] || null,
  };
}

/* ==========================================================================
   The run
   ========================================================================== */
(async () => {
  makeMicFile(MIC);
  const args = chromium.args.filter((a) => !/^--single-process/.test(a)).concat([
    "--no-sandbox", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
    "--use-file-for-fake-audio-capture=" + MIC, "--autoplay-policy=no-user-gesture-required",
  ]);
  const browser = await puppeteer.launch({ executablePath: await chromium.executablePath(), headless: "shell", args });
  console.log("Browser: " + (await browser.version()) + "   Server: " + BASE + "   Screenshots: " + SHOTS);

  /* Test people and memories. "shared" is the name she uses when she saves something for the household. */
  const alice = await makePerson("QA Alice");
  const bob = await makePerson("QA Bob");
  let carol = null;   // made when the voice sections need her
  const voicePeople = () => [
    { person_id: alice.person_id, name: alice.name, faces: 0, voices: 3 },
    { person_id: bob.person_id, name: bob.name, faces: 0, voices: 2 },
    { person_id: carol.person_id, name: carol.name, faces: 1, voices: 0 },   // her face is known, her voice is not
  ];
  await makeMemory("QA shared note: the house wifi is slow", "default");
  await makeMemory("QA household note: bins go out on Tuesday", "shared");
  await makeMemory("QA Alice likes jasmine tea", "person:" + alice.person_id);
  await makeMemory("QA Bob likes football", "person:" + bob.person_id);

  /* ------------------------------------------------------------------ Memory */
  await section("Memory screen (desktop)", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP);
    await go(page, "memory");
    await until(async () => (await rows(page)).length >= 5);                       // four memories and "You"
    await page.evaluate(() => document.querySelector("input[name='memView'][value='list']").click());
    await sleep(300);

    const h2 = await page.$$eval("#memList h2", (e) => e.length), h3 = await page.$$eval("#memList h3", (e) => e.length);
    check("list headings are h2, and there is no h3", h2 >= 2 && h3 === 0, h2 + " h2, " + h3 + " h3");

    let r = await rows(page);
    const ownerOf = (word) => ((r.find((x) => x.text.includes(word)) || {}).owner || "(no row)");
    check("owner label: a shared memory says Shared", ownerOf("house wifi") === "Shared", ownerOf("house wifi"));
    check('owner label: a memory saved as "shared" says Shared', ownerOf("bins go out") === "Shared", ownerOf("bins go out"));
    check("owner label: Alice's memory says QA Alice", ownerOf("jasmine") === "QA Alice", ownerOf("jasmine"));
    check("owner label: Bob's memory says QA Bob", ownerOf("football") === "QA Bob", ownerOf("football"));

    const filter = await options(page, "#memFilter");
    check("filter has All, Shared and each person", filter.length === 4 && filter[0].label === "All memories" && filter[1].label === "Shared memories" && /^QA Alice.*memories$/.test(filter[2].label) && /^QA Bob.*memories$/.test(filter[3].label), JSON.stringify(filter));
    check("filter values are '', default, person:<id>", filter[0].value === "" && filter[1].value === "default" && filter[2].value === "person:" + alice.person_id, JSON.stringify(filter.map((f) => f.value)));

    await page.select("#memFilter", "person:" + alice.person_id);
    await until(async () => (await rows(page)).filter((x) => x.owner).length === 1);
    r = await rows(page);
    check("filter Alice: only her memory is listed", r.filter((x) => x.owner).length === 1 && r.some((x) => x.text.includes("jasmine")), JSON.stringify(r.map((x) => x.text.slice(0, 30))));
    await page.select("#memFilter", "default");
    await until(async () => (await rows(page)).filter((x) => x.owner).length === 2);
    r = await rows(page);
    check('filter Shared: both the "default" and the "shared" memories', r.filter((x) => x.owner).length === 2 && r.some((x) => x.text.includes("house wifi")) && r.some((x) => x.text.includes("bins go out")), JSON.stringify(r.map((x) => x.text.slice(0, 30))));
    await page.select("#memFilter", "");
    await until(async () => (await rows(page)).filter((x) => x.owner).length === 4);
    check("filter All: all four", (await rows(page)).filter((x) => x.owner).length === 4);

    /* "Whose memory?" */
    check('the label says exactly "Whose memory?"', (await page.$eval("label[for=memWhose]", (e) => e.textContent.trim())) === "Whose memory?");
    const whose = await options(page, "#memWhose");
    check("Whose memory? has Shared, then each person", whose.length === 3 && /^Shared/.test(whose[0].label) && whose[0].value === "default" && whose[1].value === "person:" + alice.person_id, JSON.stringify(whose));
    check("with nobody here it starts on Shared", (await valueOf(page, "#memWhose")) === "default");

    /* choose Alice with the real "Who is here?" pop-up on Home */
    await go(page, "home");
    await page.click("[data-who-open]");
    await page.waitForSelector("#whoDlg[open] [data-pick]", { timeout: 8000 });
    await page.click("#whoDlg [data-pick='" + alice.person_id + "']");
    await sleep(400);
    await go(page, "memory");
    check("Who is here = Alice: Whose memory? starts on Alice", (await valueOf(page, "#memWhose")) === "person:" + alice.person_id, await valueOf(page, "#memWhose"));
    check("the hint says it is private", /only QA Alice|Private/i.test(await innerText(page, "#memWhoseHint")), await innerText(page, "#memWhoseHint"));

    /* save for Bob, then for everyone */
    await page.select("#memWhose", "person:" + bob.person_id);
    await page.type("#memNew", "QA saved for Bob from the screen");
    await page.click("#memAdd");
    const savedBob = await until(async () => (await mems("person:" + bob.person_id)).some((m) => m.text.includes("saved for Bob from the screen")));
    check("saving for Bob puts it in person:<Bob id>", savedBob);
    check("the message says it was saved for Bob", await until(async () => (await toasts(page)).some((t) => /Saved for QA Bob/.test(t)), 6000), JSON.stringify(await toasts(page)));
    check("after saving, the choice goes back to the person who is here", await until(async () => (await valueOf(page, "#memWhose")) === "person:" + alice.person_id, 4000), await valueOf(page, "#memWhose"));
    await page.select("#memWhose", "default");
    await page.type("#memNew", "QA saved as shared from the screen");
    await page.click("#memAdd");
    check("saving as shared puts it in default", await until(async () => (await mems("default")).some((m) => m.text.includes("saved as shared from the screen"))));

    /* the node card names the owner */
    await page.evaluate(() => document.querySelector("#memList .mem-item[data-go]:not([data-go='you'])").click());
    check("the memory card says whose memory it is", await until(async () => /Whose memory/.test(await innerText(page, "#nodeCard")) && (await page.$("#nodeCard .badge.owner")) !== null, 5000), await innerText(page, "#nodeCard"));

    /* a person made while the page is open is in the choices as soon as the Identity screen has looked */
    const carol = await makePerson("QA Carol");
    await go(page, "identity");
    await until(() => page.$$eval("#ownList .own-row", (e) => e.length >= 3));
    await go(page, "memory");
    check("a new person is in Whose memory? and Show at once", (await options(page, "#memWhose")).some((o) => o.label === "QA Carol") && (await options(page, "#memFilter")).some((o) => /QA Carol/.test(o.label)));
    await api("DELETE", "/v1/identity/people/" + encodeURIComponent(carol.person_id));
    await go(page, "identity");
    await until(() => page.$$eval("#ownList .own-row", (e) => e.length === 2));
    await go(page, "memory");
    check("a forgotten person is gone from the choices at once", !(await options(page, "#memWhose")).some((o) => /Carol/.test(o.label)) && !(await options(page, "#memFilter")).some((o) => /Carol/.test(o.label)));

    await shot(page, "memory-desktop");
    await axeRun(page, "Memory list (desktop)");
    await page.evaluate(() => document.querySelector("input[name='memView'][value='graph']").click());
    await sleep(400);
    await axeRun(page, "Memory map (desktop)");
    await ctx.close();
  });

  /* ---------------------------------------------------------------- Identity */
  await section("Identity screen: each person's own memories", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP);
    await go(page, "identity");
    await until(() => page.$$eval("#ownList .own-row", (e) => e.length >= 2));
    check("the card has an h2 with the right title", (await page.$eval("#ownTitle", (e) => e.tagName + ":" + e.textContent.trim())) === "H2:Each person's own memories");
    const names = await page.$$eval("#ownList .own-row strong", (e) => e.map((x) => x.textContent.trim()));
    check("every person is listed", names.includes("QA Alice") && names.includes("QA Bob"), JSON.stringify(names));
    const labels = await page.$$eval("#ownList .own-row", (e) => e.map((r) => [r.querySelector("[data-claim]").textContent.trim(), r.querySelector("[data-share]").textContent.trim()]));
    check('buttons say "Make the old memories mine" and "Share all of their memories"', labels.every((l) => l[0] === "Make the old memories mine" && l[1] === "Share all of their memories"), JSON.stringify(labels[0]));
    const aria = await page.$eval("[data-share='" + alice.person_id + "']", (e) => e.getAttribute("aria-label"));
    check("each button names the person for a screen reader", /Share all of their memories/.test(aria) && /QA Alice/.test(aria), aria);

    const before = { shared: (await mems("default")).length, alice: (await mems("person:" + alice.person_id)).length, bob: (await mems("person:" + bob.person_id)).length };

    /* Share: the question says ALL, and "No" moves nothing */
    let asked = nextDialog(page, false);
    await page.click("[data-share='" + alice.person_id + "']");
    let msg = await asked;
    check("Share asks first, and says it moves ALL of their memories", /ALL of QA Alice's memories/.test(msg) && /everyone/i.test(msg), msg.replace(/\n/g, " / "));
    await sleep(500);
    check("answering No moves nothing", (await mems("person:" + alice.person_id)).length === before.alice);
    asked = nextDialog(page, true);
    await page.click("[data-share='" + alice.person_id + "']");
    await asked;
    const moved1 = await until(async () => (await mems("person:" + alice.person_id)).length === 0);
    const afterShare = (await mems("default")).length;
    check("answering Yes shares them all", moved1 && afterShare === before.shared + before.alice, "shared now " + afterShare + ", expected " + (before.shared + before.alice));
    check("the screen tells you how many moved", /memor/.test(await innerText(page, "#ownHint")), await innerText(page, "#ownHint"));

    /* Claim: the old memories become Bob's */
    asked = nextDialog(page, false);
    await page.click("[data-claim='" + bob.person_id + "']");
    msg = await asked;
    check("Claim asks first, and names who gets them", /QA Bob's own/.test(msg), msg.replace(/\n/g, " / "));
    asked = nextDialog(page, true);
    await page.click("[data-claim='" + bob.person_id + "']");
    await asked;
    const moved2 = await until(async () => (await mems("default")).length === 0);
    const bobNow = (await mems("person:" + bob.person_id)).length;
    check("answering Yes gives the old memories to Bob", moved2 && bobNow === before.bob + afterShare, "Bob has " + bobNow + ", expected " + (before.bob + afterShare));
    check('memories saved as "shared" stay shared', (await mems("shared")).length === 1);

    await shot(page, "identity-desktop");
    await axeRun(page, "Identity (desktop)");
    await ctx.close();
  });

  /* ------------------------------------------------------------------ Agents */
  await section("Agents screen: reminders and calendars", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP);
    await setWho(page, alice);
    await go(page, "agents");

    /* a reminder */
    await page.click("#addReminder");
    await page.waitForSelector("#remindDlg[open]", { timeout: 8000 });
    check("the Remind me form opens with the cursor in the first box", (await page.evaluate(() => document.activeElement.id)) === "remindWhat");
    check('the choice is labelled "For"', (await page.$eval("label[for=remindFor]", (e) => e.textContent.trim())) === "For");
    const forOptions = await options(page, "#remindFor");
    check("For has Everyone, then each person", forOptions.length === 3 && forOptions[0].label === "Everyone" && forOptions[0].value === "", JSON.stringify(forOptions));
    check("For starts on the person who is here", (await valueOf(page, "#remindFor")) === alice.person_id, await valueOf(page, "#remindFor"));
    await page.click("#remindForm button[type=submit]");
    check("an empty reminder is refused inside the form", /Write what/.test(await innerText(page, "#remindError")) && (await page.$("#remindDlg[open]")) !== null);
    await page.type("#remindWhat", "QA remind Bob to call the dentist");
    await page.$eval("#remindWhen", (e) => { e.value = "someday maybe"; });
    await page.click("#remindForm button[type=submit]");
    check("a time she cannot read is refused inside the form", /could not understand that time/.test(await innerText(page, "#remindError")));
    await page.$eval("#remindWhen", (e) => { e.value = "in 10 minutes"; });
    await page.select("#remindFor", bob.person_id);
    await page.click("#remindForm button[type=submit]");
    const bobJob = await until(async () => (await jobs()).find((j) => String(j.prompt).startsWith("[reminder:" + bob.person_id + "] QA remind Bob")));
    check('a reminder for Bob is saved as "[reminder:<Bob id>] text"', !!bobJob, JSON.stringify((await jobs()).map((j) => j.prompt)));
    check("the form closes and the message names Bob", await until(async () => (await page.$("#remindDlg[open]")) === null && (await toasts(page)).some((t) => /remind QA Bob/.test(t)), 6000), JSON.stringify(await toasts(page)));
    await page.click("#addReminder");
    await page.waitForSelector("#remindDlg[open]");
    await page.type("#remindWhat", "QA remind everyone about the bins");
    await page.select("#remindFor", "");
    await page.click("#remindForm button[type=submit]");
    check('a reminder for Everyone stays "[reminder] text"', !!(await until(async () => (await jobs()).find((j) => j.prompt === "[reminder] QA remind everyone about the bins"))));
    await until(() => page.evaluate(() => /For QA Bob/.test(document.querySelector("#routineList").innerText) && /For everyone/.test(document.querySelector("#routineList").innerText)));
    const rl = await innerText(page, "#routineList");
    check('the list shows "For QA Bob" and "For everyone", and never the raw marker', /For QA Bob/.test(rl) && /For everyone/.test(rl) && !/\[reminder/.test(rl), rl.slice(0, 300));

    /* a calendar */
    await page.click("#addCalendar");
    await page.waitForSelector("#calDlg[open]", { timeout: 8000 });
    check('the calendar choice is labelled "Whose calendar?"', (await page.$eval("label[for=calWhose]", (e) => e.textContent.trim())) === "Whose calendar?");
    const calOptions = await options(page, "#calWhose");
    check("Whose calendar? has Everyone's (shared), then each person", calOptions.length === 3 && calOptions[0].value === "", JSON.stringify(calOptions));
    check("it starts on the person who is here", (await valueOf(page, "#calWhose")) === alice.person_id);
    await page.click("#calForm button[type=submit]");
    check("an empty link is refused inside the form", /Paste your calendar/.test(await innerText(page, "#calError")));
    await page.type("#calUrl", "https://calendar.example.invalid/private/qa-secret-link-0451.ics");
    await page.click("#calForm button[type=submit]");
    const aliceFeed = await until(async () => (await feeds()).find((f) => f.owner === alice.person_id));
    check("the calendar is saved as Alice's", !!aliceFeed, JSON.stringify(await feeds()));
    await until(() => page.evaluate(() => document.querySelector("[data-cal-owner]") !== null));
    check("the form closes when the calendar is added", await until(() => page.evaluate(() => !document.querySelector("#calDlg").open), 8000));
    check("the link box is empty after closing (the link is a secret)", (await valueOf(page, "#calUrl")) === "");
    check("each calendar has a Whose calendar? choice set to Alice", (await valueOf(page, "[data-cal-owner]")) === alice.person_id);
    const cl = await innerText(page, "#calendarList");
    check("the events say whose they are", /QA Alice/.test(cl) && /QA Dentist/.test(cl), cl.slice(0, 300));

    await page.select("[data-cal-owner]", bob.person_id);
    check("changing it in the list makes it Bob's", !!(await until(async () => (await feeds()).find((f) => f.owner === bob.person_id))));
    await sleep(600);
    await page.select("[data-cal-owner]", "");
    check("changing it to Everyone makes it shared", !!(await until(async () => (await feeds()).every((f) => f.owner === ""))));
    await until(() => page.evaluate(() => document.querySelector("[data-cal-owner]").value === ""));
    await sleep(2500);   // let the page finish drawing the new state before we start watching it

    /* the lists are not redrawn while you use them (they refresh every 5 seconds) */
    await page.evaluate(() => { const s = document.querySelector("[data-cal-owner]"); s.__qa = 1; s.focus(); });
    await sleep(7000);
    check("a choice in the list is not wiped out by the 5-second refresh", await page.evaluate(() => { const s = document.querySelector("[data-cal-owner]"); return !!s && s.__qa === 1 && document.activeElement === s; }));

    const everywhere = await page.evaluate(() => document.documentElement.outerHTML + " " + document.body.innerText + " " + JSON.stringify(localStorage) + " " + JSON.stringify(sessionStorage));
    check("the secret calendar link is not left anywhere in the page", !/qa-secret-link-0451/.test(everywhere));

    await shot(page, "agents-desktop");
    await axeRun(page, "Agents (desktop)");
    await page.click("#addReminder");
    await page.waitForSelector("#remindDlg[open]");
    await axeRun(page, "Remind me form (desktop)");
    await page.keyboard.press("Escape");
    await sleep(300);
    check("Escape closes the form", (await page.$("#remindDlg[open]")) === null);
    await page.click("#addCalendar");
    await page.waitForSelector("#calDlg[open]");
    await axeRun(page, "Add a calendar form (desktop)");
    await page.keyboard.press("Escape");
    await ctx.close();
  });

  /* ----------------------------------------------------------------- Notices */
  await section("Private reminder notices", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP);
    await go(page, "home");
    const due = (who, secret) => api("POST", "/v1/v5/schedules", { name: "Reminder: QA notice", prompt: (who ? "[reminder:" + who.person_id + "] " : "[reminder] ") + secret, next_run: new Date(Date.now() + 1500).toISOString().replace(/\.\d{3}Z$/, "+00:00") });
    const arrived = (title, secret) => until(async () => ((await api("GET", "/v1/v5/notifications")).notifications || []).some((n) => n.title === title && String(n.body).includes(secret)), 20000, 500);
    const leaksIn = async (pg, secret) => {
      const all = await pg.evaluate(() => document.documentElement.outerHTML + " " + document.body.innerText + " " + JSON.stringify(localStorage) + " " + JSON.stringify(sessionStorage));
      return all.includes(secret) || (await toasts(pg)).join(" ").includes(secret) || (await spoken(pg)).join(" ").includes(secret);
    };
    const leaks = (secret) => leaksIn(page, secret);
    const wait = async (re) => until(async () => (await toasts(page)).some((t) => re.test(t)), 9000, 150);

    /* Bob is here; the reminder is Alice's */
    await setWho(page, bob);
    await due(alice, "QA-SECRET-ALICE-1111 parcel at the door");
    check("the server made a notice titled Reminder for QA Alice", await arrived("Reminder for QA Alice", "QA-SECRET-ALICE-1111"));
    await setWho(page, bob);                        // a change of Who is here makes the page look again
    check('Bob sees only "A private reminder for QA Alice is due"', await wait(/^A private reminder for QA Alice is due$/), JSON.stringify(await toasts(page)));
    await sleep(1500);
    check("the reminder text is nowhere on the screen, in storage, or spoken", !(await leaks("QA-SECRET-ALICE-1111")));
    check("nothing is spoken for a private reminder that is not yours", (await spoken(page)).length === 0, JSON.stringify(await spoken(page)));
    await go(page, "activity");
    check("Activity shows the private line, not the text", !/QA-SECRET-ALICE-1111/.test(await page.evaluate(() => document.body.innerText)) && /private reminder for QA Alice/i.test(await page.evaluate(() => document.body.innerText)));

    /* a guest */
    const count = async () => (await toasts(page)).filter((t) => /private reminder for QA Alice/.test(t)).length;
    const was = await count();
    await guestOn(page);
    await sleep(1800);
    check("a guest still does not get the text, and the line is not repeated", !(await leaks("QA-SECRET-ALICE-1111")) && (await count()) === was, "lines: " + (await count()));

    /* Alice arrives: she gets it in full, shown and spoken */
    await setWho(page, alice);
    check("when Alice is here the full reminder is shown", await wait(/Reminder for QA Alice: QA-SECRET-ALICE-1111 parcel at the door/), JSON.stringify(await toasts(page)));
    check("and spoken", (await spoken(page)).some((t) => /QA-SECRET-ALICE-1111/.test(t)), JSON.stringify(await spoken(page)));

    /* Bob's reminder, Alice here: held back, then shown when Bob comes */
    await due(bob, "QA-SECRET-BOB-2222 call the plumber");
    check("the server made a notice titled Reminder for QA Bob", await arrived("Reminder for QA Bob", "QA-SECRET-BOB-2222"));
    await setWho(page, alice);
    check("Alice sees only that a private reminder for Bob is due", await wait(/^A private reminder for QA Bob is due$/));
    check("Bob's text is not on the screen or spoken while Alice is here", !(await leaks("QA-SECRET-BOB-2222")));
    await setWho(page, bob);
    check("it is not lost: Bob gets it in full when he is here", await wait(/Reminder for QA Bob: QA-SECRET-BOB-2222 call the plumber/));

    /* a reminder for everyone reaches a guest; with nobody set, a private one shows in full */
    await guestOn(page);
    await due(null, "QA-EVERYONE-3333 the bins go out");
    await arrived("Reminder", "QA-EVERYONE-3333");
    await guestOn(page);                            // a change of Who is here makes the page look again
    check("a reminder for everyone is shown to a guest", await wait(/QA-EVERYONE-3333/), JSON.stringify(await toasts(page)));
    await nobody(page);
    await due(alice, "QA-SECRET-ALICE-4444 pay the water bill");
    await arrived("Reminder for QA Alice", "QA-SECRET-ALICE-4444");
    await nobody(page);
    check("with nobody set, a private reminder is shown in full", await wait(/QA-SECRET-ALICE-4444/));
    await ctx.close();

    /* many notices waiting: the first look shows at most 3 messages, full and private together */
    for (let i = 1; i <= 3; i++) { await due(alice, "QA-SECRET-FLOOD-ALICE-" + i); await due(bob, "QA-FLOOD-BOB-" + i); }
    check("six more reminders were made", await arrived("Reminder for QA Alice", "QA-SECRET-FLOOD-ALICE-3") && await arrived("Reminder for QA Bob", "QA-FLOOD-BOB-3"));
    const flood = await openPage(browser, DESKTOP, "light", bob);
    await sleep(4500);
    const shown = (await toasts(flood.page)).filter((t) => /reminder/i.test(t));
    check("a first look shows at most 3 notices in total, however many wait", shown.length >= 1 && shown.length <= 3, shown.length + ": " + JSON.stringify(shown.map((t) => t.slice(0, 50))));
    check("and none of Alice's reminder text is among them", !shown.join(" ").includes("QA-SECRET"), JSON.stringify(shown));
    await flood.ctx.close();

    /* crafted notices: the page is given a list, so each rule is checked exactly */
    const crafted = await openPage(browser, DESKTOP, "light", bob, true);
    await sleep(1500);                                  // the first look finds nothing
    const note = (id, title, body) => ({ notification_id: id, title, body, severity: "info", read: false });
    crafted.fake.list = [
      note("c7", "Reminder for QA Alice", "QA-CRAFT-ALICE-3 text"), note("c6", "Reminder for QA Alice", "QA-CRAFT-ALICE-2 text"),
      note("c5", "Reminder for QA Alice", "QA-CRAFT-ALICE-1 text"), note("c4", "Reminder for QA Bob", "QA-CRAFT-BOB call"),
      note("c3", "Reminder for someone", "QA-CRAFT-UNKNOWN text"), note("c2", "Garden check", "QA-CRAFT-PLAIN all fine"),
    ];
    await setWho(crafted.page, bob);
    await until(async () => (await toasts(crafted.page)).some((t) => /QA-CRAFT-PLAIN/.test(t)), 6000);
    const t1 = await toasts(crafted.page);
    check("several private reminders for one person are one line", t1.filter((t) => /private reminders? for QA Alice/.test(t)).length === 1 && t1.includes("3 private reminders for QA Alice are due"), JSON.stringify(t1));
    check("Bob's own reminder is shown in full, and spoken", t1.some((t) => /Reminder for QA Bob: QA-CRAFT-BOB call/.test(t)) && (await spoken(crafted.page)).some((t) => /QA-CRAFT-BOB call/.test(t)), JSON.stringify(await spoken(crafted.page)));
    check("a reminder for an owner she cannot name stays private unless nobody is set", t1.includes("A private reminder for someone is due") && !t1.join(" ").includes("QA-CRAFT-UNKNOWN"), JSON.stringify(t1));
    check("an ordinary notice is shown to Bob as usual", t1.some((t) => /Garden check/.test(t)));
    check("the held text is nowhere: not on the screen, in storage, or spoken", !(await leaksIn(crafted.page, "QA-CRAFT-ALICE")) && !(await leaksIn(crafted.page, "QA-CRAFT-UNKNOWN")));
    await nobody(crafted.page);
    await until(async () => (await toasts(crafted.page)).some((t) => /QA-CRAFT-UNKNOWN/.test(t)), 6000);
    const t2 = await toasts(crafted.page);
    check("with nobody set, the held reminders are shown in full, once each", [1, 2, 3].every((i) => t2.filter((t) => t.includes("QA-CRAFT-ALICE-" + i)).length === 1) && t2.filter((t) => t.includes("QA-CRAFT-UNKNOWN")).length === 1, JSON.stringify(t2));
    await crafted.ctx.close();
  });

  /* ------------------------------------------------------- Fake microphone */
  await section("Fake microphone and Voice ID", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP);
    const level = await page.evaluate(async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ac = new AudioContext(), an = ac.createAnalyser();
      an.fftSize = 2048; ac.createMediaStreamSource(stream).connect(an);
      const buf = new Float32Array(an.fftSize); let peak = 0; const t0 = performance.now();
      while (performance.now() - t0 < 1500) { an.getFloatTimeDomainData(buf); for (const v of buf) peak = Math.max(peak, Math.abs(v)); await new Promise((r) => setTimeout(r, 50)); }
      stream.getTracks().forEach((t) => t.stop()); await ac.close();
      return peak;
    });
    check("the page hears the fake microphone file", level > 0.004, "peak " + level);

    await go(page, "identity");
    await page.click("#voiceCheck");
    const said = await until(async () => {
      const t = await innerText(page, "#voicePrompt");
      return t && !/^Say anything|^Checking|^Opening|^Starting/.test(t) ? t : false;
    }, 90000, 500);
    console.log("     (Voice ID said: " + String(said).slice(0, 140) + ")");
    const noSound = /heard no sound/i.test(said || "");
    const modelProblem = /download|model|network|connect|offline|reach/i.test(said || "");
    if (said && modelProblem && !noSound) console.log("SKIP Voice ID answer from the server needs the voice model, which could not be loaded here: " + String(said).slice(0, 160));
    else check("Voice ID: the recording is sent and the server answers (not 'no sound')", !!said && !noSound, said);
    await ctx.close();
  });

  /* --------------------------------------------- Voice check while she listens */
  await section("Voice check while she listens", async () => {
    carol = carol || (await makePerson("QA Carol"));
    const { page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]);
    const kit = await watchVoice(page, voicePeople());
    const state = () => page.evaluate(() => IRAS.autoid.state());
    const idle = () => until(async () => !(await state()).asking, 12000, 100);
    const said = () => toasts(page);

    const s0 = await state();
    check("the voice check is on by itself on a computer, and it can work here", s0.enabled === true && s0.available.ok === true, JSON.stringify(s0.available));

    /* a clear match */
    await nobody(page);
    let t = await voiceTurn(page, kit, { answer: answerFor("match", alice, 0.83) });
    const wav = parseWav(t.verify && t.verify.audio);
    check("she asks the server while you talk, and the chat is not held up for long", !!t.sent && t.asked === 1 && t.waited < 2500, JSON.stringify({ sent: !!t.sent, asked: t.asked, waited: t.waited }));
    check("the recording is a small 16 kHz mono WAV with real sound in it", !!wav && wav.ch === 1 && wav.rate === 16000 && wav.bits === 16 && wav.seconds >= 1.8 && wav.seconds < 4.5 && wav.peak > 0.05, JSON.stringify(wav));
    check("it is sent with the access token", !!t.verify && t.verify._auth === true);
    await until(async () => ((await whoNow(page)) || {}).id === alice.person_id, 4000);
    let w = await whoNow(page);
    check("a clear match sets Who is here to that person, by voice", !!w && w.kind === "person" && w.id === alice.person_id && w.via === "voice", JSON.stringify(w));
    check("the chat that followed already carried that person and the score", !!t.chat && !!t.chat.speaker && t.chat.speaker.person_id === alice.person_id && t.chat.speaker.via === "voice" && t.chat.speaker.score === 0.83, JSON.stringify(t.chat && t.chat.speaker));
    check("a message says she knows the voice", (await said()).some((x) => /I know your voice, QA Alice/.test(x)));
    check("the pill shows the name and the word voice", /QA Alice\s*voice/.test(await page.$eval("[data-who] .who-pill", (e) => e.innerText.replace(/\s+/g, " ").trim())));
    check("the microphone is let go and the header chip is back", await page.evaluate(() => window.__streams.length === 1 && window.__streams.every((s) => s.getTracks().every((x) => x.readyState === "ended")) && (typeof S === "undefined" || S.mic === "off")));
    check("Activity has a line that says what she heard", await page.evaluate(() => { const r = IRAS.audit.items.find((i) => i.title === "Checked who is speaking"); return !!r && /QA Alice/.test(r.detail) && /83%/.test(r.detail); }));

    /* a long talk: she asks before you stop */
    t = await voiceTurn(page, kit, { answer: answerFor("match", alice, 0.8), talkMs: 4800 });
    check("in a longer talk she asks once while you are still talking, and not again at the end", t.whileTalking === 1 && t.asked === 1, JSON.stringify({ whileTalking: t.whileTalking, asked: t.asked }));
    check("when the answer is already there, the chat goes out at once", !!t.sent && t.waited < 1200, t.waited);

    /* another person */
    t = await voiceTurn(page, kit, { answer: answerFor("match", bob, 0.77) });
    w = await whoNow(page);
    check("another person's voice switches Who is here before the reply is made", !!w && w.id === bob.person_id && w.via === "voice" && !!t.chat.speaker && t.chat.speaker.person_id === bob.person_id, JSON.stringify({ w, speaker: t.chat && t.chat.speaker }));
    check("and she says so", (await said()).some((x) => /I hear QA Bob now, not QA Alice/.test(x)));

    /* "nobody I know" */
    t = await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    w = await whoNow(page);
    let st = await state();
    check("one \"nobody I know\" changes nothing (someone else may just be talking)", !!w && w.id === bob.person_id && st.strikes === 1 && !!t.chat.speaker && t.chat.speaker.person_id === bob.person_id, JSON.stringify({ w, strikes: st.strikes }));
    t = await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    w = await whoNow(page);
    check("two in a row make her stop using the name", w === null, JSON.stringify(w));
    check("...before the reply is made: that chat goes out with no name", !!t.sent && t.chat.speaker === undefined, JSON.stringify(t.chat && t.chat.speaker));
    check("...and she says why", (await said()).some((x) => /did not sound like QA Bob, twice in a row/.test(x)));

    await setWho(page, carol);   // her face is known, her voice is not
    await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    w = await whoNow(page);
    check("a person whose voice she never learned is not dropped because of a strange voice", !!w && w.id === carol.person_id, JSON.stringify(w));

    await setWho(page, alice);
    await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    await voiceTurn(page, kit, { answer: answerFor("match", alice, 0.8) });
    await voiceTurn(page, kit, { answer: answerFor("other", bob) });
    w = await whoNow(page);
    st = await state();
    check("a match in between starts the count again", !!w && w.id === alice.person_id && st.strikes === 1, JSON.stringify({ w, strikes: st.strikes }));

    await voiceTurn(page, kit, { answer: answerFor("unsure", alice) });
    await voiceTurn(page, kit, { answer: answerFor("unheard") });
    w = await whoNow(page);
    check("\"not sure\" and \"too little speech\" change nothing", !!w && w.id === alice.person_id, JSON.stringify(w));

    const older = answerFor("match", bob, 0.7); delete older.verdict;   // an older server does not say the word
    await voiceTurn(page, kit, { answer: older });
    w = await whoNow(page);
    check("an answer from an older server (no verdict word) still works", !!w && w.id === bob.person_id, JSON.stringify(w));

    await setWho(page, alice);
    t = await voiceTurn(page, kit, { talkMs: 4800, answers: [{ body: answerFor("unheard") }, { body: answerFor("match", bob, 0.7) }] });
    w = await whoNow(page);
    check("if the early clip had too little speech, she asks once more at the end", t.whileTalking === 1 && t.asked === 2 && !!w && w.id === bob.person_id, JSON.stringify({ whileTalking: t.whileTalking, asked: t.asked, w }));

    /* guest mode */
    await guestOn(page);
    t = await voiceTurn(page, kit, { answer: answerFor("match", alice, 0.9) });
    w = await whoNow(page);
    check("in guest mode she does not even record, and a voice never ends guest mode", !!t.sent && t.asked === 0 && t.gum === 0 && !!w && w.kind === "guest", JSON.stringify({ asked: t.asked, gum: t.gum, w }));
    await nobody(page);

    /* a slow server */
    t = await voiceTurn(page, kit, { answer: answerFor("match", alice, 0.8), delay: 5000 });
    w = await whoNow(page);
    check("a slow server holds her up for about 2 seconds at most", !!t.sent && t.waited >= 1500 && t.waited < 2900, t.waited);
    check("the chat that went out did not wait for the answer", w === null && t.chat.speaker === undefined, JSON.stringify({ w, speaker: t.chat && t.chat.speaker }));
    check("when the slow answer comes, it is used for the next turn", !!(await until(async () => ((await whoNow(page)) || {}).id === alice.person_id, 9000)));

    await idle();
    await nobody(page);
    await voiceTurn(page, kit, { answer: answerFor("match", bob, 0.8), delay: 4000 });
    await setWho(page, carol);   // you pick someone while the check is still out
    await idle();
    w = await whoNow(page);
    check("if you pick a person while the check is out, your choice is kept", !!w && w.id === carol.person_id && w.via === "chosen", JSON.stringify(w));

    /* Stop while she is checking */
    kit.plan.verify.length = 0; kit.plan.verify.push({ body: answerFor("match", alice, 0.8), delay: 4000 });
    await settleUi(page);
    const before = kit.seen.chat.length;
    await page.evaluate(() => IRAS.voice.toggle());
    await sleep(2600);
    await page.evaluate(() => { window.__sr.last.say("stop this one"); window.__sr.last.stop(); });
    await sleep(300);
    await page.evaluate(() => IRAS.stopAll());
    await sleep(3000);
    check("if you press Stop while she is checking, nothing is sent", kit.seen.chat.length === before, kit.seen.chat.length - before);
    await idle();

    check("no microphone is left open at the end", await page.evaluate(() => window.__streams.every((s) => s.getTracks().every((x) => x.readyState === "ended")) && !IRAS.autoid.state().recording));
    await ctx.close();
  });

  await section("Voice check: the switch in Settings", async () => {
    carol = carol || (await makePerson("QA Carol"));
    const { page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]);
    const kit = await watchVoice(page, voicePeople());
    await go(page, "settings");
    const row = await page.$eval("#setAutoWho", (e) => ({ checked: e.checked, hint: document.querySelector("#autoWhoHint").textContent }));
    check("Settings has the switch, on, with a plain sentence", row.checked === true && /While you talk to her, she checks whose voice it is/.test(row.hint), JSON.stringify(row));
    await axeRun(page, "Settings (desktop)");
    await page.evaluate(() => document.querySelector("#setAutoWho").click());
    const off = await page.evaluate(() => ({ v: IRAS.settings.autoWho, hint: document.querySelector("#autoWhoHint").textContent, checked: document.querySelector("#setAutoWho").checked }));
    check("turning it off is saved and the sentence says so", off.v === false && off.checked === false && /^Off\./.test(off.hint), JSON.stringify(off));
    const t = await voiceTurn(page, kit, { answer: answerFor("match", alice) });
    check("with the switch off she does not record or ask", !!t.sent && t.asked === 0 && t.gum === 0, JSON.stringify({ asked: t.asked, gum: t.gum }));
    await page.evaluate(() => document.querySelector("#setAutoWho").click());
    const on = await page.evaluate(() => ({ v: IRAS.settings.autoWho, hint: document.querySelector("#autoWhoHint").textContent }));
    check("turning it on again works", on.v === true && /^On\./.test(on.hint), JSON.stringify(on));
    await ctx.close();
  });

  await section("Voice check: nobody has a taught voice", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]);
    const kit = await watchVoice(page, [{ person_id: alice.person_id, name: alice.name, faces: 1, voices: 0 }]);
    const t = await voiceTurn(page, kit, { answer: answerFor("match", alice) });
    check("with no taught voice she does not record, and the chat is not held up", !!t.sent && t.asked === 0 && t.gum === 0 && t.waited < 1000, JSON.stringify({ asked: t.asked, gum: t.gum, waited: t.waited }));
    check("the sentence says to teach a voice first", /Teach her a voice/.test(await page.evaluate(() => IRAS.autoid.hint())));
    await ctx.close();
  });

  await section("Voice check: a microphone that cannot be shared", async () => {
    carol = carol || (await makePerson("QA Carol"));
    /* a microphone that gives no sound */
    let { page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]);
    let kit = await watchVoice(page, voicePeople());
    await page.evaluate(() => { window.__mic = "silent"; });
    let t1 = await voiceTurn(page, kit, {}), t2 = await voiceTurn(page, kit, {});
    let st = await page.evaluate(() => IRAS.autoid.state());
    check("a microphone that gives no sound twice in a row turns the check off, and she says so", !!t1.sent && !!t2.sent && !!st.off && (await toasts(page)).some((x) => /turned the voice check off/.test(x)), JSON.stringify({ off: st.off }));
    check("...and voice chat itself is not held up", t1.waited < 1000 && t2.waited < 1000, JSON.stringify([t1.waited, t2.waited]));
    const t3 = await voiceTurn(page, kit, {});
    check("...and she stops trying", t3.gum === 0, t3.gum);
    check("the sentence in Settings says it cannot work now", /cannot work now/.test(await page.evaluate(() => IRAS.autoid.hint())));
    await ctx.close();

    /* a microphone that speech recognition holds alone */
    ({ page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]));
    kit = await watchVoice(page, voicePeople());
    await page.evaluate(() => { window.__mic = "busy"; });
    t1 = await voiceTurn(page, kit, {}); t2 = await voiceTurn(page, kit, {});
    st = await page.evaluate(() => IRAS.autoid.state());
    check("a microphone that cannot be shared turns the check off after two tries", !!t1.sent && !!t2.sent && /cannot be shared with speech recognition/.test(st.off), JSON.stringify({ off: st.off }));
    check("...and voice chat itself is not held up", t1.waited < 1000 && t2.waited < 1000, JSON.stringify([t1.waited, t2.waited]));
    await ctx.close();

    /* listening stops while the check records */
    ({ page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech]));
    kit = await watchVoice(page, voicePeople());
    await page.evaluate(() => IRAS.voice.toggle());
    await until(async () => (await page.evaluate(() => IRAS.autoid.state())).streaming, 8000);
    await page.evaluate(() => window.__sr.last.onerror({ error: "audio-capture" }));
    st = await page.evaluate(() => IRAS.autoid.state());
    check("if listening fails while the check records, the check turns itself off and lets go of the microphone", !!st.off && st.recording === false && await page.evaluate(() => window.__streams.every((s) => s.getTracks().every((x) => x.readyState === "ended"))), JSON.stringify({ off: st.off, recording: st.recording }));
    await page.evaluate(() => window.__sr.last.stop());
    await settleUi(page);
    await ctx.close();
  });

  await section("Voice check: the Android app", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP, "light", null, false, [watchedMic, fakeSpeech, androidApp]);
    const a = await page.evaluate(() => IRAS.autoid.available());
    check("inside the Android app the check says it cannot work, and why", a.ok === false && /Android app/.test(a.why) && /phone's own speech recognizer/.test(a.why), JSON.stringify(a));
    await page.evaluate(() => IRAS.voice.toggle());   // the app's own listening starts; the page records nothing
    await sleep(800);
    check("the page opens no microphone of its own in the app", (await page.evaluate(() => window.__gum)) === 0);
    check("the sentence in Settings says so", /cannot work now/.test(await page.evaluate(() => IRAS.autoid.hint())));
    await ctx.close();
  });

  await section("Voice check: a phone browser", async () => {
    const { page, ctx } = await openPage(browser, PHONES[0], "light", null, false, [watchedMic, fakeSpeech, phoneBrowser]);
    const s = await page.evaluate(() => ({ on: IRAS.autoid.enabled(), setting: IRAS.settings.autoWho, hint: IRAS.autoid.hint() }));
    check("in a phone's browser the check starts off (on some phones listening and recording together do not work)", s.on === false && s.setting === null && /^Off\./.test(s.hint), JSON.stringify(s));
    await go(page, "settings");
    await page.$eval("#setAutoWho", (e) => e.scrollIntoView({ block: "center" }));
    check("360 px Settings: nothing sticks out sideways", await noSideways(page));
    check("360 px Settings: the switch is inside the screen and shows off", await page.$eval("#setAutoWho", (e) => { const r = e.closest(".switch").getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1 && !e.checked; }));
    await axeRun(page, "Settings (360px)");
    await page.evaluate(() => document.querySelector("#setAutoWho").click());
    check("a person can switch it on", await page.evaluate(() => IRAS.autoid.enabled() === true && IRAS.settings.autoWho === true));
    await ctx.close();
  });

  /* ------------------------------------------------------------ Phone widths */
  for (const size of PHONES) {
    await section("Phone " + size.width + " px wide", async () => {
      const { page, ctx } = await openPage(browser, size);
      await setWho(page, alice);
      const tag = size.width + "px";

      await go(page, "memory");
      await page.evaluate(() => document.querySelector("input[name='memView'][value='list']").click());
      await sleep(400);
      check(tag + " Memory: nothing sticks out sideways", await noSideways(page));
      check(tag + " Memory: the Show choice is inside the screen", await insideScreen(page, "#memFilter").catch(() => false) || await page.$eval("#memFilter", (e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1; }));
      await page.$eval("#memNew", (e) => e.scrollIntoView({ block: "center" }));
      check(tag + " Memory: Whose memory? is inside the screen", await page.$eval("#memWhose", (e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1; }));
      await shot(page, "memory-" + tag);
      await axeRun(page, "Memory list (" + tag + ")");

      await go(page, "identity");
      await until(() => page.$$eval("#ownList .own-row", (e) => e.length >= 2));
      check(tag + " Identity: nothing sticks out sideways", await noSideways(page));
      check(tag + " Identity: both buttons of every person are inside the screen", await page.$$eval("#ownList button", (bs) => bs.every((b) => { const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1; })));
      await page.$eval("#ownCard", (e) => e.scrollIntoView({ block: "start" }));
      await shot(page, "identity-" + tag);
      await axeRun(page, "Identity (" + tag + ")");

      await go(page, "agents");
      await until(() => page.evaluate(() => document.querySelector("[data-cal-owner]") !== null || true));
      check(tag + " Agents: nothing sticks out sideways", await noSideways(page));
      await tap(page, "#addReminder");
      await page.waitForSelector("#remindDlg[open]");
      check(tag + " Remind me form fits the screen", await insideScreen(page, "#remindDlg"));
      await shot(page, "remind-" + tag);
      await axeRun(page, "Remind me form (" + tag + ")");
      await page.keyboard.press("Escape");
      await tap(page, "#addCalendar");
      await page.waitForSelector("#calDlg[open]");
      check(tag + " Add a calendar form fits the screen", await insideScreen(page, "#calDlg"));
      await shot(page, "calendar-" + tag);
      await page.keyboard.press("Escape");
      await sleep(200);
      await axeRun(page, "Agents (" + tag + ")");
      await ctx.close();
    });
  }

  /* ----------------------------------------------- the other look: dark ---- */
  await section("Dark look", async () => {
    const { page, ctx } = await openPage(browser, DESKTOP, "dark");
    await go(page, "memory");
    await page.evaluate(() => document.querySelector("input[name='memView'][value='list']").click());
    await sleep(500);
    await axeRun(page, "Memory list (dark)");
    await go(page, "identity");
    await until(() => page.$$eval("#ownList .own-row", (e) => e.length >= 2));
    await axeRun(page, "Identity (dark)");
    await go(page, "agents");
    await page.click("#addReminder");
    await page.waitForSelector("#remindDlg[open]");
    await axeRun(page, "Remind me form (dark)");
    await shot(page, "remind-dark");
    await ctx.close();
  });

  /* ---------------------------------------------------------------- the end */
  await cleanup();
  await browser.close();

  const errors = pageProblems.filter((p, i, a) => a.indexOf(p) === i);
  const real = errors.filter((p) => /^page error/.test(p));
  check("no uncaught errors in the page", real.length === 0, real.join(" | "));
  if (errors.length) console.log("\nConsole messages from the page (" + errors.length + "):\n  " + errors.slice(0, 12).map((e) => e.slice(0, 200)).join("\n  "));

  const failed = results.filter((r) => !r.ok);
  console.log("\n" + (results.length - failed.length) + " of " + results.length + " checks passed." + (failed.length ? " FAILED: " + failed.map((f) => f.name).join("; ") : ""));
  process.exit(failed.length ? 1 : 0);
})().catch(async (e) => { console.error("The test could not run: " + (e && e.message || e)); try { await cleanup(); } catch (x) { /* ignore */ } process.exit(2); });
