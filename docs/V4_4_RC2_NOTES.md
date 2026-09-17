# IRAS v4.4.0 RC2 — Provider Status + CI Hotfix

RC2 is a narrow stabilization release on top of v4.4 RC1.

## Fixes

- GitHub Actions now validates the current v4.4 release with `run-v440-validation.ps1` instead of the stale v4.3 RC8 validator.
- Provider status rows are de-duplicated by logical provider identity on the server.
- The web Providers panel also de-duplicates defensively and ignores stale concurrent refresh responses.
- Provider cards are rendered atomically with `replaceChildren`, preventing duplicate cards when two status refreshes overlap.
- Ollama/device-local telemetry is merged into one logical Ollama provider card.
- Existing persistent-job, restart-resume, retry-failed, rollback metadata, responsive bridge, Remote authorization, and protocol v1 behavior are unchanged.

## Compatibility

Remote protocol remains `1`; no device re-pairing is required.
