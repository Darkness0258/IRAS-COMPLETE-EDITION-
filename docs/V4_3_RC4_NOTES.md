# IRAS v4.3.0 RC4 — Engineering Planner Quality Gate

RC4 hardens autonomous engineering planning after real-device RC3 acceptance exposed a semantically weak Planner graph.

## Changes

- Treats both `improve` and `improvement` as implementation intent so routing, Remote preflight, fallback planning, and planner validation agree.
- Adds semantic Planner validation for engineering objectives. Valid JSON is rejected when it lacks Coder, Tester, Reviewer, or dependency ordering.
- Automatically upgrades weak Planner output to the deterministic Inspect → Coder → Tester → Reviewer fallback DAG.
- Preserves RC3 main-chat completion delivery, verified project binding, truthful partial-failure status, device backpressure, and all safety boundaries.

Remote protocol remains version 1.
