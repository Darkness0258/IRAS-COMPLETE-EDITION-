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
