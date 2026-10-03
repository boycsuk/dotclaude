# statusLine command: prints "<model> · <context>% ctx" below the prompt.
#
# Context percentage is the point: the number that decides when compaction hits
# is otherwise invisible until it happens, and compaction is what reinject-rules
# exists to repair.
#
# Runs on every assistant message, after /compact, and on permission-mode
# changes, so it must be cheap and must never fail loudly: a status line that
# errors prints its error where the status belongs. Every failure path exits 0
# with no output.
#
# Lockstep sibling of statusline.sh.

$rawInput = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($rawInput)) { exit 0 }
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$parts = @()

$model = $data.model.display_name
if ($model) { $parts += [string]$model }

# used_percentage is null before the first API call and again right after
# /compact until the next one — exactly when someone glances at the bar. Show
# nothing rather than a misleading 0%.
$ctx = $data.context_window
if ($null -ne $ctx -and $ctx.used_percentage -is [ValueType]) {
    $pct = [int][math]::Floor($ctx.used_percentage)
    # A 1M-context session sits at single digits for most of a long run, so the
    # threshold is on remaining headroom, not a fixed percentage.
    $size = 0
    if ($ctx.context_window_size -is [ValueType]) { $size = [int]$ctx.context_window_size }
    $warn = ($pct -ge 70) -or ($size -gt 0 -and ($size - $size * $pct / 100) -lt 40000)
    $mark = if ($warn) { "!" } else { "" }
    $parts += "$mark$pct% ctx"
}

# @(...) then .Count: PowerShell unwraps a one-element array to a bare string,
# whose .Count is 1 but whose -join would still be fine — the guard is for the
# empty case, where an unwrapped $null would print a blank line.
if (@($parts).Count -gt 0) { (@($parts) -join " · ") | Write-Output }

exit 0
