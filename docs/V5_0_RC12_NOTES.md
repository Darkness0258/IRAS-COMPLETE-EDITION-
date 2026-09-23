# IRAS v5.0 RC12 — Goal Continuity Ledger

RC12 builds on RC11 desktop perception and deliberate repair by adding restart-safe goal execution continuity. It does not add authority and does not change Remote Protocol 1.

## Added

- Persistent Goal Continuity Ledger backed by the existing SQLite/PostgreSQL v5 state layer.
- Goal → observation → action → verification → repair/checkpoint history with bounded summaries and confidence.
- Restart/idempotency support through optional `run_key` values.
- Freshness-aware resume decisions: `continue`, `verify`, `repair`, `reobserve`, or `stop`.
- World-fingerprint change detection so a resumed task re-observes instead of trusting stale desktop assumptions.
- Explicit terminal blocker/completion/cancellation states.
- Completion requires explicit verified evidence in the ledger.
- Side-effect replay is always disabled; the continuity layer never executes tools itself.
- Permission bypass is always disabled; all real actions still pass through the existing ToolRegistry/Remote/Master enforcement layers.
- Seven model-facing continuity tools for status, begin, list, get, record, assess, and cancel.
- Secret-like metadata/payload keys are redacted before persistence (passwords, tokens, API keys, Authorization and cookies).

## Safety and compatibility contract

- Remote Protocol remains `1`.
- No new external authority is granted by a continuity record.
- A restart never means “repeat the last click/command/send”. RC12 assesses evidence freshness first.
- Permission, authentication, UAC, emergency-stop, local policy, and Master/Remote boundaries remain unchanged.
- RC11 calm deliberate repair remains the failure-analysis layer; RC12 supplies the persistent execution context around it.

## Expected regression delta

RC11 baseline: 932 passed, 2 skipped.
RC12 adds six deterministic continuity tests, so the expected full local suite is 938 passed, 2 skipped if no environment-dependent tests change.
