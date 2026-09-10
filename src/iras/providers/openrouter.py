from __future__ import annotations

from iras.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter chat-completions provider with IRAS identification headers."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 90,
        base_url: str = "https://openrouter.ai/api/v1",
        app_url: str = "https://github.com/Darkness0258/IRAS",
        app_name: str = "IRAS",
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
