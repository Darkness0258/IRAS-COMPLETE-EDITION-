# IRAS v2.5.1 build release

This release aligns the old continuous-voice test with the new Chrome hands-free
implementation and bumps both desktop and Android package versions to 2.5.1.

Why the previous apply script still committed after pytest failed:
Windows PowerShell 5.1 does not automatically treat a native program's non-zero
exit code as a terminating PowerShell error. The new release script explicitly
checks `$LASTEXITCODE` after pytest and refuses to commit if any test fails.

Expected GitHub Actions artifacts after push:

- IRAS-Android-APK
- IRAS-Windows-EXE

The existing workflow rules already rebuild Android when
`clients/android/**` changes and rebuild Windows when `pyproject.toml` changes.
