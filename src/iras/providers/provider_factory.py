from __future__ import annotations

import os

from iras.providers.multi_provider import MultiProvider, ProviderSlot
from iras.providers.openai_compatible import OpenAICompatibleProvider
from iras.providers.gemini_compatible import GeminiOpenAICompatibleProvider
from iras.providers.openrouter import OpenRouterProvider


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _max_tokens() -> int:
    try:
        return max(64, int(_env("IRAS_MAX_OUTPUT_TOKENS", "360")))
    except ValueError:
        return 360


def _openai_provider(*, api_key: str, base_url: str, model: str, timeout: float):
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_tokens=_max_tokens(),
    )


def build_multi_provider(settings) -> MultiProvider:
    providers = {}

    groq_key = _env("GROQ_API_KEY")
    if groq_key:
        providers["groq"] = _openai_provider(
            api_key=groq_key,
            base_url=_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            model=_env("GROQ_MODEL", "qwen/qwen3.8-27b"),
            timeout=settings.request_timeout,
        )

    cerebras_key = _env("CEREBRAS_API_KEY")
    if cerebras_key:
        providers["cerebras"] = _openai_provider(
            api_key=cerebras_key,
            base_url=_env("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
            model=_env("CEREBRAS_MODEL", "gpt-oss-120b"),
            timeout=settings.request_timeout,
        )

    cloudflare_token = _env("CLOUDFLARE_API_TOKEN")
    cloudflare_account = _env("CLOUDFLARE_ACCOUNT_ID")
    if cloudflare_token and cloudflare_account:
        providers["cloudflare"] = _openai_provider(
            api_key=cloudflare_token,
            base_url=_env(
                "CLOUDFLARE_AI_BASE_URL",
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{cloudflare_account}/ai/v1",
            ),
            model=_env("CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash"),
            timeout=settings.request_timeout,
        )

    gemini_key = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    if gemini_key:
        providers["gemini"] = GeminiOpenAICompatibleProvider(
            api_key=gemini_key,
            base_url=_env(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            model=_env("GEMINI_MODEL", "gemini-3.8-flash"),
            timeout=settings.request_timeout,
            max_tokens=_max_tokens(),
        )

    openrouter_key = _env("OPENROUTER_API_KEY") or (
        settings.api_key if settings.provider in {"openrouter", "multi"} else ""
    )
    if openrouter_key:
        providers["openrouter"] = OpenRouterProvider(
            api_key=openrouter_key,
            model=_env("IRAS_OPENROUTER_MODEL", settings.model),
            timeout=settings.request_timeout,
            base_url=_env(
                "IRAS_OPENROUTER_BASE_URL",
                "https://openrouter.ai/api/v1",
            ),
            app_name=settings.system_name,
        )

    raw_order = _env(
        "IRAS_PROVIDER_ORDER",
        "groq,cerebras,cloudflare,gemini,openrouter",
    )
    order = [item.strip().lower() for item in raw_order.split(",") if item.strip()]

    ordered_names = []
    for name in order:
        if name in providers and name not in ordered_names:
            ordered_names.append(name)
    for name in providers:
        if name not in ordered_names:
            ordered_names.append(name)

    slots = [ProviderSlot(name=name, provider=providers[name]) for name in ordered_names]

    if not slots:
        raise ValueError(
            "IRAS_PROVIDER=multi but no provider keys are configured. Set at least "
            "one of GROQ_API_KEY, CEREBRAS_API_KEY, CLOUDFLARE_API_TOKEN + "
            "CLOUDFLARE_ACCOUNT_ID, GEMINI_API_KEY, or OPENROUTER_API_KEY."
        )

    print(
        "[IRAS PROVIDERS] configured: "
        + " -> ".join(slot.name for slot in slots),
        flush=True,
    )

    return MultiProvider(slots)
