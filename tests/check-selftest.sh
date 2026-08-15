#!/usr/bin/env bash
# Does check.py actually catch the regressions it claims to?
#
# Run: bash tests/check-selftest.sh
#
# A validator nobody tests is a validator that passes on a broken repo. Each
# case below injects one real regression into a scratch copy and asserts that
# check.py fails. This caught a genuine blind spot on its first run: the
# inline-interpreter check used glob("**/*.md"), which skips dot-directories,
# so it saw none of the central skills under global/.claude/skills/ and
# reported a clean pass on a repo that had the very bug it was written for.
#
# The final case is the control: a pristine copy must PASS, or every other
# result here is meaningless.

set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK:?}"' EXIT

pass=0
fail=0

setup() {
  rm -rf "${WORK:?}/repo"
  mkdir -p "$WORK/repo"
  # Copy only what check.py reads.
  (cd "$SRC" && tar -cf - check.py CLAUDE.md DESIGN.md install.sh install.ps1 \
      global templates skills tests 2>/dev/null) | (cd "$WORK/repo" && tar -xf -)
}

expect_fail() {
  local label="$1"
  if python3 "$WORK/repo/check.py" >/dev/null 2>&1; then
    echo "  NOT CAUGHT: $label"
    fail=$((fail + 1))
  else
    echo "  caught:     $label"
    pass=$((pass + 1))
  fi
}

echo "== self-test of check.py"

setup
rm "$WORK/repo/global/.claude/hooks/detect-secrets.ps1"
expect_fail "a hook loses its .ps1 sibling"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" add-deny-rule
expect_fail "a new Bash deny rule with no Windows mapping"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" drop-design-heading
expect_fail "DESIGN.md loses a structural heading"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" diverge-extensions
expect_fail "the two rules' extension globs diverge"

setup
printf 'run `python3 -c "import os"` to check\n' >> "$WORK/repo/global/.claude/skills/verify/SKILL.md"
expect_fail "a central skill gains an inline interpreter"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" drop-hook-from-readme
expect_fail "a doc inventory drops a hook"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" wire-missing-hook
expect_fail "settings.json wires a hook that does not exist"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" drop-push-case
expect_fail "the guard-push-main matrix drops a known-bypass case"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" drop-hook-matrix
expect_fail "a safety hook loses its case matrix entirely"

setup
printf 'not json' > "$WORK/repo/templates/project/.claude/settings.json"
expect_fail "a shipped JSON file stops parsing"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" readd-if-gate
expect_fail "a hook entry regains a prefix 'if' gate"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" revert-advisory-to-stderr
expect_fail "an advisory hook stops emitting additionalContext"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" delete-central-agent
expect_fail "a central agent is deleted outright"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" break-frontmatter
expect_fail "an artifact's frontmatter fence is broken"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" pin-model-on-reviewer
expect_fail "a reasoning agent pins a model against §7"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" wrap-mcp-fragment
expect_fail "an MCP fragment regains the 'mcpServers' wrapper"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" break-mcp-fragment-json
expect_fail "an MCP fragment carries a JSON syntax error"

setup
python3 "$SRC/tests/inject.py" "$WORK/repo" delete-central-skill
expect_fail "a central skill directory is deleted outright"

setup
if python3 "$WORK/repo/check.py" >/dev/null 2>&1; then
  echo "  caught:     (control) pristine repo passes"
  pass=$((pass + 1))
else
  echo "  BROKEN:     control run FAILS on a pristine repo — fix that first"
  python3 "$WORK/repo/check.py" 2>&1 | sed 's/^/              /'
  fail=$((fail + 1))
fi

echo
echo "self-test: $pass ok, $fail bad"
exit $fail
