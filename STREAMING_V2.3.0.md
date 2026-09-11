# IRAS True Streaming v2.3.0

## What changes

IRAS now has a streaming endpoint:

```text
POST /v1/chat/stream
Content-Type: application/json
Accept: text/event-stream
```

The backend uses OpenRouter's documented `stream: true` chat-completions mode
for ordinary no-tool conversation.

The server emits SSE events:

```text
event: start
event: token
event: done
event: error
```

## Tool safety

Normal conversation streams directly.

Turns that need memory/personality/web/API tools continue through the existing
permissioned agent loop. Their completed answer is sent through the same SSE
protocol so all clients can use one endpoint without weakening tool safety.

## Model fallback

If the primary free model gets a 429/provider failure before the first text
token, IRAS automatically tries the configured fallback model.

After any text has already reached the user, IRAS does not swap models mid-
sentence because that could duplicate or contradict the partial response.

## Web

The web client:

- renders tokens as they arrive
- shows a live cursor
- reports first-token/total timing
- starts IRAS voice sentence-by-sentence instead of waiting for the whole answer
- keeps the same server-generated JennyNeural voice

## Windows EXE

The desktop client now streams text live. It speaks the complete response after
the stream completes to keep local playback stable.

The Windows client also reuses one HTTP connection to the Render server.

## Android APK

The Android client now reads the SSE stream line-by-line and updates the IRAS
message while text arrives. It generates the same IRAS voice after the text
stream finishes.

## Logs

Normal streaming requests now produce:

```text
[IRAS STREAM] first_token=...ms total=...ms model=...ms model_used=...
```

This is the metric that matters for perceived speed.
