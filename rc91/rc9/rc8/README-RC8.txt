IRAS RC8 CANDIDATE — PRODUCTION STRENGTHENING OVERLAY
====================================================

What this package adds
----------------------
1. Durable execution journals + crash/resume checkpoints + idempotency keys
2. Context compiler with token budgets over scalable RC7 memory
3. Provenance/taint labels + prompt-injection containment + memory admission checks
4. MCP 2026-07-28 bounded client interoperability
5. A2A v1.0 Agent Card discovery + message delegation client
6. Persistent eval suites + weighted regression/promotion gates
7. Secure replay-resistant webhook ingress for RC6 event automations
8. Structured EventBus trace timeline for debugging/evals

It is cumulative
----------------
If RC6/RC7 are not present, apply-iras-rc8.ps1 installs the bundled RC7 package first;
that RC7 package installs RC6 automatically if required.

Apply
-----
PowerShell:

  cd <folder where this ZIP was extracted>

  .\apply-iras-rc8.ps1 `
    -Repo "D:\Projects\IRAS-complete" `
    -Test

Then run the full existing regression suite:

  cd D:\Projects\IRAS-complete
  .\.venv\Scripts\Activate.ps1
  .\run-v500-validation.ps1

If .venv is missing:

  py -3.14 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  pip install -e ".[all,cloud]"

Secure webhook example
----------------------
First ask IRAS to create an RC8 webhook using v5_rc8_webhook_create. It will return
a secret token only once. Then call the deployed cloud service:

  POST https://<your-iras-cloud>/v1/automation-hooks/<hook_id>
  Authorization: Bearer <one-time-shown-token>
  Content-Type: application/json

  {
    "event_id": "phone-20260922-001",
    "payload": {"event": "arrived_home"}
  }

Use that event name in an RC6 event automation. Even when an external webhook fires,
the automation's declared permission cap and Master/Remote/UAC/emergency-stop gates remain final.

Interop
-------
MCP endpoints are explicitly registered and use the 2026-07-28 stateless request headers.
A2A endpoints are explicitly registered and use A2A v1.0 Agent Card discovery / message send.
Credentials are symbolic vault references; they are not stored in the interop table.

Important boundaries
--------------------
- Remote protocol stays 1.
- This does not bypass ToolRegistry, Remote authorization, Master Control, UAC, audit,
  filesystem roots, Emergency Stop, or verification.
- Prompt-injection heuristics are defense-in-depth, not perfect detection.
- MCP/A2A support is a bounded interoperable client surface, not a claim of TCK certification.
- Durable journals do not automatically replay state-changing side effects.

Rollback RC8 only
-----------------
  .\restore-iras-rc8.ps1 -Repo "D:\Projects\IRAS-complete"

This restores the three modified RC8 integration files and removes RC8-added files.
RC6 and RC7 remain installed.
