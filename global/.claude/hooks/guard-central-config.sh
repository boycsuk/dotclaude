#!/usr/bin/env bash
# PreToolUse hook (Edit|Write): block edits to the CENTRAL dotclaude config in
# ~/.claude/. The reusable artifacts (hooks, agents, skills, rules,
# output-styles) live there and apply to every project; editing them from
# inside a project would silently change behavior everywhere. The source of
# truth is the dotclaude repo (global/.claude/) — change them there and run
# ./install.sh, never in the installed ~/.claude/ copy.
#
# Exit 2 = block + stderr to Claude. This guards the INSTALLED copy
# (~/.claude/...), not the repo source (a path under the dotclaude clone like
# .../dotclaude/global/.claude/... resolves elsewhere and is allowed).

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")
[ -z "$FILE" ] && exit 0

# Resolve to an absolute, canonical path so relative paths, ~, and ../ traversal
# cannot dodge the check. Use python3 (already a hook prerequisite) — it does not
# require the target to exist (unlike realpath -e).
ABS=$(FILE="$FILE" python3 -c "import os; print(os.path.realpath(os.path.expanduser(os.environ['FILE'])))" 2>/dev/null || echo "")
[ -z "$ABS" ] && exit 0

CLAUDE_HOME="$(python3 -c "import os; print(os.path.realpath(os.path.expanduser('~/.claude')))" 2>/dev/null || echo "$HOME/.claude")"

# APFS is case-insensitive by default: fold both sides on Darwin so
# ~/.Claude/... cannot dodge the guard. Linux (ext4, case-sensitive) keeps the
# exact match — there ~/.Claude genuinely IS a different path.
if [ "$(uname -s)" = "Darwin" ]; then
  ABS=$(printf '%s' "$ABS" | tr '[:upper:]' '[:lower:]')
  CLAUDE_HOME=$(printf '%s' "$CLAUDE_HOME" | tr '[:upper:]' '[:lower:]')
fi

case "$ABS" in
  # The registry that WIRES every central hook and permission. Editing it from
  # inside a project can silently disable the whole deterministic layer, so it
  # is guarded like the artifacts it points at. (~/.claude/settings.local.json
  # stays editable: it is the user's personal, per-machine override.)
  "$CLAUDE_HOME"/settings.json)
    echo "BLOCKED: '$FILE' is the central settings registry (~/.claude/settings.json)." >&2
    echo "        It wires every central hook and permission — editing it from inside a project" >&2
    echo "        can disable the deterministic safety layer for ALL your projects." >&2
    echo "        Edit global/.claude/settings.json in the dotclaude repo and run ./install.sh instead." >&2
    exit 2
    ;;
  # install.sh overwrites templates/project/ wholesale on every run, so an edit
  # here is silently lost on the next install — not dangerous, just wasted work.
  "$CLAUDE_HOME"/templates/*)
    echo "BLOCKED: '$FILE' is the installed per-project template (~/.claude/templates/)." >&2
    echo "        install.sh overwrites this directory wholesale, so the edit would be lost." >&2
    echo "        Edit templates/project/... in the dotclaude repo and run ./install.sh instead." >&2
    exit 2
    ;;
  "$CLAUDE_HOME"/agents/*|"$CLAUDE_HOME"/rules/*|"$CLAUDE_HOME"/skills/*|"$CLAUDE_HOME"/hooks/*|"$CLAUDE_HOME"/output-styles/*)
    echo "BLOCKED: '$FILE' is central dotclaude config (~/.claude/), shared by every project." >&2
    echo "        Don't edit the installed copy from inside a project — it changes behavior everywhere." >&2
    echo "        Edit the source in the dotclaude repo (global/.claude/...) and run ./install.sh instead." >&2
    exit 2
    ;;
esac

exit 0
