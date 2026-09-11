# IRAS Model Fallback v2.1.3

IRAS now supports automatic OpenRouter model fallback.

Recommended Render configuration:

```text
IRAS_MODEL=nex-agi/nex-n2.5-mini:free
IRAS_FALLBACK_MODELS=openrouter/free
```

Request flow:

```text
Nex-N2.5-Mini
      |
      | 429 / provider outage / timeout
      v
openrouter/free
      |
      v
normal IRAS response
```

IRAS automatically falls back for transient conditions including HTTP 429 rate limits, provider 5xx errors, timeouts, network errors, and unavailable models. HTTP 401 does not trigger fallback because an invalid API key would fail for every model.

The selected fallback is visible in Render logs as `[IRAS MODEL FALLBACK] ...`.
