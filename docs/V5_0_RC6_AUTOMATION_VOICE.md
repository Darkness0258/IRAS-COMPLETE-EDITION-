# IRAS RC6 Candidate — Automation Engine + Wake Voice Session

This update extends the existing v5 operating layer without changing Remote protocol `1`.

## Automation engine

IRAS gains persistent automations with four trigger types: `manual`, `once`, `interval`, and `event`. Actions can be either a natural-language autonomous objective (`prompt`) or a previously recorded verified workflow (`workflow`). Automations have an explicit maximum permission mode: `read_only`, `safe_action`, `system_action`, or `critical`.

Authority remains fail-closed. Read-only automations may run unattended. State-changing unattended automations require autonomous Master Control to be armed locally on the owner PC. If it is not armed, the run moves to `waiting_authorization`; it does not self-elevate. Interactive runs still pass through the normal ToolRegistry, Remote-session, local-policy, emergency-stop, filesystem-root, audit, and Windows/UAC gates.

Model-facing controls are added for listing, creating, running, pausing, resuming, cancelling, deleting, and emitting automation events. Existing recorded workflows can therefore become verified reusable automations.

## Voice behavior

The microphone path now uses a short idle window by default:

- normal listen window: **3 seconds**;
- saying **IRAS** opens a **30-second** command session;
- the session ends immediately on phrases such as **"done that's all"**, **"that's all"**, **"done IRAS"**, or **"end session"**;
- the wake word and end phrase are stripped before the command is dispatched;
- barge-in and the existing full-duplex runtime remain supported.

Environment overrides:

```env
IRAS_WAKE_SESSION=true
IRAS_WAKE_WORDS=iras
IRAS_WAKE_IDLE_SECONDS=3
IRAS_WAKE_ACTIVE_SECONDS=30
IRAS_WAKE_END_PHRASES=done that's all|that's all|done iras|end session
```

Set `IRAS_WAKE_SESSION=false` to restore the previous single long microphone capture behavior.

## Safety invariant

This update does not create an "always trusted" cloud process. Remote protocol remains `1`; a cloud or model request cannot mint its own Windows authority. Unattended state changes must be explicitly armed on the PC, and emergency stop remains authoritative below the automation planner.
