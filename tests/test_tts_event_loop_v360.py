from __future__ import annotations

import asyncio

from iras.voice.tts import Speaker


def test_edge_sync_bridge_works_inside_running_event_loop(monkeypatch):
    speaker = Speaker(provider="edge")

    async def fake_edge(text: str) -> str:
        await asyncio.sleep(0)
        assert text
        return "edge+fake"

    monkeypatch.setattr(speaker, "_edge", fake_edge)

    async def host():
        return speaker._run_edge_sync("IRAS event loop voice test")

    assert asyncio.run(host()) == "edge+fake"
