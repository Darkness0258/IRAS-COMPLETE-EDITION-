# IRAS v4.0 FINAL — Production Readiness Contract

v4.0 FINAL consolidates the bounded-autonomy safety model, multimodal desktop grounding, and permissioned remote Windows control into a deployable personal-agent architecture. “Production complete” here means bounded, observable, recoverable, permissioned, and testable—not a claim that arbitrary third-party UI can never change.

## Controller invariants

- live/current UI state is authoritative;
- state-changing actions require a fresh observation binding;
- one state-changing action consumes that observation;
- failed state-changing actions are never automatically replayed;
- semantic outcome evidence, not delivery confidence, gates completion claims;
- automatic recovery is bounded and prefers read-only observation;
- web/document/tool output is untrusted data, not executable instruction;
- learned workflow memory is context, not authorization;
- emergency stop is enforced below the model/tool-planning layer.

## Perception routing

The preferred route is:

```text
known deterministic workflow
-> Windows UI Automation
-> bounded text/OCR ROI
-> broader text-only foreground observation
-> full multimodal OmniParser only if genuinely necessary
-> model reasoning only where deterministic control cannot resolve the goal
```

The WhatsApp navigation workflow is text-semantic by nature. v4 therefore keeps its normal cold path UIA/OCR-only and does not initialize the heavy Florence/YOLO stack unless `IRAS_WHATSAPP_FULL_VISION_FALLBACK=true` is explicitly set.

## Generic deterministic primitives

`VerifiedUIPrimitives` provides reusable `find_text`, `wait_text`, `click_text`, `type_into_text`, `scroll_until_text`, and verified app-open behavior. These primitives operate on fresh scene elements and fail closed on ambiguous matches rather than guessing coordinates.

`SemanticVerifier` provides reusable terminal verification for filesystem state, foreground-window state, process state, and visible text.

## Provider resilience

`IRAS_PROVIDER=multi` can fail over among configured cloud providers. An optional local OpenAI-compatible Ollama endpoint can be the final provider by setting:

```text
IRAS_OLLAMA_FALLBACK=true
```

Deterministic device workflows do not require a cloud LLM when their controller route is recognized.

## Voice resilience

IRAS reports input-device health through `iras --doctor`; `IRAS_MIC_DEVICE` can select a sounddevice input index or device name. Text-only operation remains available when microphone hardware is unavailable.

## Persistent skills

Learned app skills are admitted only from verified task outcomes, contain semantic locators rather than raw click coordinates, maintain success/failure/confidence state, and are demoted after repeated failures. Live grounding remains authoritative when replaying a learned procedure.

## Remote administration

See `REMOTE_WINDOWS_ACCESS_V4.md`. Remote administration uses an outbound-only Windows bridge, DPAPI-protected secrets, exact-device short-lived sessions, a server permission cap, a final local permission policy, structured audit traces, and an emergency stop.

v4 includes the RC2 versioned cloud/Windows handshake. `/health` advertises `service_id=iras-cloud` and `remote_protocol=1`; bridge configuration validates that contract and the master API token before persisting configuration. Pairing also carries the protocol number and the cloud rejects mismatched clients with a clear conflict response. This prevents an old Render deployment from looking "connected" while the Windows bridge endlessly retries missing v4 routes.

## Diagnostics and observability

`iras --doctor` checks provider configuration, microphone devices, TTS, browser support, OmniParser, remote policy, bridge pairing, DPAPI protection, disk space, API-token quality, and HTTPS transport.

Remote command execution writes structured JSONL operation traces under `~/.iras/traces.jsonl` and the existing IRAS audit system records cloud session/invocation events.

## v4.0 production acceptance

The final promotion was made only after the hosted Render + real Windows acceptance path was exercised in addition to the automated suite. Verified acceptance evidence includes:

1. the complete regression and v4 validators pass;
2. the Windows bridge pairs to the hosted Render service over HTTPS with `service_id=iras-cloud` and `remote_protocol=1`;
3. `iras --doctor` reports the remote policy, DPAPI secret protection, transport, reachability, protocol compatibility, emergency-stop state, and startup task as healthy;
4. cloud-to-Windows system-status retrieval succeeds;
5. multimodal desktop observation can capture the live screen and describe the active application/UI state;
6. remote app launch and verified text entry succeed on the authorized Windows target;
7. the controller emergency stop blocks remote execution and the hardened bridge returns a bounded denial instead of leaving commands eligible for delayed execution;
8. recovery requires a local emergency clear and explicit local re-arm before remote control resumes.

Power actions and arbitrary shell execution remain separately gated opt-ins even in `full` mode. The v4.0.0 promotion does not claim that every third-party application layout is permanently stable; live grounding and verification remain authoritative.
