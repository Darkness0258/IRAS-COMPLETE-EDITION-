# IRAS Title + Rate-Limit Fix v2.3.4

## Titles are allowed

IRAS no longer strips:

```text
boss
sir
master
```

If the user explicitly requests one, IRAS stores it as:

```text
user.preferred_title
```

in shared memory.

## "who am i" uses memory tools

`who am i` is now recognized as a memory-aware request.

## Better free-model fallback chain

Default fallback order:

```text
inclusionai/ling-3.0-flash-vl:free
google/gemma-4-26b-a4b-it:free
openrouter/free
```

## Rate-limit error handling

If every available OpenRouter route returns HTTP 429, the cloud API now reports
a clear rate-limit message instead of a generic connection failure.

Important: an account-level OpenRouter free-tier quota cannot be bypassed by
switching between OpenRouter free models.
