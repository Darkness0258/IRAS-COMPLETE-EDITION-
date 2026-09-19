# IRAS RC3 Cloud AI Agent

IRAS Cloud is not only a chat endpoint. RC3 runs the same tool-capable agent loop used by the local runtime and can delegate verified work to the paired Windows node.

## Reasoning route

1. Use the configured cloud provider pool first.
2. If the entire cloud pool is unavailable or rate-limited before a response is produced, fail over to the paired PC's Ollama through the outbound device bridge.
3. Tool calls proposed by the local fallback still pass through the normal IRAS Remote permission/session policy. Device Ollama itself is a READ-level action and does not grant extra execution authority.

The paired-device fallback is controlled by `IRAS_DEVICE_OLLAMA_FALLBACK` (default `true`) and `IRAS_DEVICE_OLLAMA_MODEL`.

## Verified device work

Cloud uses the existing deterministic/specialized executors where possible, including Quick Code and the Spotify semantic workflow. If a legacy/stale Spotify bridge returns only "command sent" without the RC3 verification payload, Cloud requests one fresh `computer_observe` pass with vision forced on. It accepts playback only when Spotify is foregrounded, a visible Pause state exists, and query evidence appears in a likely now-playing region. Library/search text alone does not count as playback proof.

## Status

From the Windows cloud client:

```text
/agent
```

The server endpoint is `GET /v1/agent/status` and reports the cloud-agent mode, current provider route, paired-device Ollama readiness, deterministic executor set, Master Control support, and Remote protocol.

## Master Control

A verified Master session can raise tool authority and task budgets, but it does not change the provider failover security model. Emergency stop, Remote authentication, filesystem roots, Windows/UAC, and audit boundaries remain in force.
