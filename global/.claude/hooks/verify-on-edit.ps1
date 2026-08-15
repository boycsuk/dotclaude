# PostToolUse hook: runs the project's linter/typechecker after edits.
# Auto-detects the stack. Silent if nothing applicable. Exit 2 with stderr if checks fail.
# Configure in settings.json with "shell": "powershell".
#
# $ErrorActionPreference stays at Continue: under Windows PowerShell 5.1 with
# EAP=Stop, stderr from a native command redirected with 2>&1 becomes
# ErrorRecords and the first line throws a terminating NativeCommandError —
# npm prints warnings to stderr even on SUCCESS, so the hook died on nearly
# every JS project. (pwsh 7.2+ does not have this behaviour, but powershell.exe
# is a supported host for this file.)
#
# Lockstep sibling of verify-on-edit.sh; tests/verify-on-edit-cases.py is the
# shared contract (run it with --pwsh).

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
try { Set-Location $root } catch { exit 0 }

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$file = $data.tool_input.file_path
if (-not $file) { exit 0 }

# Project membership like the .sh's `case "$FILE" in "$ROOT"/*)`: normalized,
# separator-anchored (root C:\proj must NOT match C:\proj-other), and
# case-insensitive — NTFS is, and a lower-case drive letter otherwise skips
# verification silently.
try {
    $rootFull = [System.IO.Path]::GetFullPath($root).TrimEnd('/', '\')
    $fileFull = [System.IO.Path]::GetFullPath($file)
} catch { exit 0 }
$sep = [System.IO.Path]::DirectorySeparatorChar
if (-not $fileFull.StartsWith($rootFull + $sep, [System.StringComparison]::OrdinalIgnoreCase)) { exit 0 }

$ext = [System.IO.Path]::GetExtension($file).TrimStart('.')
$script:errors = @()

# Per-check budget. VERIFY_TIMEOUT is an env override for the test matrix;
# production default is 15s per check, under the 60s per-hook timeout in
# settings.json. The earlier version had no internal bound and one slow
# typecheck silently discarded the WHOLE hook (harness cancellation drops all
# output), losing verification on every project whose checks exceed the wrapper.
$checkTimeout = if ($env:VERIFY_TIMEOUT) { [int]$env:VERIFY_TIMEOUT } else { 15 }

function Invoke-Check {
    param([string]$Description, [string]$Exe, [string[]]$CmdArgs)
    # System.Diagnostics.Process instead of `&`: it gives a real wall-clock
    # bound (WaitForExit) and captured streams that keep their newlines —
    # interpolating an `&` output array flattened diagnostics onto one line.
    # We intentionally avoid Start-Job: $LASTEXITCODE does not propagate and
    # arguments are dropped unless passed via -ArgumentList (both were real
    # bugs here: ruff/mypy once ran with no file).
    $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { return }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $cmd.Source
    $quoted = $CmdArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    $psi.Arguments = $quoted -join ' '
    # .cmd/.bat shims (npm on Windows) are not directly executable by
    # Process.Start with UseShellExecute=$false; route them through cmd.exe.
    if ($psi.FileName -match '\.(cmd|bat)$') {
        $psi.Arguments = '/c "' + $psi.FileName + '" ' + $psi.Arguments
        $psi.FileName = if ($env:ComSpec) { $env:ComSpec } else { "cmd.exe" }
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = (Get-Location).Path
    try { $p = [System.Diagnostics.Process]::Start($psi) } catch { return }
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($checkTimeout * 1000)) {
        # The check timed out: the budget's fault, not the code's. Reporting
        # it as a lint failure is the cry-wolf DESIGN.md §26 warns about.
        try { $p.Kill($true) } catch { try { $p.Kill() } catch { } }
        return
    }
    if ($p.ExitCode -ne 0) {
        $script:errors += "$Description failed:`n" + ($outTask.Result + $errTask.Result).TrimEnd()
    }
}

switch -Regex ($ext) {
    '^(ts|tsx|mts|cts|js|jsx|mjs|cjs)$' {
        if (Test-Path package.json) {
            # Prefer the runner the project actually uses (lockfile evidence);
            # fall back to npm. Invoke-Check itself bails out quietly when the
            # runner is not on PATH — a bun/pnpm-only environment must not
            # turn every .ts edit into "npm: command not found".
            $runner = "npm"
            if (((Test-Path bun.lockb) -or (Test-Path bun.lock)) -and (Get-Command bun -ErrorAction SilentlyContinue)) { $runner = "bun" }
            elseif ((Test-Path pnpm-lock.yaml) -and (Get-Command pnpm -ErrorAction SilentlyContinue)) { $runner = "pnpm" }
            elseif ((Test-Path yarn.lock) -and (Get-Command yarn -ErrorAction SilentlyContinue)) { $runner = "yarn" }
            # Look under "scripts" specifically: a regex over the whole file
            # also matched dependency names, running scripts that do not exist.
            try { $scripts = (Get-Content package.json -Raw | ConvertFrom-Json).scripts } catch { $scripts = $null }
            if ($scripts -and $scripts.PSObject.Properties['typecheck']) { Invoke-Check "typecheck" $runner @("run", "typecheck", "--silent") }
            if ($scripts -and $scripts.PSObject.Properties['lint']) { Invoke-Check "lint" $runner @("run", "lint", "--silent") }
        }
        break
    }
    '^(py|pyi)$' {
        $hasRuffCfg = (Test-Path pyproject.toml) -or (Test-Path ruff.toml) -or (Test-Path .ruff.toml)
        if ((Get-Command ruff -ErrorAction SilentlyContinue) -and $hasRuffCfg) {
            Invoke-Check "ruff" "ruff" @("check", $file)
        }
        if ((Get-Command mypy -ErrorAction SilentlyContinue) -and (Test-Path pyproject.toml)) {
            $pyproject = Get-Content pyproject.toml -Raw
            if ($pyproject -match '\[tool\.mypy\]') {
            Invoke-Check "mypy" "mypy" @($file)
            }
        }
        break
    }
    '^rs$' {
        if ((Test-Path Cargo.toml) -and (Get-Command cargo -ErrorAction SilentlyContinue)) {
            Invoke-Check "clippy" "cargo" @("clippy", "--quiet", "--message-format=short", "--", "-D", "warnings")
        }
        break
    }
    '^go$' {
        if ((Test-Path go.mod) -and (Get-Command go -ErrorAction SilentlyContinue)) {
            Invoke-Check "go vet" "go" @("vet", "./...")
        }
        break
    }
    default { exit 0 }
}

if ($script:errors.Count -gt 0) {
    [Console]::Error.WriteLine("Verification failed after editing $($file):`n" + ($script:errors -join "`n"))
    exit 2
}
exit 0
