# IRAS RC8 Candidate — Production Strengthening Overlay

RC8 is a cumulative hardening layer on top of RC6 Automation/Wake Voice and RC7 Cognitive Core. It keeps Remote protocol `1` and does not bypass ToolRegistry permissions, Remote authorization, Master Control, audit logging, filesystem boundaries, Emergency Stop, Windows UAC, or existing verification requirements.

## 1. Durable execution and crash-resume checkpoints

Long-horizon work can create a persistent execution journal, write idempotent checkpoints, pause, resume after process/device failure, and recover from the last successful step without automatically replaying consequential side effects. This follows the same high-level production pattern used by durable workflow systems: orchestration state is persistent; side effects remain separately permissioned.

## 2. Context compiler

RC7 memory can grow far beyond any one model context window. RC8 adds a finite-context compiler that scores context by query relevance, priority, provenance trust, and token cost, then packs the best evidence into a configurable token budget. Context is labelled TRUSTED or UNTRUSTED DATA, and quarantined records are excluded by default.

## 3. Provenance and prompt-injection containment

External/web/tool/document inputs receive provenance labels, taint state, and deterministic prompt-injection heuristics. High-risk external text is recommended for quarantine and blocked from the RC8 memory-admission path by default. A high-impact action preflight gives an additional intent-alignment signal, but is explicitly advisory: the existing permission system remains the final enforcement layer.

## 4. MCP 2026-07-28 client interoperability

IRAS can register fixed MCP endpoints with symbolic vault credential references and use the current stateless request contract (`MCP-Protocol-Version: 2026-07-28`, `Mcp-Method`, optional `Mcp-Name`). The bounded client supports server discovery, tool/resource/prompt listing/reads, and `tools/call`. A real `tools/call` is classified as SYSTEM_ACTION by the IRAS ToolRegistry.

## 5. A2A v1.0 client interoperability

IRAS can register A2A endpoints, fetch `/.well-known/agent-card.json`, and delegate a text task through the v1.0 HTTP+JSON `POST /message:send` form with `application/a2a+json`. Delegation is a SYSTEM_ACTION because it sends user/agent data to an external agent.

## 6. Continuous eval and regression gates

A persistent evaluation lab stores deterministic cases (`exact`, `contains`, `regex`, `json_subset`, `truthy`), candidate results, weighted suite summaries, and a promotion gate. This gives IRAS an evidence layer for deciding whether a changed model, workflow, prompt, capability, or voice path is actually better instead of assuming it is.

## 7. Secure automation webhooks

IRAS can create external webhook endpoints for event-driven automations. Webhook secrets are shown once, stored only as SHA-256 hashes, compared with constant-time verification, and require caller-supplied event IDs for replay protection. Accepted payloads are published to the existing EventBus, so RC6 event automations can consume them while keeping their own permission caps.

Cloud endpoint:

`POST /v1/automation-hooks/{hook_id}`

Headers:

`Authorization: Bearer <hook-token>`

Body:

```json
{
  "event_id": "unique-event-id",
  "payload": {"key": "value"}
}
```

## 8. Structured event timeline

RC8 records EventBus activity into a compact structured trace ledger for postmortems, regression analysis, and debugging. This complements — and does not replace — the existing security audit log.

## Limits and non-claims

- Prompt-injection detection is defense-in-depth, not a proof that malicious text can always be recognized.
- MCP and A2A support is a bounded client surface, not a claim of full ecosystem/TCK certification.
- Durable checkpoints do not make arbitrary side effects safe to replay. Idempotency and existing permission/verification gates still matter.
- RC8 does not give IRAS consciousness, unlimited physical storage, or permission to bypass owner/system controls.
