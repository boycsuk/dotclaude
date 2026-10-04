# dotclaude installer for Windows.
#
# Installs the CENTRAL config into $HOME\.claude\ - hooks, agents, skills,
# rules, output-styles, and the base settings.json. These apply to every
# project automatically, so improving the master repo and re-running this
# script propagates to all your projects at once.
#
# Also installs the per-project template and the /init-project skill.
#
# Re-running is safe: it refreshes the central artifacts it owns by removing only
# the files it shipped last time (per the manifest), so your own skills/agents/
# rules in those directories survive. It never clobbers your personal CLAUDE.md.
# In $HOME\.claude\settings.json it keeps every key you own, seeds defaults only
# when absent, and REPLACES the keys dotclaude owns (permissions, hooks,
# attribution) - saving a backup first whenever your file had entries there.
#
# This is the lockstep sibling of install.sh. On Windows the .ps1 hooks run
# under PowerShell, so the central settings.json points at the .ps1 files with
# "shell": "powershell", and every Bash permission rule gets a PowerShell(...) twin.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Join-Path $HOME ".claude"

Write-Host "==> Installing dotclaude into $Target"

# Prerequisite check, mirroring install.sh: the .ps1 hooks and this installer
# need PowerShell 5.1+, and the .py hooks run on Python.
if ($PSVersionTable.PSVersion.Major -lt 5) {
    [Console]::Error.WriteLine("ERROR: PowerShell 5.1 or newer is required (found $($PSVersionTable.PSVersion)).")
    exit 1
}
# Resolve an interpreter that actually RUNS, and wire the .py hooks to its full
# path. Get-Command alone is not enough: the Microsoft Store "python3" alias
# exists on a clean Windows install and only opens the Store. Every PATH match
# is tried, and the py launcher last (the python.org installer's default when
# python.exe is not on PATH). The path is baked into the hook commands, so after
# moving or upgrading Python, re-run this installer.
$PythonExe = $null
$PythonArgs = ""
foreach ($candidate in @(@("python3", ""), @("python", ""), @("py", "-3"))) {
    foreach ($cmd in @(Get-Command $candidate[0] -CommandType Application -All -ErrorAction SilentlyContinue)) {
        try {
            if ($candidate[1]) { & $cmd.Source $candidate[1] --version *> $null } else { & $cmd.Source --version *> $null }
            if ($LASTEXITCODE -eq 0) { $PythonExe = $cmd.Source; $PythonArgs = $candidate[1]; break }
        } catch { }
    }
    if ($PythonExe) { break }
}
if (-not $PythonExe) {
    [Console]::Error.WriteLine("ERROR: no working Python found (tried python3, python, py -3) - the .py hooks run on it. Install Python and re-run.")
    exit 1
}

# --- Syntax pre-flight: never install a hook that cannot be parsed -----------
# Lockstep with install.sh. A hook that fails to parse is a wall, not a degraded
# hook: the central guards run on PreToolUse, so an unparseable one breaks every
# session, and that state cannot be repaired from inside Claude Code (the broken
# hook blocks the installer that would replace it). Abort
# before copying, leaving the previously installed working hooks in place.
$hookDir = Join-Path $ScriptDir "global/.claude/hooks"
if (Test-Path $hookDir) {
    foreach ($hook in @(Get-ChildItem -Path $hookDir -Filter "*.ps1" -File)) {
        $tokens = $null
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            $hook.FullName, [ref]$tokens, [ref]$errors) | Out-Null
        if ($errors -and $errors.Count -gt 0) {
            [Console]::Error.WriteLine("  ! $($hook.Name) does not parse - aborting before anything is copied.")
            [Console]::Error.WriteLine("    $($errors[0].Message)")
            [Console]::Error.WriteLine("    Your currently installed hooks are untouched. Fix the source and re-run.")
            exit 1
        }
    }
}

# --- Central settings.json: derive the PowerShell form BEFORE copying anything --
# Its hard failures (an `if` gate, an unmapped rule) must abort while the
# previously installed hooks and settings still match each other.
function New-Hook($src, $name, $isPython) {
    # No `if` parameter on purpose: hook entries carry no `if` gates (a
    # prefix-anchored pattern reopens the wrapped-form bypasses the hooks'
    # own parsers close). check.py enforces the same on the
    # source JSON; the guard below keeps Windows from reintroducing one.
    # Claude Code launches a "shell": "powershell" hook as `powershell -Command
    # <command>`, and -Command converts a script's or program's exit 2 into
    # process exit 1 - which does not block. Without the trailing
    # `exit $LASTEXITCODE` every .ps1 guard was a no-op on Windows.
    if ($isPython) {
        $script = Join-Path (Join-Path $Target "hooks") "$name.py"
        $launcherArgs = if ($PythonArgs) { " $PythonArgs" } else { "" }
        $command = "& '$($PythonExe -replace "'", "''")'$launcherArgs '$($script -replace "'", "''")'; exit `$LASTEXITCODE"
    } else {
        $command = "& '$("$Target\hooks\$name.ps1" -replace "'", "''")'; exit `$LASTEXITCODE"
    }
    # Every other field of the source entry is carried over as is (timeout,
    # async, statusMessage, ...): re-typing a fixed set silently dropped any
    # field added to settings.json later, and invented a 5s timeout.
    $entry = [ordered]@{}
    foreach ($p in $src.PSObject.Properties) {
        if ($p.Name -notin @("command", "if")) { $entry[$p.Name] = $p.Value }
    }
    $entry["command"] = $command
    $entry["shell"] = "powershell"
    return $entry
}

# --- Derive the Windows config FROM the Unix source, never re-typed ----------
# global/.claude/settings.json is the single source of truth. Re-typing its
# rules here is how the two drifted before (Windows silently lost the sudo/dd/
# mkfs/shred/truncate denies). Everything below TRANSLATES that file:
#   - Bash(x)          -> kept, plus PowerShell(<mapped equivalent>) unless unmappable
#   - hooks .sh        -> .ps1 + "shell": "powershell"
#   - hooks .py        -> same .py, run by the verified $PythonExe
# Adding a rule to the JSON therefore reaches Windows with no edit here - and a
# rule with no mapping is a HARD FAILURE below, never a silent drop.

# -Encoding UTF8 on every read: Windows PowerShell 5.1 reads a BOM-less file in
# the ANSI code page, so a non-ASCII value came back as mojibake and was then
# written out as UTF-8 - corrupting the user's own keys on every install.
$srcSettings = Get-Content (Join-Path $ScriptDir "global\.claude\settings.json") -Raw -Encoding UTF8 | ConvertFrom-Json

# Bash verb -> PowerShell equivalent. $null means "no Windows analogue, drop it"
# (e.g. sudo). A verb absent from this table is reported below, so a new rule in
# the JSON can never be silently lost.
$verbMap = @{
    # Claude Code canonicalises rm/del/ri to Remove-Item, so a bare
    # `Remove-Item *` denied every single-file delete on Windows.
    "rm -rf"          = "Remove-Item *-Recurse*"
    "rm -fr"          = "Remove-Item *-Recurse*"
    "git push --force" = "git push --force *"
    "git push -f"     = "git push -f *"
    "git reset --hard" = "git reset --hard *"
    "git clean -fd"   = "git clean *-f*"
    "git clean -fdx"  = "git clean *-f*"
    "git branch -D"   = "git branch -D *"
    "sudo"            = $null
    "dd"              = "dd *"
    "mkfs"            = "mkfs *"
    "mkfs.*"          = "mkfs.* *"
    "shred"           = "shred *"
    "truncate"        = "truncate *"
    "eval"            = "Invoke-Expression *"
    "git push"        = "git push *"
    "git rebase"      = "git rebase *"
    "git commit *--amend*" = "git commit *--amend*"
    "git filter-branch"  = "git filter-branch *"
    "npm install"     = "npm install *"
    "pnpm install"    = "pnpm install *"
    "yarn add"        = "yarn add *"
    "pip install"     = "pip install *"
    "cargo add"       = "cargo add *"
    "go get"          = "go get *"
    "chmod"           = "icacls *"
    "chown"           = "Set-ItemProperty *"
    "chgrp"           = "Set-ItemProperty *"
}

$unmapped = @()
function Convert-Rule($rule) {
    # Non-Bash rules (Read(...), bare tool names) pass through untouched.
    if ($rule -eq "Bash") { return "PowerShell" }
    # Byte-for-byte the regex check.py uses, and it strips ONLY a literal `:*`
    # suffix. A pattern that also ate a lone trailing `*` turned the wildcard
    # rule `Bash(mkfs.*)` into the verb `mkfs.` (unmapped), and the older
    # `Bash(mkfs.*:*)` spelling it replaced matched nothing at all on Unix:
    # Claude Code reads `*` before `:*` literally.
    if ($rule -notmatch '^Bash\((.*?)(?::\*)?\)$') { return $rule }
    $verb = $Matches[1]
    if ($verbMap.ContainsKey($verb)) {
        if ($null -eq $verbMap[$verb]) { return $null }   # deliberately dropped
        return "PowerShell($($verbMap[$verb]))"
    }
    $script:unmapped += $verb
    return $null
}

function Convert-RuleList($rules) {
    # The Bash rule stays next to its PowerShell translation: with Git for
    # Windows the Bash tool remains available alongside PowerShell, and a
    # replaced rule left every Git Bash call with no deny or ask at all.
    $out = @()
    foreach ($r in $rules) {
        foreach ($c in @($r, (Convert-Rule $r))) {
            if ($c -and $out -notcontains $c) { $out += $c }
        }
    }
    return $out
}

# Windows always needs the extra PowerShell-specific denies that have no Bash
# counterpart in the source (iex is an alias Invoke-Expression's rule misses).
$extraDeny = @("PowerShell(iex *)")

$central = [ordered]@{
    permissions = [ordered]@{
        # @(...) on every list: PowerShell unwraps a single-element array to a
        # bare scalar, which ConvertTo-Json would then emit as a string instead
        # of a one-item array - silently invalid settings.json.
        allow = @(Convert-RuleList $srcSettings.permissions.allow)
        ask   = @(Convert-RuleList $srcSettings.permissions.ask)
        deny  = @(Convert-RuleList $srcSettings.permissions.deny) + $extraDeny
        disableBypassPermissionsMode = $srcSettings.permissions.disableBypassPermissionsMode
        defaultMode = $srcSettings.permissions.defaultMode
    }
    # Derived, not hardcoded: every sibling above reads $srcSettings, and
    # install.sh copies "attribution" straight from the source JSON. A literal
    # pair here meant any future change to attribution in
    # global/.claude/settings.json silently never reached Windows - exactly the
    # drift CLAUDE.md requires install.ps1 to avoid by deriving its config.
    attribution = $srcSettings.attribution
    hooks = [ordered]@{}
}
# Any other permissions key (a scalar added to the source later) reaches
# Windows as is: rebuilding the object from named keys dropped new ones.
foreach ($p in $srcSettings.permissions.PSObject.Properties) {
    if (-not $central.permissions.Contains($p.Name)) { $central.permissions[$p.Name] = $p.Value }
}

# Translate the hooks tree: same events, same matchers, same order - only the
# script extension, the shell, and any "if" rule change.
foreach ($event in $srcSettings.hooks.PSObject.Properties) {
    $groups = @()
    foreach ($group in $event.Value) {
        $hooks = @()
        foreach ($h in $group.hooks) {
            # Split by hand: .NET Framework (PowerShell 5.1) throws on the quotes in
            # "python3 "$HOME"/..." where .NET Core quietly accepts them.
            $name = (($h.command -split "[/\\]")[-1].Trim([char]34) -replace "\.(py|sh|ps1)$", "")
            if ($h.'if') {
                [Console]::Error.WriteLine("ERROR: hook '$name' carries an `"if`" gate in global/.claude/settings.json.")
                [Console]::Error.WriteLine("       Prefix-anchored `"if`" patterns reopen the wrapped-form bypasses the")
                [Console]::Error.WriteLine("       hooks' own parsers close (DESIGN.md 27b). Remove it; hooks self-gate.")
                exit 1
            }
            $hooks += (New-Hook $h $name ($h.command -match '\.py"?$'))
        }
        # Every group key is carried over; only `hooks` is rebuilt. Events
        # without matcher support (Stop, ...) carry no matcher in the source,
        # and copying keys (rather than writing "matcher": $null) keeps it so.
        $entry = [ordered]@{}
        foreach ($p in $group.PSObject.Properties) {
            if ($p.Name -ne "hooks") { $entry[$p.Name] = $p.Value }
        }
        $entry["hooks"] = $hooks
        $groups += $entry
    }
    $central.hooks[$event.Name] = $groups
}

if ($unmapped.Count -gt 0) {
    # Hard failure, not a warning: a dropped rule is a permission the user
    # believes they have. Silently losing one is how Windows lost the
    # sudo/dd/mkfs/shred denies before check.py existed.
    [Console]::Error.WriteLine("ERROR: permission rules with no PowerShell mapping - Windows would silently lose them:")
    foreach ($u in ($unmapped | Select-Object -Unique)) { [Console]::Error.WriteLine("       Bash($u)") }
    [Console]::Error.WriteLine("       Add them to `$verbMap in install.ps1 (use `$null to drop one deliberately).")
    exit 1
}

# The .py hooks: one that fails to compile exits 1, a non-blocking error, so the
# guard would be silently off. Compiled in memory: no __pycache__ is written.
$pyHooks = @(Get-ChildItem -Path $hookDir -Recurse -Filter "*.py" -File | ForEach-Object { $_.FullName })
if ($pyHooks.Count -gt 0) {
    $probe = "import sys`nfor p in sys.argv[1:]:`n    compile(open(p, encoding='utf-8').read(), p, 'exec')"
    $pyArgs = @()
    if ($PythonArgs) { $pyArgs += $PythonArgs }
    & $PythonExe @pyArgs -c $probe @pyHooks
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("  ! a Python hook does not compile (above) - aborting before anything is copied.")
        [Console]::Error.WriteLine("    Your currently installed hooks are untouched. Fix the source and re-run.")
        exit 1
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Target "templates") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Target "skills") | Out-Null

# --- Central artifacts: hooks, agents, skills, rules, output-styles ----------
# Owned by this repo - but the DIRECTORIES are shared with the user, who may
# keep their own skills/agents/rules there. Removing each directory outright
# (the previous form) silently deleted all of them on every re-install. So:
# remove only the files this repo shipped LAST time (from the manifest), then
# copy the current set and rewrite it. See install.sh for the same logic.
$manifestPath = Join-Path $Target ".dotclaude-manifest"
$oldManifest = if (Test-Path -LiteralPath $manifestPath) { @(Get-Content -LiteralPath $manifestPath -Encoding UTF8) } else { @() }
$emptied = @()
foreach ($rel in $oldManifest) {
    if ([string]::IsNullOrWhiteSpace($rel) -or $rel -like "*..*") { continue }
    # -LiteralPath: a manifest line holding [ ] * ? must name one file, never a
    # wildcard over the user's files.
    $victim = Join-Path $Target ($rel -replace '/', '\')
    if (Test-Path -LiteralPath $victim) { Remove-Item -LiteralPath $victim -Force -ErrorAction SilentlyContinue }
    $emptied += (Split-Path -Parent $rel)
}

$manifest = @()
foreach ($dir in @("hooks", "agents", "skills", "rules", "output-styles")) {
    $src = Join-Path $ScriptDir "global\.claude\$dir"
    if (-not (Test-Path $src)) { continue }
    $dst = Join-Path $Target $dir
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    # File by file, skipping __pycache__: a dev checkout that ran the Python
    # hooks or tests holds bytecode that must not land in a repo-owned tree.
    $files = Get-ChildItem -Path $src -Recurse -File |
        Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' }
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/') -replace '\\', '/'
        # Windows uses the .ps1 hooks, so the .sh siblings in hooks/ are never
        # written (a .sh anywhere else IS, and stays tracked). Copying them and
        # deleting hooks\*.sh afterwards also deleted the user's own Git Bash hooks.
        if ($dir -eq "hooks" -and $rel -like "*.sh") { continue }
        $destFile = Join-Path $dst ($rel -replace '/', [System.IO.Path]::DirectorySeparatorChar)
        # A user file that shares a shipped name would be overwritten and then
        # adopted into the manifest. Keep a copy and say so.
        if ((Test-Path -LiteralPath $destFile) -and ($oldManifest -notcontains "$dir/$rel")) {
            Copy-Item -LiteralPath $destFile -Destination "$destFile.user-backup" -Force
            Write-Host "  ! ~/.claude/$dir/$rel was yours, not dotclaude's; saved as $rel.user-backup before replacing it"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destFile) | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination $destFile -Force
        $manifest += "$dir/$rel"
    }
}
# Removing a skill's files leaves its directory behind, and an empty
# skills\<name>\ still shows up in the skill listing as a phantom. Prune only
# the directories removing our own files emptied - an empty directory the user
# made is theirs - and never climb above the top-level tree.
foreach ($d in ($emptied | Sort-Object -Unique -Descending)) {
    while ($d -and ($d -match '[\\/]')) {
        $full = Join-Path $Target ($d -replace '/', '\')
        if (-not (Test-Path -LiteralPath $full) -or (Get-ChildItem -LiteralPath $full -Force)) { break }
        Remove-Item -LiteralPath $full -Force
        $d = Split-Path -Parent $d
    }
}
# BOM-less: PS 5.1's Set-Content -Encoding UTF8 writes a BOM, which glued itself
# to the first entry so it never matched again (and install.sh read it too).
[System.IO.File]::WriteAllLines($manifestPath, [string[]]$manifest, (New-Object System.Text.UTF8Encoding($false)))
# A hook this repo stopped shipping is still wired in every project deployed
# with it; its entry now points at a deleted script. Say how to clean that up.
$retired = @($oldManifest | Where-Object { $_ -match '^hooks/[^/]+$' -and $manifest -notcontains $_ })
if ($retired.Count -gt 0) {
    Write-Host "  ! retired hooks removed: $(($retired | ForEach-Object { $_ -replace '^hooks/', '' }) -join ' ')"
    Write-Host "    Projects that wired them: run /init-project --update (or init.ps1) to prune the entries."
}
Write-Host "  - central hooks/agents/skills/rules/output-styles installed (Python hooks)"

# Mirrors OWNED/SEEDED in install.sh; check.py asserts the three sites agree.
# OWNED is overwritten every install (it is the deterministic guarantee);
# SEEDED is written only when the key is absent, so a /config choice survives
# a re-install.
$owned  = @("permissions", "hooks", "attribution")
$seeded = @("outputStyle", "fileCheckpointingEnabled", "statusLine")

# statusLine is seeded verbatim from the source like every other seeded key,
# but its `command` is the POSIX form. statusLine has no `shell` field: Claude
# Code runs it through Git Bash when that is installed, where `& "C:\..."` is a
# syntax error. A command starting with a bare `powershell` runs under Git Bash,
# cmd and PowerShell alike, and hands stdin to the Python it starts.
$slLegacy = @()
if ($srcSettings.PSObject.Properties.Name -contains "statusLine" -and $srcSettings.statusLine.command) {
    $slName = (($srcSettings.statusLine.command -split "[/\\]")[-1].Trim([char]34) -replace "\.(py|sh|ps1)$", "")
    # The forms earlier installs seeded (the .ps1 twin is gone), ours to repair.
    $slLegacy = @("& `"$Target\hooks\$slName.ps1`"",
                  "powershell -NoProfile -File `"$((Join-Path (Join-Path $Target "hooks") "$slName.ps1") -replace '\\', '/')`"")
    $q = { param($s) "'" + ($s -replace "'", "''") + "'" }
    $slScript = (Join-Path (Join-Path $Target "hooks") "$slName.py") -replace '\\', '/'
    $slExe = $PythonExe -replace '\\', '/'
    $launcher = if ($PythonArgs) { " $PythonArgs" } else { "" }
    $srcSettings.statusLine.command = "powershell -NoProfile -Command `"& $(& $q $slExe)$launcher $(& $q $slScript)`""
}

$settingsPath = Join-Path $Target "settings.json"
$existing = [ordered]@{}
$raw = $null
if (Test-Path $settingsPath) {
    try {
        $raw = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        # Copy existing keys we do NOT own, so the user's theme/effort/etc survive.
        foreach ($p in $raw.PSObject.Properties) {
            if ($p.Name -notin $owned) {
                $existing[$p.Name] = $p.Value
            }
        }
    } catch {
        # An unparseable settings.json is almost always a hand-edit typo. Going
        # on silently would drop every personal key (theme, model, statusLine,
        # env, outputStyle), so back it up and say where it went.
        $backup = "$settingsPath.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
        Copy-Item $settingsPath $backup -Force
        [Console]::Error.WriteLine("  ! $settingsPath does not parse; your keys could not be preserved.")
        [Console]::Error.WriteLine("    A copy is saved at $backup - merge anything you need back by hand.")
    }
}
# The owned keys are replaced - but a deny rule or hook the user added there
# must never vanish without a trace. Compared as JSON, so key order is noise.
if ($raw) {
    $replaced = @()
    foreach ($k in $owned) {
        if ($null -eq $central[$k] -or -not ($raw.PSObject.Properties.Name -contains $k)) { continue }
        $mine = $raw.$k | ConvertTo-Json -Depth 12 -Compress
        $ours = $central[$k] | ConvertTo-Json -Depth 12 -Compress
        if ($mine -ne $ours) { $replaced += $k }
    }
    if ($replaced.Count -gt 0) {
        $backup = "$settingsPath.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
        Copy-Item -LiteralPath $settingsPath -Destination $backup -Force
        [Console]::Error.WriteLine("  ! $($replaced -join ', ') was replaced in ~/.claude/settings.json (dotclaude owns it); your previous")
        [Console]::Error.WriteLine("    file is saved at $backup - move personal rules or hooks to a project's")
        [Console]::Error.WriteLine("    .claude/settings.json or settings.local.json, which merge on top.")
    }
}
# Skip null-valued central keys: install.sh copies an owned key only `if key in
# src`, so a key absent from the source JSON must be absent here too rather than
# written as an explicit "attribution": null.
foreach ($k in $central.Keys) {
    if ($null -ne $central[$k]) { $existing[$k] = $central[$k] }
}
# A statusLine an earlier install seeded in the broken form is ours to repair;
# any other value is the user's choice and stays.
if ($existing.Contains("statusLine") -and $slLegacy -contains $existing["statusLine"].command) {
    $existing.Remove("statusLine")
}
# Seed AFTER the user's keys were copied in, so an existing value wins.
$seededNow = @()
$srcKeys = @($srcSettings.PSObject.Properties.Name)
foreach ($k in $seeded) {
    # Absent from the source is not the same as present-and-null: test the
    # property list, since $srcSettings.$k returns $null for both.
    if ($srcKeys -contains $k -and -not $existing.Contains($k)) {
        $existing[$k] = $srcSettings.$k
        $seededNow += $k
    }
}
# BOM-less on purpose: PS 5.1's Set-Content -Encoding UTF8 writes a BOM, which
# strict JSON parsers reject - settings.json is read by more than PowerShell.
[System.IO.File]::WriteAllText($settingsPath, ($existing | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
$seedNote = if ($seededNow.Count -gt 0) { " seeded $($seededNow -join ', ');" } else { "" }
Write-Host "  - $settingsPath merged (permissions, hooks, attribution set to dotclaude's;$seedNote your other keys kept)"

# --- Per-project template and the /init-project skill ------------------------
$templateDest = Join-Path $Target "templates\project"
if (Test-Path $templateDest) { Remove-Item -Recurse -Force $templateDest }
Copy-Item -Recurse (Join-Path $ScriptDir "templates\project") (Join-Path $Target "templates\")
Write-Host "  - templates/project/ installed"

$skillDest = Join-Path $Target "skills\init-project"
if (Test-Path $skillDest) { Remove-Item -Recurse -Force $skillDest }
Copy-Item -Recurse (Join-Path $ScriptDir "skills\init-project") (Join-Path $Target "skills\")
Write-Host "  - skills/init-project/ installed"

# --- ~/.claude/CLAUDE.md is the USER's own - never touch it ------------------
# The repo's CLAUDE.md is the maintenance guide for THIS repo, not user global
# preferences, so the installer does not copy it anywhere. Your
# ~/.claude/CLAUDE.md (global preferences for all projects) is yours to manage.

# --- Validate ----------------------------------------------------------------
try {
    Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
    Write-Host "  - settings.json valid"
} catch {
    Write-Host "  ! settings.json failed to parse - investigate before using"
    exit 1
}

# --- Smoke test: every guard blocks, run through the command just written ----
# A mistyped path or a broken launch form fails open without a word; compiling
# the hooks cannot see it. Lockstep with install.sh. The commands are run by
# this same PowerShell, the way a "shell": "powershell" hook is.
$smokeArgs = @()
if ($PythonArgs) { $smokeArgs += $PythonArgs }
$smokeArgs += @((Join-Path $ScriptDir "scripts/smoke-guards.py"), $settingsPath, "powershell", (Get-Process -Id $PID).Path)
& $PythonExe @smokeArgs
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Done. Central config is in $Target and applies to every project."
Write-Host "Open Claude Code in any project and run /init-project to deploy the"
Write-Host "per-project files (CLAUDE.md, docs/, scaffolds)."
