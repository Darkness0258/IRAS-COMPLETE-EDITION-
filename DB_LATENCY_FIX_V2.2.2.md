# IRAS DB Latency Fix v2.2.2

The latency logs identified the bottleneck very clearly:

```text
total=10366ms  model=1029ms
total=10000ms  model=681ms
```

The LLM is already fast. Around 9 seconds per turn were happening outside
the model.

## Root cause

`PostgresMemoryStore` opened a brand-new Supabase/PostgreSQL connection for
every operation:

- save user message
- update adaptive personality
- read facts
- read recent conversation
- save assistant response

Each connection requires network/TLS/Postgres authentication. Render is in
Singapore while the current Supabase pooler hostname is in
`ap-southeast-2` (Sydney), so repeatedly opening connections is especially
expensive.

## Fix

IRAS now keeps one PostgreSQL connection open and reuses it.

If Render or Supabase closes that connection during inactivity, IRAS
automatically reconnects once on the next database query.

Expected warm-request path:

```text
Before:
5-ish DB handshakes + model
≈ 10 seconds

After:
existing DB connection + model
target: roughly 1–3 seconds on warm requests
```

Actual performance depends on Supabase, OpenRouter, network conditions, and
whether Render is waking from a free-tier cold start.

No memory functionality is removed.
