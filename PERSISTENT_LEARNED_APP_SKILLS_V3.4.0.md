# IRAS v3.4.0 — Persistent Learned App Skills

## Goal

IRAS v3.4 learns reusable semantic workflows only after a workflow has been
verified. Learned skills are execution hints, never a separate permission path.

## First run

```text
User goal
  -> planner
  -> device_skill_find (no match)
  -> device_observe_ui
  -> device_semantic_action
  -> verification_observation
  -> successful workflow finalization
  -> PersistentSkillStore learns semantic trace
```

## Later run

```text
User goal
  -> device_skill_find
  -> device_skill_validate for each learned step
       -> fresh Windows UI Automation observation
       -> Automation ID match, then name+role fallback
  -> existing device_semantic_action
  -> existing verification_observation
  -> success confidence increases
```

## UI changed

```text
learned target
  -> fresh validation observation
  -> old Automation ID missing
  -> semantic name/role still resolves: update locator safely
     OR
  -> target missing: return live v3.2 observation + mark stale
  -> planner recovers with normal visual control
  -> verified recovered semantic trace refreshes the skill
```

## Safety invariants

- No raw screen coordinates are stored in a skill.
- `rect`, `bounds`, x/y and derived cursor positions are stripped.
- A role alone can never identify a learned target.
- Only verified `device_semantic_action` steps are learnable.
- Workflows containing generic state-changing/coordinate interaction are not
  persisted as skills.
- Shell/admin targets (PowerShell, cmd, Windows Terminal, WSL, bash, regedit,
  MMC, Python consoles, Task Scheduler, Services, Group Policy, etc.) are
  rejected by the skill serializer as a second defense layer.
- Execution still uses `device_semantic_action`; therefore the existing tool
  permission engine, audit log, app-scope guard and Windows UIA verification
  remain authoritative.
- Learned-skill lookup/inspection/validation is read-only. Deleting a skill is
  `SAFE_ACTION` and should only be selected for an explicit user request.

## Confidence and demotion

Each skill tracks successes, failures, consecutive failures, confidence and
status. A successful verified reuse increases confidence. A stale validation or
failed learned semantic action decreases confidence. Two consecutive failures
(or sufficiently low confidence) demote the skill so it is not returned by
normal lookup.

## Parameters

The skill format supports placeholders in intent templates, semantic locators,
text and keys, for example:

```text
message {contact} {text}
```

`device_skill_find` binds parameters from the current command and
`device_skill_validate` resolves the rendered semantic target live. Parameter
placeholders are preserved when a locator adapts so one successful run cannot
collapse a generic skill into a single contact/value.

## Persistence

- Local/default: atomic `data/app_skills.json`.
- Hosted with `IRAS_SKILL_DATABASE_URL` (or the normal cloud `DATABASE_URL`):
  Postgres table `iras_app_skills_v1`.
- `IRAS_SKILL_NAMESPACE` can isolate independent users/deployments; default is
  `default` for existing single-user IRAS deployments.

## Management tools

- `device_skill_list`
- `device_skill_inspect`
- `device_skill_delete`
- `device_skill_find`
- `device_skill_validate`

## Version

This patch bumps both package metadata and `iras.__version__` to `3.4.0`.
