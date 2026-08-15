#!/usr/bin/env bash
# PreToolUse hook (Serena+Graphify projects only): nudges toward the knowledge graph
# BEFORE grepping raw files or reading code one file at a time, when a built graph exists.
#
# Where `prefer-serena-bash` nudges from text tools to Serena's SYMBOL level, this nudges
# from file-scanning to Graphify's GRAPH level — the missing "graph-first, then Serena"
# reflex. It fires on three shapes:
#   (a) Bash search commands (grep/rg/find/fd/ack/ag) — broad "where/what" scans,
#   (b) the Grep tool — a content search across files is exactly a graph question, and
#   (c) Read/Glob of a code file — reading source one file at a time to answer a question.
# In each case a scoped `graphify query` is usually far cheaper than scanning files.
#
# GATED on $CLAUDE_PROJECT_DIR/graphify-out/graph.json (hooks do not always run with the
# project as cwd): silent when no graph is built, so it never fires in a project without
# Graphify.
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0 — the
# documented non-blocking channel that actually reaches the model. The previous form
# (stderr + exit 0) is a dead channel in PreToolUse: with exit 0 stderr goes to the
# debug log only, so the whole mechanism was silently inert. DEBOUNCED: at most one
# nudge per project per 5 minutes — additionalContext enters the context on every
# firing, and this hook matches every code-file Read.
#
# The graph answers structure/impact questions ("what depends on X", "what breaks if I
# change Y"); raw file reads stay correct for MODIFYING or debugging specific code.

INPUT=$(cat)

# Only nudge when a graph actually exists in the project.
ROOT="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$ROOT/graphify-out/graph.json" ] || exit 0

TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_name', ''))" 2>/dev/null || echo "")

emit_nudge() {
  MSG="$1" MSG_KEY="graphify" python3 -c '
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
}

SEARCH_MSG='Graphify hint: a knowledge graph exists at graphify-out/. For a focused where/what/who-calls question, run `graphify query "<question>"` (scoped subgraph, usually much smaller than grepping raw files) — or `graphify path "<A>" "<B>"` for relationships. Read raw files to modify or debug specific code, or when the graph lacks detail. Advisory; the command still runs.'
READ_MSG='Graphify hint: a knowledge graph exists at graphify-out/. To ANSWER a codebase question, run `graphify query "<question>"`, `graphify explain "<concept>"`, or `graphify path "<A>" "<B>"` (scoped subgraph, cheaper than reading files one by one). Read raw files to MODIFY or debug specific code, or when the graph lacks the detail. Advisory; the read still runs.'

case "$TOOL" in
  Bash)
    CMD=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('command', ''))" 2>/dev/null || echo "")
    [ -z "$CMD" ] && exit 0
    # Broad search tools used to explore the codebase.
    if echo "$CMD" | grep -qE '(^|[[:space:]|])(grep|rg|ripgrep|ack|ag)([[:space:]])' \
       || echo "$CMD" | grep -qE '(^|[[:space:]|])(find|fd)([[:space:]])'; then
      emit_nudge "$SEARCH_MSG"
    fi
    ;;
  Grep)
    # A content search across the codebase is exactly the question the graph
    # answers — no code-extension requirement (search patterns rarely name one).
    emit_nudge "$SEARCH_MSG"
    ;;
  Read|Glob)
    BLOB=$(printf '%s' "$INPUT" | python3 -c "import sys, json; t=json.load(sys.stdin).get('tool_input', {}); print((str(t.get('file_path') or '')+' '+str(t.get('pattern') or '')+' '+str(t.get('path') or '')).replace(chr(92), '/').lower())" 2>/dev/null || echo "")
    [ -z "$BLOB" ] && exit 0
    # Only nudge when reading a CODE file (not graphify-out/ itself, not config/docs).
    # Backslashes were normalized to / above so the exclusion also works on Windows paths.
    if echo "$BLOB" | grep -qvE 'graphify-out/' \
       && echo "$BLOB" | grep -qE '\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|kts|rb|php|c|cc|cpp|cxx|h|hpp|hh|cs|swift|scala|clj|ex|exs|erl|hs|ml|sql|vue|svelte|lua|sh)([[:space:]]|$)'; then
      emit_nudge "$READ_MSG"
    fi
    ;;
esac

exit 0
