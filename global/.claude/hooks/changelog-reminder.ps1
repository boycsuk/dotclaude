# Stop hook: says so when a turn ends with code changed but CHANGELOG.md untouched.
#
# ADVISORY BY CONSTRUCTION. Emits `systemMessage` and exits 0, never
# `decision: "block"` and never exit 2. Both of those, and
# `hookSpecificOutput.additionalContext` too, CONTINUE the conversation on Stop
# — the docs give additionalContext "the same loop protections as
# decision: block", so it is not a passive channel. A Stop hook cannot tell a
# finished task from a half-done one (it fires on every turn), so anything that
# resumes the turn would interrupt legitimate mid-task work. systemMessage is
# the one combination that surfaces text without resuming.
#
# Lockstep sibling of changelog-reminder.sh.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

# Already continuing because of a stop hook: stay quiet. Moot while this hook is
# advisory, kept so adding a blocking path later cannot forget the guard.
if ($data.stop_hook_active) { exit 0 }

$root = $data.cwd
if (-not $root) { $root = (Get-Location).Path }
if (-not (Test-Path -LiteralPath $root -PathType Container)) { exit 0 }

# Bound every git call: an unbounded git on a huge or locked repo would sit in
# the turn-end path. WaitForExit needs no external binary, unlike the .sh's
# `timeout` (GNU coreutils, absent from a stock macOS).
function Invoke-Git {
    param([string[]]$GitArgs, [int]$TimeoutMs = 2000)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    # -C first so the call never depends on the session's location.
    foreach ($a in (@("-C", $root) + $GitArgs)) { [void]$psi.ArgumentList.Add($a) }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    try { $p = [System.Diagnostics.Process]::Start($psi) } catch { return $null }
    $stdout = $p.StandardOutput.ReadToEnd()
    if (-not $p.WaitForExit($TimeoutMs)) {
        try { $p.Kill() } catch { }
        return $null
    }
    if ($p.ExitCode -ne 0) { return $null }
    return $stdout
}

if ($null -eq (Invoke-Git @("rev-parse", "--git-dir"))) { exit 0 }

# A repo with no CHANGELOG.md has not opted into keeping one.
if (-not (Test-Path -LiteralPath (Join-Path $root "CHANGELOG.md") -PathType Leaf)) { exit 0 }

$status = Invoke-Git @("status", "--porcelain")
if ([string]::IsNullOrWhiteSpace($status)) { exit 0 }

# @(...) on every split: PowerShell unwraps a one-element array to a bare
# string, and indexing a string yields its first character.
$changed = @($status -split "`n" |
    ForEach-Object { if ($_.Length -gt 3) { $_.Substring(3).Trim() } } |
    Where-Object { $_ })

# -ccontains, matching the .sh's `grep -qx`: on a case-insensitive filesystem
# `changelog.md` really is the file, but the comparison itself stays exact so
# both siblings agree on every case.
if ($changed -ccontains "CHANGELOG.md") { exit 0 }

# Docs, config and lockfiles are not the "code changed" this reminder is about.
$skipExt = '\.(md|txt|lock|json|ya?ml|toml|cfg|ini)$'
$skipName = '(^|/)(CHANGELOG|README|LICENSE)'
$code = @($changed | Where-Object { $_ -notmatch $skipExt -and $_ -notmatch $skipName })
if ($code.Count -eq 0) { exit 0 }

$first = ($code | Select-Object -First 3) -join " "
$msg = "CHANGELOG.md not updated — $($code.Count) changed file(s): $first " +
       "(A task is done only when it compiles, passes tests, and is logged in CHANGELOG.md.)"

@{ systemMessage = $msg } | ConvertTo-Json -Compress | Write-Output

exit 0
