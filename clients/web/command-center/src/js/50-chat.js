/* ==========================================================================
   Chat: streaming replies, tool chips, small safe markdown, code cards
   ========================================================================== */
"use strict";

(function () {
  const thread = $("#thread");
  const empty = $("#chatEmpty");
  let turn = null;
  let raf = 0;
  const markSrc = () => ($(".rail .mark") || {}).src || "";

  /* ---------- markdown: escape first, then format. Links must be http(s). ---------- */
  function inline(t) {
    return t
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
      .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }
  function codeCard(lang, body) {
    const lines = body.replace(/\n$/, "").split("\n");
    const long = lines.length > 12;
    const html = lines.map((l) => {
      let cls = "ln";
      if (lang === "diff") {
        if (/^\+/.test(l) && !/^\+\+\+/.test(l)) cls += " d-add";
        else if (/^-/.test(l) && !/^---/.test(l)) cls += " d-del";
        else if (/^@@/.test(l)) cls += " d-hunk";
      }
      return `<span class="${cls}">${esc(l) || " "}</span>`;
    }).join("");
    return `<figure class="code-card${long ? " is-long" : ""}"><figcaption><span class="code-lang">${esc(lang || "text")}</span><span class="grow"></span>` +
      `<button type="button" class="btn sm ghost copy-code">${icon("copy", "i-sm")}<span>Copy</span></button>` +
      `<button type="button" class="btn sm ghost expand-code" aria-expanded="false">${icon("maximize-2", "i-sm")}<span>Expand</span></button></figcaption>` +
      `<pre tabindex="0"><code>${html}</code></pre></figure>`;
  }
  function renderMarkdown(src) {
    const lines = String(src).replace(/\r/g, "").split("\n");
    const out = [];
    let i = 0;
    const isBlock = (l) => /^```/.test(l) || /^#{1,4}\s/.test(l) || /^\s*[-*]\s+/.test(l) || /^\s*\d+[.)]\s+/.test(l) || /^>\s?/.test(l);
    while (i < lines.length) {
      const line = lines[i];
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        const body = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) { body.push(lines[i]); i++; }
        i++;
        out.push(codeCard(fence[1], body.join("\n")));
        continue;
      }
      if (/^\s*$/.test(line)) { i++; continue; }
      let m;
      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { const n = m[1].length < 3 ? 3 : 4; out.push(`<h${n}>${inline(esc(m[2]))}</h${n}>`); i++; continue; }
      if (/^\s*[-*]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
        out.push("<ul>" + items.map((t) => `<li>${inline(esc(t))}</li>`).join("") + "</ul>");
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
        out.push("<ol>" + items.map((t) => `<li>${inline(esc(t))}</li>`).join("") + "</ol>");
        continue;
      }
      if (/^>\s?/.test(line)) {
        const q = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, "")); i++; }
        out.push(`<blockquote>${q.map((t) => inline(esc(t))).join("<br>")}</blockquote>`);
        continue;
      }
      const para = [];
      while (i < lines.length && !/^\s*$/.test(lines[i]) && !isBlock(lines[i])) { para.push(lines[i]); i++; }
      out.push("<p>" + para.map((t) => inline(esc(t))).join("<br>") + "</p>");
    }
    return out.join("");
  }
  IRAS.renderMarkdown = renderMarkdown;

  /* ---------- thread helpers ---------- */
  const nearBottom = () => thread.scrollHeight - thread.scrollTop - thread.clientHeight < 140;
  const stick = (force) => { if (force || turn && turn.pinned) thread.scrollTop = thread.scrollHeight; };
  const hideEmpty = () => { if (empty && empty.isConnected) empty.remove(); };

  function addUser(text, via) {
    hideEmpty();
    const el = document.createElement("div");
    el.className = "msg user";
    el.innerHTML = `<div class="bubble"><span class="sr-only">You ${via === "voice" ? "said" : "wrote"}: </span>${esc(text)}</div>`;
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
  }

  function startTurn() {
    hideEmpty();
    const el = document.createElement("div");
    el.className = "msg assistant is-streaming";
    el.innerHTML = `<img class="avatar" src="${markSrc()}" alt="IRAS" width="32" height="32"><div class="msg-body"><div class="tools" hidden></div><div class="prose"><span class="typing" aria-label="IRAS is thinking"><i></i><i></i><i></i></span></div><div class="msg-meta" hidden></div></div>`;
    thread.appendChild(el);
    turn = { el, prose: $(".prose", el), tools: $(".tools", el), meta: $(".msg-meta", el), text: "", t0: performance.now(), first: null, chips: new Map(), pinned: true };
    thread.scrollTop = thread.scrollHeight;
  }

  function render() {
    raf = 0;
    if (!turn || !turn.text) return;
    turn.pinned = nearBottom();
    turn.prose.innerHTML = renderMarkdown(turn.text);
    stick();
  }

  const TOOL_ICON = (id) => (id.startsWith("spotify") ? "music" : id.startsWith("mail") ? "mail" : id.startsWith("calendar") ? "calendar" : id.startsWith("winget") ? "package" : id.startsWith("fs.delete") ? "trash-2" : id.startsWith("fs") ? "folder" : "zap");

  function setChip(key, { label, status, level, ic }) {
    if (!turn) return;
    turn.tools.hidden = false;
    let chip = turn.chips.get(key);
    if (!chip) { chip = document.createElement("span"); chip.className = "tool-chip"; turn.tools.appendChild(chip); turn.chips.set(key, chip); }
    chip.dataset.status = status;
    chip.className = "tool-chip" + (level === "critical" ? " crit" : level === "system" ? " warn" : "");
    chip.innerHTML = `${icon(status === "running" ? "loader-circle" : ic || "check", "i-sm")}<span>${esc(label)}</span>`;
  }

  function endTurn(opts = {}) {
    if (!turn) return;
    const t = turn;
    turn = null;
    cancelAnimationFrame(raf);
    raf = 0;
    t.el.classList.remove("is-streaming");
    if (!t.text) {
      if (opts.stopped) { t.prose.innerHTML = `<p class="muted">Stopped.</p>`; }
      else if (!t.chips.size) { t.el.remove(); return; }
      else t.prose.remove();
    } else {
      t.prose.innerHTML = renderMarkdown(t.text);
    }
    const total = performance.now() - t.t0;
    const bits = [];
    if (t.first != null && t.text && t.first < 3500) bits.push(`<span class="msg-note">${icon("zap", "i-sm")}First word in ${fmtDur(t.first)}</span>`);
    if (opts.stopped) bits.push(`<span class="msg-note">${icon("square", "i-sm")}You stopped this reply</span>`);
    else if (t.text) bits.push(`<span class="msg-note">${icon("clock", "i-sm")}Done in ${fmtDur(total)}</span>`);
    if (t.text) bits.push(`<button type="button" class="btn-icon sm copy-msg" aria-label="Copy this reply" title="Copy this reply">${icon("copy", "i-sm")}</button>`);
    if (bits.length) { t.meta.hidden = false; t.meta.innerHTML = bits.join(""); }
    thread.scrollTop = thread.scrollHeight;
  }

  /* ---------- events ---------- */
  bus.on("submit", (e) => { addUser(e.text, e.via); startTurn(); });
  bus.on("speech_end", (e) => { if (e.text) { addUser(e.text, "voice"); startTurn(); } });
  bus.on("token", (e) => {
    if (!turn) startTurn();
    if (turn.first == null) turn.first = performance.now() - turn.t0;
    turn.text += e.text;
    if (!raf) raf = requestAnimationFrame(render);
  });
  bus.on("tool_start", (e) => {
    if (!turn) return;
    setChip(e.id, { label: e.title || e.tool, status: "running", level: e.authority });
  });
  bus.on("tool_end", (e) => {
    if (!turn || !turn.chips.has(e.id)) return;
    const item = audit.byId.get(e.id);
    const tool = item && item.payload && item.payload.tool || "";
    setChip(e.id, { label: `${e.title || (item && item.title) || "Done"}, ${fmtDur(e.ms || 0)}`, status: e.ok === false ? "failed" : "done", level: item && item.authority, ic: e.ok === false ? "circle-alert" : TOOL_ICON(tool) });
  });
  bus.on("agent_step", (e) => {
    if (!turn) return;
    const name = e.agent === "code" ? "Code agent" : e.agent === "research" ? "Research agent" : "Agent";
    const label = e.step && e.step.label || "";
    setChip("run_" + e.run, e.final && e.status !== "running"
      ? { label: `${name} finished`, status: "done", ic: e.agent === "code" ? "bug" : "flask-conical" }
      : { label: `${name}: ${label}`, status: "running" });
  });
  bus.on("approval_request", (e) => { if (turn) setChip("ap_" + e.id, { label: "Waiting for your approval", status: "waiting", level: e.authority, ic: e.authority === "critical" ? "shield-alert" : "shield" }); });
  bus.on("approval_result", (e) => {
    if (!turn) return;
    const label = e.decision === "approve" ? "You approved this" : e.decision === "expired" ? "Approval expired" : "You denied this";
    setChip("ap_" + e.id, { label, status: "done", level: S.authority || (audit.byId.get("ap_" + e.id) || {}).authority, ic: e.decision === "approve" ? "shield-check" : "shield" });
  });
  bus.on("done", () => endTurn());
  bus.on("cancel", () => endTurn({ stopped: true }));
  bus.on("error", () => endTurn({ stopped: true }));

  /* ---------- copy and expand ---------- */
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      ta.remove();
      return ok;
    }
  }
  IRAS.copyText = copyText;
  thread.addEventListener("click", async (e) => {
    const cc = e.target.closest(".copy-code");
    if (cc) {
      const ok = await copyText($("code", cc.closest(".code-card")).textContent);
      toast(ok ? "Code copied." : "Couldn’t copy. Select the text and copy it yourself.", { icon: ok ? "copy" : "info" });
      return;
    }
    const cm = e.target.closest(".copy-msg");
    if (cm) { const ok = await copyText($(".prose", cm.closest(".msg")).innerText); toast(ok ? "Reply copied." : "Couldn’t copy.", { icon: ok ? "copy" : "info" }); return; }
    const ex = e.target.closest(".expand-code");
    if (ex) {
      const card = ex.closest(".code-card");
      const open = card.classList.toggle("is-open");
      ex.setAttribute("aria-expanded", String(open));
      ex.innerHTML = `${icon(open ? "minimize-2" : "maximize-2", "i-sm")}<span>${open ? "Collapse" : "Expand"}</span>`;
    }
  });

  IRAS.initChat = function () {
    const host = $("#chatSuggest");
    host.innerHTML = IRAS.PROMPTS.filter((p) => !p.tour).slice(0, 4).map((p) => `<button type="button" class="suggest" data-text="${esc(p.text)}">${icon(p.icon)}<span>${esc(p.text)}</span></button>`).join("");
    host.addEventListener("click", (e) => { const b = e.target.closest(".suggest"); if (b) IRAS.run(b.dataset.text, { via: "text" }); });
    $("#newThread").addEventListener("click", () => {
      if (S.busy) { toast("Press Stop first, then start a new chat.", { icon: "info" }); return; }
      $$(".msg", thread).forEach((m) => m.remove());
      if (!empty.isConnected) thread.appendChild(empty);
      toast("New conversation.", { icon: "message-square" });
    });
  };
})();
