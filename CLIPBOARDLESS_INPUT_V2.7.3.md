# IRAS v2.7.3 — Clipboardless Windows Input

The Spotify error came from the current text-entry path using the global Windows
clipboard. Another process can temporarily own the clipboard, causing:

```text
Could not open Windows clipboard.
```

v2.7.3 changes active text entry to Win32 `SendInput` with
`KEYEVENTF_UNICODE`.

Spotify flow becomes:

```text
focus Spotify
→ Ctrl+K
→ type the query with SendInput
→ Down
→ Enter
```

The active typing path no longer depends on the clipboard, so it also improves
text entry in Chrome, VS Code, Notepad, and File Explorer.

Version:

```text
IRAS / Windows: 2.7.3
Android: 2.7.3
Android versionCode: 20703
```
