# IRAS v3.6.0 — Cross-App Workflow Memory

v3.6.0 completes the v3.5 recovery-intelligence line and adds verified, session-scoped cross-app workflow memory.

## What changed

### Stale recovery learning protection

Recovery-route history now records consecutive verified success/failure streaks. When an app update or accessibility change causes a previously successful contextual route to fail repeatedly, the learned score influence is degraded and then quarantined. This suppresses stale history without blocking a route that is still supported by the current live UI.

### Verified cross-app handoff memory

A `CrossAppWorkflowMemory` instance lives only for the current autonomous workflow. It can carry semantically verified facts across app switches together with provenance: source app, source observation, and verification predicate. Unverified targets are not inserted into the handoff memory.

The planner receives the compact handoff after it changes. This lets a verified result from one app inform the next app without pretending that the destination UI has already been observed.

### Safety and privacy invariants

- Workflow handoff memory is session-only and is never written to the persistent recovery-learning JSON.
- Cross-app memory does not grant tool authorization.
- The destination app must still be freshly observed and targets re-grounded before action.
- Failed state-changing actions are never replayed automatically.
- Learned recovery history is advisory; current UI evidence and controller hard exclusions remain authoritative.
- Persistent recovery context remains privacy-bounded to whitelisted app identity and coarse UIA/vision/semantic flags.

## Validate

```powershell
.\run-v360-validation.ps1
```

The runner performs the integrated v3.6 checks and then executes the full pytest regression suite.
