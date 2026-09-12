# IRAS Universal Installed-App Launcher Fix

The app detector and the app launcher were previously treated as if they were
the same thing. They are not.

Windows can expose several Start-menu/App Paths records for one installed app,
for example:

```text
Blender 5.2
Blender 5.2.1.0
blender-launcher
```

The old resolver could reject this as ambiguous, even though all of those
records belong to the same app family.

The old launcher also selected only one record and one launch mechanism. If
that Windows record did not launch correctly, IRAS stopped instead of trying
an equivalent safe record.

This hotfix adds:

- version-aware app-family matching;
- direct EXE preference when an App Paths executable exists;
- ShellExecuteW for Windows AppsFolder/AUMID launches;
- explorer.exe AppsFolder fallback;
- equivalent-record retry for the same application family;
- lightweight process/foreground verification;
- detailed launch-attempt diagnostics;
- a real-machine catalog self-resolution audit.

Shells/admin consoles remain blocked.

Note: "detected by Windows" still does not mean "safe GUI application." IRAS
intentionally will not remotely launch Command Prompt, PowerShell, Windows
Terminal, WSL, Registry Editor, or similar command/admin surfaces.
