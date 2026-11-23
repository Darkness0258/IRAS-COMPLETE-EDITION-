/* ==========================================================================
   People: the people she knows, for every screen that needs a name.

     GET /v1/identity/people     { people: [{ person_id, name, faces, voices }] }

     IRAS.people.load(force)   Promise of the list. It asks the server at most every 30 seconds.
     IRAS.people.use(rows)     a screen that just asked the server for the people hands the answer in, so the rest are up to date at once
     IRAS.people.all()         the list we have right now
     IRAS.people.name(id)      the name for a person id, or ""
     IRAS.people.known(id)     true when she knows that person
     IRAS.people.voices(id)    how many voice recordings she has of that person (0 when none)
     IRAS.people.withVoice()   how many people have a taught voice
     IRAS.people.here()        the id of the person who is here now (Who is here), or ""
     IRAS.people.options(o)    <option> tags for a select
                               o.first     [[value, label], ...] choices that come before the people
                               o.prefix    put in front of each person id to make the value
                               o.label     (person) => text   (default: the name)
                               o.selected  the value to mark as chosen
   Emits the bus event "people" when the list changes.
   ========================================================================== */
"use strict";

(function () {
  const TTL = 30000;
  let list = [], at = 0, pending = null;

  const same = (a, b) => a.length === b.length && a.every((p, i) => p.person_id === b[i].person_id && p.name === b[i].name && p.voices === b[i].voices);

  function use(rows) {
    const next = (rows || []).map((p) => ({ person_id: String(p.person_id), name: String(p.name || ""), voices: Math.max(0, Number(p.voices) || 0) }));
    at = Date.now();
    if (!same(list, next)) { list = next; bus.emit("people", { count: list.length }); }
    return list;
  }

  function load(force) {
    if (pending) return pending;
    if (!force && at && Date.now() - at < TTL) return Promise.resolve(list);
    pending = IRAS.api("/v1/identity/people")
      .then((r) => use(r && r.people))
      .catch(() => list)   // an older server, or no connection: keep what we had
      .then((l) => { pending = null; return l; });
    return pending;
  }

  const find = (id) => list.find((p) => p.person_id === id) || null;

  function here() {
    const w = IRAS.who && IRAS.who.current();
    return w && w.kind === "person" ? String(w.person_id || "") : "";
  }

  function options(o = {}) {
    const label = o.label || ((p) => p.name);
    const rows = (o.first || []).concat(list.map((p) => [(o.prefix || "") + p.person_id, label(p)]));
    return rows.map(([v, t]) => `<option value="${esc(v)}"${v === o.selected ? " selected" : ""}>${esc(t)}</option>`).join("");
  }

  IRAS.people = {
    load, use, all: () => list, name: (id) => (find(id) || {}).name || "", known: (id) => !!find(id), here, options,
    voices: (id) => (find(id) || {}).voices || 0,
    withVoice: () => list.filter((p) => p.voices > 0).length,
  };
})();
