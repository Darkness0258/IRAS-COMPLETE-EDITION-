# IRAS v3.4.4 — Request Queue Backpressure Hotfix

Real-device testing showed a valid tool workflow taking about 59.9 seconds (23 tool calls, 10 planner rounds), while the streaming endpoint waited only 12 seconds for the global agent lock. v3.4.4 keeps shared agent state serialized but queues later requests instead of prematurely rejecting them.

Contended requests now emit an immediate `queued` SSE event, retry lock acquisition in short intervals, send periodic queue heartbeats to keep the connection alive, and run normally as soon as the previous request completes. Only exhaustion of `IRAS_CHAT_QUEUE_TIMEOUT` returns `request_busy`.

Default queue timeout: 180 seconds. Allowed range: 15–300 seconds. The final `done` event includes `queue_wait_ms`.

The Groq 413 input-token-limit and Gemini INVALID_ARGUMENT failures observed in the same log are separate provider/latency issues and are intentionally not mixed into this concurrency hotfix.
