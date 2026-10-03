# dotclaude installer for Windows.
#
# Installs the CENTRAL config into $HOME\.claude\ — hooks, agents, skills,
# rules, output-styles, and the base settings.json. These apply to every
# project automatically, so improving the master repo and re-running this
# script propagates to all your projects at once.
#
# Also installs the per-project template and the /init-project skill.
#
# Re-running is safe: it refreshes the central artifacts it owns by removing only
# the files it shipped last time (per the manifest), so your own skills/agents/
# rules in those directories survive. It never clobbers your personal CLAUDE.md,
# and MERGES the base settings into $HOME\.claude\settings.json without dropping
# your own keys.
#
# This is the lockstep sibling of install.sh. On Windows the .ps1 hooks run
# under PowerShell, so the central settings.json points at the .ps1 files with
# "shell": "powershell", and every Bash permission rule gets a PowerShell(...) twin.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Join-Path $HOME ".claude"

Write-Host "==> Installing dotclaude into $Target"

# Prerequisite check, mirroring install.sh: the .ps1 hooks and this installer
# need PowerShell 5.1+, and the .py hooks run on Python (DESIGN.md §5).
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
    [Console]::Error.WriteLine("ERROR: no working Python found (tried python3, python, py -3) — the .py hooks run on it. Install Python and re-run.")
    exit 1
}

# --- Syntax pre-flight: never install a hook that cannot be parsed -----------
# Lockstep with install.sh. A hook that fails to parse is a wall, not a degraded
# hook: the central guards run on PreToolUse, so an unparseable one breaks every
# session, and that state cannot be repaired from inside Claude Code (the broken
# hook blocks the installer that would replace it). See DESIGN.md §32. Abort
# before copying, leaving the previously installed working hooks in place.
$hookDir = Join-Path $ScriptDir "global/.claude/hooks"
if (Test-Path $hookDir) {
    foreach ($hook in @(Get-ChildItem -Path $hookDir -Filter "*.ps1" -File)) {
        $tokens = $null
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            $hook.FullName, [ref]$tokens, [ref]$errors) | Out-Null
        if ($errors -and $errors.Count -gt 0) {
            [Console]::Error.WriteLine("  ! $($hook.Name) does not parse — aborting before anything is copied.")
            [Console]::Error.WriteLine("    $($errors[0].Message)")
            [Console]::Error.WriteLine("    Your currently installed hooks are untouched. Fix the source and re-run.")
            exit 1
        }
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Target "templates") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Target "skills") | Out-Null

# --- Central artifacts: hooks, agents, skills, rules, output-styles ----------
# Owned by this repo — but the DIRECTORIES are shared with the user, who may
# keep their own skills/agents/rules there. Removing each directory outright
# (the previous form) silently deleted all of them on every re-install. So:
# remove only the files this repo shipped LAST time (from the manifest), then
# copy the current set and rewrite it. See install.sh for the same logic.
$manifestPath = Join-Path $Target ".dotclaude-manifest"
if (Test-Path $manifestPath) {
    foreach ($rel in (Get-Content $manifestPath)) {
        if ([string]::IsNullOrWhiteSpace($rel) -or $rel -like "*..*") { continue }
        $victim = Join-Path $Target ($rel -replace '/', '\')
        if (Test-Path $victim) { Remove-Item -Force $victim -ErrorAction SilentlyContinue }
    }
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
        $destFile = Join-Path $dst ($rel -replace '/', [System.IO.Path]::DirectorySeparatorChar)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destFile) | Out-Null
        Copy-Item -Force $f.FullName $destFile
        # Windows keeps the .ps1 hooks; the .sh siblings are dropped below and
        # must stay out of the manifest so a later run does not chase them.
        # Only hooks/ is filtered: a .sh anywhere else IS written, so it must
        # stay tracked or it becomes an unmanaged orphan later.
        if (-not ($dir -eq "hooks" -and $rel -like "*.sh")) { $manifest += "$dir/$rel" }
    }
}
# Windows uses the .ps1 hooks; drop the .sh siblings.
Get-ChildItem -Path (Join-Path $Target "hooks") -Filter "*.sh" -File -ErrorAction SilentlyContinue | Remove-Item -Force
# Removing a skill's files leaves its directory behind, and an empty
# skills\<name>\ still shows up in the skill listing as a phantom. Prune empty
# dirs in the trees we own (never the roots themselves).
foreach ($dir in @("skills", "agents", "rules", "output-styles", "hooks")) {
    $root = Join-Path $Target $dir
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem -Path $root -Recurse -Directory -ErrorAction SilentlyContinue |
        Sort-Object -Property FullName -Descending |
        Where-Object { -not (Get-ChildItem -Path $_.FullName -Force -ErrorAction SilentlyContinue) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
$oldManifest = if (Test-Path $manifestPath) { @(Get-Content $manifestPath) } else { @() }
$manifest | Set-Content -Path $manifestPath -Encoding UTF8
# A hook this repo stopped shipping is still wired in every project deployed
# with it; its entry now points at a deleted script. Say how to clean that up.
$retired = @($oldManifest | Where-Object { $_ -match '^hooks/[^/]+$' -and $manifest -notcontains $_ })
if ($retired.Count -gt 0) {
    Write-Host "  ! retired hooks removed: $(($retired | ForEach-Object { $_ -replace '^hooks/', '' }) -join ' ')"
    Write-Host "    Projects that wired them: run /init-project --update (or init.ps1) to prune the entries."
}
Write-Host "  - central hooks/agents/skills/rules/output-styles installed (.ps1 + .py hooks)"

# --- Central settings.json: build the PowerShell form and MERGE into user's --
function New-Hook($name, $t, $isPython) {
    # No `if` parameter on purpose: hook entries carry no `if` gates (a
    # prefix-anchored pattern reopens the wrapped-form bypasses the hooks'
    # own parsers close — DESIGN.md §27b). check.py enforces the same on the
    # source JSON; the guard below keeps Windows from reintroducing one.
    # Claude Code launches a "shell": "powershell" hook as `powershell -Command
    # <command>`, and -Command converts a script's or program's exit 2 into
    # process exit 1 — which does not block. Without the trailing
    # `exit $LASTEXITCODE` every .ps1 guard was a no-op on Windows.
    if ($isPython) {
        $script = Join-Path (Join-Path $Target "hooks") "$name.py"
        $launcherArgs = if ($PythonArgs) { " $PythonArgs" } else { "" }
        $command = "& `"$PythonExe`"$launcherArgs `"$script`"; exit `$LASTEXITCODE"
    } else {
        $command = "& `"$Target\hooks\$name.ps1`"; exit `$LASTEXITCODE"
    }
    return [ordered]@{
        type    = "command"
        command = $command
        shell   = "powershell"
        timeout = $t
    }
}

# --- Derive the Windows config FROM the Unix source, never re-typed ----------
# global/.claude/settings.json is the single source of truth. Re-typing its
# rules here is how the two drifted before (Windows silently lost the sudo/dd/
# mkfs/shred/truncate denies). Everything below TRANSLATES that file:
#   - Bash(x)          -> kept, plus PowerShell(<mapped equivalent>) unless unmappable
#   - hooks .sh        -> .ps1 + "shell": "powershell"
#   - hooks .py        -> same .py, run by the verified $PythonExe
# Adding a rule to the JSON therefore reaches Windows with no edit here — and a
# rule with no mapping is a HARD FAILURE below, never a silent drop.

$srcSettings = Get-Content (Join-Path $ScriptDir "global\.claude\settings.json") -Raw | ConvertFrom-Json

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
    # Claude Code reads `*` before `:*` literally (DESIGN.md §35).
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
        # of a one-item array — silently invalid settings.json.
        allow = @(Convert-RuleList $srcSettings.permissions.allow)
        ask   = @(Convert-RuleList $srcSettings.permissions.ask)
        deny  = @(Convert-RuleList $srcSettings.permissions.deny) + $extraDeny
        disableBypassPermissionsMode = $srcSettings.permissions.disableBypassPermissionsMode
        defaultMode = $srcSettings.permissions.defaultMode
    }
    # Derived, not hardcoded: every sibling above reads $srcSettings, and
    # install.sh copies "attribution" straight from the source JSON. A literal
    # pair here meant any future change to attribution in
    # global/.claude/settings.json silently never reached Windows — exactly the
    # drift CLAUDE.md requires install.ps1 to avoid by deriving its config.
    attribution = $srcSettings.attribution
    hooks = [ordered]@{}
}

# Translate the hooks tree: same events, same matchers, same order — only the
# script extension, the shell, and any "if" rule change.
foreach ($event in $srcSettings.hooks.PSObject.Properties) {
    $groups = @()
    foreach ($group in $event.Value) {
        $hooks = @()
        foreach ($h in $group.hooks) {
            $name = [System.IO.Path]::GetFileNameWithoutExtension($h.command)
            if ($h.'if') {
                [Console]::Error.WriteLine("ERROR: hook '$name' carries an `"if`" gate in global/.claude/settings.json.")
                [Console]::Error.WriteLine("       Prefix-anchored `"if`" patterns reopen the wrapped-form bypasses the")
                [Console]::Error.WriteLine("       hooks' own parsers close (DESIGN.md 27b). Remove it; hooks self-gate.")
                exit 1
            }
            $timeout = if ($h.timeout) { $h.timeout } else { 5 }
            $hooks += (New-Hook $name $timeout ($h.command -match '\.py"?$'))
        }
        # Events without matcher support (Stop, UserPromptSubmit, ...) carry no
        # matcher in the source; emitting "matcher": null is not the same as
        # omitting the key, so build the entry without it.
        $entry = [ordered]@{}
        if ($null -ne $group.matcher) { $entry["matcher"] = $group.matcher }
        $entry["hooks"] = $hooks
        $groups += $entry
    }
    $central.hooks[$event.Name] = $groups
}

if ($unmapped.Count -gt 0) {
    # Hard failure, not a warning: a dropped rule is a permission the user
    # believes they have. Silently losing one is how Windows lost the
    # sudo/dd/mkfs/shred denies before check.py existed.
    [Console]::Error.WriteLine("ERROR: permission rules with no PowerShell mapping — Windows would silently lose them:")
    foreach ($u in ($unmapped | Select-Object -Unique)) { [Console]::Error.WriteLine("       Bash($u)") }
    [Console]::Error.WriteLine("       Add them to `$verbMap in install.ps1 (use `$null to drop one deliberately).")
    exit 1
}

# Mirrors OWNED/SEEDED in install.sh; check.py asserts the three sites agree.
# OWNED is overwritten every install (it is the deterministic guarantee);
# SEEDED is written only when the key is absent, so a /config choice survives
# a re-install.
$owned  = @("permissions", "hooks", "attribution")
$seeded = @("outputStyle", "fileCheckpointingEnabled", "statusLine")

# statusLine is seeded verbatim from the source like every other seeded key,
# but its `command` is the .sh form. statusLine has no `shell` field: Claude
# Code runs it through Git Bash when that is installed, where `& "C:\..."` is a
# syntax error. The form the statusline docs give works under either shell.
$slLegacy = $null
if ($srcSettings.PSObject.Properties.Name -contains "statusLine" -and $srcSettings.statusLine.command) {
    $slName = [System.IO.Path]::GetFileNameWithoutExtension($srcSettings.statusLine.command)
    $slLegacy = "& `"$Target\hooks\$slName.ps1`""
    $slPath = (Join-Path (Join-Path $Target "hooks") "$slName.ps1") -replace '\\', '/'
    $srcSettings.statusLine.command = "powershell -NoProfile -File `"$slPath`""
}

$settingsPath = Join-Path $Target "settings.json"
$existing = [ordered]@{}
if (Test-Path $settingsPath) {
    try {
        $raw = Get-Content $settingsPath -Raw | ConvertFrom-Json
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
        [Console]::Error.WriteLine("    A copy is saved at $backup — merge anything you need back by hand.")
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
if ($slLegacy -and $existing.Contains("statusLine") -and $existing["statusLine"].command -eq $slLegacy) {
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
# strict JSON parsers reject — settings.json is read by more than PowerShell.
[System.IO.File]::WriteAllText($settingsPath, ($existing | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
$seedNote = if ($seededNow.Count -gt 0) { " seeded $($seededNow -join ', ');" } else { "" }
Write-Host "  - $settingsPath merged (PowerShell base permissions + hooks;$seedNote your other keys kept)"

# --- Per-project template and the /init-project skill ------------------------
$templateDest = Join-Path $Target "templates\project"
if (Test-Path $templateDest) { Remove-Item -Recurse -Force $templateDest }
Copy-Item -Recurse (Join-Path $ScriptDir "templates\project") (Join-Path $Target "templates\")
Write-Host "  - templates/project/ installed"

$skillDest = Join-Path $Target "skills\init-project"
if (Test-Path $skillDest) { Remove-Item -Recurse -Force $skillDest }
Copy-Item -Recurse (Join-Path $ScriptDir "skills\init-project") (Join-Path $Target "skills\")
Write-Host "  - skills/init-project/ installed"

# --- ~/.claude/CLAUDE.md is the USER's own — never touch it ------------------
# The repo's CLAUDE.md is the maintenance guide for THIS repo, not user global
# preferences, so the installer does not copy it anywhere. Your
# ~/.claude/CLAUDE.md (global preferences for all projects) is yours to manage.

# --- Validate ----------------------------------------------------------------
try {
    Get-Content $settingsPath -Raw | ConvertFrom-Json | Out-Null
    Write-Host "  - settings.json valid"
} catch {
    Write-Host "  ! settings.json failed to parse - investigate before using"
    exit 1
}

Write-Host ""
Write-Host "Done. Central config is in $Target and applies to every project."
Write-Host "Open Claude Code in any project and run /init-project to deploy the"
Write-Host "per-project files (CLAUDE.md, docs/, scaffolds)."
