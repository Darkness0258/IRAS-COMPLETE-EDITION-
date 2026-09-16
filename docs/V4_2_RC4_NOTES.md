# IRAS v4.2.0 RC4 — Direct deterministic parity

RC4 closes the reliability gap between normal Direct/Cloud chat and the v4.2 multi-agent executor.

## What changed

- Normal `/v1/chat` and `/v1/chat/stream` recognize the same narrow exact-text-file objective used by the multi-agent deterministic fallback.
- Direct exact-file work now runs `write_text` → `read_text` exact verification → `git_status` review without an LLM call.
- State-changing work still requires a live FULL IRAS Remote session and still traverses the authenticated Windows command queue, permission classification, allowed-root enforcement, local policy, and emergency stop.
- When the Remote session is missing, Direct mode returns a clear activation message instead of falling through to an AI provider.
- General conversation and open-ended reasoning still require the configured AI provider pool; IRAS does not fabricate reasoning during provider outages.

Remote protocol remains version `1`.
