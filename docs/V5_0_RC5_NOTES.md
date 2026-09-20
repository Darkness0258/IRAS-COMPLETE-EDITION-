# IRAS v5.0.0 RC5 — Research + Installer + Coding-Agent Reliability

RC5 extends RC3 without changing Remote protocol `1`.

## Dedicated Web Research Agent

`/research <question>` starts a read-only evidence workflow: scope the question, discover sources, fetch evidence, cross-check claims, review conflicts/recency, then synthesize a cited result. The Research Agent receives only public web retrieval tools and cannot inherit Windows mutation authority. Controls: `/research status`, `/research pause`, `/research resume`, `/research cancel`.

## Permissioned Software Installer Agent

`/install search <software>` performs package discovery. `/install <software-or-exact-package-id>` uses the WinGet path and resolves an exact package ID before installation. `/install url <https://...exe|msi>` is the direct-web fallback for an official installer URL.

Direct web installers are fail-closed: public HTTPS only; private/loopback/link-local/reserved targets are rejected; downloads are size-bounded and cached under the IRAS installer cache; SHA-256 is recorded; Authenticode must be `Valid` both when prepared and immediately before execution. Arbitrary local executable paths are not accepted. `.msi` uses bounded `msiexec`; `.exe` launches without a shell and may then use the existing permissioned UI controls. IRAS never bypasses UAC, SmartScreen, Remote authentication, local policy, emergency stop or ToolRegistry approval.

Software installation is CRITICAL and additionally requires the laptop-local Remote policy to allow shell/command execution. Master Control can suppress ordinary IRAS approval prompts only within its existing bounded authority; it does not bypass Windows elevation.

## Coding Agent reliability fixes

RC5 retains the RC3 project resolver (explicit path precedence, typo-tolerant project identity, project-root preference over nested artifact/mockup/test repositories, fail-closed ambiguity, remembered/revalidated project selection) and hardens success semantics. Coding/installer tasks that report permission/device blockers or explicitly say they could not perform the work are not recorded as successful. Dedicated state-changing agent runs require a coordinator `OUTCOME: COMPLETE` before the run can end as `succeeded`.

## Release/validator fixes

The clean-tree validator now ignores `.venv`, `.git`, `.tox`, `.nox` and `node_modules` while still rejecting source caches, compiled Python, build/dist and egg-info debris. This fixes the false failure observed when a legitimate local virtual environment contained `__pycache__` files.

## Deployment requirement

The Windows Cloud Client and Render Cloud API must run the same RC5 source. If `/code projects`, `/code use`, `/research`, or `/install` returns HTTP 404, the cloud deployment is stale and must be redeployed from RC5. A local ZIP update alone cannot add server routes to an older Render deployment.

## Validation

RC5 is accepted only when the clean-tree validator, integrated validator, compile validation and full local pytest suite pass from the packaged source. Remote protocol must remain `1`.


## Software lifecycle additions

RC5 adds update discovery, targeted updates, explicit update-all, and exact-package uninstall. State-changing operations are CRITICAL, require a live authenticated Remote session and laptop-local `allow_shell`, use WinGet with `shell=False`, and verify the resulting installed/update state. Direct URL receipts remain installation-only.
