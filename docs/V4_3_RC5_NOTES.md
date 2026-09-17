# IRAS v4.3.0 RC5 — Remote Authorization Continuation

RC5 fixes the real-device handoff exposed after RC4: autonomous engineering requests could be classified correctly but stop at the Remote safety gate, leaving Tasks empty and requiring the user to manually authorize and resend the objective.

## Changes

- Browser engineering-intent preflight now recognizes noun forms such as `improvement` as well as `improve`.
- Added a generic `ensureRemoteAuthorization()` consent helper.
- Streaming chat recognizes the server `execution_mode=authorization_required` contract.
- After explicit user consent creates a Remote session, the same chat turn is automatically retried once with Remote headers; the user message is not duplicated.
- Temporary authorization-gate text is not spoken when the client can continue the turn.
- Tasks/Start Goal also retries once after a server 403 Remote-session requirement instead of surfacing `Multi-agent start error`.
- A declined authorization does not start or retry state-changing work.
- The server safety gate remains unchanged and authoritative. IRAS never creates a Remote session without the user's confirmation.

Remote protocol remains version 1.
