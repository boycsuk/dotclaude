# PreToolUse hook (Edit|Write): block edits to the CENTRAL dotclaude config in
# ~/.claude/. The reusable artifacts (hooks, agents, skills, rules,
# output-styles) live there and apply to every project; editing them from
# inside a project would silently change behavior everywhere. The source of
# truth is the dotclaude repo (global/.claude/) — change them there and run
# .\install.ps1, never in the installed ~/.claude/ copy.
#
# Exit 2 = block + stderr to Claude. Lockstep sibling of guard-central-config.sh.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$file = $data.tool_input.file_path
if (-not $file) { exit 0 }

# Expand ~ then resolve to an absolute, canonical path so relative paths and
# ../ traversal cannot dodge the check. GetFullPath does not require existence.
$expanded = $file -replace '^~', $HOME
try { $abs = [System.IO.Path]::GetFullPath($expanded) } catch { exit 0 }

# GetFullPath does not resolve symlinks (the .sh's realpath does): when the
# target exists and is a link, follow it so a symlink into ~/.claude is judged
# as the file it points at. ResolveLinkTarget needs .NET 6+; .Target covers
# Windows PowerShell 5.1.
try {
    $item = Get-Item -LiteralPath $abs -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType) {
        $t = $null
        try { $t = $item.ResolveLinkTarget($true).FullName } catch { if ($item.Target) { $t = @($item.Target)[0] } }
        if ($t) { try { $abs = [System.IO.Path]::GetFullPath($t) } catch { } }
    }
} catch { }
$absN = $abs -replace '\\', '/'

$claudeHome = ([System.IO.Path]::GetFullPath((Join-Path $HOME ".claude"))) -replace '\\', '/'

# The registry that WIRES every central hook and permission. Editing it from
# inside a project can silently disable the whole deterministic layer, so it is
# guarded like the artifacts it points at. (~/.claude/settings.local.json stays
# editable: it is the user's personal, per-machine override.)
# Every comparison below is ordinal case-INSENSITIVE: NTFS and APFS are
# case-insensitive, so c:\users\...\.Claude\... writes the guarded file while
# a case-sensitive StartsWith would wave it through. (String.StartsWith is
# case-SENSITIVE by default even though PowerShell's -eq is not — mixing the
# two semantics is exactly the bug this comment prevents from returning.)
if ([string]::Equals($absN, "$claudeHome/settings.json", [System.StringComparison]::OrdinalIgnoreCase)) {
    [Console]::Error.WriteLine("BLOCKED: '$file' is the central settings registry (~/.claude/settings.json).")
    [Console]::Error.WriteLine("        It wires every central hook and permission — editing it from inside a project")
    [Console]::Error.WriteLine("        can disable the deterministic safety layer for ALL your projects.")
    [Console]::Error.WriteLine("        Edit global\.claude\settings.json in the dotclaude repo and run .\install.ps1 instead.")
    exit 2
}

# install.ps1 overwrites templates\project\ wholesale on every run, so an edit
# here is silently lost on the next install — not dangerous, just wasted work.
if ($absN.StartsWith("$claudeHome/templates/", [System.StringComparison]::OrdinalIgnoreCase)) {
    [Console]::Error.WriteLine("BLOCKED: '$file' is the installed per-project template (~/.claude/templates/).")
    [Console]::Error.WriteLine("        install.ps1 overwrites this directory wholesale, so the edit would be lost.")
    [Console]::Error.WriteLine("        Edit templates\project\... in the dotclaude repo and run .\install.ps1 instead.")
    exit 2
}

foreach ($sub in @("agents", "rules", "skills", "hooks", "output-styles")) {
    $prefix = "$claudeHome/$sub/"
    if ($absN.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        [Console]::Error.WriteLine("BLOCKED: '$file' is central dotclaude config (~/.claude/), shared by every project.")
        [Console]::Error.WriteLine("        Don't edit the installed copy from inside a project — it changes behavior everywhere.")
        [Console]::Error.WriteLine("        Edit the source in the dotclaude repo (global\.claude\...) and run .\install.ps1 instead.")
        exit 2
    }
}

exit 0
