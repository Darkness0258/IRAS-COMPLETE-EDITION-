"""The test-day checklist (TEST-DAY.md): one list, in order, for everything only you can try.

It is only useful if it tells the truth. So these tests check that it covers every thing that is still
untested, that every name of a button or a label in it exists on a real screen of the page, that the steps
come in the order that they depend on each other, that it names no secret, and that the notes point to it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "TEST-DAY.md").read_text(encoding="utf-8")
PAGE = (ROOT / "clients" / "web" / "index.html").read_text(encoding="utf-8")
NOTES = (ROOT / "UPDATE-NOTES.md").read_text(encoding="utf-8")

# the names, exactly as the page shows them. Each one must be in the checklist AND on a real screen.
NAMES = [
    "Test connection", "Run checks", "Copy report", "Check everything", "Server address", "Access token",
    "Test her voice", "Voice identity", "Human · Gemini Leda",
    "Secret iCal link", "Whose calendar?", "Add calendar", "Calendar added:", "events in the next 7 days",
    "Start camera", "Teach her my face", "Who is this?", "Your name",
    "Teach her my voice", "Who is speaking?",
    "Know who is speaking by voice", "Checked who is speaking", "A guest is here",
    "Tell her what is going on around her", "Right now", "Live activity", "Next event", "Reminders due", "Who is here", "Hidden for a guest",
    "What should IRAS remember?", "Whose memory?", "Save to memory", "Each person's own memories",
    "Make the old memories mine", "Share all of their memories",
    "Remind me", "What should she remind you about?", "When?", "Set reminder", "A private reminder for",
    "Synced",
]


def test_it_covers_everything_that_is_still_untested():
    low = DOC.lower()
    for thing in ("render", "android", "windows", "gemini", "calendar", "face id", "voice id", "update 6", "update 7", "update 8", "right now", "the voice check"):
        assert thing in low, thing
    for step in ("Put it live on Render", "Start the two builds", "Check everything", "Her voice (Gemini)", "Your calendar link",
                 "Face ID with the webcam", "Voice ID with your microphone", "The voice check while you talk", "Right now (update 8)",
                 "The update 6 screens", "The apps"):
        assert step in DOC, step
    assert "real microphone and Chrome's real speech recognition" in DOC.replace("It uses your real microphone with", "real microphone and").replace("together", "").replace("Chrome's real speech recognition", "Chrome's real speech recognition") or "real microphone" in DOC


def test_every_name_in_it_is_on_a_real_screen():
    for name in NAMES:
        assert name in DOC, f"{name!r} is not in the checklist"
        assert name in PAGE, f"{name!r} is in the checklist but not on any screen of the page"


def test_the_steps_come_in_the_order_they_depend_on_each_other():
    heads = re.findall(r"(?m)^## (\d+)\. (.+)$", DOC)
    assert [int(n) for n, _ in heads] == list(range(1, 12))
    titles = [t for _, t in heads]
    at = {name: i for i, name in enumerate(titles)}
    first = lambda word: next(i for i, t in enumerate(titles) if word in t)
    assert first("Render") < first("builds") < first("Check everything")     # live first, builds started early, then the check
    assert first("calendar") < first("Right now")                            # Right now needs the calendar
    assert first("Voice ID") < first("voice check")                          # the voice check needs a taught voice
    assert first("Face ID") < first("update 6") and first("Voice ID") < first("update 6")  # the update 6 screens need two people
    assert first("update 6") < first("apps") == len(titles) - 1             # the apps come last


def test_every_step_has_boxes_to_tick_and_a_line_in_the_results_block():
    body = DOC.split("## 1.")[1].split("## If something goes wrong")[0]
    for part in re.split(r"(?m)^## ", "## " + body)[1:]:
        assert "- [ ]" in part, part.splitlines()[0]
    block = DOC.split("## Send me this")[1]
    for n in range(1, 12):
        assert re.search(rf"(?m)^{n}\s", block.split("```")[1]), n
    assert DOC.count("```") == 2


def test_it_names_no_secret_and_tells_you_not_to_send_any():
    assert "Never send me" in DOC and "access token" in DOC and "Gemini key" in DOC and "calendar link" in DOC
    assert not re.search(r"(ghp_|gho_|github_pat_|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|Bearer\s+[A-Za-z0-9._-]{20,})", DOC)
    assert "OPENROUTER_API_KEY" not in DOC
    assert not re.search(r"https?://(?!example\.)", DOC)  # no real address (a calendar link or your server)


def test_the_notes_point_to_it():
    assert "TEST-DAY.md" in NOTES
