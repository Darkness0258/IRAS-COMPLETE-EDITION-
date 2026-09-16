# IRAS v4.2 RC2 — Provider-aware multi-agent orchestration

IRAS v4.2 RC2 hardens the v4.2 multi-agent DAG runtime after real Render testing exposed a mismatch between task retry timing and AI-provider cooldown timing. The remote wire protocol remains `1`, so existing paired Windows bridges remain compatible.

## What changed

- **Provider-aware graph backpressure.** `ALL_PROVIDERS_UNAVAILABLE` is now treated as temporary infrastructure backpressure instead of an immediate task failure.
- **Cooldown-aware automatic retry.** The orchestrator parses the provider's advertised retry delay, keeps the task queued, and retries after that delay rather than retrying again after roughly one second.
- **Task retry budgets are preserved.** Waiting for provider recovery does not consume the task's normal bounded retry allowance; that allowance remains available for actual execution failures.
- **Bounded waiting.** `IRAS_ORCHESTRATION_PROVIDER_WAIT_SECONDS` defaults to `300` seconds and is bounded to `0..1800`. Once that budget is exhausted, the existing bounded task retry/failure behavior resumes.
- **Visible waiting state.** Task status exposes `waiting_for_provider`, `provider_waits`, and `retry_after_seconds`; the Tasks UI shows a provider-wait state instead of making the graph look permanently failed.
- **No safety weakening.** Dependency gates, request-local remote-device binding, local Windows policy, DPAPI secrets, emergency stop, action replay prevention, pause/resume/cancel, and the v4 remote protocol are unchanged.

## Why RC2 exists

A real v4.2 RC1 goal successfully planned a Coder → Tester → Reviewer → Coordinator graph, but the Coder and Coordinator encountered temporary provider cooldowns. RC1 retried almost immediately, exhausted each task's small retry budget while the providers were still cooling down, then correctly blocked dependent tasks. RC2 aligns orchestration scheduling with provider availability instead of treating cooldown as task logic failure.

## Acceptance target

1. Run `run-v420-validation.ps1` and require a clean pass.
2. Deploy Render and verify `/health` reports `version=4.2.0-rc2` with `remote_protocol=1`.
3. Re-run a bounded multi-agent objective while providers are available.
4. If providers cool down during the run, confirm the Tasks UI shows a waiting state and the graph resumes automatically after cooldown instead of failing immediately.
5. Verify the requested Windows-side result independently and confirm no unrelated changes were made.
