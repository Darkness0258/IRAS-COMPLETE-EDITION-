"""Voice check while you talk: what the page must do, and what it must never do.

The page records the same few seconds that the speech recognition hears and asks the server whose voice it
is (see 39-autoid.js). These tests read the sources and the built page, so a later change cannot quietly
break the rules that matter: nothing is saved, guest mode is never changed by a voice, the Android app is
left alone, the microphone is always let go, and a slow server never holds her up for long.
The real behaviour is tried in a real browser by clients/web/command-center/qa/browser-test.cjs
(the "Voice check" sections). The server's side is in test_voice_listen_along.py.
"""
import math
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


AUTO = src("39-autoid.js")
AUTO_CODE = code_only(AUTO)
VOICE = src("38-voice.js")


def number(name: str) -> float:
    m = re.search(rf"const {name} = ([0-9.]+(?: \* [0-9]+)*)", AUTO)
    assert m, name
    return math.prod(float(part) for part in m.group(1).split(" * "))  # a plain number or a product such as 10 * 60 * 1000


# ---------- it is part of the page ----------
def test_the_module_is_in_the_built_page_and_the_start_up_list():
    page = PAGE.read_text(encoding="utf-8")
    assert "IRAS.autoid" in page and "Checked who is speaking" in page and 'id="setAutoWho"' in page
    assert '"initAutoId"' in src("90-app.js") and "IRAS.initAutoId" in AUTO


def test_it_asks_only_the_voice_endpoint_that_already_exists():
    paths = set(re.findall(r'"(/v1/[^"]*)"', AUTO_CODE))
    assert paths == {"/v1/identity/voice/verify"}
    assert "IRAS.api(" in AUTO_CODE and "fetch(" not in AUTO_CODE  # the same call, the same token handling as every screen


# ---------- nothing is kept ----------
def test_sound_and_answers_are_never_stored_anywhere():
    for bad in ("localStorage", "sessionStorage", "indexedDB", "store.set", "store.sset", "rawSet", "document.cookie", "caches."):
        assert bad not in AUTO_CODE, bad
    assert "OPENROUTER" not in AUTO and "iras-api-token" not in AUTO   # no key and no token in this file
    assert AUTO_CODE.count("chunks = []") >= 3 and "KEEP_MS" not in AUTO_CODE   # the sound in memory is dropped as soon as it is sent


def test_sound_is_sent_only_as_a_small_wav_and_only_a_few_seconds_of_it():
    assert "wavBlob(" in AUTO_CODE and "to16k(" in AUTO_CODE
    assert 8 <= number("MAX_S") <= 12   # the server uses up to 10 seconds of speech
    assert number("MIN_S") >= 1.5   # a clip too short for any check is not sent


# ---------- what a voice may and may not change ----------
def test_a_voice_never_changes_guest_mode():
    assert AUTO_CODE.count('cur.kind === "guest"') >= 1 and 'cur && cur.kind === "guest"' in AUTO_CODE   # adopt: a guest stays a guest
    assert 'here.kind === "guest"' in AUTO_CODE   # begin: in guest mode she does not even record
    assert "IRAS.who.guest" not in AUTO_CODE and "who.guest(" not in AUTO_CODE   # it can never switch guest mode on or off


def test_a_name_is_dropped_only_after_two_in_a_row_and_only_for_a_person_with_a_taught_voice():
    assert number("STRIKES") == 2
    assert "IRAS.people.voices(cur.person_id)" in AUTO_CODE   # no taught voice, no evidence against the person
    assert "who.clear()" in AUTO_CODE and "strikes = 0" in AUTO_CODE   # a match starts the count again


def test_what_you_did_meanwhile_is_newer_than_a_late_answer():
    assert "rev++" in AUTO_CODE and "my.rev !== rev" in AUTO_CODE and "mineDepth" in AUTO_CODE


def test_it_only_hints_and_never_approves_anything():
    for word in ("approval", "approve", "authorize", "authority", "IRAS.pollApprovals"):
        assert word not in AUTO_CODE, word


# ---------- the Android app, phones and the switch ----------
def test_it_is_off_in_the_android_app_and_the_native_listening_is_left_alone():
    assert "window.IRASNative" in AUTO_CODE and "does not share the microphone" in AUTO
    native = re.search(r"function startNative\(\).*?\n  }\n", VOICE, flags=re.S).group(0)
    assert "autoid" not in native   # the app's own listening path never starts the extra recording


def test_a_phone_browser_starts_off_and_the_switch_can_override_it():
    assert "autoWho: null" in src("00-core.js")
    assert "Android|iPhone|iPad|iPod|Mobile" in AUTO_CODE
    assert "settings.autoWho" in AUTO_CODE and '"autoWho"' in src("80-settings.js")


def test_the_switch_is_a_labelled_checkbox_with_a_plain_sentence():
    html = (CC / "src" / "views" / "settings.html").read_text(encoding="utf-8")
    assert re.search(r'<label class="label" for="setAutoWho">Know who is speaking by voice</label>', html)
    assert 'id="autoWhoHint"' in html and 'aria-describedby="autoWhoHint"' in html and 'role="switch"' in html


def test_the_people_helper_knows_who_has_a_taught_voice():
    people = src("36-people.js")
    assert "voices: Math.max(0, Number(p.voices) || 0)" in people and "withVoice" in people and "voices: (id)" in people


# ---------- the voice chat code ----------
def test_voice_chat_starts_the_check_in_the_same_tap_and_never_before_listening_starts():
    toggle = VOICE[VOICE.index("voice.toggle = function"):VOICE.index("/* ---------- speaking")]
    assert toggle.index("rec.start()") < toggle.index("IRAS.autoid.begin()")   # listening first, the extra recording after it
    assert "listenFailed(ev.error)" in toggle   # if listening fails, the check can turn itself off


def test_voice_chat_waits_only_a_moment_and_a_stop_in_the_meantime_wins():
    finish = VOICE[VOICE.index("function finishHeard()"):VOICE.index("function startNative()")]
    assert "IRAS.autoid.end(!!said)" in finish and "stops === at" in finish
    assert 'bus.emit("speech_end"' in finish and finish.index('bus.emit("speech_end"') < finish.index("check.then(")   # your words show at once
    assert number("WAIT_MS") <= 2500   # a slow server never holds her up for more than about two seconds


def test_the_message_is_sent_straight_away_when_there_is_nothing_to_wait_for():
    finish = VOICE[VOICE.index("function finishHeard()"):VOICE.index("function startNative()")]
    assert "if (!check) { IRAS.live.send(text" in finish


# ---------- the microphone is always let go ----------
def test_every_way_out_lets_the_microphone_go():
    for needle in ('bus.on("ui"', 'bus.on("cancel"', 'bus.on("visibility"', 'addEventListener("pagehide"', "(MAX_S + 5) * 1000", "getTracks().forEach((t) => t.stop())"):
        assert needle in AUTO_CODE, needle
    assert "release(my);   // the microphone is let go at once" in AUTO   # at the end of a talk, before anything else
    assert "echoCancellation: false" in AUTO_CODE   # the same way the Voice ID screen teaches a voice


def test_a_microphone_that_cannot_be_shared_turns_the_check_off_and_says_so():
    assert "NotReadableError" in AUTO_CODE and "quietTurns >= 2" in AUTO_CODE and "audio-capture" in AUTO_CODE
    assert "Voice chat still works" in AUTO   # the message tells you the check is not needed for voice chat


# ---------- you can see what she heard ----------
def test_activity_shows_each_check_and_check_everything_reports_it():
    assert "Checked who is speaking" in AUTO and '"voice id"' in AUTO_CODE
    assert "IRAS.autoid.hint()" in src("81-check.js") and "IRAS.autoid.hint()" in src("80-settings.js")


def test_the_real_browser_test_keeps_its_voice_check_sections():
    qa = (CC / "qa" / "browser-test.cjs").read_text(encoding="utf-8")
    for name in ("Voice check while she listens", "Voice check: the switch in Settings", "Voice check: a microphone that cannot be shared",
                 "Voice check: the Android app", "Voice check: a phone browser", "Voice check: nobody has a taught voice"):
        assert name in qa, name
