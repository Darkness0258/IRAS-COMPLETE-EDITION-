/* ==========================================================================
   Who is here: which person is talking to her right now.

   It is a hint for how she talks: a name, or extra care when a guest is here.
   It is not a login. It never unlocks an approval, and a guest cannot approve anything.

     - Face ID or Voice ID recognises someone: she keeps that for 30 minutes.
     - You can also pick a person by hand, or say that a guest is here.
     - A guest stays until you clear it. She never forgets a guest on her own,
       because that would quietly hand a visitor your private things.

   The chat sends only a person id (or "guest"). The server looks the name up itself,
   and only for a person it already knows.

     IRAS.who.set(person, via, score)   person = { person_id, name }, via = "face" | "voice" | "chosen"
     IRAS.who.guest() / clear() / open() / current() / forChat()
   Emits bus event "who".
   ========================================================================== */
"use strict";

(function () {
  const KEY = "iras-who";               // sessionStorage: this window only
  const HOLD = 30 * 60 * 1000;          // a recognised person is kept this long
  const ICON = { face: "scan-face", voice: "audio-lines", chosen: "user" };
  const HOW = { face: "face", voice: "voice", chosen: "picked" };
  let state = read();
  let people = [];

  function read() {
    try {
      const v = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (!v) return null;
      if (v.kind === "guest") return { kind: "guest", at: Number(v.at) || Date.now() };
      if (v.kind === "person" && v.person_id && Date.now() - Number(v.at || 0) < HOLD) return v;
    } catch (e) { /* a private window may refuse storage */ }
    return null;
  }

  function save() {
    try {
      if (state) sessionStorage.setItem(KEY, JSON.stringify(state));
      else sessionStorage.removeItem(KEY);
    } catch (e) { /* fine: it is only a hint */ }
  }

  function current() {
    if (state && state.kind === "person" && Date.now() - state.at >= HOLD) { state = null; save(); render(); }
    return state;
  }

  function changed() {
    save();
    render();
    bus.emit("who", { kind: state ? state.kind : "none", name: state && state.name ? state.name : "", via: state && state.via ? state.via : "" });
  }

  /* ---------- the pill ---------- */
  function pill() {
    const s = current();
    if (!s) return `<button class="who-pill" type="button" data-who-open aria-haspopup="dialog">${icon("users", "i-sm")}<span>Who is here?</span></button>`;
    if (s.kind === "guest") {
      return `<button class="who-pill is-guest" type="button" data-who-open aria-haspopup="dialog" title="Guest mode. Your private things stay private until you clear it.">${icon("shield", "i-sm")}<span>A guest is here</span></button>`;
    }
    const mins = Math.max(1, Math.ceil((HOLD - (Date.now() - s.at)) / 60000));
    return `<button class="who-pill is-person" type="button" data-who-open aria-haspopup="dialog" title="She remembers this for about ${mins} more minutes." aria-label="Talking as ${esc(s.name)}, ${HOW[s.via] || "picked"}. Change who is here.">${icon(ICON[s.via] || "user", "i-sm")}<span>${esc(s.name)}</span><small>${HOW[s.via] || "picked"}</small></button>`;
  }

  /* Rebuilt only when what it says changes, so a click or the keyboard focus is never lost to a timer.
     The "minutes left" hint is updated in place. */
  let drawn = "";
  function render() {
    const s = current();
    const key = s ? [s.kind, s.person_id || "", s.name || "", s.via || ""].join("|") : "";
    if (key === drawn && $("[data-who] .who-pill")) {
      if (s && s.kind === "person") {
        const mins = Math.max(1, Math.ceil((HOLD - (Date.now() - s.at)) / 60000));
        $$("[data-who] .who-pill").forEach((b) => b.setAttribute("title", "She remembers this for about " + mins + " more minutes."));
      }
      return;
    }
    drawn = key;
    const html = pill();
    $$("[data-who]").forEach((slot) => { slot.innerHTML = html; });
  }

  /* ---------- the question ---------- */
  /* Only the list of people is rebuilt (it arrives a moment after the pop-up opens).
     The three fixed buttons are never replaced, so a quick click is never lost. */
  function drawList(note) {
    const s = current();
    $("#whoPeople").innerHTML = people.map((p) => {
      const on = s && s.kind === "person" && s.person_id === p.person_id;
      return `<li><button class="btn who-opt${on ? " is-on" : ""}" type="button" data-pick="${esc(p.person_id)}" aria-pressed="${!!on}">${icon(on ? "badge-check" : "user", "i-sm")}<span>I am ${esc(p.name)}</span></button></li>`;
    }).join("");
    const guestOn = !!(s && s.kind === "guest");
    $("#whoGuest").classList.toggle("is-on", guestOn);
    $("#whoGuest").setAttribute("aria-pressed", String(guestOn));
    $("#whoNote").textContent = note || "";
  }

  async function open() {
    drawList("Looking for the people she knows…");
    IRAS.openDialog($("#whoDlg"));
    try {
      const r = await IRAS.api("/v1/identity/people");
      people = (r && r.people) || [];
      drawList(people.length ? "" : "She does not know anyone yet. Teach her a face or a voice on the Identity screen.");
    } catch (e) {
      people = [];
      drawList("I could not load the people she knows. " + (e.message || ""));
    }
  }

  function close() { IRAS.closeDialog($("#whoDlg")); }

  /* ---------- changing it ---------- */
  function set(person, via, score) {
    if (!person || !person.person_id) return;
    state = { kind: "person", person_id: String(person.person_id), name: String(person.name || "").slice(0, 60), via: ICON[via] ? via : "chosen", score: clamp(Number(score) || 0, 0, 1), at: Date.now() };
    changed();
  }

  function guest() { state = { kind: "guest", at: Date.now() }; changed(); }
  function clear() { state = null; changed(); }

  /* what the chat sends: an id and how she knew, never the name */
  function forChat() {
    const s = current();
    if (!s) return undefined;
    if (s.kind === "guest") return { guest: true };
    return s.via === "chosen" ? { person_id: s.person_id, via: "chosen" } : { person_id: s.person_id, via: s.via, score: s.score };
  }

  IRAS.who = { current, set, guest, clear, open, forChat };

  IRAS.initWho = function () {
    render();
    document.addEventListener("click", (e) => { if (e.target.closest("[data-who-open]")) open(); });
    $("#whoDlg").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.pick !== undefined) {
        const p = people.find((x) => x.person_id === b.dataset.pick);
        if (p) { set(p, "chosen", 0); close(); toast("Okay. Talking as " + p.name + ".", { icon: "user" }); }
      } else if (b.dataset.guest !== undefined) {
        guest(); close(); toast("Guest mode is on. Your private things stay private. Clear it when they leave.", { icon: "shield", timeout: 6000 });
      } else if (b.dataset.clear !== undefined) {
        clear(); close(); toast("Okay. No one in particular.", { icon: "x" });
      } else if (b.dataset.recognise !== undefined) {
        close(); IRAS.go("identity");
      } else if (b.id === "whoClose") close();
    });
    setInterval(() => { current(); render(); }, 30000);  // a recognised person fades out by itself
  };
})();
