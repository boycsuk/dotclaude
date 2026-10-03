#!/usr/bin/env bash
# Stop hook: says so when a turn ends with code changed but CHANGELOG.md untouched.
#
# ADVISORY BY CONSTRUCTION. It emits `systemMessage` and exits 0, never
# `decision: "block"` and never exit 2. Both of those, and
# `hookSpecificOutput.additionalContext` too, CONTINUE the conversation on Stop
# — the docs give additionalContext "the same loop protections as
# decision: block", so it is not a passive channel. A Stop hook cannot tell a
# finished task from a half-done one (it fires on every turn), so anything that
# resumes the turn would interrupt legitimate mid-task work. systemMessage is
# the one combination that surfaces text without resuming: plain stdout is only
# added to context for UserPromptSubmit, UserPromptExpansion, SessionStart and
# PostModelSwitch — Stop is not in that list.
#
# Being advisory also makes stop_hook_active moot (nothing to loop on) and puts
# this hook nowhere near the 8-consecutive-block cap. It is still read below,
# because a future edit that adds blocking must not have to remember it.
#
# Does not fire on a user interrupt (Ctrl+C/Esc), and an API error fires
# StopFailure instead. So this only ever speaks on a turn that ended normally.

set -euo pipefail

INPUT=$(cat)

_CR_OUT=$(mktemp)
trap 'rm -f "$_CR_OUT"' EXIT
# Heredoc at top level, never inside $( ): bash mis-lexes a quoted heredoc body
# opened within a command substitution followed by an operator (DESIGN.md §32).
INPUT="$INPUT" python3 > "$_CR_OUT" 2>/dev/null <<'PY' || true
import json, os, sys
try:
    d = json.loads(os.environ.get("INPUT", "") or "{}")
except ValueError:
    sys.exit(0)
print(d.get("cwd", ""))
print("1" if d.get("stop_hook_active") else "0")
PY

CWD=$(sed -n '1p' "$_CR_OUT")
STOP_HOOK_ACTIVE=$(sed -n '2p' "$_CR_OUT")

# Already continuing because of a stop hook: stay quiet. Moot while this hook is
# advisory, kept so adding a blocking path later cannot forget the guard.
[ "$STOP_HOOK_ACTIVE" = "1" ] && exit 0

ROOT="${CWD:-$(pwd)}"
[ -d "$ROOT" ] || exit 0
cd "$ROOT" 2>/dev/null || exit 0

TOP=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# A repo with no CHANGELOG.md has not opted into keeping one. Saying so every
# turn would be the cry-wolf failure DESIGN.md §26 warns about. Looked up at
# the repo root: a session in a subdirectory stayed silent.
[ -f "$TOP/CHANGELOG.md" ] || exit 0

# 2s bound: an unbounded git on a huge or locked repo would otherwise sit in the
# turn-end path. Same reasoning as guard-push-main's branch lookup.
GIT_TIMEOUT=""
if command -v timeout >/dev/null 2>&1; then GIT_TIMEOUT="timeout 2"
elif command -v gtimeout >/dev/null 2>&1; then GIT_TIMEOUT="gtimeout 2"
fi

CHANGED=$($GIT_TIMEOUT git status --porcelain 2>/dev/null | sed 's/^...//') || exit 0
[ -n "$CHANGED" ] || exit 0

printf '%s\n' "$CHANGED" | grep -qx 'CHANGELOG.md' && exit 0

# Docs, config and lockfiles are not the "code changed" this reminder is about.
CODE=$(printf '%s\n' "$CHANGED" | grep -vE '\.(md|txt|lock|json|ya?ml|toml|cfg|ini)$' | grep -vE '(^|/)(CHANGELOG|README|LICENSE)' || true)
[ -n "$CODE" ] || exit 0

COUNT=$(printf '%s\n' "$CODE" | grep -c . || true)
FIRST=$(printf '%s\n' "$CODE" | head -3 | tr '\n' ' ')

MSG="CHANGELOG.md not updated — $COUNT changed file(s): ${FIRST}(A task is done only when it compiles, passes tests, and is logged in CHANGELOG.md.)"

MSG="$MSG" python3 <<'PY' || exit 0
import json, os
print(json.dumps({"systemMessage": os.environ["MSG"]}))
PY

exit 0
