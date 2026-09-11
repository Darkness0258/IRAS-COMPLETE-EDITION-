# IRAS Provider Stability v2.6.1

The v2.6 device bridge itself is healthy. These responses:

```text
POST /v1/devices/pair 200
GET /v1/device/commands/next?timeout=25 200
```

mean the Windows PC paired successfully and is maintaining its outbound HTTPS
command channel.

The failures after `/v1/chat/stream` are AI-provider failures.

## Gemini 3 tool-call signatures

Gemini 3 requires a `thought_signature` when function calls are replayed during
a multi-step tool turn.

IRAS can fail over from another provider to Gemini in the same tool turn. Such
imported function-call history has no Google signature. v2.6.1 uses Google's
documented compatibility escape hatch:

```text
skip_thought_signature_validator
```

only when no real Google signature is already present. Real signatures are
preserved unchanged.

## Correct HTTP 402 diagnostics

The shared OpenAI-compatible provider previously labeled every 402 response as
an OpenRouter credit problem. v2.6.1 reports the actual provider body instead,
so Cerebras failures can be diagnosed correctly.

## Better `/health`

Provider status now includes:

```text
ready
cooldown_seconds
failures
last_error
```

## Recommended provider order

```text
IRAS_PROVIDER_ORDER=gemini,groq,cerebras,openrouter
```

## Version

```text
IRAS / Windows: 2.6.1
Android: 2.6.1
Android versionCode: 20601
```
