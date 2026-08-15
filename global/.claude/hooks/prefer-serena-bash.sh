#!/usr/bin/env bash
# PreToolUse hook (Serena projects only): nudges away from reading CODE files via
# shell text tools (sed/cat/head/tail/awk/grep/rg) when Serena's symbol tools fit better.
#
# This fills the gap Serena's own `serena-hooks remind` does NOT cover: that hook only
# watches Grep/Read in the MAIN thread. It is blind to (a) sed/cat/awk/grep INSIDE Bash,
# and (b) sub-agents (including the built-in Explore agent, which skips CLAUDE.md but NOT
# settings.json PreToolUse hooks). A PreToolUse hook on Bash reaches both at once.
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0 — the
# documented non-blocking channel that actually reaches the model. The previous
# form (stderr + exit 0) is a dead channel in PreToolUse: with exit 0 stderr goes
# to the debug log only, so the whole mechanism was silently inert. Exit 2 would
# deliver but blocks, which DESIGN.md §21 rejects for advisory nudges.
# DEBOUNCED: at most one nudge per project per 5 minutes — additionalContext
# enters the context each time, and repeating it every shell read would cost
# more than it teaches.
#
# The advisory names rust-analyzer's cold start on purpose. rust-analyzer cannot persist its
# index to disk (rust-lang/rust-analyzer #4712, open since 2020), so it re-indexes ~10s on
# every session start — during which find_symbol on Rust code returns empty. The model used to
# hit that dead window, fall back to sed, and stay on sed for the whole session. Telling it to
# retry once (instead of "just use find_symbol", which was dead at that moment) is why this
# nudge can now be heeded rather than rationally ignored. Other languages start in <1s.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('command', ''))" 2>/dev/null || echo "")

[ -z "$CMD" ] && exit 0

# Only consider text-extraction tools used for READING. A `cat > file` / heredoc is a write,
# not a navigation read — skip when the command redirects output. `2>/dev/null` is an
# fd-redirect, not a write (the digit before `>` excludes it), and a quoted heredoc
# delimiter (<<'EOF') is still a heredoc.
if echo "$CMD" | grep -qE '(^|[[:space:]|])(sed|cat|head|tail|awk|grep|rg|ack|ag)([[:space:]])' \
   && ! echo "$CMD" | grep -qE '(^|[^0-9>&])>[[:space:]]*[^&]|<<-?[[:space:]]*["'"'"']?[A-Za-z_]'; then

  # Does the command name a file with a code extension? Excludes config/doc/data files
  # (.md .json .yaml .toml .txt .log .env .lock .csv) and vendored/build dirs by simply
  # NOT listing them here — only true source extensions trigger the nudge.
  if echo "$CMD" | grep -qE '\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|kts|rb|php|c|cc|cpp|cxx|h|hpp|hh|cs|swift|scala|clj|ex|exs|erl|hs|ml|sql|vue|svelte)([[:space:]]|$|["'"'"'])' \
     && ! echo "$CMD" | grep -qE '(node_modules|\.git/|/dist/|/build/|/vendor/|/target/|\.next/|__pycache__)'; then
    MSG="Serena hint: this reads a code file via shell text tools. Prefer Serena's symbol tools — get_symbols_overview (file shape), find_symbol (a definition), find_referencing_symbols (callers) — they're structure-aware and cheaper than scanning text. If a find_symbol just now returned empty/errored on a Rust file early in the session, that is rust-analyzer still indexing (~10s cold start, it cannot cache to disk) — retry find_symbol once before falling back, and do NOT abandon Serena for the rest of the session over one cold-start miss. Use cat/sed only when you genuinely need raw bytes (a diff, a non-symbol slice). This is advisory; the command will still run." \
    MSG_KEY="serena" python3 -c '
import hashlib, json, os, tempfile, time
proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
key = hashlib.md5(proj.encode()).hexdigest()[:8]
marker = os.path.join(tempfile.gettempdir(),
                      "dotclaude-nudge-%s-%s" % (os.environ["MSG_KEY"], key))
try:
    fresh = time.time() - os.path.getmtime(marker) < 300
except OSError:
    fresh = False
if not fresh:
    open(marker, "w").close()
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": os.environ["MSG"]}}))
' 2>/dev/null || true
  fi
fi

exit 0
