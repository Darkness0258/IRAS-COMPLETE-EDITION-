# IRAS v3.1.0 — Universal Safe GUI App Launcher

This release generalizes bootstrap-launch handling to every safe GUI app
Windows can discover. It removes the split between legacy open-app launching
and AppCatalog-based launching.

IRAS now discovers and can use:

- Windows Get-StartApps / AppsFolder IDs
- App Paths registry executables
- User Start-menu shortcuts
- System Start-menu shortcuts
- User Desktop shortcuts
- Public Desktop shortcuts

For EXE apps, IRAS tries direct launch with the correct working directory,
verifies the real process/window, then tries generic Windows ShellExecuteW
against the discovered executable and equivalent app-family records.

For shortcut apps, IRAS uses Windows ShellExecuteW on the discovered .lnk.

For packaged/UWP AppsFolder entries, IRAS uses ShellExecuteW and explorer.exe
AppsFolder fallback.

Immediate nonzero bootstrap exit codes are recorded rather than treated as
definitive failure before verification/fallbacks run.

There is no Steam-only protocol or per-app hardcoding in this launcher.

Security remains unchanged: command shells, PowerShell, Windows Terminal, WSL,
Registry Editor, MMC/admin consoles, Python interpreters, and similar command-
capable targets remain blocked.
