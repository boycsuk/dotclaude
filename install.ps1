# dotclaude installer for Windows.
#
# Installs the CENTRAL config into $HOME\.claude\ — hooks, agents, skills,
# rules, output-styles, and the base settings.json. These apply to every
# project automatically, so improving the master repo and re-running this
# script propagates to all your projects at once.
#
# Also installs the per-project template and the /init-project skill.
#
# Re-running is safe: it overwrites the central artifacts (owned by this repo)
# but never clobbers your personal CLAUDE.md, and MERGES the base settings into
# $HOME\.claude\settings.json without dropping your own keys.
#
# This is the lockstep sibling of install.sh. On Windows the .ps1 hooks run
# under PowerShell, so the central settings.json points at the .ps1 files with
# "shell": "powershell" and mirrors the Bash permission rules to PowerShell(...).

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Join-Path $HOME ".claude"

Write-Host "==> Installing dotclaude into $Target"

# Prerequisite check, mirroring install.sh: the .ps1 hooks and this installer
# need PowerShell 5.1+, and several hooks shell out to python3 exactly as the
# .sh ones do (DESIGN.md §5). Without python3 the guard hooks fail silently.
if ($PSVersionTable.PSVersion.Major -lt 5) {
    [Console]::Error.WriteLine("ERROR: PowerShell 5.1 or newer is required (found $($PSVersionTable.PSVersion)).")
    exit 1
}
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine("ERROR: python3 not found — the hooks parse hook input with it. Install Python and re-run.")
    exit 1
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
    Copy-Item -Recurse -Force (Join-Path $src "*") $dst
    foreach ($f in (Get-ChildItem -Path $src -Recurse -File)) {
        $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/') -replace '\\', '/'
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
$manifest | Set-Content -Path $manifestPath -Encoding UTF8
Write-Host "  - central hooks/agents/skills/rules/output-styles installed (.ps1 hooks)"

# --- Central settings.json: build the PowerShell form and MERGE into user's --
function New-Hook($name, $t) {
    # No `if` parameter on purpose: hook entries carry no `if` gates (a
    # prefix-anchored pattern reopens the wrapped-form bypasses the hooks'
    # own parsers close — DESIGN.md §27b). check.py enforces the same on the
    # source JSON; the guard below keeps Windows from reintroducing one.
    return [ordered]@{
        type    = "command"
        command = "& `"$Target\hooks\$name.ps1`""
        shell   = "powershell"
        timeout = $t
    }
}

# --- Derive the Windows config FROM the Unix source, never re-typed ----------
# global/.claude/settings.json is the single source of truth. Re-typing its
# rules here is how the two drifted before (Windows silently lost the sudo/dd/
# mkfs/shred/truncate denies). Everything below TRANSLATES that file:
#   - Bash(x)          -> PowerShell(<mapped equivalent>), dropped if unmappable
#   - hooks .sh        -> .ps1 + "shell": "powershell"
# Adding a rule to the JSON therefore reaches Windows with no edit here — and a
# rule with no mapping is a HARD FAILURE below, never a silent drop.

$srcSettings = Get-Content (Join-Path $ScriptDir "global\.claude\settings.json") -Raw | ConvertFrom-Json

# Bash verb -> PowerShell equivalent. $null means "no Windows analogue, drop it"
# (e.g. sudo). A verb absent from this table is reported below, so a new rule in
# the JSON can never be silently lost.
$verbMap = @{
    "rm -rf"          = "Remove-Item *"
    "rm -fr"          = "Remove-Item *"
    "git push --force" = "git push --force *"
    "git push -f"     = "git push -f *"
    "git reset --hard" = "git reset --hard *"
    "git clean -fd"   = "git clean *"
    "git clean -fdx"  = "git clean *"
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
    "git commit *--amend" = "git commit *--amend*"
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
    # Non-greedy with the suffix absorbed into the pattern — byte-for-byte the
    # regex check.py uses. The greedy form plus two -replace calls disagreed on
    # `Bash(mkfs.*:*)`: check.py derived `mkfs.*` (mapped) while this side
    # derived `mkfs.` (unmapped), so the deny silently vanished on Windows
    # while check.py reported a clean pass.
    if ($rule -notmatch '^Bash\((.*?):?\*?\)$') { return $rule }
    $verb = $Matches[1]
    if ($verbMap.ContainsKey($verb)) {
        if ($null -eq $verbMap[$verb]) { return $null }   # deliberately dropped
        return "PowerShell($($verbMap[$verb]))"
    }
    $script:unmapped += $verb
    return $null
}

function Convert-RuleList($rules) {
    $out = @()
    foreach ($r in $rules) {
        $c = Convert-Rule $r
        if ($c -and $out -notcontains $c) { $out += $c }
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
    }
    attribution = [ordered]@{ commit = ""; pr = "" }
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
            $hooks += (New-Hook $name $timeout)
        }
        $groups += [ordered]@{ matcher = $group.matcher; hooks = $hooks }
    }
    # The Bash matcher is spelled PowerShell on Windows.
    foreach ($g in $groups) {
        if ($g.matcher -eq "Bash") { $g.matcher = "PowerShell" }
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

$settingsPath = Join-Path $Target "settings.json"
$existing = [ordered]@{}
if (Test-Path $settingsPath) {
    try {
        $raw = Get-Content $settingsPath -Raw | ConvertFrom-Json
        # Copy existing keys we do NOT own, so the user's theme/effort/etc survive.
        foreach ($p in $raw.PSObject.Properties) {
            if ($p.Name -notin @("permissions", "hooks", "attribution")) {
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
foreach ($k in $central.Keys) { $existing[$k] = $central[$k] }
# BOM-less on purpose: PS 5.1's Set-Content -Encoding UTF8 writes a BOM, which
# strict JSON parsers reject — settings.json is read by more than PowerShell.
[System.IO.File]::WriteAllText($settingsPath, ($existing | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "  - $settingsPath merged (PowerShell base permissions + hooks; your other keys kept)"

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
