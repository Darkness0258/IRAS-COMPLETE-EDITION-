# IRAS Multi-Provider Failover v2.4.0

IRAS can now fail over across independent AI providers instead of depending on one OpenRouter quota.

Default order:

```text
Groq -> Cerebras -> Cloudflare Workers AI -> Gemini -> OpenRouter
```

Only providers whose credentials are configured are enabled.

## Render variables

```text
IRAS_PROVIDER=multi
IRAS_PROVIDER_ORDER=groq,cerebras,cloudflare,gemini,openrouter
IRAS_PROVIDER_COOLDOWN_SECONDS=60
```

### Groq

```text
GROQ_API_KEY=...
GROQ_MODEL=qwen/qwen3.8-27b
```

### Cerebras

```text
CEREBRAS_API_KEY=...
CEREBRAS_MODEL=gpt-oss-120b
```

### Cloudflare Workers AI

```text
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_MODEL=@cf/zai-org/glm-4.7-flash
```

### Gemini

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.8-flash
```

### OpenRouter

Existing variables remain valid:

```text
OPENROUTER_API_KEY=...
IRAS_OPENROUTER_MODEL=nex-agi/nex-n2.5-mini:free
IRAS_FALLBACK_MODELS=inclusionai/ling-3.0-flash-vl:free,google/gemma-4-26b-a4b-it:free,openrouter/free
```

## Behavior

A provider that returns rate-limit, authentication, quota, network, or server errors is temporarily cooled down and skipped on later requests. IRAS switches providers during streaming only before the first visible token.

`/health` reports provider names/models/readiness, but never keys or tokens.
