from __future__ import annotations

from iras.core.agent import IRASAgent


class FakeMemory:
    def __init__(self):
        self.messages = []

    def add_message(
        self,
        role,
        content,
    ):
        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    def recent_messages(
        self,
        limit,
    ):
        return self.messages[-limit:]

    def all_facts(
        self,
        limit,
    ):
        return []


class FakeAudit:
    def record(
        self,
        *_args,
        **_kwargs,
    ):
        pass


class FakeTools:
    def schemas(
        self,
        names=None,
    ):
        if names is None:
            return [{"name": "all"}]

        return [
            {"name": name}
            for name in names
        ]

    def execute(
        self,
        name,
        args,
    ):
        raise AssertionError(
            "No tool expected"
        )


class StreamingProvider:
    model = "fake/stream"
    last_model = "fake/stream"

    def stream_text(
        self,
        messages,
        tools,
    ):
        assert tools == []
        yield "Hello"
        yield " there."

    def complete(
        self,
        messages,
        tools,
    ):
        raise AssertionError(
            "complete() should not "
            "run for normal chat"
        )


def test_normal_chat_streams_and_persists():
    memory = FakeMemory()

    agent = IRASAgent(
        StreamingProvider(),
        FakeTools(),
        memory,
        FakeAudit(),
        smart_tools=True,
        context_fact_limit=10,
        context_message_limit=8,
    )

    chunks = list(
        agent.handle_stream(
            "hello"
        )
    )

    assert chunks == [
        "Hello",
        " there.",
    ]

    assert memory.messages[-1] == {
        "role": "assistant",
        "content": "Hello there.",
    }

    assert (
        agent.last_metrics[
            "streamed"
        ]
        is True
    )


def test_memory_turn_is_not_direct_stream():
    agent = IRASAgent(
        StreamingProvider(),
        FakeTools(),
        FakeMemory(),
        FakeAudit(),
        smart_tools=True,
    )

    assert not agent.can_stream(
        "remember this"
    )

    assert agent.can_stream(
        "how are you"
    )
