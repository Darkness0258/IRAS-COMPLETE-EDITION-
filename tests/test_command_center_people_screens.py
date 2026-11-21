"""Checks for the screens of each person's own memory, calendar and reminders.

Same style as the other UI tests: read the files and look for what must stay true.
The real-browser test is clients/web/command-center/qa/browser-test.cjs.
"""
import re
from pathlib import Path

import pytest

from iras.v5 import reminders as rem

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "clients" / "web" / "command-center"
PAGE = ROOT / "clients" / "web" / "index.html"  # the built page the server shows


def src(*parts):
    return CC.joinpath("src", *parts).read_text(encoding="utf-8")


def js_literal(text, name):
    """The regular expression written as `const NAME = /.../flags;` in a script."""
    found = re.search(r"const " + name + r"\s*=\s*/(.+)/([a-z]*);", text)
    assert found, name + " is not in the script"
    return found.group(1), found.group(2)


class Notices:
    def __init__(self):
        self.sent = []

    def notify(self, title, text, severity="info", channel="browser"):
        self.sent.append((title, text))


# ---------- the shared list of people ----------
def test_every_screen_gets_names_from_one_shared_helper():
    helper = src("js", "36-people.js")
    assert "IRAS.people = " in helper and "/v1/identity/people" in helper
    for name in ("60-agents.js", "70-memory.js"):
        assert "IRAS.people." in src("js", name), name
    assert "IRAS.people = " in PAGE.read_text(encoding="utf-8")
    assert "IRAS.people.use(people)" in src("js", "75-identity.js")      # a person you just taught her is in every choice at once


# ---------- Memory screen ----------
def test_memory_screen_asks_whose_memory_and_can_filter():
    html = src("views", "memory.html")
    assert re.search(r'<label[^>]*for="memWhose"[^>]*>Whose memory\?</label>', html)
    assert 'id="memWhose"' in html and 'id="memFilter"' in html
    code = src("js", "70-memory.js")
    assert 'PERSON = "person:"' in code
    assert "namespace: ns" in code and 'namespace: "default"' not in code     # saves where you chose, not always shared
    assert "IRAS.people.here()" in code                                         # starts on the person who is here
    assert "All memories" in code and "Shared memories" in code
    assert '"/v1/v5/memory/search?limit=60&q="' in code and "&namespace=" in code


def test_memory_list_headings_are_h2_not_h3():
    code = src("js", "70-memory.js")
    assert "<h3" not in code
    assert re.search(r'<div class="mem-group"><h2>', code)
    css = src("css", "memory.css")
    assert ".mem-group h2" in css and ".mem-group h3" not in css


def test_every_memory_shows_whose_it_is():
    code = src("js", "70-memory.js")
    assert "ns: String(m.namespace" in code          # the row has `namespace`
    assert "const ownerBadge = (ns) =>" in code
    assert code.count("ownerBadge(n.ns)") == 2       # on each row of the list, and on the memory's card
    assert '"Someone she no longer knows"' in code   # a person who was forgotten


# ---------- Identity screen ----------
def test_identity_screen_can_claim_and_share_each_persons_memories():
    html = src("views", "identity.html")
    assert re.search(r'<h2[^>]*id="ownTitle"[^>]*>Each person\'s own memories</h2>', html)
    code = src("js", "75-identity.js")
    assert "Make the old memories mine" in code and "Share all of their memories" in code
    assert '"claim-memory"' in code and '"share-memory"' in code
    assert 'method: "POST"' in code


def test_sharing_says_it_moves_all_memories_and_asks_first():
    code = src("js", "75-identity.js")
    ask = re.search(r'"Share ALL of " \+ who\.name .*?"', code)
    assert ask, "the Share question must say ALL"
    assert "EVERY memory and fact" in code and "everyone" in code.lower()
    assert code.index("window.confirm(ask)") < code.index('"/claim-memory"') if '"/claim-memory"' in code else True
    assert "if (!window.confirm(ask)) return;" in code   # nothing is sent before you say yes


# ---------- Agents screen ----------
def test_reminders_and_calendars_ask_whose_they_are_inside_the_page():
    shell = src("index.template.html")
    assert re.search(r'<label[^>]*for="remindFor"[^>]*>For</label>', shell)
    assert re.search(r'<label[^>]*for="calWhose"[^>]*>Whose calendar\?</label>', shell)
    code = src("js", "60-agents.js")
    assert '"[reminder:" + owner + "] "' in code and '"[reminder] "' in code
    assert '"/v1/calendar/feeds/" + encodeURIComponent(id) + "/owner"' in code
    assert "body.owner = owner" in code
    assert 'ask("What should she remind you about?")' not in code      # the old pop-up questions are gone
    assert "Paste your calendar's secret iCal link.\\n" not in code


def test_the_secret_calendar_link_is_cleared_when_the_form_closes():
    code = src("js", "60-agents.js")
    assert '$("#calDlg").addEventListener("close"' in code and '$("#calUrl").value = ""' in code
    assert "https://" not in src("index.template.html").split('id="calDlg"')[1].split("</dialog>")[0]   # the build refuses stray web addresses


def test_lists_with_a_choice_in_them_are_not_redrawn_when_nothing_changed():
    code = src("js", "60-agents.js")
    assert "const put = (el, html) =>" in code and 'put(el, (rows ||' in code


def test_the_page_reads_a_reminder_marker_like_the_server_does():
    pattern, flags = js_literal(src("js", "60-agents.js"), "REMINDER")
    page = re.compile(pattern, re.I if "i" in flags else 0)
    for prompt in ["[reminder] Take the bins out", "[reminder:per_abc] Call the dentist", "[Reminder:per_abc]   spaced",
                   "[reminder:bad id] x", "[reminder:] x", "remind me", "x [reminder] y", "[reminder]", "[reminder:per_abc]"]:
        found = page.match(prompt)
        mine = (found.group(1) or "", prompt[found.end():]) if found else None
        assert mine == rem.parse(prompt), prompt


# ---------- notices ----------
def test_a_private_reminder_notice_is_found_by_the_wording_the_server_uses():
    pattern, flags = js_literal(src("js", "39-proactive.js"), "PRIVATE")
    page = re.compile(pattern, re.I if "i" in flags else 0)
    n = Notices()
    rem.deliver("[reminder:per_a] Call the dentist", {}, n, None, owner_name=lambda pid: "Alice")
    rem.deliver("[reminder:per_gone] Call the dentist", {}, n, None, owner_name=lambda pid: None)
    rem.deliver("[reminder] Take the bins out", {}, n, None)
    named, unnamed, everyone = (t for t, _ in n.sent)
    assert page.match(named).group(1) == "Alice"
    assert page.match(unnamed).group(1) == "someone"     # the page treats "someone" as nobody it can match
    assert page.match(everyone) is None                  # a reminder for everyone is not private


def test_a_private_reminder_is_shown_only_to_that_person_or_nobody_and_its_text_is_never_kept():
    code = src("js", "39-proactive.js")
    assert '"A private reminder for " + name + " is due"' in code
    may = code[code.index("function mayRead"):code.index("const hiddenFrom")]
    assert "if (!w) return true" in may                       # nobody in particular: everyone's
    assert 'w.kind !== "person") return false' in may         # a guest: never
    assert '"someone"' in may                                 # an owner the server could not name: only "nobody"
    private = code[code.index("function showPrivate"):code.index("function show(")]
    assert "n.body" not in private and "detail: \"\"" in private and "speak" not in private   # no text, nothing spoken
    pull = code[code.index("async function pull"):]
    assert "const line = { name, ids: [] }" in pull and "masked.add(id)" in pull    # only the ids and the name are kept
    assert "todo.slice(0, first ? 3 : 5)" in pull                                    # full and private lines share one limit
    assert "private reminders for " in code                                          # several for one person are one line
    assert 'bus.on("who"' in code                                                    # a held reminder shows when the right person arrives


# ---------- the page and the files ----------
def test_the_built_page_has_the_new_screens():
    page = PAGE.read_text(encoding="utf-8")
    for needle in ('id="memWhose"', 'id="memFilter"', 'id="ownList"', 'id="remindDlg"', 'id="calDlg"', "A private reminder for", "claim-memory", "share-memory"):
        assert needle in page, needle


@pytest.mark.parametrize("name", ["browser-test.cjs", "test_server.py"])
def test_the_browser_test_files_never_hold_a_key_or_a_token(name):
    text = (CC / "qa" / name).read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" not in text                  # the web files must not name the key
    assert not re.search(r"Bearer [A-Za-z0-9]{16,}", text)
    assert "token" not in re.findall(r"print\(.*\)", text, flags=re.S) or "token-file" in text
