from iras.persona import BASE_SYSTEM_PROMPT
from iras.personality.adaptive import (
    AdaptivePersonality,
    PersonalityState,
)


class Memory:
    def __init__(self):
        self.data = {}

    def get_fact(
        self,
        key,
        default=None,
    ):
        return self.data.get(
            key,
            default,
        )

    def remember(
        self,
        key,
        value,
    ):
        self.data[key] = value


def test_persona_avoids_robotic_social_disclaimer():
    prompt = BASE_SYSTEM_PROMPT

    assert (
        "Do NOT constantly remind the user"
        in prompt
    )
    assert (
        'Never say things like "I don\'t experience happiness like a person"'
        in prompt
    )
    assert (
        "How can I assist you today?"
        in prompt
    )


def test_new_humanlike_traits_have_adult_defaults():
    state = PersonalityState()

    assert state.naturalness >= 0.90
    assert state.reciprocity >= 0.60
    assert state.spontaneity >= 0.50
    assert (
        state.emotional_expression
        >= 0.60
    )


def test_humanlike_feedback_nudges_naturalness():
    memory = Memory()
    personality = AdaptivePersonality(
        memory,
        enabled=True,
    )

    before = (
        personality.state.naturalness
    )

    personality.observe_user(
        "talk naturally and behave like human"
    )

    after = (
        personality.state.naturalness
    )

    assert after >= before
