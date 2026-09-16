# IRAS v4.2.0 RC3 — deterministic resilience for bounded orchestration

RC3 addresses the real-device RC2 failure mode where all configured cloud AI providers can remain unavailable beyond the orchestration cooldown budget. Provider waiting is still retained for reasoning tasks, but a narrow class of explicit user goals no longer needs an LLM after intent is unambiguous.

## Deterministic exact-file path

Objectives matching `Create <absolute Windows .txt path> containing exactly "<text>"` receive a fixed three-node graph: Coder writes the exact text, Tester reads it back and requires an exact match, Reviewer checks Git working-tree status for unrelated changes, and the existing Coordinator receives the verified dependency evidence. The deterministic path never invokes a shell or arbitrary command.

The write still requires an authenticated IRAS Remote session with sufficient permission. All device actions traverse the normal authenticated command queue and remain subject to the Windows allowed-root sandbox, local RemoteAccessPolicy, permission classification, and emergency-stop controller.

## Provider behavior

General research/reasoning/coding goals continue to use the configured multi-provider pool. `IRAS_ORCHESTRATION_PROVIDER_WAIT_SECONDS` now defaults to 900 seconds (bounded `0..1800`) so transient provider outages do not prematurely consume task retry budgets.

## Acceptance

RC3 acceptance requires the complete v4.2 validator plus a real Windows goal that creates one exact text file, verifies its exact content, reviews Git status, and produces a final coordinator report while the cloud provider layer may be unavailable.
