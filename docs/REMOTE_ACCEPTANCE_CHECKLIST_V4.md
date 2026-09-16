# IRAS v4 Real-Device Acceptance Checklist

Run this only after `run-v400-validation.ps1` passes.

1. `iras --doctor` — inspect warnings and confirm remote server HTTPS/token/bridge configuration. **Remote protocol compatible** must report the deployed v4 cloud version and `remote_protocol=1`; if it does not, redeploy Render before continuing.
2. `iras --remote-status` — confirm the intended local mode and high-risk opt-ins.
3. Start/verify the scheduled bridge: `iras-device --status` and Task Scheduler entry `IRAS Remote Windows Agent`.
4. From the hosted web client create a short-lived Remote session and request **Screen**.
5. Ask: `Tell me the Windows hostname and foreground app. Do not change anything.`
6. Ask a reversible control task such as opening Notepad, then verify the foreground title.
7. On the laptop run `iras --emergency-stop`; repeat a control request remotely and confirm it fails.
8. Locally run `iras --emergency-clear`, re-arm remote policy, and revoke the old cloud session before creating a new one.
9. If full file access is intended, create/delete only a disposable test file inside an allowed root.
10. If power/command opt-ins are intended, validate them separately only when interruption is acceptable.

Never use the acceptance test to bypass the Windows login/UAC secure desktop. IRAS intentionally does not implement that behavior.
