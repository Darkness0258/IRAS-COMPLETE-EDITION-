# IRAS v5 architecture

```text
User / Voice / Mobile / Web
          |
   V5 Goal + Schedule Layer
          |
  +-------+-----------------------------+
  |       |        |         |          |
Memory  Monitor  Research  Coding    Workflow
  |       |        |       Worktrees   Recorder
  +-------+--------+---------+----------+
          |
     V4.4 Agent Core
          |
 Permissioned ToolRegistry
          |
 Remote session / Local policy / Emergency stop
          |
 Windows bridge / Browser / Files / Git / Connectors
```

The v5 layer organizes long-lived goals, schedules, knowledge, connectors, artifacts, and recovery. It does not replace the v4.4 enforcement boundary. Every real external action still descends through the existing permissioned tools.

The dedicated Coding Agent resolves one verified Windows project root before its engineering DAG starts. Resolution uses explicit-path precedence, named/fuzzy identity matching, root-over-artifact ranking, and fail-closed ambiguity handling. A selected project may be remembered for follow-up `/code` commands, but the remembered path is re-validated through the existing bridge/Git read path before use. Selection never bypasses ToolRegistry permissions, the active Remote/Master session, local Remote policy, configured filesystem roots, emergency stop, or Windows/UAC. Remote protocol remains `1`.

## V5 subsystem boundaries

- **State:** PostgreSQL on cloud deployments when configured; SQLite locally.
- **Secrets:** symbolic vault references only; DPAPI on Windows or explicit AES-GCM master key on non-Windows.
- **Code:** isolated Git worktrees; no automatic merge.
- **Skills:** proposal -> sandbox -> explicit approval; marketplace packages require signatures.
- **Network/home:** adapter allowlists; no ambient scanning; state changes need approval.
- **Sync:** ciphertext-only bundles; transport does not receive plaintext state.

## v5.0 RC5 operating-layer surface

RC5 preserves the 36-family v5 operating layer and extends the permissioned Software Installer Agent into a **Software Lifecycle Agent**. WinGet remains the preferred package identity/control plane. Read-only update discovery is separate from CRITICAL update/uninstall execution.

Lifecycle commands resolve exact installed package identity, fail closed on ambiguity, require authenticated Remote authority plus laptop-local `allow_shell` for state changes, and verify the post-action state. `update all` exists only as an explicit user command; IRAS does not infer it from a vague update request. Direct HTTPS receipt execution remains installation-only and keeps SHA-256 + Authenticode continuity.

Remote protocol remains `1`. ToolRegistry authorization, authenticated Remote sessions, laptop-local Remote policy, configured filesystem roots, device bridge/executor, emergency stop, audit, SmartScreen/UAC and Windows security remain authoritative.

## v5.0 RC4 operating-layer surface

RC4 declares 36 feature families. It retains the complete RC3 operating layer and adds two dedicated agents outside the generic worker path:

- **Web Research Agent:** read-only public-web workflow with source discovery, bounded retrieval, evidence cross-checking and review before synthesis. It receives only `web_search`, `http_get` and `api_request`; it cannot inherit Windows mutation tools.
- **Software Installer Agent:** package-manager-first Windows installation. WinGet search/show/list/install uses fixed argument vectors with exact package IDs. Direct URLs are restricted to public HTTPS `.exe`/`.msi`, cached under IRAS control, SHA-256 pinned, and Authenticode revalidated immediately before execution. Arbitrary executable paths are not accepted.

Coding Agent project selection remains explicit-path-first, typo-tolerant and fail-closed on ambiguity. RC4 additionally treats permission/device blockers as failed tasks and requires an explicit verified coordinator completion signal before Coding/Installer runs may end as `succeeded`.

The authoritative feature mapping is `RC4-FEATURE-MATRIX.md`. Remote protocol remains `1`. ToolRegistry authorization, authenticated Remote sessions, laptop-local Remote policy, configured filesystem roots, device bridge/executor, emergency stop, audit and Windows/UAC remain the enforcement boundary. Installer support extends these boundaries; it does not bypass them.


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

## v4.0 FINAL — Permissioned Worldwide Windows Agent

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


## v4.1 RC1 — Bounded Parallel Task Supervisor

v4.1 keeps the v4.0 remote protocol and safety boundary unchanged while adding a cloud-side multitask supervisor. A bounded `ThreadPoolExecutor` runs independent IRAS worker agents concurrently. Each worker receives an isolated conversation snapshot, a fresh provider instance, and an independent `PermissionEngine`; durable facts, audit logging, the device registry, and learned app-skill storage are intentionally shared.

Remote provenance is concurrency-safe. The active remote session ID, requester, and exact target device are carried with `ContextVar` state instead of mutating a global preferred-device field. This prevents two concurrent sessions from leaking target-device or permission state into one another.

The web client exposes a **Tasks** panel backed by `/v1/multitask/runs`; explicit chat syntax `/parallel ... || ...` uses the same supervisor. Worker and per-run limits are bounded by environment configuration. Existing emergency stop, local remote policy, remote-session permission caps, DPAPI pairing, command TTLs, and audit traces remain authoritative. Device-side commands continue through the single authenticated command queue, which serializes Windows UI mutation even when several cloud workers are active.


## v4.2 RC1 — Multi-Agent Execution Graph

The v4.2 cloud runtime adds `OrchestrationManager`, a bounded dependency-DAG supervisor above the isolated v4.1 worker model. An objective is planned by a tool-less Planner provider call. The graph is validated for unique IDs, known dependencies, and acyclicity before execution. Ready nodes are ordered by priority and dispatched to isolated workers.

Each graph worker receives a role-specific system directive plus request-local remote-session context. Dependency outputs are included only as explicitly labelled untrusted data. Normal downstream nodes require successful dependencies; failed branches are marked blocked. The automatically added Coordinator uses `continue_on_failure` so it can synthesize a truthful result after partial failure.

Pause is cooperative: running bounded turns complete, but no new nodes start. Cancel marks queued nodes cancelled and discards late results from already-running workers. The Windows device queue, permission engine, local policy, fresh-state verification, and emergency-stop controller remain below this orchestration layer and therefore remain authoritative.

## v4.2 RC5 — Autonomous Chat Execution Router

RC5 moves execution-mode selection in front of the normal chat agent. A local,
provider-independent `execution_router` classifies each ordinary turn as direct,
deterministic, parallel, or dependency-aware orchestration. This keeps routing
available even when every cloud model provider is cooling down. Explicit
`/parallel` and `/goal` syntax remains a user override, not a requirement.

Automatic parallel jobs are converted into a dependency-free orchestration graph
rather than using the older one-shot supervisor, so they inherit provider-cooldown
waiting, isolated worker contexts, pause/cancel lifecycle, request-local remote
provenance, and final synthesis. Dependency-heavy implementation/test/review work
is promoted to the Planner/Coder/Tester/Reviewer/Coordinator graph instead.

The router chooses execution strategy only; it never grants authority. Browser
Remote sessions are still explicit user authorization. Exact deterministic Windows
writes are preflighted in both chat and the Tasks panel, and the cloud API refuses
to start such state-changing work without a live Remote session. Local laptop
policy, allowed roots, permission classification, and emergency stop remain the
final execution boundary.

## v4.2 RC6 — Specialized Agent Execution Hardening

RC6 makes the autonomous execution modes operationally asymmetric on purpose: each multi-agent role receives only the schemas needed for its job. Researcher workers receive text-first public-web retrieval (`web_search` + readable `http_get`) rather than generic browser/UI automation. Coder workers receive project inspection, bounded `device_replace_text`, new-file `device_write_text`, git status, and bounded test execution; arbitrary shell and destructive file operations are not part of the role capability set.

`device_replace_text` is implemented below the model layer in `DeviceExecutor`. It resolves the target through the configured allowed roots, rejects files larger than 2 MB, requires a non-empty exact old snippet, bounds snippet size and replacement count, and fails if the expected text is not present. It is classified as a `SYSTEM_ACTION`, so the authenticated Remote session, server permission cap, laptop-local RemoteAccessPolicy, command queue, and EmergencyStop remain authoritative.

Research web retrieval also remains fail-closed against SSRF: public HTTP URLs are resolved and checked before each request, and every redirect target is revalidated before it is followed. HTML is converted to readable text in-process so a Researcher can inspect documentation without opening or visually scraping Chrome.

When the Planner provider is unavailable, implementation-oriented goals now use a local fallback DAG that preserves `Inspect -> Coder -> Tester -> Reviewer -> Coordinator` dependencies instead of collapsing the entire objective into one general worker. Orchestration workers have a separate bounded tool-step budget (`IRAS_ORCHESTRATION_AGENT_MAX_STEPS`, default 14, maximum 24); ordinary chat keeps its existing conservative budget.


## v4.3 RC1 — Deep Tool-Boundary Audit

v4.3 hardens the boundary between model reasoning and external state. Retrieved web/API/browser content is wrapped with explicit untrusted-data metadata before it re-enters the model loop, including prompt-injection indicators. Tool arguments are schema-validated before authorization and execution, while audit redaction is applied to richer credential/token patterns.

Remote Windows tools now resolve their cloud permission dynamically from the exact `RemoteAccessPolicy` action and arguments. Sensitive credential paths and process termination are `CRITICAL`; this closes the class of bugs where a generic cloud tool permission could be weaker than the device-side action permission. The project surface adds bounded search, ranged reads, hashing, Git diff/log, and targeted tests without granting a general shell.

Filesystem mutation uses atomic replacement and recursive copy refuses symlink-containing trees. Public network tools bound response size/type and revalidate redirects. Supervisors cap active runs per requester. Orchestration journals are loaded only for observable history; active work found after a restart is failed as interrupted rather than replayed, and no remote-session secrets are restored.


## v4.3 RC2 — Project-Aware Engineering Preflight

Engineering objectives are preflighted against the paired Windows device before orchestration. The cloud verifies the session target is online, calls the bounded read-only `find_projects` device action, selects a project inside the configured bridge roots, verifies Git access, and stores that Windows project root in request-local orchestration context. Workers are instructed to use exactly that path for project/Git/search/edit/test tools. Cloud container paths are never treated as substitutes for the user's Windows repository.

If the target device temporarily disappears during a graph, orchestration classifies the outage as infrastructure backpressure and waits up to `IRAS_ORCHESTRATION_DEVICE_WAIT_SECONDS` without consuming normal task retries. Authorization/root violations remain hard failures.

## v4.3 RC4 — Result Delivery and Project Binding

Autonomous orchestration completion is now a first-class chat event. The web
client watches the `orchestration_run_id` returned by ordinary chat and posts the
terminal coordinator result into the main conversation. Tasks remains the
inspection/control surface, not the only place where results can be read.

The coordinator emits a structured first-line outcome token. Orchestration maps
that token into `verified_outcome` and refuses to label an incomplete verified
result as a successful run.

For engineering runs, `project_root` is carried through a ContextVar alongside
remote-session/device provenance. Project-scoped device tools bind relative or
placeholder paths to that verified root and reject absolute escapes. The project
root is therefore enforced by the tool boundary rather than depending only on a
system-prompt instruction.


## v4.3 RC5 — Remote Authorization Continuation

State-changing autonomous objectives keep the server-side Remote-session gate. The web client now treats an `authorization_required` completion as a resumable safety checkpoint: it asks the user to authorize the Remote session, then retries the same pending turn once with the new request-local Remote credentials. Manual Tasks goals use the same one-retry handoff on a 403 Remote requirement. Declining consent leaves the objective unstarted.
