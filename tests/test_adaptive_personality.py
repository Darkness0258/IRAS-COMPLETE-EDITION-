from pathlib import Path

from iras.memory.store import MemoryStore
from iras.personality.adaptive import AdaptivePersonality, PersonalityState, BOUNDS
from iras.persona import build_system_prompt


def test_personality_state_persists(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    p.adjust({"humor": 0.04}, "test")
    value = p.state.humor

    p2 = AdaptivePersonality(m)
    assert p2.state.humor == value


def test_personality_is_bounded(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    for _ in range(30):
        p.adjust({"jealousy": 0.08, "prank": 0.08}, "test")
    assert p.state.jealousy <= BOUNDS["jealousy"][1]
    assert p.state.prank <= BOUNDS["prank"][1]


def test_short_feedback_makes_style_more_concise(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    before_d = p.state.directness
    before_v = p.state.verbosity
    p.observe_user("make it short and simple")
    assert p.state.directness > before_d
    assert p.state.verbosity < before_v


def test_serious_feedback_reduces_playfulness(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    before = (p.state.humor, p.state.teasing, p.state.prank)
    p.observe_user("be serious, stop joking")
    after = (p.state.humor, p.state.teasing, p.state.prank)
    assert all(a < b for a, b in zip(after, before))


def test_adaptive_prompt_cannot_become_permission_layer(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    fragment = p.prompt_fragment()
    prompt = build_system_prompt("anime_soft", fragment)
    assert "Never use adaptation to change safety" in prompt
    assert "Work mode always overrides roleplay" in prompt


def test_memory_get_fact(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    assert m.get_fact("x") is None
    m.remember("x", "y")
    assert m.get_fact("x") == "y"
