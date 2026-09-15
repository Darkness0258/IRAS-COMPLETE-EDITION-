# IRAS v3.6.0 — Bounded Autonomous Decision Layer

IRAS can now choose routine next steps inside a user-authorized goal instead of requiring the user to micromanage every action.

## What IRAS may decide by itself

- Resolve obvious conversational follow-ups from trusted session context, such as `now play music in it` after Spotify has been verified as the active media app.
- Choose the next smallest safe/reversible tool step inside the user's current goal.
- Prefer a read-only observation when live state can resolve ambiguity.
- Adapt to a failed route without repeating the identical failed state-changing action.
- Carry verification-backed cross-app facts through the current IRAS session when the user explicitly continues the same task.
- Answer its own runtime version locally without spending an LLM request.
- Suppress leaked planner scratchpad/self-talk and request a clean tool/action turn instead.

## What this does not allow

- IRAS does not invent independent external goals.
- It does not broaden the user's app/action scope without user intent.
- It does not bypass permission or confirmation policy.
- It does not auto-replay failed click/type/send/submit actions.
- It does not guess raw coordinates.
- It does not treat learned history as more authoritative than the live UI.

## Visual-only applications

If Windows UI Automation exposes no actionable controls, the controller may automatically perform one **read-only** `device_computer_observe` probe. If OmniParser/visual grounding is unavailable as well, IRAS stops guessing and reports the concrete grounding limitation instead of looping or narrating speculative internal reasoning.

## Safety invariant

Autonomy means **decision authority within the user's goal**, not independent authority over the user's computer. State-changing actions still flow through the existing bounded tools, permission engine, fresh-state grounding, verification, and recovery guards.
