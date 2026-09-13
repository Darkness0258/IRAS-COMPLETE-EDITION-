# IRAS v3.4.3 — Stream Lock Lifecycle Hotfix

Real-device/browser testing exposed a cloud concurrency bug.

A tool-bearing request sent through `/v1/chat/stream` could finish its actual
agent work but still keep the global `agent_lock` held while the single SSE
result chunk was being delivered. If the browser/network paused or interrupted
at that point, the next request could hit `IRAS_CHAT_LOCK_TIMEOUT` and fail with:

`IRAS is still finishing a previous request. Retry in a moment.`

This is a transport-lifecycle bug, not an AI-provider outage.

## v3.4.3

Tool-bearing turns now:

1. complete the device/tool workflow under the global agent lock;
2. copy the final metrics;
3. release the lock;
4. then emit the SSE `token` and `done` events.

Normal no-tool conversation keeps true token streaming.

The cloud API now reports a distinct `request_busy` SSE error code, and the web
client shows `IRAS busy · retry in a moment` instead of incorrectly showing
`AI provider unavailable`.

No permission, planner, device-control, or learned-skill boundary is changed.
