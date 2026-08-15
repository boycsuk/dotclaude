# PreToolUse hook: blocks force pushes and direct pushes to main/master.
#
# The push-to-main rule is opt-out: a workflow that lives entirely on main
# (solo project, prototype, scratch repo) is legitimate. To opt out, set
# "allowPushToMain": true in .claude/settings.local.json (gitignored, so
# the choice is personal — never forced onto teammates). Force push is
# never opt-out — it can rewrite shared history and stays blocked always.
#
# Everything is decided from the ISOLATED ARGUMENTS OF THE PUSH ITSELF, never
# from the raw command line. Two failure modes motivate that (both were real):
#   - Matching the whole string blocks innocent commands: a commit message
#     containing "+main", or a heredoc that merely writes the words "git push",
#     is not a push. False positives here are expensive — they teach the model
#     that this hook is noise, and it is the one guarantee DESIGN.md §18 calls
#     unconditional.
#   - Matching surface syntax misses real pushes: `+main:main` force-pushes
#     without the --force flag, `HEAD:main` targets main without the word
#     appearing as a token, and a bare `git push` on main names no branch at
#     all. So resolve the refspec DESTINATION, and fall back to the checked-out
#     branch when no refspec is given.
#
# Lockstep sibling of guard-push-main.sh — tests/guard-push-main-cases.py
# (run with --pwsh) is the shared contract.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$cmd = $data.tool_input.command
if (-not $cmd) { exit 0 }

# --- Strip file-writer heredoc bodies; keep executed ones --------------------
# Same allowlist as guard-destructive: a heredoc piped into `cat > file` /
# `tee file` is data being written, and judging it would false-positive on
# notes that merely contain "git push origin main". A heredoc fed to an
# interpreter (`bash <<EOF`) EXECUTES its body, so it stays in the scanned
# text. Unknown shapes fail CLOSED (body kept).
$writerRe = '^\s*(?:cat\s*>{1,2}\s*[^\s|;&<>()]+|tee\s+(?:-a\s+)?[^\s|;&<>()]+)\s*<<-?\s*["'']?[A-Za-z_][A-Za-z0-9_]*["'']?\s*$'
$unsafeRe = '[|`]|\$\(|;|&&|\|\||\bsh\b|\bbash\b|\bzsh\b|\bssh\b|\bdocker\b|\bkubectl\b|\beval\b|\bpython[0-9.]*\b|\bnode\b|\bperl\b|\bruby\b'
$lines = $cmd -split "`n"
$keptLines = @()
$i = 0
while ($i -lt $lines.Count) {
    $line = $lines[$i]
    $keptLines += $line
    $m = [regex]::Match($line, '<<-?\s*["'']?([A-Za-z_][A-Za-z0-9_]*)["'']?')
    if (-not $m.Success -or $line -notmatch $writerRe -or $line -match $unsafeRe) {
        $i++
        continue
    }
    $delim = $m.Groups[1].Value
    $j = $i + 1
    while ($j -lt $lines.Count -and $lines[$j].Trim() -ne $delim) { $j++ }
    if ($j -ge $lines.Count) { $i++; continue }   # unterminated — keep everything
    $keptLines += $lines[$j]                       # keep the closing delimiter
    $i = $j + 1
}
$cmd = $keptLines -join "`n"

# --- Tokenise, honouring quotes ----------------------------------------------
# A newline OUTSIDE quotes separates commands exactly like ';' — collapsing it
# to whitespace used to merge a multi-line block into ONE segment, and the
# push at the end was judged by the block's first command. A newline inside
# quotes (a multi-line commit message) stays part of the token.
function Split-CommandLine([string]$line) {
    $tokens = @()
    $current = ""
    $quote = $null
    $chars = $line.ToCharArray()
    for ($k = 0; $k -lt $chars.Count; $k++) {
        $ch = $chars[$k]
        if ($quote) {
            if ($ch -eq $quote) { $quote = $null } else { $current += $ch }
        } elseif ($ch -eq '"' -or $ch -eq "'") {
            $quote = $ch
        } elseif ($ch -eq '\' -and $k + 1 -lt $chars.Count -and $chars[$k + 1] -eq "`n") {
            $k++                                    # line continuation
        } elseif ($ch -eq "`n" -or $ch -eq "`r") {
            if ($current -ne "") { $tokens += $current; $current = "" }
            $tokens += ";"
        } elseif ($ch -match '\s') {
            if ($current -ne "") { $tokens += $current; $current = "" }
        } else {
            $current += $ch
        }
    }
    if ($current -ne "") { $tokens += $current }
    # Plain return, NOT `,$tokens`: the caller wraps with @(...), which does
    # not unwrap — a comma-wrapped return arrives as ONE nested element and
    # the `;` separator tokens are never seen individually. (`,$array` is only
    # right when the caller assigns without @(), as Get-PushArgs' caller does.)
    return $tokens
}

$tokens = @(Split-CommandLine $cmd)

# Split into separate commands so `git commit -m "..." ; git push ...` is judged
# on the push alone.
$segments = @()
$currentSeg = @()
foreach ($tok in $tokens) {
    if ($tok -in @("&&", "||", ";", "|", "&")) {
        $segments += ,$currentSeg
        $currentSeg = @()
    } else {
        $currentSeg += $tok
    }
}
$segments += ,$currentSeg

# Global git flags that consume the following argument.
$VALUED_GIT = @("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
# push flags that consume the following argument. --signed is NOT here: it is
# boolean (--signed / --no-signed / --signed=<mode>) and never consumes a
# separate token — listing it swallowed the remote and let
# `git push --signed origin HEAD:main` pass.
$VALUED_PUSH = @("--repo", "-o", "--push-option", "--receive-pack", "--exec",
                 "--recurse-submodules")

function Test-GitWord([string]$w) {
    # The git binary in any spelling: git, git.exe, \path\to\git(.exe).
    return ($w -eq "git" -or $w -eq "git.exe" -or
            $w -like "*/git" -or $w -like "*\git" -or
            $w -like "*/git.exe" -or $w -like "*\git.exe")
}

function Get-PushArgs($seg) {
    # Returns the arguments AFTER `push`, or $null if this segment is not a push.
    $gi = -1
    for ($i = 0; $i -lt $seg.Count; $i++) {
        if (Test-GitWord $seg[$i]) { $gi = $i; break }
    }
    if ($gi -lt 0) { return $null }
    # @(...) is load-bearing: a one-element slice collapses to a bare string, and
    # then $rest[0] is its first CHARACTER, so `git push` (whose only remaining
    # token is "push") silently failed to be recognised as a push at all.
    $rest = @(if ($gi + 1 -lt $seg.Count) { $seg[($gi + 1)..($seg.Count - 1)] } else { @() })
    $i = 0
    while ($i -lt $rest.Count) {
        $w = $rest[$i]
        if ($w.StartsWith("-")) {
            $i += if ($VALUED_GIT -contains $w) { 2 } else { 1 }
            continue
        }
        if ($w -ne "push") { return $null }
        # `return if (...) {...}` is a runtime error in PowerShell — `if` is a
        # statement, not an expression, in that position. Assign, then return.
        $after = @(if ($i + 1 -lt $rest.Count) { $rest[($i + 1)..($rest.Count - 1)] } else { @() })
        return ,$after
    }
    return $null
}

$verdict = $null
$verdictBranch = $null

foreach ($seg in $segments) {
    # Get-PushArgs returns $null for "not a push" and a (possibly empty) array
    # otherwise. The ,$array wrapping inside it keeps an empty result from
    # collapsing to $null — a bare `git push` has no arguments and must still
    # be judged, since it targets the checked-out branch.
    $pushArgs = Get-PushArgs $seg
    if ($null -eq $pushArgs) { continue }
    $args = @($pushArgs)

    # --- Force, by flag, by --mirror, or by a leading '+' on a refspec -------
    foreach ($a in $args) {
        if ($a -eq "-f" -or $a.StartsWith("--force")) { $verdict = "FORCE_FLAG"; break }
    }
    if ($verdict) { break }
    if ($args -contains "--mirror") { $verdict = "MIRROR"; break }
    foreach ($a in $args) {
        if (-not $a.StartsWith("-") -and $a.StartsWith("+")) { $verdict = "FORCE_REFSPEC"; break }
    }
    if ($verdict) { break }

    # --- Which branch would this land on? -----------------------------------
    $cleaned = @()
    $j = 0
    while ($j -lt $args.Count) {
        $a = $args[$j]
        if ($a.StartsWith("-")) {
            $j += if ($VALUED_PUSH -contains $a) { 2 } else { 1 }
            continue
        }
        $cleaned += $a
        $j++
    }
    # @(...) again: `git push origin main` leaves one refspec, and an unwrapped
    # single-element slice would be iterated character by character.
    $refspecs = @(if ($cleaned.Count -gt 1) { $cleaned[1..($cleaned.Count - 1)] } else { @() })

    $deleteMode = ($args -contains "--delete") -or ($args -contains "-d")
    $allMode = ($args -contains "--all") -or ($args -contains "--branches")

    $targets = @()
    foreach ($spec in $refspecs) {
        $dst = ($spec -split ':')[-1]
        $dst = $dst.TrimStart('+') -replace '^refs/heads/', ''
        # A deletion (--delete flag, or an empty-src ':dst' refspec) is not a
        # push of commits: deleting remote main/master is destructive and
        # never opt-out; deleting a feature branch is legitimate.
        $deleting = $deleteMode -or ($spec.Contains(":") -and ((($spec -split ':', 2)[0]).TrimStart('+') -eq ""))
        if ($deleting) {
            if ($dst -in @("main", "master")) { $verdict = "DELETE"; $verdictBranch = $dst; break }
            continue
        }
        $targets += $dst
    }
    if ($verdict) { break }

    if ($allMode) { $targets += "main" }           # --all/--branches push main too

    # No refspec at all, or one whose destination is HEAD/@: git resolves it
    # from the checked-out branch, which never appears in the command string.
    # A deletion-only push must NOT fall back to HEAD.
    $needsHead = (($refspecs.Count -eq 0) -and ($targets.Count -eq 0))
    foreach ($t in $targets) { if ($t -in @("HEAD", "@", "")) { $needsHead = $true } }
    if ($needsHead) {
        $targets = @($targets | Where-Object { $_ -notin @("HEAD", "@", "") })
        try {
            $branch = & git symbolic-ref --quiet --short HEAD 2>$null
            if ($LASTEXITCODE -eq 0 -and $branch) { $targets += $branch.Trim() }
        } catch { }
    }

    foreach ($t in $targets) {
        if ($t -in @("main", "master")) {
            $verdict = "MAIN"
            $verdictBranch = $t
            break
        }
    }
    if ($verdict) { break }
}

if (-not $verdict) { exit 0 }

if ($verdict -eq "FORCE_FLAG") {
    [Console]::Error.WriteLine("BLOCKED: force push detected. The user must run this manually if absolutely necessary.")
    exit 2
}
if ($verdict -eq "FORCE_REFSPEC") {
    [Console]::Error.WriteLine("BLOCKED: force push detected (a leading '+' on a refspec forces the update).")
    [Console]::Error.WriteLine("        The user must run this manually if absolutely necessary.")
    exit 2
}
if ($verdict -eq "MIRROR") {
    [Console]::Error.WriteLine("BLOCKED: 'git push --mirror' can rewrite or delete remote refs — equivalent to a force push.")
    [Console]::Error.WriteLine("        The user must run this manually if absolutely necessary.")
    exit 2
}
if ($verdict -eq "DELETE") {
    [Console]::Error.WriteLine("BLOCKED: this would DELETE the remote '$verdictBranch' branch — as destructive as a force push.")
    [Console]::Error.WriteLine("        The user must run this manually if absolutely necessary.")
    exit 2
}

# MAIN — honour the opt-out.
$allowMain = $false
$projectDir = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$localSettings = Join-Path $projectDir ".claude\settings.local.json"
if (Test-Path $localSettings) {
    try {
        $local = Get-Content $localSettings -Raw | ConvertFrom-Json
        if ($local.allowPushToMain -eq $true) { $allowMain = $true }
    } catch { }
}
if ($allowMain) { exit 0 }

[Console]::Error.WriteLine("BLOCKED: direct push to main/master (target branch: $verdictBranch). Use a feature branch and a PR instead.")
[Console]::Error.WriteLine("        If this project intentionally lives on main, set `"allowPushToMain`": true in .claude/settings.local.json.")
exit 2
