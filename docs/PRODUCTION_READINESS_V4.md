# IRAS v4.0 RC1 — Production Readiness Contract

v4.0 RC1 consolidates the v3.6 bounded-autonomy safety model and v3.7 multimodal work into a deployable Windows personal-agent architecture. “Production complete” here means bounded, observable, recoverable, permissioned, and testable—not a claim that arbitrary third-party UI can never change.

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

## Diagnostics and observability

`iras --doctor` checks provider configuration, microphone devices, TTS, browser support, OmniParser, remote policy, bridge pairing, DPAPI protection, disk space, API-token quality, and HTTPS transport.

Remote command execution writes structured JSONL operation traces under `~/.iras/traces.jsonl` and the existing IRAS audit system records cloud session/invocation events.

## Acceptance definition for v4.0 final

RC1 is code-complete only after:

1. the complete regression and v4 validators pass;
2. the Windows read-only smoke test passes;
3. one real outbound cloud pairing is verified over HTTPS;
4. a remote session can read system state and capture a screen preview;
5. a remote `control` action is verified on the laptop;
6. the local kill switch blocks the same action;
7. any explicitly enabled `full` operation is tested only on a disposable target;
8. at least one cold and warm multimodal task is benchmarked on the target Windows hardware.

No automated test can prove a third-party cloud network path or the user's physical microphone/display from this build environment, so those last-mile checks remain real-device acceptance items rather than hidden assumptions.
