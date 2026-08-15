# PreToolUse hook (Serena projects only): nudges away from reading CODE files via
# shell text tools (sed/cat/head/tail/awk/grep/rg) when Serena's symbol tools fit better.
#
# Fills the gap Serena's own `serena-hooks remind` does NOT cover: that hook only watches
# Grep/Read in the MAIN thread. It is blind to (a) sed/cat/awk/grep INSIDE Bash, and (b)
# sub-agents (incl. the built-in Explore agent, which skips CLAUDE.md but NOT settings.json
# PreToolUse hooks). A PreToolUse hook on Bash reaches both at once.
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0 — the
# documented non-blocking channel that actually reaches the model. The previous form
# (stderr + exit 0) is a dead channel in PreToolUse. DEBOUNCED: at most one nudge per
# project per 5 minutes. Lockstep sibling of prefer-serena-bash.sh.
#
# The advisory names rust-analyzer's cold start on purpose (rust-lang/rust-analyzer #4712):
# it re-indexes ~10s each session start, find_symbol returns empty meanwhile, and the model
# used to abandon Serena for the whole session over that one cold-start miss.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$cmd = $data.tool_input.command
if (-not $cmd) { exit 0 }

# Only consider text-extraction tools used for READING. `2>/dev/null` is an fd-redirect,
# not a write (digit before `>` excluded), and a quoted heredoc (<<'EOF') is a heredoc.
if ($cmd -match '(^|[\s|])(sed|cat|head|tail|awk|grep|rg|ack|ag)\s' `
    -and $cmd -notmatch '(^|[^0-9>&])>\s*[^&]|<<-?\s*["'']?[A-Za-z_]') {

    # True source extensions only; config/doc/data files (.md .json .yaml .toml .txt .log
    # .env .lock .csv) are not listed, so they never trigger. Vendored/build dirs excluded.
    if ($cmd -match '\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|kts|rb|php|c|cc|cpp|cxx|h|hpp|hh|cs|swift|scala|clj|ex|exs|erl|hs|ml|sql|vue|svelte)(\s|$|["''])' `
        -and $cmd -notmatch '(node_modules|\.git/|/dist/|/build/|/vendor/|/target/|\.next/|__pycache__)') {

        $proj = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
        $md5 = [System.Security.Cryptography.MD5]::Create()
        $key = ([System.BitConverter]::ToString($md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($proj))) -replace '-', '').Substring(0, 8).ToLower()
        $marker = Join-Path ([System.IO.Path]::GetTempPath()) "dotclaude-nudge-serena-$key"
        $fresh = $false
        if (Test-Path $marker) {
            $fresh = ((Get-Date) - (Get-Item $marker).LastWriteTime).TotalSeconds -lt 300
        }
        if (-not $fresh) {
            New-Item -ItemType File -Force -Path $marker | Out-Null
            $msg = "Serena hint: this reads a code file via shell text tools. Prefer Serena's symbol tools — get_symbols_overview (file shape), find_symbol (a definition), find_referencing_symbols (callers) — they're structure-aware and cheaper than scanning text. If a find_symbol just now returned empty/errored on a Rust file early in the session, that is rust-analyzer still indexing (~10s cold start, it cannot cache to disk) — retry find_symbol once before falling back, and do NOT abandon Serena for the rest of the session over one cold-start miss. Use cat/sed only when you genuinely need raw bytes (a diff, a non-symbol slice). This is advisory; the command will still run."
            $payload = @{ hookSpecificOutput = @{ hookEventName = "PreToolUse"; additionalContext = $msg } } | ConvertTo-Json -Compress -Depth 3
            [Console]::Out.WriteLine($payload)
        }
    }
}

exit 0
