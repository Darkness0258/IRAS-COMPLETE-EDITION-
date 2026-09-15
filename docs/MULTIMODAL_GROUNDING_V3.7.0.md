# IRAS v3.7.0 — Multimodal Perception and WebView Grounding

v3.7.0 extends the v3.6 bounded-autonomy controller with a multimodal perception
layer for interfaces that Windows UI Automation cannot fully expose.

## Observation cascade

In `vision=auto` mode IRAS prefers the cheapest/highest-semantic evidence:

1. Windows UI Automation for the foreground application.
2. Foreground-window OmniParser grounding when UIA has no meaningful action
   targets.
3. Desktop OmniParser grounding only when auto-scope foreground grounding is
   unavailable or returns no elements.

OmniParser is lazily auto-started for local endpoints when visual grounding is
actually needed. Startup is bounded, direct-process only (`shell=False`), and
never installs dependencies or downloads weights.
 On Windows the built-in launcher explicitly preloads PyTorch
before importing OmniParser, avoiding the known PaddleOCR/PyTorch DLL-load-order
conflict while keeping the same bounded process lifecycle.

## Unified scene graph

Each observation fuses accessibility and visual evidence into one scene graph.
Elements include:

- deterministic/stable `element_id` values rather than index-only IDs;
- semantic label/name/role;
- screen rectangle and center derived from observed geometry;
- `confidence`;
- provenance (`windows_uia` or `omniparser` plus capture hash);
- source corroboration when UIA and vision identify the same control;
- ambiguity markers for repeated actionable labels.

UIA is preferred when both backends identify the same control. Vision-only
controls remain available for WebViews, Electron/canvas interfaces, and other
custom-rendered surfaces.

## Action binding

A state-changing universal computer action must reference an element from a
fresh observation. v3.7 adds a one-input-per-observation guard: once a click,
type, press, hotkey, scroll, drag, or similar input is authorized from an
observation, that observation is consumed. Any subsequent state-changing input
requires a new observation.

This remains true even when the first action reports an error after possible
partial delivery, preventing blind replay.

## Confidence guard

Visual targets are rejected when grounding confidence is below
`IRAS_VISUAL_ACTION_MIN_CONFIDENCE` (default `0.72`). Repeated labels require a
higher confidence before action. The controller requests re-observation or
re-grounding instead of guessing.

## Closed-loop visual evidence

Post-action observations calculate both exact state hashes and a bounded image
change score from low-resolution normalized screenshots. This improves
sensitivity to meaningful visual changes without treating change alone as proof
of the user's semantic goal.

The semantic end state still requires `device_computer_verify`.

## Preserved safety invariants

- live UI state remains authoritative;
- permissions remain independent from visual understanding;
- raw model-generated click coordinates remain unsupported;
- state-changing action replay remains disabled;
- recovery remains bounded;
- cross-app memory remains context, not authorization;
- visual change is delivery/state evidence, not semantic goal proof.

## R3 bounded fast path and performance hardening

The common navigation-only WhatsApp goal “open a named chat and visually verify
the chat header without sending” now has a controller-owned deterministic fast
path. It does not call the language model, never types into the composer, never
presses Enter, and never sends a message. Search typing and chat selection are
still bound to fresh observations and every state-changing observation is
consumed after one input. A final fresh visual observation must prove the
right-pane header; a matching name in the left chat list is not accepted as
terminal evidence.

Exact OmniParser results are cached briefly by screenshot SHA-256. Cache reuse is
allowed only when the newly captured pixels are byte-identical; every observation
still receives a new observation ID, so cache reuse cannot replay an old action
authorization. This reduces duplicate CPU inference without weakening freshness.

The local OmniParser launcher now runs one non-reloading uvicorn process instead
of the upstream development reloader. IRAS persists only runtime ownership
metadata (PID/base URL/start time) under `%USERPROFILE%\.iras\omniparser` so a
new CLI/runtime-manager instance can correctly report `started_by_iras` for an
already-running IRAS-owned service.

## R4 ROI grounding and lightweight text perception

R4 reduces CPU vision cost for bounded workflows whose semantic target can only
exist in a known portion of the foreground application. The universal computer
controller now has an internal `observe_region(...)` path that captures only a
foreground-bounded region of interest (ROI), preserves absolute screen geometry,
and still produces a fresh single-use observation ID.

IRAS-managed local OmniParser startup now prefers a small bridge process running
inside the user's OmniParser virtual environment. The bridge exposes the normal
full `/parse/` contract plus `/parse_text/`, an EasyOCR-only path intended for
text-heavy ROIs such as WhatsApp search results and chat headers. Florence/YOLO
full semantics are loaded lazily only when full parsing is actually requested.
If `/parse_text/` is unavailable (for example, an already-running upstream
OmniParser server), IRAS falls back once to full parsing of the same ROI.

The WhatsApp navigation fast path uses three bounded regions when needed:

1. top band — detect an already-open target or the global chat-search field;
2. left results pane — ground the requested contact after search typing;
3. right header band — prove the destination chat header after the click.

A click or type still consumes the exact observation that authorized it. The
contact click is never replayed automatically. Header retries are read-only, and
the older full-scene path remains a compatibility fallback when ROI grounding is
unavailable or inconclusive.

R4 observations include timing telemetry (`capture_ms`, HTTP/vision time, server
latency, cache hit, source/input pixels, and total ROI observation time) so real
Windows runs can identify whether remaining latency is capture, OCR, model load,
or full semantic parsing.
