import os

from iras.cli import _voice_intent
from iras.models import PermissionLevel
from iras.tools.system import classify_launch


def test_voice_intents():
    assert _voice_intent('/voice') == 'toggle'
    assert _voice_intent('voice') == 'toggle'
    assert _voice_intent('voice on') == 'on'
    assert _voice_intent('turn voice off') == 'off'
    assert _voice_intent('tell me about voice actors') is None


def test_launch_app_permission_classification():
    assert classify_launch({'command': 'chrome'}) == PermissionLevel.SAFE_ACTION
    assert classify_launch({'command': 'google-chrome'}) == PermissionLevel.SAFE_ACTION
    assert classify_launch({'command': 'powershell -Command whoami'}) == PermissionLevel.SYSTEM_ACTION
    assert classify_launch({'command': 'chrome & whoami'}) == PermissionLevel.SYSTEM_ACTION
