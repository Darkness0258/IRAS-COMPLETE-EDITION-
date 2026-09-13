# IRAS v3.4.2 — Real-Device Reliability Hotfix

This patch is based on real Windows testing of IRAS v3.4.1.

## Spotify finding

A semantic action such as opening the Spotify profile menu can succeed while the user's compound goal (`Open Spotify and open Settings`) is still incomplete.

v3.4.2 distinguishes **action-level verification** from **goal-level completion**. For compound GUI goals, IRAS requires a fresh `device_observe_ui` checkpoint after verified semantic actions. If the terminal requested semantic target has not been acted on, the planner must continue instead of finalizing.

Incomplete compound workflows are not persisted as learned skills.

## WhatsApp finding

Some rendered desktop applications expose few or no useful controls through Windows UI Automation even though the human-visible UI is present.

v3.4.2 now reports:

- `accessibility_available`
- `accessibility_status`
- `accessibility_reason`
- `vision_fallback_recommended`

An empty UIA tree is explicitly **not** treated as proof that the app is visually blank. Screenshot capture remains evidence/audit data; this patch does not pretend the text-only planner can understand screenshot pixels.

No raw coordinates are invented and no permission boundary is bypassed.

## Scope

v3.4.2 is intentionally a reliability hotfix, not the full v3.5 outcome engine or v3.7 multimodal vision system.
