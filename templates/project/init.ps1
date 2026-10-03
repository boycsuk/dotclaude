# Deploy the PER-PROJECT files of the dotclaude template (Windows).
#
# The reusable artifacts — hooks, agents, skills, rules, output-styles — are
# NOT deployed here: they live centrally in $HOME\.claude\ (installed from the
# dotclaude repo via install.ps1) and the harness applies them to every project
# automatically. This script only writes what is specific to THIS project:
# CLAUDE.md, CHANGELOG.md, docs/, a minimal settings.json stub, .gitignore,
# optional .mcp.json servers, and optional infra scaffolds. Every run also
# prunes hook entries dotclaude no longer ships (obsolete.json).
#
# Lockstep sibling of init.sh — see it for the full semantics.
#
# Usage (run inside the target project directory):
#   powershell -File "$HOME\.claude\templates\project\init.ps1" [--xcode] [--ui] [--codebase-memory] [--lsp=<plugin>] [--update] [scaffold flags]
#
# --update, --db (no-op now: db-inspector is central), and the scaffold flags
# (--fullstack, --runtime=, --compose, --proxy=, --deploy-script) behave as in
# init.sh. --serena was removed and only warns.
#
# --xcode is recognised for lockstep with init.sh but can never succeed here:
# Apple's mcpbridge ships with Xcode, so the flag exits 5 on any Windows host.
# It is parsed rather than ignored so the failure is an explicit, documented exit
# code instead of a "unknown flag" warning followed by a silently xcode-less deploy.
#
# --ui merges the 'playwright' browser server (@playwright/mcp via npx) into
# ./.mcp.json for the visual verification loop the central /implement-ui skill
# drives. Exit 7 if 'npx' is not in PATH.
#
# --update --recursive [dir] updates every dotclaude project under dir, and
# --remove-obsolete-mcp removes obsolete MCP servers (see init.sh).
#
# --codebase-memory merges the 'codebase-memory-mcp' server and its read-only
# tool permissions (see init.sh). Exit 8 if the binary is not in PATH.
#
# --lsp=<plugin> (repeatable) installs an official LSP plugin at project scope
# via `claude plugin install --scope project`; never fatal (see init.sh).

$ErrorActionPreference = "Stop"

$InstallXcode  = $false
$InstallUi     = $false
$LspPlugins    = @()
$InstallCodebaseMemory = $false
$Recursive     = $false
$RecursiveDir  = "."
$RecursiveArgs = @()
$RemoveObsoleteMcp = $false
$Positional    = $null
$Unknown       = @()
$Fullstack     = $false
$Runtime       = ""
$Compose       = $false
$Proxy         = ""
$DeployScript  = $false
foreach ($arg in $args) {
    # A command printed by an older /init-project may still carry it.
    if     ($arg -eq "--serena")        { [Console]::Error.WriteLine("WARN: --serena was removed (Serena and Graphify are no longer shipped); ignoring it.") }
    elseif ($arg -eq "--xcode")         { $InstallXcode  = $true }
    elseif ($arg -eq "--ui")            { $InstallUi     = $true }
    elseif ($arg -like "--lsp=*")       { $LspPlugins   += $arg.Substring(6) }
    elseif ($arg -eq "--codebase-memory") { $InstallCodebaseMemory = $true }
    elseif ($arg -eq "--update")        { }  # informational: seeding always skips existing files
    elseif ($arg -eq "--recursive")     { $Recursive = $true }
    elseif ($arg -eq "--yes" -or $arg -eq "--dry-run") { $RecursiveArgs += $arg }
    elseif ($arg -eq "--remove-obsolete-mcp") { $RemoveObsoleteMcp = $true }
    elseif ($arg -eq "--db")            { }  # accepted, no-op (db-inspector is central now)
    elseif ($arg -eq "--fullstack")     { $Fullstack     = $true }
    elseif ($arg -eq "--compose")       { $Compose       = $true }
    elseif ($arg -eq "--deploy-script") { $DeployScript  = $true }
    elseif ($arg -like "--runtime=*")   { $Runtime       = $arg.Substring(10) }
    elseif ($arg -like "--proxy=*")     { $Proxy         = $arg.Substring(8) }
    elseif ($arg -like "-*")            { $Unknown += $arg }
    else                                { $Positional = $arg }
}
if ($Positional) {
    if ($Recursive) { $RecursiveDir = $Positional }
    else { $Unknown += "$Positional (a directory is only taken with --recursive)" }
}
# Exit 9 before anything is written: older versions only warned and deployed
# anyway, which seeded the template into a folder of projects (see init.sh).
if ($Unknown.Count -gt 0) {
    foreach ($u in $Unknown) { [Console]::Error.WriteLine("ERROR: unknown argument: $u") }
    [Console]::Error.WriteLine("       Nothing was deployed. Run 'git pull; ./install.ps1' in dotclaude if the flag is new.")
    exit 9
}

# Lockstep sibling of merge_mcp_servers in init.sh: ./.mcp.json is COMPOSED from
# per-server fragments, never copied, so each flag owns only its own keys and
# leaves everything else — including servers the user added by hand — untouched.
# See tests/mcp-merge-cases.py for the cases this must satisfy.
function Merge-McpServers {
    param([string[]]$Fragments)

    $dst = ".\.mcp.json"
    try {
        if (Test-Path $dst) {
            $cfg = Get-Content $dst -Raw | ConvertFrom-Json
        } else {
            $cfg = [PSCustomObject]@{ mcpServers = [PSCustomObject]@{} }
        }
        if (-not $cfg.PSObject.Properties.Name.Contains("mcpServers")) {
            $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([PSCustomObject]@{})
        }
        # PS 5.1's ConvertFrom-Json collapses empty JSON arrays to $null: a
        # hand-added server with "args": [] must not round-trip to "args": null
        # (same restore the settings merge below does for permissions).
        foreach ($srv in $cfg.mcpServers.PSObject.Properties) {
            if ($srv.Value.PSObject.Properties['args'] -and ($null -eq $srv.Value.args)) {
                $srv.Value | Add-Member -NotePropertyName args -NotePropertyValue @() -Force
            }
        }

        $added = @(); $updated = @(); $skipped = @()
        foreach ($frag in $Fragments) {
            $spec = Get-Content $frag -Raw | ConvertFrom-Json
            foreach ($prop in $spec.PSObject.Properties) {
                $name = $prop.Name
                $existing = $cfg.mcpServers.PSObject.Properties[$name]
                # Compare serialized form: PSCustomObject has no structural equality.
                if ($existing -and (($existing.Value | ConvertTo-Json -Depth 20 -Compress) -eq ($prop.Value | ConvertTo-Json -Depth 20 -Compress))) {
                    $skipped += $name
                } elseif ($existing) {
                    $cfg.mcpServers.$name = $prop.Value
                    $updated += $name
                } else {
                    $cfg.mcpServers | Add-Member -NotePropertyName $name -NotePropertyValue $prop.Value
                    $added += $name
                }
            }
        }

        if ($added.Count -or $updated.Count) {
            Write-Utf8NoBom $dst (($cfg | ConvertTo-Json -Depth 20) + "`n")
        }
        foreach ($pair in @(@("merged", $added), @("updated", $updated), @("skip", $skipped))) {
            if ($pair[1].Count) {
                [Console]::Error.WriteLine("  - $($pair[0]): $(($pair[1] | Sort-Object) -join ', ') in $dst")
            }
        }
    } catch {
        # Never fatal, matching init.sh: a broken .mcp.json must not abort the deploy.
        [Console]::Error.WriteLine("WARN: could not compose $dst ($_); deploy continues.")
        [Console]::Error.WriteLine("      Merge the server fragments manually from $(Join-Path $TemplateDir 'mcp')")
    }
}

# PS 5.1's Set-Content -Encoding UTF8 writes a BOM, which strict JSON parsers
# (python json.load, Node JSON.parse) reject — breaking mixed WSL+Windows use
# of the same checkout. pwsh 7 is BOM-less, so tests never see this; write
# explicitly BOM-less on every host.
function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $full = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location) $Path }
    [System.IO.File]::WriteAllText($full, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# Run one of the template's Python scripts (shared with init.sh). The
# interpreter must actually RUN: the Microsoft Store "python3" alias exists on a
# clean Windows install, exits non-zero and would make the step a silent no-op.
# Never fatal — every failure is a WARN naming what did not happen.
$script:PythonCmd = $null
function Resolve-TemplatePython {
    if (-not $script:PythonCmd) {
        foreach ($candidate in @(@("python3"), @("python"), @("py", "-3"))) {
            foreach ($cmd in @(Get-Command $candidate[0] -CommandType Application -All -ErrorAction SilentlyContinue)) {
                $prefix = @($cmd.Source) + @($candidate | Select-Object -Skip 1)
                try {
                    & $prefix[0] @($prefix | Select-Object -Skip 1) --version *> $null
                    if ($LASTEXITCODE -eq 0) { $script:PythonCmd = $prefix; break }
                } catch { }
            }
            if ($script:PythonCmd) { break }
        }
    }
    # The comma keeps a one-element array an array; PowerShell would unwrap it
    # into a bare string and [0] would then be its first character.
    return ,$script:PythonCmd
}

function Invoke-TemplatePython {
    param([string]$What, [string[]]$ScriptArgs, [switch]$DiscardStdout)
    if (-not (Resolve-TemplatePython)) {
        [Console]::Error.WriteLine("WARN: no working Python (tried python3, python, py -3); $What skipped. Deploy continues.")
        return
    }
    $argv = @($script:PythonCmd | Select-Object -Skip 1) + $ScriptArgs
    try {
        if ($DiscardStdout) { & $script:PythonCmd[0] @argv | Out-Null } else { & $script:PythonCmd[0] @argv }
        $ok = ($LASTEXITCODE -eq 0)
    } catch { $ok = $false }
    if (-not $ok) { [Console]::Error.WriteLine("WARN: $What did not complete; deploy continues.") }
}

function Seed-Copy {
    param([string]$Src, [string]$Dst)
    if (Test-Path $Dst) {
        Write-Host "  - skip: $Dst (already exists)"
        return
    }
    $dir = Split-Path -Parent $Dst
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Copy-Item -Path $Src -Destination $Dst
    Write-Host "  - wrote: $Dst"
}

$TemplateDir = if ($env:TEMPLATE_DIR) { $env:TEMPLATE_DIR } else { Join-Path $HOME ".claude\templates\project" }
$SrcRoot = Join-Path $TemplateDir ".claude"
$DstRoot = Join-Path (Get-Location) ".claude"

if (-not (Test-Path $TemplateDir)) {
    # [Console]::Error, not Write-Error: under $ErrorActionPreference = "Stop"
    # a Write-Error is promoted to a TERMINATING error, so the script dies
    # right there with exit code 1 and the `exit N` below never runs — the
    # documented exit codes were unreachable, and the skill keys its
    # remediation off them.
    [Console]::Error.WriteLine("ERROR: template not found at $TemplateDir (run install.ps1 from the dotclaude repo)")
    exit 1
}

# --- Recursive mode: hand over to the shared walker (scripts/update-projects.py),
# which runs this same script once per project with that project's own flags.
if ($Recursive) {
    $py = Resolve-TemplatePython
    if (-not $py) {
        [Console]::Error.WriteLine("ERROR: --recursive needs a working Python (tried python3, python, py -3).")
        exit 1
    }
    $pwshExe = (Get-Process -Id $PID).Path
    $walkerArgs = @($py | Select-Object -Skip 1) + @((Join-Path $TemplateDir "scripts/update-projects.py"),
        $RecursiveDir, "--init", $PSCommandPath, "--pwsh", $pwshExe) + $RecursiveArgs
    & $py[0] @walkerArgs
    exit $LASTEXITCODE
}

# --- Per-project .claude/ : only the project-specific files ------------------
if (-not (Test-Path $DstRoot)) { New-Item -ItemType Directory -Path $DstRoot -Force | Out-Null }

# settings.json: per-project stub (base config is central). Seed only if absent.
Seed-Copy (Join-Path $SrcRoot "settings.json") (Join-Path $DstRoot "settings.json")

# settings.local.json.example: refresh if untouched, drift-report if edited.
$localExample = Join-Path $SrcRoot "settings.local.json.example"
$localExampleDst = Join-Path $DstRoot "settings.local.json.example"
if (Test-Path $localExample) {
    if (-not (Test-Path $localExampleDst)) {
        Copy-Item $localExample $localExampleDst
    } elseif ((Get-FileHash $localExample).Hash -ne (Get-FileHash $localExampleDst).Hash) {
        [Console]::Error.WriteLine("DRIFT: .claude\settings.local.json.example (template updated; your edits kept)")
    }
}

# --- Obsolete artifacts: prune dead hook entries, report the rest ------------
# Lockstep sibling of the init.sh block, through the SAME Python script so the
# pruning rules exist once. stdout carries KEY= lines for detect-drift.py only.
$obsolete = Join-Path $TemplateDir "obsolete.json"
if (Test-Path $obsolete) {
    $pruneArgs = @((Join-Path $TemplateDir "scripts/prune-obsolete.py"), $obsolete, (Get-Location).Path)
    if ($RemoveObsoleteMcp) { $pruneArgs += "--remove-mcp" }
    Invoke-TemplatePython -What "obsolete-artifact check" -DiscardStdout -ScriptArgs $pruneArgs
}

# --- CLAUDE.md, CHANGELOG.md : user-owned, seed when absent ------------------
if (-not (Test-Path ".\CLAUDE.md"))    { Copy-Item (Join-Path $TemplateDir "CLAUDE.md.template")    ".\CLAUDE.md" }
if (-not (Test-Path ".\CHANGELOG.md")) { Copy-Item (Join-Path $TemplateDir "CHANGELOG.md.template") ".\CHANGELOG.md" }

# --- docs/ : portable contract surface, seed each file when absent -----------
$DocsSrc = Join-Path $TemplateDir "docs"
if (Test-Path $DocsSrc) {
    if (-not (Test-Path ".\docs")) { New-Item -ItemType Directory -Path ".\docs" -Force | Out-Null }
    Get-ChildItem -Path $DocsSrc -Filter "*.md" -File | ForEach-Object {
        $dst = Join-Path ".\docs" $_.Name
        if (-not (Test-Path $dst)) { Copy-Item -Path $_.FullName -Destination $dst }
    }
}

# --- .gitignore : merge template entries in (or seed if absent) --------------
# APPEND, never sort. Order is semantic in .gitignore: a negation (`!x`) only
# re-includes when it comes AFTER the pattern that excluded it, and sorting
# hoists negations above their parents — verified with real git: both the
# template's own `!.env.example` and a user's `!keep.log` ended up ignored.
$gi = ".\.gitignore"
$giTpl = Join-Path $TemplateDir ".gitignore.template"
if (Test-Path $gi) {
    # Appends are accumulated and written once through Write-Utf8NoBom rather
    # than with Add-Content: on PS 5.1 Add-Content defaults to ANSI and CRLF,
    # which mangles a non-ASCII pattern and mixes line endings in a checkout
    # shared with WSL. -ccontains matches the .sh sibling's `grep -qxF`, which
    # is case-SENSITIVE: -contains would treat a user's `thumbs.db` as already
    # covering the template's `Thumbs.db` and silently skip it.
    $existing = @(Get-Content $gi)
    $appended = @()
    if ($existing -cnotcontains "# --- dotclaude template ---") {
        $appended += ""
        $appended += "# --- dotclaude template ---"
        $existing += "# --- dotclaude template ---"
    }
    foreach ($line in (Get-Content $giTpl)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($existing -cnotcontains $line) {
            $appended += $line
            $existing += $line
        }
    }
    if ($appended.Count -gt 0) {
        $current = [System.IO.File]::ReadAllText((Join-Path (Get-Location) ".gitignore"))
        if ($current -and -not $current.EndsWith("`n")) { $current += "`n" }
        Write-Utf8NoBom $gi ($current + (($appended -join "`n") + "`n"))
    }
} else {
    Copy-Item $giTpl $gi
}

# --- Xcode MCP (opt-in, macOS only) ------------------------------------------
# Lockstep sibling of the --xcode block in init.sh. PowerShell does run on macOS,
# so this is not dead code there — but $IsMacOS is $false on Windows PowerShell 5.1
# (the variable does not exist), which is exactly the host that must fail here.
if ($InstallXcode) {
    # $IsMacOS is an engine variable, so unlike init.sh's `uname` it cannot be
    # stubbed through PATH. Two escape hatches let tests/mcp-merge-cases.py
    # exercise BOTH verdicts from either kind of runner, and neither is ever set
    # in normal use: MCP_FORCE_DARWIN reaches the merge logic from a non-Mac,
    # and MCP_FORCE_NON_DARWIN reaches this abort from a Mac — without the
    # latter, the exit-5 case silently passed on Linux and inverted on macOS.
    $isMac = [bool]$IsMacOS
    if ($env:MCP_FORCE_DARWIN) { $isMac = $true }
    if ($env:MCP_FORCE_NON_DARWIN) { $isMac = $false }
    if (-not $isMac) {
        [Console]::Error.WriteLine("ERROR: --xcode is macOS-only (Apple's mcpbridge ships with Xcode).")
        exit 5
    }
    # `xcrun --find mcpbridge` is the capability probe: xcrun exists with the
    # Command Line Tools, but mcpbridge only from Xcode 26.3.
    & xcrun --find mcpbridge *> $null
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("ERROR: 'xcrun mcpbridge' not available — needs Xcode 26.3 or later.")
        [Console]::Error.WriteLine("       Check the selected toolchain with: xcode-select -p")
        [Console]::Error.WriteLine("       Then enable MCP in Xcode > Settings > Intelligence.")
        exit 6
    }

    Merge-McpServers @((Join-Path $TemplateDir "mcp/xcode.json"))
}

# --- Playwright MCP (opt-in) --------------------------------------------------
# Lockstep sibling of the --ui block in init.sh: browser eyes for UI work so the
# model can screenshot the running app and compare against a design reference.
# npx fetches @playwright/mcp on demand; npx itself is the only prerequisite.
if ($InstallUi) {
    if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine("ERROR: 'npx' not found in PATH — the playwright MCP server launches via npx.")
        [Console]::Error.WriteLine("       Install Node.js (which ships npx) and re-run.")
        exit 7
    }
    Merge-McpServers @((Join-Path $TemplateDir "mcp/playwright.json"))
}

# --- codebase-memory-mcp (opt-in) ---------------------------------------------
# Lockstep sibling of the init.sh block; permissions go through the SAME Python
# script so the read-only allowlist is merged identically on both platforms.
if ($InstallCodebaseMemory) {
    if (-not (Get-Command codebase-memory-mcp -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine("ERROR: 'codebase-memory-mcp' not found in PATH (--codebase-memory needs it).")
        [Console]::Error.WriteLine("       Install the BINARY only, with one of:")
        [Console]::Error.WriteLine("         npm install -g codebase-memory-mcp")
        [Console]::Error.WriteLine("         pip install --user codebase-memory-mcp")
        [Console]::Error.WriteLine("         release archive + checksums.txt from github.com/DeusData/codebase-memory-mcp/releases")
        [Console]::Error.WriteLine("         (verify the SHA-256 with Get-FileHash, then put the binary on PATH)")
        [Console]::Error.WriteLine("       Do NOT run 'codebase-memory-mcp install' or its install.ps1: they rewrite")
        [Console]::Error.WriteLine("       ~/.claude/settings.json hooks, add agents and skills, and edit your profile.")
        exit 8
    }
    Merge-McpServers @((Join-Path $TemplateDir "mcp/codebase-memory-mcp.json"))
    Invoke-TemplatePython -What "codebase-memory-mcp permission merge" `
        -ScriptArgs @((Join-Path $TemplateDir "scripts/merge-permissions.py"), (Join-Path $TemplateDir "permissions/codebase-memory-mcp.json"), (Get-Location).Path)
}

# --- LSP plugins (opt-in, one per --lsp=<plugin>) -----------------------------
# Lockstep sibling of the init.sh block: same catalog (lsp-plugins.json), same
# never-fatal contract — every problem is a WARN carrying the command that fixes it.
if ($LspPlugins.Count -gt 0) {
    $catalog = Get-Content -Raw (Join-Path $TemplateDir "lsp-plugins.json") | ConvertFrom-Json
    foreach ($plugin in $LspPlugins) {
        $entry = $catalog.plugins.PSObject.Properties[$plugin]
        if (-not $entry) {
            [Console]::Error.WriteLine("WARN: --lsp=$plugin is not an official LSP plugin (see $(Join-Path $TemplateDir 'lsp-plugins.json')); skipped.")
            continue
        }
        $marketplace = $catalog.marketplace
        if (-not (Get-Command $entry.Value.binary -ErrorAction SilentlyContinue)) {
            [Console]::Error.WriteLine("WARN: language server '$($entry.Value.binary)' is not in PATH — $plugin stays inert until you install it:")
            [Console]::Error.WriteLine("        $($entry.Value.install)")
        }
        if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
            [Console]::Error.WriteLine("WARN: 'claude' CLI not in PATH; install the plugin from Claude Code with:")
            [Console]::Error.WriteLine("        /plugin install $plugin@$marketplace   (choose project scope)")
            continue
        }
        # try/catch: on PowerShell 5.1 redirected native stderr becomes an error
        # record, which $ErrorActionPreference = "Stop" would turn into an abort.
        try {
            & claude plugin install "$plugin@$marketplace" --scope project *> $null
            $installed = ($LASTEXITCODE -eq 0)
        } catch { $installed = $false }
        if ($installed) {
            [Console]::Error.WriteLine("  - installed LSP plugin $plugin (project scope, recorded in .claude/settings.json)")
        } else {
            [Console]::Error.WriteLine("WARN: could not install $plugin; run it yourself:")
            [Console]::Error.WriteLine("        claude plugin install $plugin@$marketplace --scope project")
        }
    }
}

# --- Optional scaffolding — each block is independent; flags can be combined -
$Scaffolds = Join-Path $TemplateDir "scaffolds"

if ($Fullstack) {
    foreach ($d in @("backend", "clients\web", "scripts")) {
        if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    }
    Seed-Copy (Join-Path $Scaffolds "env.example.template") ".\.env.example"
}

if ($Runtime) {
    switch ($Runtime) {
        "node"   { Seed-Copy (Join-Path $Scaffolds "Dockerfile.node")   ".\Dockerfile" }
        "python" { Seed-Copy (Join-Path $Scaffolds "Dockerfile.python") ".\Dockerfile" }
        default  { Write-Warning "unknown --runtime=$Runtime, skipping Dockerfile." }
    }
    if ($Runtime -eq "node" -or $Runtime -eq "python") {
        Seed-Copy (Join-Path $Scaffolds "dockerignore.template") ".\.dockerignore"
    }
}

if ($Compose) {
    Seed-Copy (Join-Path $Scaffolds "docker-compose.yml.template") ".\docker-compose.yml"
}

if ($Proxy) {
    switch ($Proxy) {
        "caddy"  { Seed-Copy (Join-Path $Scaffolds "Caddyfile.template") ".\Caddyfile" }
        "nginx"  { Write-Warning "--proxy=nginx scaffold not yet implemented; Caddyfile only on day 1." }
        default  { Write-Warning "unknown --proxy=$Proxy, skipping reverse-proxy config." }
    }
}

if ($DeployScript) {
    Seed-Copy (Join-Path $Scaffolds "deploy.ps1.template") ".\deploy.ps1"
}

Write-Output "init.ps1: deploy OK"
