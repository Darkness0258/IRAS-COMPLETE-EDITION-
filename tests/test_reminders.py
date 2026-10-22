from iras.v5.reminders import deliver, is_reminder


class FakeNotifications:
    def __init__(self):
        self.sent = []

    def notify(self, title, body, *, severity="info", channel="browser"):
        self.sent.append((title, body, severity, channel))


class FakeMobile:
    def __init__(self):
        self.events = []

    def push_event(self, kind, payload):
        self.events.append((kind, payload))


def test_a_reminder_becomes_a_notice_and_a_phone_event():
    n, m = FakeNotifications(), FakeMobile()
    out = deliver("[reminder] call mom at five", {"job_id": "job_1"}, n, m)
    assert out == "Reminder delivered."
    assert n.sent == [("Reminder", "call mom at five", "info", "browser")]
    assert m.events == [("reminder.due", {"text": "call mom at five", "schedule_id": "job_1"})]


def test_other_prompts_are_left_for_the_agent():
    n = FakeNotifications()
    assert deliver("Check my email", {}, n) is None
    assert not is_reminder("remind me later")
    assert n.sent == []


def test_an_empty_reminder_still_says_something_and_a_phone_failure_is_ignored():
    class Broken:
        def push_event(self, *a):
            raise RuntimeError("offline")

    n = FakeNotifications()
    assert deliver("[REMINDER]   ", {"job_id": "j"}, n, Broken()) == "Reminder delivered."
    assert n.sent[0][1] == "You asked me to remind you."
