from __future__ import annotations

import os

from iras.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


class _OpenRouterModelProvider(
    OpenAICompatibleProvider
):
    def __init__(
        self,
        *args,
        provider_sort: str = "latency",
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )
        self.provider_sort = (
            provider_sort.strip()
        )

    def _payload(
        self,
        messages,
        tools,
    ):
        payload = super()._payload(
            messages,
            tools,
        )

        if (
            self.provider_sort
            and not tools
        ):
            payload["provider"] = {
                "sort": self.provider_sort,
                "allow_fallbacks": True,
            }

        return payload


class OpenRouterProvider(
    OpenAICompatibleProvider
):
    """
    OpenRouter provider with:
    - automatic model fallback
    - persistent HTTP connections
    - latency-prioritized routing for normal chat
    - streaming fallback before the first token
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 90,
        base_url: str = (
            "https://openrouter.ai/api/v1"
        ),
        app_url: str = (
            "https://github.com/"
            "Darkness0258/"
            "IRAS-COMPLETE-EDITION-"
        ),
        app_name: str = "IRAS",
        fallback_models: list[str] | None = None,
    ):
        if not api_key:
            raise ValueError(
                "OpenRouter API key is missing. "
                "Set OPENROUTER_API_KEY in "
                "your .env file."
            )

        max_tokens_raw = os.getenv(
            "IRAS_MAX_OUTPUT_TOKENS",
            "360",
        ).strip()

        try:
            max_tokens = max(
                64,
                int(max_tokens_raw),
            )
        except ValueError:
            max_tokens = 360

        self.provider_sort = os.getenv(
            "IRAS_PROVIDER_SORT",
            "latency",
        ).strip()

        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            extra_headers={
                "HTTP-Referer": app_url,
                "X-Title": app_name,
            },
            max_tokens=max_tokens,
        )

        if fallback_models is None:
            raw = os.getenv(
                "IRAS_FALLBACK_MODELS",
                (
                    "inclusionai/ling-3.0-flash-vl:free,"
                    "google/gemma-4-26b-a4b-it:free,"
                    "openrouter/free"
                ),
            )

            fallback_models = [
                item.strip()
                for item in raw.split(",")
                if item.strip()
            ]

        seen = {model}
        self.fallback_models = []

        for candidate in fallback_models:
            if candidate not in seen:
                seen.add(candidate)
                self.fallback_models.append(
                    candidate
                )

        self.last_model = model
        self._model_providers = {}

    @staticmethod
    def _retryable_error(
        exc: RuntimeError,
    ) -> bool:
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
    ) -> _OpenRouterModelProvider:
        provider = (
            self._model_providers
            .get(model)
        )

        if provider is None:
            provider = (
                _OpenRouterModelProvider(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model=model,
                    timeout=self.timeout,
                    extra_headers=self.extra_headers,
                    max_tokens=self.max_tokens,
                    provider_sort=(
                        self.provider_sort
                    ),
                )
            )

            self._model_providers[
                model
            ] = provider

        return provider

    def complete(
        self,
        messages,
        tools,
    ):
        models = [
            self.model,
            *self.fallback_models,
        ]

        last_error = None

        for index, model in enumerate(
            models
        ):
            provider = (
                self._provider_for_model(
                    model
                )
            )

            try:
                reply = provider.complete(
                    messages,
                    tools,
                )

                self.last_model = (
                    getattr(
                        provider,
                        "last_response_model",
                        None,
                    )
                    or model
                )

                self.last_request_ms = int(
                    getattr(
                        provider,
                        "last_request_ms",
                        0,
                    )
                    or 0
                )

                self.last_first_token_ms = int(
                    getattr(
                        provider,
                        "last_first_token_ms",
                        0,
                    )
                    or 0
                )

                if index > 0:
                    print(
                        "[IRAS MODEL FALLBACK] "
                        "recovered with "
                        f"{self.last_model}",
                        flush=True,
                    )

                return reply

            except RuntimeError as exc:
                last_error = exc

                self.last_request_ms = int(
                    getattr(
                        provider,
                        "last_request_ms",
                        0,
                    )
                    or 0
                )

                if (
                    index
                    >= len(models) - 1
                    or not self
                    ._retryable_error(exc)
                ):
                    raise

                next_model = (
                    models[index + 1]
                )

                print(
                    "[IRAS MODEL FALLBACK] "
                    f"{model} failed: "
                    f"{exc} -> trying "
                    f"{next_model}",
                    flush=True,
                )

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "No OpenRouter model "
            "was available."
        )

    def stream_text(
        self,
        messages,
        tools,
    ):
        """
        Stream from the primary model.

        If the primary fails before emitting any text, IRAS transparently
        moves to the configured fallback. Once text has reached the user,
        switching models would risk duplicate/inconsistent output, so an
        error after the first token is surfaced instead.
        """
        models = [
            self.model,
            *self.fallback_models,
        ]

        last_error = None

        for index, model in enumerate(
            models
        ):
            provider = (
                self._provider_for_model(
                    model
                )
            )
            emitted = False

            try:
                for text in provider.stream_text(
                    messages,
                    tools,
                ):
                    emitted = True
                    yield text

                self.last_model = (
                    getattr(
                        provider,
                        "last_response_model",
                        None,
                    )
                    or model
                )

                self.last_request_ms = int(
                    getattr(
                        provider,
                        "last_request_ms",
                        0,
                    )
                    or 0
                )
                self.last_first_token_ms = int(
                    getattr(
                        provider,
                        "last_first_token_ms",
                        0,
                    )
                    or 0
                )

                if index > 0:
                    print(
                        "[IRAS MODEL FALLBACK] "
                        "stream recovered with "
                        f"{self.last_model}",
                        flush=True,
                    )

                return

            except RuntimeError as exc:
                last_error = exc

                self.last_request_ms = int(
                    getattr(
                        provider,
                        "last_request_ms",
                        0,
                    )
                    or 0
                )
                self.last_first_token_ms = int(
                    getattr(
                        provider,
                        "last_first_token_ms",
                        0,
                    )
                    or 0
                )

                if emitted:
                    raise

                if (
                    index
                    >= len(models) - 1
                    or not self
                    ._retryable_error(exc)
                ):
                    raise

                next_model = (
                    models[index + 1]
                )

                print(
                    "[IRAS MODEL FALLBACK] "
                    f"{model} stream failed "
                    f"before first token: {exc} "
                    f"-> trying {next_model}",
                    flush=True,
                )

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "No OpenRouter model "
            "was available."
        )

    def close(self) -> None:
        for provider in (
            self._model_providers
            .values()
        ):
            close = getattr(
                provider,
                "close",
                None,
            )

            if callable(close):
                close()

        super().close()
