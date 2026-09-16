# IRAS v4.3 RC1 Deep Audit Report

## Scope

This pass audited the v4.2 RC6 cloud runtime, autonomous routing, orchestration and multitasking supervisors, Windows bridge, file/project tools, public web/API retrieval, tool registry, audit logging, permissions, and release contracts. It also added regression coverage for the newly identified failure classes.

No finite audit can prove that all bugs are gone. This release closes the high-confidence defects and missing capabilities found in this pass and records residual risks explicitly rather than hiding them.

## High-confidence issues fixed

1. **External-content prompt-injection ambiguity** — web/API/browser output now carries an explicit untrusted-data security envelope and prompt-injection indicators before being returned to model context.
2. **Tool arguments were not schema-enforced at execution time** — arguments are now validated before authorization/handler execution.
3. **Secret redaction gaps** — env-style secrets, bearer tokens, common provider/GitHub token formats, and JWT-like values embedded in generic strings are redacted.
4. **Cloud/local permission mismatch** — device tools now resolve permission from the exact remote action and arguments. Sensitive paths and process termination require `CRITICAL`.
5. **Oversized/binary web/API response risk** — public retrieval is streamed with byte caps, textual content-type checks, header limits, URL credential rejection, and redirect revalidation.
6. **Non-atomic text mutation** — non-append writes and exact replacement now use same-directory temp files plus atomic replacement.
7. **Symlink traversal during recursive copy/search** — recursive copy fails closed on symlink-containing trees; search skips symlinks and credential paths.
8. **Insufficient engineering inspection tools** — added ranged reads, bounded recursive text search, file metadata/SHA-256, Git diff/log, and targeted pytest execution.
9. **Generic Git command surface too permissive** — unsafe config/credential/helper mechanisms are blocked and mutation classes receive stronger permissions.
10. **Unbounded supervisor queue growth** — orchestration and classic multitask runs are capped per requester.
11. **Orchestration history disappeared after cloud restart** — journal history is loaded for observability; interrupted work is failed, not replayed, and session secrets are never restored.
12. **Kill-process classification too weak** — arbitrary process termination is now `CRITICAL`.

## New developer tools

- `device_read_text_range`
- `device_search_text`
- `device_file_info` with SHA-256
- `device_git_diff`
- `device_git_log`
- targeted `device_run_tests`
- local equivalents for ranged read/search/file info

All are bounded and constrained to configured/allowed roots where applicable.

## Residual risks / deliberate boundaries

- DNS rebinding cannot be eliminated solely by pre-resolution checks; the current public-target checks and redirect validation reduce but do not mathematically eliminate DNS TOCTOU risk.
- Dependency supply-chain reproducibility is not fully pinned to immutable hashes in this RC. CI action tags and Python dependency ranges should eventually be pinned after verified compatibility/upgrade policy is established.
- Running a project test suite executes project code. It remains permission-gated and bounded, but it is not a sandbox. A future release can add a dedicated local `allow_code_execution` policy or disposable test sandbox.
- Cancellation remains cooperative for already-running bounded workers; completed late results are discarded rather than forcefully killing threads.
- No automated test suite proves the absence of all prompt-injection strategies; the design therefore combines explicit trust labels, least privilege, schema validation, permission gates, and below-model safety controls.

## Release validation

- Full regression suite: 686 tests.
- Dedicated deep-audit regressions: prompt-injection labelling, secret redaction, schema rejection, sensitive-path permissions, dynamic remote permission resolution, atomic writes, symlink refusal, project search/read/hash, bounded Git diff/log, targeted tests, restart recovery without replay, and active-run backpressure.
- Remote protocol remains version `1` because the transport/wire contract did not change.
