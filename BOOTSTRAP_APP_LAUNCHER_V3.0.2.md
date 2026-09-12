# IRAS v3.0.2 — Bootstrap App Launcher Fix

The Steam failure was not an app-discovery problem.

IRAS correctly found `Steam.exe`, but the launcher treated any immediate
nonzero child-process exit as definitive failure:

```text
Steam.exe exited immediately with code 4294967295
```

`4294967295` is the unsigned representation of `0xFFFFFFFF` / `-1`. Desktop
clients such as Steam can behave like bootstrap processes: the first process can
signal/spawn another instance and then exit. Therefore the bootstrap process'
exit code alone is not enough to decide whether the app opened.

v3.0.2 changes launch semantics:

1. Start a direct EXE with its installation directory as the working directory.
2. Record an early nonzero exit instead of immediately raising.
3. Verify whether the real application/process/window appeared.
4. Try equivalent Windows app records if available.
5. If Steam still does not verify, use the explicit safe registered protocol
   `steam://open/main`.
6. Never execute arbitrary URI schemes supplied by the user.

PowerShell, Command Prompt, Windows Terminal, WSL, Registry Editor and other
blocked command/admin targets remain blocked.

The repeated Render `/health` 200 responses are healthy probe traffic. The
`/favicon.ico` 404 is also harmless.
