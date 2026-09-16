# IRAS v4.0.0 RC2 Notes

RC2 hardens the Render-to-Windows boundary discovered during the previous release-candidate acceptance work. It intentionally remains a release candidate until the real Windows + hosted Render acceptance checklist is completed.

## Fixed in RC2

- Added an explicit versioned remote-cloud contract: `service_id=iras-cloud`, `remote_protocol=1`, and the deployed IRAS version are exposed by `/health`.
- Windows bridge configuration now preflights the cloud before saving configuration.
- The setup preflight verifies both the v4 protocol contract and `IRAS_API_TOKEN` through the authenticated device API.
- Old v3.x, wrong-service, missing-protocol, and stale Render deployments fail with actionable errors instead of entering an ambiguous reconnect loop.
- Device pairing is bidirectional: the Windows bridge sends `remote_protocol`, and the cloud rejects mismatched clients with HTTP 409.
- The bridge persists the verified cloud version/protocol and exposes them through `iras-device --status`.
- `iras --doctor` now has a separate **Remote protocol compatible** check so simple HTTP reachability is not mistaken for a compatible deployment.
- Direct `iras-device --configure` now requires a 32+ character master token, matching the Windows setup contract.

## Validation in this package

- v4 integrated validator: PASS
- Python compile validation: PASS
- Full regression suite: 615 passed
- Clean-tree/release-hygiene validator: run after packaging cleanup

## Still requires the real target environment

The following cannot be truthfully proven from the build container and remain final v4.0 acceptance items:

1. Deploy this RC2 code to the actual Render service and confirm `/health` reports `version=4.0.0-rc2`, `service_id=iras-cloud`, `remote_protocol=1`.
2. Run Windows setup against that Render URL and verify pairing.
3. Verify a remote read-only command and screen preview.
4. Verify one reversible `control` action such as opening Notepad and confirming its foreground title.
5. Trip the local emergency stop and confirm the same remote action is blocked.
6. Run the target-machine multimodal cold/warm smoke checks.

Do not tag v4.0.0 final until those acceptance checks pass.

## 2026-09-16 CI / Windows setup hotfix

The hosted RC2 acceptance pass exposed four legacy Windows setup contract tests that still represented useful production guarantees. The setup script now preserves those guarantees instead of weakening the tests:

- Probe `/health` before requesting `IRAS_API_TOKEN`, so stale or wrong Render deployments fail without asking for a secret.
- Require the v4 service identity and remote protocol during the PowerShell preflight as well as in the Python bridge handshake.
- Fall back to `python -m iras.device_bridge.agent` when the `iras-device` console entry point is missing from `PATH`.
- Register the scheduled task correctly for both the console-entry-point and Python-module launch paths.

The complete Python regression suite is 619/619 passing with the previously failing `test_remote_setup_script_v400.py` contract restored.

## Final acceptance hotfix (2026-09-16)

Real hosted RC2 acceptance proved cloud-to-Windows status, app launch, typing, protocol compatibility, DPAPI secret protection, and startup-task registration. Two last-mile issues were addressed without changing the remote protocol:

- Descriptive screenshot requests (for example, "take a screenshot and describe what is open") now route to `device_computer_observe`, so the cloud model receives UIA/OmniParser scene data instead of only a Windows-local screenshot path. Plain screenshot requests still use `device_capture_screen` and save a durable local image.
- The persistent bridge scheduled task now starts through hidden PowerShell while retaining `Interactive` logon type. This removes the long-running visible console without moving the bridge out of the desktop session required for screenshots and UI control.

The complete regression suite after this hotfix is 623 passing tests.
