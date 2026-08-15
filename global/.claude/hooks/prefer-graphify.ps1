# PreToolUse hook (Serena+Graphify projects only): nudges toward the knowledge graph
# BEFORE grepping raw files or reading code one file at a time, when a built graph exists.
#
# Where `prefer-serena-bash` nudges from text tools to Serena's SYMBOL level, this nudges
# from file-scanning to Graphify's GRAPH level. Fires on (a) Bash search commands,
# (b) the Grep tool (a content search is exactly a graph question), and (c) Read/Glob
# of a code file. GATED on $env:CLAUDE_PROJECT_DIR/graphify-out/graph.json.
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0 — the
# documented non-blocking channel that actually reaches the model (stderr + exit 0 was
# a dead channel). DEBOUNCED: at most one nudge per project per 5 minutes.
# Lockstep sibling of prefer-graphify.sh.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

# Only nudge when a graph actually exists in the project.
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
if (-not (Test-Path (Join-Path $root "graphify-out/graph.json"))) { exit 0 }

$tool = $data.tool_name

function Send-Nudge([string]$msg) {
    $proj = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $key = ([System.BitConverter]::ToString($md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($proj))) -replace '-', '').Substring(0, 8).ToLower()
    $marker = Join-Path ([System.IO.Path]::GetTempPath()) "dotclaude-nudge-graphify-$key"
    if (Test-Path $marker) {
        if (((Get-Date) - (Get-Item $marker).LastWriteTime).TotalSeconds -lt 300) { return }
    }
    New-Item -ItemType File -Force -Path $marker | Out-Null
    $payload = @{ hookSpecificOutput = @{ hookEventName = "PreToolUse"; additionalContext = $msg } } | ConvertTo-Json -Compress -Depth 3
    [Console]::Out.WriteLine($payload)
}

$searchMsg = 'Graphify hint: a knowledge graph exists at graphify-out/. For a focused where/what/who-calls question, run `graphify query "<question>"` (scoped subgraph, usually much smaller than grepping raw files) — or `graphify path "<A>" "<B>"` for relationships. Read raw files to modify or debug specific code, or when the graph lacks detail. Advisory; the command still runs.'
$readMsg = 'Graphify hint: a knowledge graph exists at graphify-out/. To ANSWER a codebase question, run `graphify query "<question>"`, `graphify explain "<concept>"`, or `graphify path "<A>" "<B>"` (scoped subgraph, cheaper than reading files one by one). Read raw files to MODIFY or debug specific code, or when the graph lacks the detail. Advisory; the read still runs.'

switch ($tool) {
    'Bash' {
        $cmd = $data.tool_input.command
        if (-not $cmd) { exit 0 }
        # Broad search tools used to explore the codebase.
        if ($cmd -match '(^|[\s|])(grep|rg|ripgrep|ack|ag)\s' -or $cmd -match '(^|[\s|])(find|fd)\s') {
            Send-Nudge $searchMsg
        }
    }
    'Grep' {
        # A content search across the codebase is exactly the question the graph
        # answers — no code-extension requirement (patterns rarely name one).
        Send-Nudge $searchMsg
    }
    { $_ -in 'Read', 'Glob' } {
        $t = $data.tool_input
        # Backslashes normalized to / so the graphify-out/ exclusion works on Windows paths.
        $blob = ((("" + $t.file_path) + ' ' + ("" + $t.pattern) + ' ' + ("" + $t.path)) -replace '\\', '/').ToLower()
        if (-not $blob.Trim()) { exit 0 }
        # Only nudge when reading a CODE file (not graphify-out/ itself, not config/docs).
        if ($blob -notmatch 'graphify-out/' `
            -and $blob -match '\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|kts|rb|php|c|cc|cpp|cxx|h|hpp|hh|cs|swift|scala|clj|ex|exs|erl|hs|ml|sql|vue|svelte|lua|sh)(\s|$)') {
            Send-Nudge $readMsg
        }
    }
}

exit 0
