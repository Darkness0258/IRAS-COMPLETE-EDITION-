IRAS RC6 CANDIDATE — AUTOMATION + WAKE VOICE
=============================================

Validated baseline
------------------
GitHub main commit: a5dbaf36e3a692212c246b1880af674d057ae26b
Current release underneath the candidate: IRAS 5.0.0 RC5
Remote protocol: stays 1

What this update adds
---------------------
1. Persistent automation engine
   - manual trigger
   - one-time trigger
   - interval trigger
   - event trigger with exact JSON field matching
   - natural-language autonomous objective actions
   - recorded verified workflow actions
   - pause / resume / cancel / delete / run-now
   - persistent state, execution leases, bounded worker pool
   - result/error/status history

2. Permission-scoped automation
   - read_only
   - safe_action
   - system_action
   - critical
   - read-only unattended jobs can run normally
   - state-changing unattended jobs require locally armed autonomous Master Control
   - otherwise the job enters waiting_authorization instead of self-elevating
   - scheduled read-only workers stay READ even if Master Control is enabled
   - ToolRegistry, audit, emergency stop, filesystem roots, Remote policy and Windows/UAC remain authoritative

3. Wake voice session
   - normal microphone listen window: 3 seconds
   - saying "IRAS" opens a command session for up to 30 seconds
   - silence still ends individual phrases naturally
   - "done that's all" closes the session immediately
   - also recognizes "that's all", "done iras", and "end session"
   - wake/end control phrases are removed before sending the command to the agent
   - microphone is not placed into an endless capture loop by this update

Optional environment variables
------------------------------
IRAS_WAKE_SESSION=true
IRAS_WAKE_WORDS=iras
IRAS_WAKE_IDLE_SECONDS=3
IRAS_WAKE_ACTIVE_SECONDS=30
IRAS_WAKE_END_PHRASES=done that's all|that's all|done iras|end session
IRAS_V5_AUTOMATION_POLL_SECONDS=2
IRAS_V5_AUTOMATION_WORKERS=4
IRAS_V5_AUTOMATION_WAIT_SECONDS=1800

Apply
-----
1. Extract this ZIP anywhere.
2. Open PowerShell in the extracted folder.
3. Run:

   .\apply-iras-rc6.ps1 -Repo "D:\Projects\IRAS-complete" -Test

The installer refuses a different Git HEAD by default. It also creates a backup at:

   <repo>\.iras_rc6_backup\<timestamp>\

After targeted tests pass, run the complete IRAS release validator:

   cd D:\Projects\IRAS-complete
   .\.venv\Scripts\Activate.ps1
   .\run-v500-validation.ps1

Useful natural-language examples after IRAS starts
--------------------------------------------------
- Every hour check my project health and notify me only if something is wrong.
- At the next scheduled run, inspect my Git projects and prepare a status brief.
- When monitor.changed fires with healthy=false, investigate the failure and notify my phone.
- Create an automation that runs my recorded backup workflow every 6 hours.
- List my automations.
- Pause the health automation.
- Run the project-status automation now.

Voice examples
--------------
Say/click microphone, then:

   IRAS, open Spotify and play Starboy ... done that's all

or:

   IRAS
   open VS Code
   open my IRAS project
   done that's all

Security note
-------------
"From anywhere" means authenticated IRAS Cloud/Web/Android can request work while the paired PC is online. This package deliberately does not create permanent unauthenticated control or bypass UAC/emergency stop. For unattended state-changing local automation, the owner must explicitly arm autonomous Master Control on the PC.
