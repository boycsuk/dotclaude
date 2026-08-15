# Deploy the PER-PROJECT files of the dotclaude template (Windows).
#
# The reusable artifacts — hooks, agents, skills, rules, output-styles — are
# NOT deployed here: they live centrally in $HOME\.claude\ (installed from the
# dotclaude repo via install.ps1) and the harness applies them to every project
# automatically. This script only writes what is specific to THIS project:
# CLAUDE.md, CHANGELOG.md, docs/, a minimal settings.json stub, .gitignore,
# the optional Serena + Graphify .mcp.json bundle, and optional infra scaffolds.
#
# Lockstep sibling of init.sh — see it for the full semantics.
#
# Usage (run inside the target project directory):
#   powershell -File "$HOME\.claude\templates\project\init.ps1" [--serena] [--update] [scaffold flags]
#
# --serena (deploys the serena + graphify MCP bundle AND merges Serena's
# drift-prevention hooks from serena-hooks.json into the project settings.json;
# aborts if 'serena' is missing, warns if 'graphify' is missing), --update, --db (no-op now:
# db-inspector is central), and the scaffold flags (--fullstack, --runtime=,
# --compose, --proxy=, --deploy-script) behave as in init.sh.
#
# --xcode is recognised for lockstep with init.sh but can never succeed here:
# Apple's mcpbridge ships with Xcode, so the flag exits 5 on any Windows host.
# It is parsed rather than ignored so the failure is an explicit, documented exit
# code instead of a "unknown flag" warning followed by a silently xcode-less deploy.
#
# --ui merges the 'playwright' browser server (@playwright/mcp via npx) into
# ./.mcp.json for the visual verification loop the central /implement-ui skill
# drives. Exit 7 if 'npx' is not in PATH.

$ErrorActionPreference = "Stop"

$InstallSerena = $false
$InstallXcode  = $false
$InstallUi     = $false
$Fullstack     = $false
$Runtime       = ""
$Compose       = $false
$Proxy         = ""
$DeployScript  = $false
foreach ($arg in $args) {
    if     ($arg -eq "--serena")        { $InstallSerena = $true }
    elseif ($arg -eq "--xcode")         { $InstallXcode  = $true }
    elseif ($arg -eq "--ui")            { $InstallUi     = $true }
    elseif ($arg -eq "--update")        { }  # informational: seeding always skips existing files
    elseif ($arg -eq "--db")            { }  # accepted, no-op (db-inspector is central now)
    elseif ($arg -eq "--fullstack")     { $Fullstack     = $true }
    elseif ($arg -eq "--compose")       { $Compose       = $true }
    elseif ($arg -eq "--deploy-script") { $DeployScript  = $true }
    elseif ($arg -like "--runtime=*")   { $Runtime       = $arg.Substring(10) }
    elseif ($arg -like "--proxy=*")     { $Proxy         = $arg.Substring(8) }
    else                                { Write-Warning "ignoring unknown flag $arg" }
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
    # documented exit codes (3 = .mcp.json conflict, 4 = serena missing) were
    # unreachable, and the skill keys its remediation off them.
    [Console]::Error.WriteLine("ERROR: template not found at $TemplateDir (run install.ps1 from the dotclaude repo)")
    exit 1
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
    $existing = @(Get-Content $gi)
    if ($existing -notcontains "# --- dotclaude template ---") {
        Add-Content -Path $gi -Value ""
        Add-Content -Path $gi -Value "# --- dotclaude template ---"
        $existing += "# --- dotclaude template ---"
    }
    foreach ($line in (Get-Content $giTpl)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($existing -notcontains $line) {
            Add-Content -Path $gi -Value $line
            $existing += $line
        }
    }
} else {
    Copy-Item $giTpl $gi
}

# --- Serena + Graphify MCP (opt-in) ------------------------------------------
# Both servers deploy together (companions: Serena = symbol-level, Graphify =
# graph-level). Serena is required (abort if missing);
# Graphify is a soft prerequisite (warn only) — its MCP server is secondary and
# starts only after a graph is built (/graphify .), failing inertly otherwise
# without affecting Serena.
if ($InstallSerena) {
    if (-not (Get-Command serena -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine("ERROR: 'serena' binary not found in PATH. Install once per machine: uv tool install -p 3.13 serena-agent@latest --prerelease=allow (requires uv).")
        exit 4
    }
    if (-not (Get-Command graphify -ErrorAction SilentlyContinue)) {
        Write-Warning "'graphify' not found in PATH - the bundled graphify MCP server will be unavailable until you install it and build a graph: uv tool install graphifyy, then run '/graphify .' once to build graphify-out/graph.json. Serena still works; this is non-fatal."
    } else {
        # Graphify present: install its git hooks so the graph auto-rebuilds and
        # never goes stale (a stale graph is why graph-first gets abandoned). We do
        # NOT run 'graphify install'/'graphify claude install' - those append a raw
        # CLAUDE.md block + per-project skill that duplicate the template + central
        # prefer-graphify hook. '/graphify .' still builds the graph; hooks keep it fresh.
        try {
            graphify hook install *> $null
            Write-Host "  - graphify git hooks installed (graph auto-rebuilds on commit/checkout)"
        } catch {
            Write-Warning "graphify hook install failed (non-fatal); run 'graphify hook install' manually"
        }
    }
    # Serena and Graphify are companions and always deploy together.
    Merge-McpServers @(
        (Join-Path $TemplateDir "mcp/serena.json"),
        (Join-Path $TemplateDir "mcp/graphify.json")
    )

    # Merge Serena's drift-prevention hooks into the project's settings.json.
    # Lockstep sibling of the python3 merge in init.sh — these make the model
    # deterministically prefer Serena's tools over Grep/Edit instead of drifting
    # back over a long session (oraios/serena #1201). MERGE (not overwrite) so
    # project-specific hooks/permissions survive; de-duplicate by command so
    # re-running --serena is idempotent. 'serena' is confirmed in PATH above, so
    # 'serena-hooks' ships alongside it.
    $hooksSrc = Join-Path $SrcRoot "serena-hooks.json"
    $settingsDst = Join-Path $DstRoot "settings.json"
    if (Test-Path $hooksSrc) {
        # {{HOOK_EXT}} resolves to the OS hook form: 'ps1' here, 'sh' in init.sh.
        # serena-hooks.json stays OS-agnostic; only the merge picks the concrete script.
        $hookBlock = ((Get-Content -Raw $hooksSrc).Replace('{{HOOK_EXT}}', 'ps1') | ConvertFrom-Json).hooks
        # The JSON ships POSIX-form script entries ("$HOME"/.claude/hooks/x.ps1).
        # A bare .ps1 path never executes under the default hook shell and
        # "$HOME" only expands in sh — rewrite to install.ps1's New-Hook form
        # (& "<abs path>" + shell: powershell) or the merged hooks are inert.
        foreach ($event in $hookBlock.PSObject.Properties.Name) {
            foreach ($group in @($hookBlock.$event)) {
                foreach ($h in @($group.hooks)) {
                    if ($h.command -match '\.claude/hooks/([A-Za-z0-9_.-]+\.ps1)') {
                        $scriptPath = Join-Path (Join-Path $HOME ".claude\hooks") $Matches[1]
                        $h.command = "& `"$scriptPath`""
                        $h | Add-Member -NotePropertyName shell -NotePropertyValue "powershell" -Force
                    }
                }
            }
        }
        if (Test-Path $settingsDst) {
            # -Encoding UTF8: PS 5.1 reads/writes ANSI by default, which would
            # corrupt non-ASCII content (Unicode paths, identifiers) on round-trip.
            try { $settings = Get-Content -Raw $settingsDst -Encoding UTF8 | ConvertFrom-Json }
            catch { $settings = [PSCustomObject]@{} }
        } else {
            $settings = [PSCustomObject]@{}
        }
        # PS 5.1's ConvertFrom-Json collapses empty JSON arrays ([]) to $null. The
        # project stub ships "permissions":{"allow":[],"ask":[],"deny":[]}; without
        # this restore, the round-trip below would rewrite them as null, which
        # Claude Code rejects. Re-materialize any collapsed array back to @().
        if ($settings.PSObject.Properties['permissions']) {
            foreach ($key in @('allow', 'ask', 'deny')) {
                if ((-not $settings.permissions.PSObject.Properties[$key]) -or ($null -eq $settings.permissions.$key)) {
                    $settings.permissions | Add-Member -NotePropertyName $key -NotePropertyValue @() -Force
                }
            }
        }
        if (-not $settings.PSObject.Properties['hooks']) {
            $settings | Add-Member -NotePropertyName hooks -NotePropertyValue ([PSCustomObject]@{})
        }

        function Get-HookCommands($groupList) {
            $out = @()
            foreach ($g in @($groupList)) {
                foreach ($h in @($g.hooks)) {
                    if ($h.command) { $out += $h.command }
                }
            }
            return $out
        }

        $changed = $false
        foreach ($event in $hookBlock.PSObject.Properties.Name) {
            if (-not $settings.hooks.PSObject.Properties[$event]) {
                $settings.hooks | Add-Member -NotePropertyName $event -NotePropertyValue @()
            }
            $existing = @($settings.hooks.$event)
            $have = Get-HookCommands $existing
            foreach ($group in @($hookBlock.$event)) {
                $newCmds = Get-HookCommands $group
                $allPresent = ($newCmds.Count -gt 0) -and (-not ($newCmds | Where-Object { $_ -notin $have }))
                if ($allPresent) { continue }  # already present — keep idempotent
                $existing += $group
                $have += $newCmds
                $changed = $true
            }
            # Write back via Add-Member -Force, NOT `$settings.hooks.$event = $existing`:
            # PS 5.1's `=` property assignment unwraps a single-element array to a
            # bare object, so a one-group event (e.g. SessionStart) would serialize
            # as {...} instead of [{...}] and Claude Code would reject it. Add-Member
            # stores the array reference as-is. Cast to [array] for belt-and-braces.
            $settings.hooks | Add-Member -NotePropertyName $event -NotePropertyValue ([array]$existing) -Force
        }

        if ($changed) {
            # BOM-less + trailing newline to match the python3 sibling in init.sh.
            Write-Utf8NoBom $settingsDst (($settings | ConvertTo-Json -Depth 20) + "`n")
            [Console]::Error.WriteLine("  - merged: Serena drift-prevention hooks into $settingsDst")
        } else {
            [Console]::Error.WriteLine("  - skip: Serena hooks already present in $settingsDst")
        }
    }
}

# --- Xcode MCP (opt-in, macOS only) ------------------------------------------
# Lockstep sibling of the --xcode block in init.sh. PowerShell does run on macOS,
# so this is not dead code there — but $IsMacOS is $false on Windows PowerShell 5.1
# (the variable does not exist), which is exactly the host that must fail here.
if ($InstallXcode) {
    # MCP_FORCE_DARWIN lets tests/mcp-merge-cases.py exercise the merge logic on a
    # non-Mac runner: $IsMacOS is an engine variable, so unlike init.sh's `uname`
    # it cannot be stubbed through PATH. Never set in normal use.
    if (-not $IsMacOS -and -not $env:MCP_FORCE_DARWIN) {
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
