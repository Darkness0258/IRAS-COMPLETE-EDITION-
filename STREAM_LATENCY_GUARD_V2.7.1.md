# IRAS v2.7.1 — Stream Latency Guard

The Render logs show `/v1/chat/stream` returning HTTP 200 immediately while the
browser remains on `IRAS is thinking...`. There is no matching stream-complete
or provider-failover line.

The streaming provider currently inherits `IRAS_REQUEST_TIMEOUT`, whose default
is 90 seconds. A provider that accepts the HTTP request but does not produce a
useful token can therefore hold the request for far too long. The cloud also
serializes agent turns behind one lock, so one stalled stream can delay the next
message.

v2.7.1 adds these defaults:

```text
IRAS_FIRST_TOKEN_TIMEOUT=8
IRAS_STREAM_READ_TIMEOUT=10
IRAS_CHAT_LOCK_TIMEOUT=12
```

A provider that does not produce a useful first token quickly is failed and the
multi-provider layer can move to the next provider.

Recommended Render configuration:

```text
IRAS_PROVIDER_ORDER=groq,gemini,cerebras,openrouter
IRAS_FIRST_TOKEN_TIMEOUT=8
IRAS_STREAM_READ_TIMEOUT=10
IRAS_CHAT_LOCK_TIMEOUT=12
IRAS_REQUEST_TIMEOUT=30
```

Groq is placed first for latency. If its free quota is rate-limited, its 429
normally arrives quickly and failover continues to Gemini.

Version:

```text
IRAS / Windows: 2.7.1
Android: 2.7.1
Android versionCode: 20701
```
