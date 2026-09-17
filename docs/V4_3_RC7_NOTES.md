# IRAS v4.3.0 RC7 — Project Identity & Local Tool Execution

RC7 addresses two failures found in the RC6 real-device engineering run.

## Fixed

- **Strict project identity resolution.** A named project objective can no longer silently bind to an unrelated repository. `find_projects(query=...)` returns only query-matching repositories, and cloud preflight independently filters candidates before accepting a workspace.
- **Fair scanning across bridge roots.** Project discovery now allocates a bounded scan budget per configured root. A large `C:\Users\...` tree cannot consume the entire discovery budget before `D:\Projects` or another later root is inspected.
- **Query-prioritized traversal.** Directories whose names match the requested project identity are visited first inside each bounded root scan.
- **Ollama content-tool normalization.** Some local models emit a tool request as a complete JSON assistant message rather than OpenAI `tool_calls`. RC7 converts only complete JSON requests whose tool name was actually offered for the current turn.
- **Unknown local-model tools remain text.** JSON naming an unoffered tool is never executed.
- **Correct local assistant messages.** Device-local model replies now use a real `{"role":"assistant",...}` conversation message, including normalized tool-call metadata, so follow-up tool rounds remain valid.
- **Newest-context retention.** When a local-model context must be trimmed, RC7 preserves the newest prompt/tool results first instead of discarding the latest round.
- **Explicit local tool protocol.** Tool-bearing Ollama turns receive a small protocol nudge to prefer native tool calls and use the guarded JSON fallback only when native function calling is unavailable.

## Safety properties preserved

- Project-scoped tools stay bound to the preflight-verified Windows project root.
- Absolute path escapes are rejected before device execution.
- Remote authorization, bridge roots, permission levels, DPAPI secrets, and emergency stop remain authoritative.
- Device-local reasoning remains loopback-only through the authenticated outbound bridge.
- Remote protocol remains version `1`.
