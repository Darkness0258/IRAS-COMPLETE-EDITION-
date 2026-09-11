from __future__ import annotations

from iras.core.agent import IRASAgent
from iras.tools.registry import ToolRegistry


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
        return self.messages[
            -limit:
        ]

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
            return [
                {"name": "all"}
            ]

        return [
            {"name": x}
            for x in names
        ]

    def execute(
        self,
        name,
        args,
    ):
        raise AssertionError(
            "tool execution was "
            "not expected"
        )


class FakeReply:
    text = "ok"
    tool_calls = []
    assistant_message = {
        "role": "assistant",
        "content": "ok",
    }


class FakeProvider:
    model = "fake/model"
    last_model = "fake/model"

    def complete(
        self,
        messages,
        tools,
    ):
        self.tools = tools
        return FakeReply()


def make_agent():
    provider = FakeProvider()

    agent = IRASAgent(
        provider,
        FakeTools(),
        FakeMemory(),
        FakeAudit(),
        smart_tools=True,
        context_fact_limit=10,
        context_message_limit=8,
    )

    return agent, provider


def test_casual_chat_sends_no_tools():
    agent, provider = (
        make_agent()
    )

    assert (
        agent.handle("hello")
        == "ok"
    )

    assert provider.tools == []


def test_memory_request_sends_only_memory_tools():
    agent, provider = (
        make_agent()
    )

    agent.handle(
        "remember that my "
        "test code is 42"
    )

    names = {
        item["name"]
        for item in provider.tools
    }

    assert names == {
        "remember_fact",
        "search_memory",
    }


def test_url_request_gets_network_tools():
    agent, provider = (
        make_agent()
    )

    agent.handle(
        "check this website "
        "https://example.com"
    )

    names = {
        item["name"]
        for item in provider.tools
    }

    assert {
        "http_get",
        "open_url",
        "api_request",
    }.issubset(names)
