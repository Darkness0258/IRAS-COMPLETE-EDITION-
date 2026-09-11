from __future__ import annotations

from copy import deepcopy
import os

from iras.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


class GeminiOpenAICompatibleProvider(
    OpenAICompatibleProvider
):
    # Gemini 3.x requires a thought signature when replaying function calls.
    DUMMY_THOUGHT_SIGNATURE = (
        "skip_thought_signature_validator"
    )

    @staticmethod
    def _has_google_signature(
        tool_call: dict,
    ) -> bool:
        try:
            return bool(
                tool_call["extra_content"]
                ["google"]["thought_signature"]
            )
        except (
            KeyError,
            TypeError,
        ):
            return False

    @classmethod
    def prepare_messages(
        cls,
        messages: list[dict],
    ) -> list[dict]:
        prepared = deepcopy(messages)

        for message in prepared:
            if message.get("role") not in {
                "assistant",
                "model",
            }:
                continue

            calls = message.get("tool_calls") or []

            if not calls:
                continue

            if any(
                cls._has_google_signature(call)
                for call in calls
                if isinstance(call, dict)
            ):
                continue

            first = next(
                (
                    call
                    for call in calls
                    if isinstance(call, dict)
                ),
                None,
            )

            if first is None:
                continue

            extra = first.setdefault(
                "extra_content",
                {},
            )
            google = extra.setdefault(
                "google",
                {},
            )
            google.setdefault(
                "thought_signature",
                cls.DUMMY_THOUGHT_SIGNATURE,
            )

        return prepared

    def _payload(
        self,
        messages,
        tools,
    ):
        payload = super()._payload(
            self.prepare_messages(messages),
            tools,
        )

        effort = os.getenv(
            "GEMINI_REASONING_EFFORT",
            "low",
        ).strip().lower()

        if effort in {
            "minimal",
            "low",
            "medium",
            "high",
        }:
            payload["reasoning_effort"] = effort

        return payload
