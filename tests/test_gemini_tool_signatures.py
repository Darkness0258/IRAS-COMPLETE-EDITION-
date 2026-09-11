from iras.providers.gemini_compatible import (
    GeminiOpenAICompatibleProvider,
)


def test_gemini_injects_signature_for_imported_tool_call():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "device_open_app",
                        "arguments": '{"app":"vscode"}',
                    },
                }
            ],
        }
    ]

    prepared = (
        GeminiOpenAICompatibleProvider
        .prepare_messages(messages)
    )

    assert (
        prepared[0]["tool_calls"][0]
        ["extra_content"]["google"]
        ["thought_signature"]
        == "skip_thought_signature_validator"
    )

    assert (
        "extra_content"
        not in messages[0]["tool_calls"][0]
    )


def test_gemini_preserves_real_signature():
    real = "opaque-real-signature"

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "extra_content": {
                        "google": {
                            "thought_signature": real
                        }
                    },
                    "function": {
                        "name": "device_open_app",
                        "arguments": "{}",
                    },
                }
            ],
        }
    ]

    prepared = (
        GeminiOpenAICompatibleProvider
        .prepare_messages(messages)
    )

    assert (
        prepared[0]["tool_calls"][0]
        ["extra_content"]["google"]
        ["thought_signature"]
        == real
    )


def test_gemini_does_not_touch_plain_chat():
    messages = [
        {
            "role": "user",
            "content": "hello",
        }
    ]

    prepared = (
        GeminiOpenAICompatibleProvider
        .prepare_messages(messages)
    )

    assert prepared == messages
