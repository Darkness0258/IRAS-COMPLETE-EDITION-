# IRAS v4.2.0 RC6 — Specialized Agent Execution Hardening

RC6 hardens the autonomous chat/multi-agent path after real-device acceptance exposed two last-mile issues: research workers could fall back to browser/UI observation instead of extracting web text, and implementation workers could reason about a code fix without receiving a bounded code-edit tool before exhausting the normal agent step budget.

## Researcher hardening

- Adds `web_search`, a read-only public-web search tool that returns result titles and URLs without opening a browser window.
- `http_get` now converts HTML into readable text and validates every redirect target before following it, preserving the private/local-network SSRF boundary.
- Researcher workers receive a role-scoped tool allowlist containing `web_search`, `http_get`, `api_request`, and only the read-only project tools they need.
- The Researcher directive explicitly prefers text retrieval over UI automation for ordinary web research.

## Coder hardening

- Adds remote action/tool `replace_text` / `device_replace_text` for exact bounded source edits inside configured Windows allowed roots.
- Existing source files can be patched only when the expected old snippet is present; replacement count and file size are bounded.
- `replace_text` remains a `SYSTEM_ACTION`, so cloud Remote-session permission, laptop local policy, allowed roots, command queue, and emergency stop remain authoritative.
- Coder workers receive a narrow role allowlist: inspect/list/status, `device_replace_text`, new-file `device_write_text`, and bounded test execution. No arbitrary shell is added.
- Specialized orchestration workers get a separate bounded step budget (`IRAS_ORCHESTRATION_AGENT_MAX_STEPS`, default 14, range 8..24); normal chat retains its existing budget.

## Planner fallback hardening

If the Planner model itself is unavailable, implementation-heavy objectives no longer collapse into one broad `general` worker. The local fallback graph preserves:

`Inspect current implementation -> Implement bounded change -> Test implemented change -> Review change/regressions -> Coordinator`

Upstream outputs remain explicitly labelled untrusted data.

## Compatibility

- Remote protocol remains `1`.
- Existing Windows pairing remains compatible.
- v4.2 deterministic exact-file fallback, provider cooldown handling, autonomous chat routing, pause/resume/cancel, DPAPI secrets, local policy, and emergency stop are unchanged.
