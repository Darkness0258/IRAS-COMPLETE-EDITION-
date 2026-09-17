# IRAS v4.3.0 RC8 — Responsive Device Bridge

## Real-device failure fixed

RC7 executed every device command synchronously inside the same outbound polling loop. A local `local_llm_complete` request may run for more than the cloud's 65-second online window. While Ollama was generating, the bridge stopped polling, `last_seen` stopped moving, and the cloud declared the PC offline. This also blocked otherwise unrelated app, Git, file, and test commands.

RC8 gives local Ollama inference a dedicated single-worker lane. The main bridge continues long-polling while inference runs. When that lane is busy, the device asks the cloud to temporarily skip additional `local_llm_complete` commands so ordinary Windows work remains claimable instead of being stuck behind local AI.

Safety boundaries are unchanged: the dedicated worker still enters `_execute`, so emergency stop, local RemoteAccessPolicy, declared permissions, tracing, loopback-only Ollama enforcement, and authenticated command completion remain active.

The remote protocol remains version 1; `exclude_action` is an optional bridge polling hint restricted server-side to `local_llm_complete`.
