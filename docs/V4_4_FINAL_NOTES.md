# IRAS v4.4.0 FINAL — Persistent Autonomy Production Hardening

v4.4 FINAL freezes the persistent-autonomy architecture after the RC1/RC2 acceptance cycle.

## Provider health

- Providers are **CONFIGURED** until an authenticated active probe or real request verifies them.
- The Providers panel performs low-cost `/models` probes for OpenAI-compatible cloud providers without generating text.
- Health telemetry includes last probe, last success/failure, latency, rolling success rate, cooldown, route rank, and recent outcomes.
- Multi-agent worker pools share provider health/cooldown state inside the cloud process, so one worker's rate limit immediately informs sibling workers and the status panel.
- Routing remains deterministic when providers are untested, but repeated failures/latency can demote a provider behind healthier fallbacks.
- Device Ollama remains a separately verified fallback through the outbound-only Windows bridge.

## Persistent autonomous jobs

- Checkpoints continue to mirror to `data/orchestration_runs.json` for local development.
- When `DATABASE_URL` is configured, checkpoints are also persisted to PostgreSQL in `iras_orchestration_journal`, making recovery independent of Render's ephemeral filesystem.
- Completed nodes remain completed after restart; in-flight nodes are marked interrupted and require explicit Resume.
- Remote-session credentials are never persisted and must be freshly authorized before resumed state-changing work.
- Retry Failed preserves successful checkpoint nodes.

## Guarded rollback

Engineering preflight captures a full Git HEAD hash and whether the working tree was initially clean. The Tasks panel now offers **Rollback** after terminal jobs.

Rollback is deliberately conservative:

- requires a live FULL Remote session / CRITICAL permission;
- works only if the project was clean at job start;
- refuses if Git HEAD changed since the checkpoint;
- restores tracked files only with `git restore`;
- never rewrites commits;
- never deletes untracked files.

## Long-running UI reliability

Main-chat and Tasks watchers now remain active for up to eight hours, matching the long provider-recovery window instead of silently giving up after 30 minutes.

## Compatibility

Remote protocol remains `1`. Existing paired Windows devices do not need to be re-paired. Restart the bridge after installing the FINAL package so it loads the new guarded Git actions.

## Final acceptance smoke

After deployment, run `run-v440-final-real-device-smoke.ps1`. Then use the Providers panel's **Probe Now** button and verify one long engineering goal can run while a second normal Windows command (for example opening Calculator) succeeds concurrently.
