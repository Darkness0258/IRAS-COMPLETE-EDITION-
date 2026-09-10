from pathlib import Path

from iras.memory.store import MemoryStore
from iras.personality.adaptive import AdaptivePersonality
from iras.tools.personality import make_tools


def test_personality_tool_changes_allowed_trait(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    tool = [t for t in make_tools(p) if t.name == "adapt_personality"][0]
    before = p.state.warmth
    out = tool.handler(reason="user responds well to warmth", warmth_delta=0.02)
    assert out["changed"]
    assert p.state.warmth > before


def test_personality_tool_does_not_accept_unknown_trait(tmp_path: Path):
    m = MemoryStore(tmp_path / "iras.db")
    p = AdaptivePersonality(m)
    tool = [t for t in make_tools(p) if t.name == "adapt_personality"][0]
    out = tool.handler(reason="test", permission_delta=0.08)
    assert not out["changed"]
