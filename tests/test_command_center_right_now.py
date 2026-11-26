"""Right now (the page side): what the card and the switch must do, and what they must never do.

The card on Home shows the time of day, who is here, the next calendar event and the reminders that are due.
The chat sends her the same request with each message, and the server writes her lines (see
test_right_now.py and src/iras/right_now.py). These tests read the sources and the built page, so a later
change cannot quietly break the rules that matter: nothing is stored, a guest sees no private rows, the
facts of one person are never shown for another, the key and token are never named, and "off" means off.
The real behaviour is tried in a real browser by clients/web/command-center/qa/browser-test.cjs
(the "Right now" section and the phone checks).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "clients" / "web" / "command-center"
JS = CC / "src" / "js"
PAGE = ROOT / "clients" / "web" / "index.html"


def src(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """The script without its comments, so a rule is tested on what runs, not on what is explained."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", "", text)


RN = src("78-rightnow.js")
RN_CODE = code_only(RN)
CSS = (CC / "src" / "css" / "rightnow.css").read_text(encoding="utf-8")


def body_of(name: str) -> str:
    """The text of one function in the module, from its name to the next top-level function."""
    start = RN_CODE.index(f"function {name}(")
    nxt = re.search(r"\n  (?:function |const |IRAS\.)", RN_CODE[start + 10:])
    return RN_CODE[start: start + 10 + (nxt.start() if nxt else len(RN_CODE))]


# ---------- it is part of the page ----------
def test_the_card_the_switch_and_the_start_up_are_in_the_built_page():
    page = PAGE.read_text(encoding="utf-8")
    for needle in ('id="rightNow"', 'id="rnBody"', 'id="rnToggle"', 'id="rnOpen"', 'id="setRightNow"', "IRAS.rightNow", "Tell her what is going on around her"):
        assert needle in page, needle
    assert '"initRightNow"' in src("90-app.js") and "IRAS.initRightNow" in RN
    assert '"rightnow"' in (CC / "build.py").read_text(encoding="utf-8")  # the style file is in the build list
    # the card sits above Live activity in the same column, and both are inside the side wrapper
    home = (CC / "src" / "views" / "home.html").read_text(encoding="utf-8")
    side = home[home.index('class="home-side"'):]
    assert side.index('id="rightNow"') < side.index('id="livePanel"')


def test_it_asks_only_the_one_new_endpoint_and_only_reads():
    paths = set(re.findall(r'"(/v1/[^"?]*)', RN_CODE))
    assert paths == {"/v1/right-now"}
    assert "IRAS.api(" in RN_CODE and "fetch(" not in RN_CODE  # the same call, the same token handling as every screen
    assert "method" not in RN_CODE and "POST" not in RN_CODE and "DELETE" not in RN_CODE


# ---------- nothing is kept, nothing secret is named ----------
def test_nothing_is_stored_and_no_key_or_token_is_named():
    for bad in ("localStorage", "sessionStorage", "indexedDB", "store.set", "store.sset", "rawSet", "document.cookie", "caches."):
        assert bad not in RN_CODE, bad
    for name in ("78-rightnow.js",):
        text = src(name)
        assert "OPENROUTER" not in text and "iras-api-token" not in text and "Bearer" not in text, name
    assert "OPENROUTER" not in CSS


def test_the_page_has_no_outside_address_in_the_new_files():
    for text in (RN, CSS):
        assert not re.search(r"https?://", text)


# ---------- the privacy rules of the card ----------
def test_a_guest_never_sees_private_rows_and_not_even_for_a_moment():
    state = body_of("state")
    guest_at, facts_at = state.index('"guest"'), state.index("askedFor !== key()")
    assert guest_at < facts_at  # the guest answer comes first, before any facts are looked at
    assert "return { text: text(\"Hidden for a guest\") }" in state.replace("\n", " ") or 'Hidden for a guest' in state
    assert 'w.kind === "guest" ? "guest"' in body_of("key")  # a guest has a key of its own, so another person's facts are never shown for a guest


def test_one_persons_facts_are_never_shown_for_another_person():
    key = body_of("key")
    assert 'person_id' in key and '"p:"' in key  # the key names the person
    # the facts are only used when they were asked for the same key; otherwise the rows say "Checking"
    assert "askedFor !== key()" in body_of("state") and 'text("Checking…")' in body_of("state")
    assert "askedFor = mine" in RN_CODE and "const mine = key()" in RN_CODE  # the key is taken when the question is asked, not when the answer arrives
    assert 'bus.on("who"' in RN_CODE  # a change of person redraws at once and asks again


def test_the_question_names_only_who_and_the_time_zone():
    query = body_of("query")
    assert set(re.findall(r'p\.set\("([a-z_]+)"', query)) == {"guest", "person_id", "via", "tz", "offset"}


# ---------- what the chat sends, and the switch ----------
def test_the_chat_sends_only_the_zone_and_the_offset_and_only_when_the_switch_is_on():
    assert re.search(r"const forChat = \(\) => \(enabled\(\) \? \{ tz: zone\(\), offset: Number\(offset\(\)\) \} : undefined\)", RN_CODE)
    assert "right_now: IRAS.rightNow ? IRAS.rightNow.forChat() : undefined" in src("35-live.js")
    assert "const enabled = () => settings.rightNow !== false" in RN_CODE
    core = src("00-core.js")
    assert re.search(r"\brightNow: true,", core)  # on by itself


def test_the_switch_in_settings_turns_everything_off():
    st = src("80-settings.js")
    assert 'setSetting("rightNow", e.target.checked)' in st and 'settings.rightNow !== false' in st
    assert "Right now is off. No card, and she gets none of these facts." in st
    render = body_of("render")
    assert "el.hidden = !enabled()" in render and "opener.hidden = !enabled()" in render
    refresh = body_of("refresh")
    assert refresh.index("!enabled()") < refresh.index("IRAS.api(")  # off: the server is not even asked


# ---------- the words on the card are escaped ----------
def test_every_word_that_comes_from_the_server_or_a_person_is_escaped():
    for raw in ("i.text", "c.event.title", "w.name", "ev.title", "first.text", "i.for", "r.label"):
        assert not re.search(r"\$\{" + re.escape(raw) + r"[^}]*\}", RN_CODE.replace("esc(" + raw, "")), raw  # only ever inside esc(...)
    assert "esc(i.text)" in RN_CODE and "esc(c.event.title)" in RN_CODE and "esc(w.name" in RN_CODE
    assert "textContent = summary(now)" in RN_CODE  # the phone line is text, never HTML


# ---------- the look ----------
def test_the_style_keeps_to_the_rules_of_the_page():
    rules = code_only(CSS)  # what the style does, not what its comments say
    assert "var(--warn" not in rules and "var(--crit" not in rules and "amber" not in rules  # amber and red stay for authority
    assert "transition" not in rules  # nothing here animates its size or place
    assert "var(--surface-solid)" in CSS  # the opened sheet is solid, so what is behind it does not show through
    # a phone with room has one line; a short phone has a clock button in the Live row and no extra row
    assert "(max-width: 899px) and (max-height: 799px)" in CSS and ".rn:not(.is-open) { display: none; }" in CSS
    assert ".home-side { display: contents; }" in CSS
    desktop_rule = re.search(r"@media \(min-width: 900px\) \{ \.home-side > \.live \{ flex: 1 1 auto; \} \}", CSS)
    assert desktop_rule  # the Live panel only grows on a computer (on a phone it keeps its one-line size)


# ---------- Check everything ----------
def test_check_everything_has_a_right_now_line_that_names_nothing_private():
    check = code_only(src("81-check.js"))
    assert 'id: "rightnow"' in check and "IRAS.rightNow.query()" in check and "/v1/right-now" in check
    line = check[check.index('id: "rightnow"'): check.index('id: "pc"')]
    for private in ("event.title", ".text", "i.text", "title"):
        assert private not in line, private  # the report is pasted to someone else: counts and words only, never a title or a reminder text
    assert "skip(" in line and "fail(" in line and "warn(" in line and "ok(" in line  # off, no such route, a slow calendar, and working
