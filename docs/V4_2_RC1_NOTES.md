# IRAS v4.2.0 RC1 — Multi-Agent Execution

IRAS v4.2 RC1 builds a dependency-aware multi-agent execution layer on top of the accepted v4.1 parallel-worker architecture. The v4 remote wire protocol remains `1`, so existing paired Windows bridges stay compatible.

## New execution model

A user can now give IRAS one objective instead of manually splitting it into independent jobs. The Planner Agent produces a compact dependency DAG. The scheduler then runs ready nodes by priority with a bounded worker pool and passes completed dependency outputs forward as untrusted context.

Supported specialized roles:

- **Planner** — creates the task graph only; it receives no tool schema and does not execute actions.
- **Researcher** — gathers and verifies information.
- **Coder** — performs authorized implementation/editing work.
- **Tester** — validates outcomes and reports failures.
- **Reviewer** — checks correctness, security, regressions, and quality.
- **Coordinator** — automatically runs last and synthesizes one final result without inventing unfinished work.
- **General** — bounded fallback worker for tasks that do not fit another role.

## Task-graph capabilities

- dependency DAG validation with cycle/unknown-dependency rejection;
- numeric priorities (`0..100`) for ready tasks;
- bounded retries (`0..3`) with short backoff;
- independent ready nodes execute concurrently;
- downstream nodes wait for dependencies;
- failed dependencies block normal downstream nodes;
- the final Coordinator may still run after partial failure so the user gets an accurate final report;
- background goal execution through `/v1/orchestration/runs`;
- cooperative **pause**, **resume**, and **cancel**;
- running tasks finish their current bounded turn when paused; cancel discards late results and prevents downstream work;
- task/run status, attempts, role, priority, dependencies, errors, metrics, and final synthesis are observable through the API and Tasks panel;
- a small JSON journal under the configured IRAS data directory records run snapshots for diagnostics.

## User entry points

Web: open **Tasks & multi-agent execution**, enter one objective, and choose **Start Goal**. The same panel can load the latest run and pause, resume, or cancel it.

Chat:

```text
/goal Improve IRAS voice latency, make the safest useful changes, test them, review regressions, and report the final result.
```

The command starts in the background and returns a run ID. `/orchestrate` and `/agents` are aliases. Existing `/parallel ... || ...` behavior is unchanged for independent work.

## Safety model

Multi-agent execution does not widen authority. Every worker has its own PermissionEngine, conversation view, and request-local remote-session context. Windows actions still pass through the authenticated device queue, local remote policy, permission classification, fresh-observation rules, and emergency stop. Upstream agent outputs are labelled as untrusted data before they are passed to downstream workers.

The Planner is intentionally tool-less. A graph can describe a Coder or Tester task, but those workers can only use capabilities already authorized by the active IRAS session and the laptop's local policy.

## RC1 acceptance target

Before promoting v4.2 to final:

1. `run-v420-validation.ps1` passes the complete regression suite;
2. Render `/health` reports `version=4.2.0-rc1` and `remote_protocol=1`;
3. `iras --doctor` reports both Multitasking and Multi-agent execution as PASS;
4. one real goal creates a useful Planner DAG with at least two independent nodes;
5. pause prevents new nodes from starting, resume continues them, and cancel prevents downstream work;
6. a real authorized Windows task remains bounded by the existing remote policy and emergency stop;
7. the final Coordinator reports verified successes and failures accurately.
