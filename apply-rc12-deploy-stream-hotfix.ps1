param(
    [string]$ProjectRoot = "D:\Projects\IRAS-complete"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

if (-not (Test-Path ".git")) {
    throw "Git repository not found at $ProjectRoot"
}

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "IRAS venv Python not found: $Python"
}

Write-Host "=== IRAS RC12 DEPLOY/STREAM HOTFIX ===" -ForegroundColor Cyan
git status -sb

# -------------------------------------------------------------------------
# 1. GitHub Actions: create and use the venv required by run-v500-validation.
# -------------------------------------------------------------------------
$workflow = ".github\workflows\ci.yml"
$wf = [System.IO.File]::ReadAllText((Resolve-Path $workflow))

$oldInstall = @'
      - name: Install
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all,cloud]"
'@

$newInstall = @'
      - name: Install
        shell: pwsh
        run: |
          python -m venv .venv
          .\.venv\Scripts\python.exe -m pip install --upgrade pip
          .\.venv\Scripts\python.exe -m pip install -e ".[all,cloud]"
'@

if ($wf.Contains($oldInstall)) {
    $wf = $wf.Replace($oldInstall, $newInstall)
    [System.IO.File]::WriteAllText(
        (Resolve-Path $workflow),
        $wf,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Host "Patched GitHub Actions venv setup." -ForegroundColor Green
}
elseif ($wf.Contains("python -m venv .venv")) {
    Write-Host "GitHub Actions venv setup already patched." -ForegroundColor DarkGray
}
else {
    throw "Could not find expected Install block in $workflow"
}

# -------------------------------------------------------------------------
# 2. Render SSE: bind sync generator resumes to one ContextVar context.
# -------------------------------------------------------------------------
$cloud = "src\iras\cloud_api.py"
$src = [System.IO.File]::ReadAllText((Resolve-Path $cloud))

if (-not $src.Contains("from contextvars import copy_context")) {
    $anchor = "from contextlib import contextmanager"
    if (-not $src.Contains($anchor)) {
        throw "Could not find contextlib import anchor in cloud_api.py"
    }
    $src = $src.Replace(
        $anchor,
        $anchor + [Environment]::NewLine + "from contextvars import copy_context"
    )
}

$oldLoop = @'
    def persisted_events():
        assistant_parts: list[str] = []
        recorded = False
        for chunk in events():
'@

$newLoop = @'
    def persisted_events():
        assistant_parts: list[str] = []
        recorded = False

        # StreamingResponse iterates synchronous generators through Starlette's
        # worker threadpool. Consecutive next() calls can therefore arrive with
        # different copied Context objects. Keep every events() resume inside
        # one explicit Context so ContextVar tokens created by
        # remote_command_context() are always reset in the same Context.
        stream_iter = iter(events())
        stream_context = copy_context()

        while True:
            try:
                chunk = stream_context.run(next, stream_iter)
            except StopIteration:
                break
'@

if ($src.Contains($oldLoop)) {
    $src = $src.Replace($oldLoop, $newLoop)
}
elseif ($src.Contains("stream_context.run(next, stream_iter)")) {
    Write-Host "Render stream ContextVar fix already patched." -ForegroundColor DarkGray
}
else {
    throw "Could not find persisted_events loop anchor in cloud_api.py"
}

[System.IO.File]::WriteAllText(
    (Resolve-Path $cloud),
    $src,
    (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "Patched Render SSE ContextVar handling." -ForegroundColor Green

# -------------------------------------------------------------------------
# 3. Voice doctor: suppress Windows PowerShell Invoke-WebRequest HTML warning.
# -------------------------------------------------------------------------
$doctor = ".\voice-doctor.ps1"
if (Test-Path $doctor) {
    $vd = [System.IO.File]::ReadAllText((Resolve-Path $doctor))
    $needle = @'
    $response = Invoke-WebRequest `
        -Method Post `
'@
    $replacement = @'
    $response = Invoke-WebRequest `
        -UseBasicParsing `
        -Method Post `
'@
    if ($vd.Contains($needle)) {
        $vd = $vd.Replace($needle, $replacement)
        [System.IO.File]::WriteAllText(
            (Resolve-Path $doctor),
            $vd,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Write-Host "Patched voice doctor BasicParsing mode." -ForegroundColor Green
    }
}

# -------------------------------------------------------------------------
# 4. Regression guard.
# -------------------------------------------------------------------------
$testPath = "tests\test_rc12_deploy_stream_hotfix.py"
$testBody = @'
from pathlib import Path


def test_ci_creates_the_venv_expected_by_release_validator():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m venv .venv" in text
    assert r".\.venv\Scripts\python.exe -m pip install -e" in text


def test_cloud_stream_binds_generator_resumes_to_one_context():
    text = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "from contextvars import copy_context" in text
    assert "stream_context = copy_context()" in text
    assert "stream_context.run(next, stream_iter)" in text
    assert "for chunk in events():" not in text


def test_voice_doctor_avoids_windows_powershell_html_execution_prompt():
    text = Path("voice-doctor.ps1").read_text(encoding="utf-8")
    assert "-UseBasicParsing" in text
'@

[System.IO.File]::WriteAllText(
    (Join-Path $ProjectRoot $testPath),
    $testBody,
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "`n=== TARGETED TESTS ===" -ForegroundColor Cyan
& $Python -m pytest -q `
    .\tests\test_rc12_voice_hotfix.py `
    .\tests\test_rc12_deploy_stream_hotfix.py
if ($LASTEXITCODE -ne 0) {
    throw "Targeted RC12 hotfix tests failed."
}

Write-Host "`n=== FULL RC12 VALIDATION ===" -ForegroundColor Cyan
.\run-v500-validation.ps1
if ($LASTEXITCODE -ne 0) {
    throw "Full RC12 validation failed."
}

Write-Host "`n=== GIT CHECK ===" -ForegroundColor Cyan
git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed."
}

git status --short
git diff --stat

Write-Host "`nHotfix is validated locally. Review the output, then commit and push." -ForegroundColor Green
