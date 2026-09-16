# IRAS architecture

```text
Voice / Desktop / CLI / API
            |
        Agent Core
            |
  Provider <-> Tool Registry
            |        |
          Memory   Permission Engine
                       |
                    Audit Log
                       |
    +----------+-------+---------+---------+
    |          |                 |         |
 Files      System/Shell       Browser     Git
    |          |                 |         |
 Local PC   Authorized OS    Public web   Repos

Remote machines run an authenticated IRAS Node with an independently capped permission policy.
```

## Trust model

1. LLM output is never executed directly.
2. Every capability is a named tool with a JSON schema.
3. Tool permission may depend on its arguments.
4. Elevated actions need a separate approval path.
5. Critical operations cannot be silently auto-approved.
6. External web/tool text is treated as untrusted data, not instructions.
7. Secrets are redacted from audit records.
8. Network fetch rejects private/link-local destinations.


## Hybrid Desktop Control

```text
User goal
   |
Planner / bounded task engine
   |
   +--> deterministic app/window tools
   |
   +--> UI Automation semantic controls
   |          |
   |          +-- actionable? --> grounded semantic action
   |
   +--> foreground-window vision fallback (OmniParser, opt-in)
                  |
                  +--> grounded element_id action

Every state-changing path returns to a fresh observation/verification step.
Raw model-generated desktop coordinates are not part of the universal computer
action schema.
```

## v3.5.17 materially-different replan enforcement

Automatic recovery now has route-history awareness. Two identical read-only
recoveries may run to tolerate transient UI state, but a third identical route
is classified as a cycle and is blocked before tool execution. The exhausted
tool+arguments signature is then placed behind a controller-enforced material
replan guard. The planner must choose a different safe route; a successful
different route clears the guard. The prior state-changing action remains
non-replayable.

## v3.5.16 verification-result-driven replanning

After a recovery-aware fresh action, the automatically chained verification is
now interpreted by a deterministic transition layer. Goal-sufficient ACCEPT
terminates the verification loop; RETRY/ESCALATE/RECOVER may schedule one more
read-only observation when the bounded recovery budget allows it; non-automatic
routes and exhausted budgets return control to the planner for a materially
different route. No state-changing action is automatically replayed.


## v3.5.19 Adaptive Recovery Route Scoring

Recovery selection now has two deterministic stages. First, current verification
evidence defines the routes that are actually safe/plausible in the current UI
state. Second, bounded route history ranks only that live-supported candidate set.
Recent failures, repeated use, and saturation reduce scores; successful alternatives
receive a bounded bonus. Exhausted routes and forbidden exact tool signatures are
hard exclusions. A state-changing route such as app refocus may rank highly when
foreground drift proves it is necessary, but scoring never changes its
`automatic=False` safety classification. Failed state-changing actions remain
non-replayable.

## v3.5.18 Recovery-History-Aware Planner Constraints

Recovery history is summarized into planner-facing constraints before the next
post-recovery model decision. The context includes exhausted routes, forbidden
exact tool signatures, recent failures, use counts, saturated routes, and recent
successful alternatives. This is guidance for planning; controller guards remain
mandatory and `action_replay_allowed` remains false.

## v3.5.20 Persistent Recovery Route Performance Learning

Recovery routes now accumulate bounded outcome evidence across workflow runs.
A route is not rewarded merely because its observation tool returned: the next
semantic verification result determines whether the route receives success or
failure weight. Only aggregate route statistics are persisted; no user goal,
target text, screenshots, element labels, coordinates, or action arguments are
stored. Evidence decays exponentially and is capped, so old environment behavior
cannot dominate forever. Learned priors only nudge ranking among routes already
supported by live UI evidence. Controller exclusions and no-replay safety remain
authoritative.
## v3.5.21 Context-Aware Recovery Learning

Persistent recovery performance is now split into a global fallback prior and
coarse context-specific priors. Context is intentionally privacy-bounded to a
small whitelisted app identity plus UIA actionability, vision scope, and whether
the verification predicate is semantic. Arbitrary window captions are never
used as persistent keys; unknown titles collapse to `unknown`. The adaptive
scorer looks up only the exact current context and falls back to the global prior
when no context bucket exists. Context/global learning remains bounded, decayed,
advisory, and subordinate to live-state candidate generation, hard route
exclusions, and the no-action-replay policy.
## v3.5.22 Recovery Confidence Calibration & Exploration Control

Learned recovery history is now uncertainty-aware. Global and contextual priors
are converted into confidence-calibrated score adjustments using decayed effective
sample weight and a bounded uncertainty estimate. Sparse evidence receives little
planning influence; mature evidence can influence ranking more strongly but remains
capped and subordinate to live UI evidence.

A small deterministic exploration bonus may be applied only to a live-supported,
read-only `device_computer_observe` route that is within a narrow score margin of
the current best route, is less sampled, and is competing against a low/medium
confidence best estimate. Exploration cannot manufacture routes, bypass exhausted
or forbidden-route guards, auto-execute app focus, or enable action replay.



## v3.6.0 Cross-App Workflow Memory and Stale-Learning Protection

The autonomous task tracker now owns an ephemeral `CrossAppWorkflowMemory`. Only semantically verified facts enter this memory. App transitions preserve those facts with provenance so the next planner turn can use them, but the destination app must still be observed and re-grounded before action. The memory is never persisted and does not grant permission or action replay.

Recovery-route persistence also tracks consecutive semantic outcome streaks. Repeated contextual failures degrade/quarantine only the learned score contribution; current live UI candidate generation remains authoritative and controller exclusions remain hard.
## Bounded autonomous decision supervisor

The local/cloud agent keeps a small session-scoped autonomy context (current app, previous app, last media app, and verified semantic target). It is advisory context for planning and deterministic follow-ups; it is not a permission grant. The supervisor may choose the next safe step within the user's current goal, resolve obvious deictic follow-ups, request read-only state probes, and reject leaked planner scratchpad. Live UI state, the permission engine, fresh observation bindings, semantic verification, bounded recovery, and the no-action-replay invariant remain authoritative.

For custom-rendered/WebView applications, an inaccessible UIA snapshot can trigger one controller-level read-only computer observation. If neither UIA nor configured visual grounding is actionable, state-changing actions are not guessed.

## v3.7.0 Multimodal Perception and WebView Grounding

The universal computer controller now emits a unified multimodal scene graph.
Windows UI Automation remains the preferred semantic source; when UIA exposes
no meaningful action targets, IRAS can lazily start a local OmniParser service
and ground the foreground screenshot. In auto scope, a failed/empty foreground
visual pass may broaden once to desktop vision.

Scene elements use stable semantic/geometry-derived IDs, confidence, and
provenance. UIA evidence is preferred when it overlaps equivalent visual
evidence; visual-only elements remain available for WebViews, Electron, canvas,
and other custom-rendered interfaces.

Every state-changing universal computer input consumes the observation binding
that authorized it. A second click/type/press/scroll/drag requires a fresh
observation, including after partial failures. Low-confidence or ambiguous
visual targets fail closed. Post-action observations include normalized image
change evidence, but visual change never substitutes for semantic end-state
verification. `action_replay_allowed` remains false.

OmniParser process startup is bounded and local-only: IRAS probes first, starts
only a configured/discovered local installation with `shell=False`, never
auto-installs dependencies/weights, and reuses an already-running server.

### v3.7 R3 deterministic visual-navigation fast path

A narrow controller-owned WhatsApp navigation workflow bypasses the LLM for the
explicit goal of opening one named chat and visually verifying its header without
sending. The workflow is still closed-loop: focus/launch, fresh observation,
optional grounded search typing, fresh observation, unique contact selection,
fresh visual header verification. It never types into the composer or presses
Enter. A failed click/type is never replayed automatically.

The visual controller may reuse OmniParser semantics only for a newly captured
screenshot with the exact same SHA-256. Observation IDs remain fresh per capture,
so cached perception does not reuse action authorization. OmniParser runs as a
single non-reloading child process, and IRAS persists only local PID/base-URL
ownership metadata so CLI/controller instances agree on runtime ownership.

### v3.7 R4 ROI perception fast path

Bounded controller-owned workflows may request a foreground-clamped region of
interest instead of a full-window visual parse. ROI observations are not exposed
as free-form model coordinates: the controller authors the region, captures fresh
pixels, builds ordinary stable scene elements, and stores a fresh observation
that is subject to the same foreground-freshness and one-state-changing-input
consumption rules.

For local OmniParser, IRAS can launch its own lightweight bridge inside the
OmniParser virtual environment. The bridge becomes ready without eagerly loading
the full Florence/YOLO stack. Its `/parse_text/` endpoint performs EasyOCR-only
text grounding for narrow ROIs; `/parse/` lazily initializes the full upstream
OmniParser when richer icon semantics are required. Existing external/upstream
servers remain supported because a missing text endpoint falls back to full
parsing of the same bounded image.

### v3.7 R5 cold-start text prewarm and bounded ROI retries

The IRAS-managed OmniParser bridge now starts EasyOCR warmup in a background
thread after the HTTP service becomes available. The WhatsApp fast path can begin
that local runtime startup concurrently with application focus, then consume the
same initialized OCR reader when the first ROI request arrives. `/probe/` exposes
text-model warmup state for diagnostics; full Florence/YOLO initialization remains
lazy and separate.

Cold navigation no longer broadens to full-scene vision after one empty top-band
OCR result. The controller checks the right header, then a narrow left search
region with bounded read-only retries, may consult UIA without vision, and checks
text-only search results before any full semantic fallback. Once search typing or
a contact click has occurred, that state-changing action is never automatically
replayed; only fresh read-only evidence may follow it.

## v4.0 RC1 — Permissioned Worldwide Windows Agent

v4 adds an outbound-only Windows device bridge as the preferred remote-control
transport. The laptop initiates HTTPS long-polling to IRAS Cloud, so the design
requires no router port forwarding or inbound Windows listener. Pairing/API
secrets are persisted with Windows DPAPI and a visible per-user scheduled task
starts the bridge at logon.

Remote authorization uses independent layers:

1. the cloud master API token authorizes creation of a short-lived session;
2. that session is bound to one paired device, has an expiry and permission cap,
   and stores only a token hash server-side;
3. the Windows bridge independently classifies every action;
4. the locally persisted `RemoteAccessPolicy` is the final maximum permission;
5. restart/shutdown and explicit executable execution require additional local
   opt-ins even in full mode;
6. `EmergencyStop` blocks `DeviceExecutor` below model/tool planning and can be
   cleared only locally.

The cloud model therefore cannot turn a read-only or locally disarmed laptop into
an unrestricted machine merely by selecting a different tool.

### Generic deterministic Windows primitives

v4 promotes the successful app-specific closed-loop pattern into reusable
controller primitives: fresh find/wait/click/type/scroll operations over semantic
UI elements and a `SemanticVerifier` for terminal filesystem, process, foreground,
and visible-text state. Ambiguous duplicate text fails closed; a click/type/scroll
consumes its observation and is never automatically replayed.

### Remote administration surface

The paired executor supports bounded screen preview, app/UI control, clipboard,
processes, allowed-root file read/write/copy/move/delete, semantic verification,
and an explicit critical executable+argv primitive. The latter always uses
`shell=False`; launching a shell program itself is a separate full-mode user
choice and requires the laptop's command-execution opt-in.

The hosted web UI can mint a short-lived remote session and request screen
previews. Both the master token and remote session token are browser-session
secrets rather than persistent local-storage credentials.

### R6 text-first cold perception

For WhatsApp named-chat navigation, a cold miss no longer automatically implies
full Florence/YOLO initialization. After bounded header/search/result ROIs, the
controller can use a whole-foreground **text-only** OCR rescue. The normal path
therefore remains UIA/EasyOCR-only and `IRAS_WHATSAPP_FULL_VISION_FALLBACK=false`
by default. Full visual semantics remain an explicit last-resort compatibility
option for unusual icon-only layouts.

### Last-mile trust boundary

IRAS does not bypass Windows authentication, lock screen, BitLocker, UAC secure
desktop, or credential prompts. GUI control requires an interactive logged-in
user session. This is a deliberate security boundary, not a missing remote-access
feature.
