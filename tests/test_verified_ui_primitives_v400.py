from __future__ import annotations

import pytest

from iras.device_bridge.primitives import VerifiedUIPrimitives


class _UI:
    pass


class _Computer:
    def __init__(self, observations):
        self.observations = list(observations)
        self.actions = []

    def observe(self, **_kwargs):
        return self.observations.pop(0)

    def action(self, **kwargs):
        self.actions.append(dict(kwargs))
        return {"observation_consumed": True, "action_replay_allowed": False}


def _obs(oid, *labels):
    return {
        "observation_id": oid,
        "elements": [
            {
                "element_id": f"e{i}",
                "label": label,
                "role": "button",
                "interactive": True,
            }
            for i, label in enumerate(labels)
        ],
    }


def test_find_text_matches_instead_of_inverting_match():
    computer = _Computer([_obs("o1", "Settings", "Cancel")])
    primitives = VerifiedUIPrimitives(_UI(), computer)
    result = primitives.find_text("Settings", exact=True)
    assert result["found"] is True
    assert result["count"] == 1
    assert result["matches"][0]["label"] == "Settings"


def test_click_text_fails_closed_on_ambiguity_without_action():
    computer = _Computer([_obs("o1", "Open", "Open")])
    primitives = VerifiedUIPrimitives(_UI(), computer)
    with pytest.raises(RuntimeError, match="matched 2"):
        primitives.click_text("Open", exact=True)
    assert computer.actions == []


def test_scroll_uses_fresh_observation_each_state_change():
    computer = _Computer([_obs("o1", "A"), _obs("o2", "A"), _obs("o3", "Target")])
    primitives = VerifiedUIPrimitives(_UI(), computer)
    result = primitives.scroll_until_text("Target", max_steps=3)
    assert result["found"] is True
    assert [call["observation_id"] for call in computer.actions] == ["o1", "o2"]
