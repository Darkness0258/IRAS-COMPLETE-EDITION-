# IRAS Latency Optimization v2.2.0

This patch targets warm-server response latency without removing IRAS's
shared memory, personality, voice, or tool capabilities.

## Changes

### 1. Persistent OpenRouter connections

IRAS now reuses `httpx.Client` connections instead of creating a fresh
TCP/TLS connection for each LLM call.

### 2. Smart tool loading

The cloud agent no longer sends every tool schema on ordinary conversation.

Examples:

```text
hello
how are you
explain recursion
```

send **0 tool schemas**.

Memory requests load only memory tools, personality requests load only
personality tools, and explicit URL/API requests load the relevant network
tools.

This reduces prompt size and avoids unnecessary tool-routing overhead.

### 3. Smaller conversation context

Cloud defaults:

```text
IRAS_CONTEXT_MESSAGES=8
IRAS_CONTEXT_FACTS=10
```

Previous behavior sent up to 12 messages and 20 facts.

### 4. Latency-first provider routing

For normal conversation with no tools:

```text
IRAS_PROVIDER_SORT=latency
```

Tool-calling requests leave provider routing to OpenRouter's tool-aware
routing instead.

### 5. Short-output cap

Default:

```text
IRAS_MAX_OUTPUT_TOKENS=360
```

This suits IRAS's short/simple conversational style while still allowing
useful technical answers. Increase it if you want longer answers.

### 6. Built-in latency measurements

Render logs now include lines like:

```text
[IRAS LATENCY] total=3420ms model=3010ms tools=0 rounds=0 model_used=...
```

The `/v1/chat` JSON response also includes:

```text
timing_ms
model_ms
tool_schema_count
model
```

This lets us identify the real bottleneck instead of guessing.

## Recommended Render variables

```text
IRAS_MODEL=nex-agi/nex-n2.5-mini:free
IRAS_FALLBACK_MODELS=openrouter/free

IRAS_SMART_TOOLS=true
IRAS_CONTEXT_MESSAGES=8
IRAS_CONTEXT_FACTS=10
IRAS_PROVIDER_SORT=latency
IRAS_MAX_OUTPUT_TOKENS=360
```

## Render Free cold starts

This patch improves a server that is already awake.

It cannot remove Render Free's platform cold start after the service has
spun down. A first request after inactivity may still be much slower than
normal warm requests.
