# IRAS v4.3.0 RC1 — Deep Audit & Tool Hardening

IRAS v4.3 RC1 is a security, reliability, and developer-tooling hardening release built on the accepted v4.2 autonomous multi-agent architecture. The remote wire protocol remains `1`; the protocol format is unchanged.

## Security hardening

- External web/API/browser tool output is wrapped as **untrusted external data** before it re-enters the model context. Common prompt-injection signals are surfaced in `_iras_security` metadata instead of silently trusting retrieved text.
- Tool arguments are JSON-schema validated before permission checks or execution.
- Secret redaction now catches env assignments, bearer tokens, common OpenAI/OpenRouter/GitHub token shapes, and JWT-like values embedded inside generic strings.
- Sensitive paths such as `.ssh`, `.aws`, `.kube`, `.env`, credential/key files, and browser credential stores are dynamically classified `CRITICAL` for file access.
- Process termination is `CRITICAL`.
- Device-tool cloud permissions are dynamically resolved from the exact Windows action/arguments, eliminating cloud/local permission mismatches.
- Public web/API retrieval rejects embedded URL credentials, private/local targets, binary response types, unsafe headers, and oversized responses; redirect targets are revalidated.

## Safer file and project operations

- Non-append text writes and exact replacements use same-directory temporary files plus atomic `os.replace`.
- Recursive copies refuse symlink-containing trees instead of following links outside configured roots.
- Search skips symlinks and sensitive credential files.
- New bounded project-inspection tools: ranged text reads, recursive text search, file metadata/SHA-256, Git diff, Git log, and targeted pytest execution.
- Generic local Git execution now fails closed on unsafe config/credential/helper subcommands and classifies mutating operations more strictly.

## Supervisor resilience

- Orchestration and classic multitasking now cap active runs per requester to prevent unbounded work-queue growth.
- Orchestration history is recovered after cloud restarts for observability, but interrupted work is marked failed and **never replayed automatically**. Remote-session credentials are not restored from the journal.

## Validation

The v4.3 regression suite includes dedicated coverage for prompt-injection trust labelling, secret redaction, schema validation, sensitive-path permissions, dynamic device permissions, atomic/symlink-safe filesystem behavior, project inspection tools, targeted tests, restart recovery without replay, and active-run backpressure.
