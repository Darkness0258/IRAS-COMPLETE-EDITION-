from __future__ import annotations

import os

from iras.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider with automatic fallback for transient model failures."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 90,
        base_url: str = "https://openrouter.ai/api/v1",
        app_url: str = "https://github.com/Darkness0258/IRAS-COMPLETE-EDITION-",
        app_name: str = "IRAS",
        fallback_models: list[str] | None = None,
    ):
        if not api_key:
            raise ValueError(
                "OpenRouter API key is missing. Set OPENROUTER_API_KEY in your .env file."
            )

        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            extra_headers={
                "HTTP-Referer": app_url,
                "X-Title": app_name,
            },
        )

        if fallback_models is None:
            raw = os.getenv(
                "IRAS_FALLBACK_MODELS",
                "openrouter/free",
            )
            fallback_models = [
                item.strip()
                for item in raw.split(",")
                if item.strip()
            ]

        seen = {model}
        self.fallback_models: list[str] = []

        for candidate in fallback_models:
            if candidate not in seen:
                seen.add(candidate)
                self.fallback_models.append(candidate)

        self.last_model = model

    @staticmethod
    def _retryable_error(exc: RuntimeError) -> bool:
        text = str(exc)

        if "LLM HTTP 401" in text:
            return False

        retryable_markers = (
            "LLM HTTP 402",
            "LLM HTTP 404",
            "LLM HTTP 408",
            "LLM HTTP 409",
            "LLM HTTP 429",
            "LLM HTTP 500",
            "LLM HTTP 502",
            "LLM HTTP 503",
            "LLM HTTP 504",
            "LLM request timed out",
            "LLM network error",
        )

        return any(
            marker in text
            for marker in retryable_markers
        )

    def _provider_for_model(
        self,
        model: str,
    ) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            base_url=self.base_url,
            api_key=self.api_key,
            model=model,
            timeout=self.timeout,
            extra_headers=self.extra_headers,
        )

    def complete(self, messages, tools):
        models = [
            self.model,
            *self.fallback_models,
        ]

        last_error: RuntimeError | None = None

        for index, model in enumerate(models):
            try:
                reply = (
                    self
                    ._provider_for_model(model)
                    .complete(messages, tools)
                )

                self.last_model = model

                if index > 0:
                    print(
                        "[IRAS MODEL FALLBACK] "
                        f"recovered with {model}",
                        flush=True,
                    )

                return reply

            except RuntimeError as exc:
                last_error = exc

                if (
                    index >= len(models) - 1
                    or not self._retryable_error(exc)
                ):
                    raise

                next_model = models[index + 1]

                print(
                    "[IRAS MODEL FALLBACK] "
                    f"{model} failed: {exc} "
                    f"-> trying {next_model}",
                    flush=True,
                )

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "No OpenRouter model was available."
        )
