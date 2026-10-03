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
  injected=1
}

# An injector that no longer applies must not read as NOT CAUGHT (or, worse,
# as caught by some unrelated check), so its failure is recorded here.
inject() {
  python3 "$SRC/tests/inject.py" "$WORK/repo" "$1" || injected=0
}

# Passes only when check.py fails AND the failing check is the one named:
# "check.py exited 1" alone let an unrelated check mask a blind one.
expect_fail() {
  local check="$1" label="$2" out
  if [ "$injected" -ne 1 ]; then
    echo "  INJECT FAILED: $label"
    fail=$((fail + 1))
    return
  fi
  out="$(python3 "$WORK/repo/check.py" 2>&1)"
  if printf '%s\n' "$out" | grep -qxF "FAIL  $check"; then
    echo "  caught:     $label"
    pass=$((pass + 1))
  else
    echo "  NOT CAUGHT: $label (expected FAIL  $check)"
    fail=$((fail + 1))
  fi
}

echo "== self-test of check.py"

setup
rm "$WORK/repo/global/.claude/hooks/detect-secrets.ps1"
expect_fail "hook .sh/.ps1 pairs" "a hook loses its .ps1 sibling"

setup
inject add-deny-rule
expect_fail "install.ps1 derives from settings.json" "a new Bash deny rule with no Windows mapping"

setup
inject drop-design-heading
expect_fail "DESIGN.md structure" "DESIGN.md loses a structural heading"

setup
inject diverge-extensions
expect_fail "code extension lists" "the two rules' extension globs diverge"

setup
printf 'run `python3 -c "import os"` to check\n' >> "$WORK/repo/global/.claude/skills/verify/SKILL.md"
expect_fail "skills avoid inline interpreters" "a central skill gains an inline interpreter"

setup
inject drop-hook-from-readme
expect_fail "doc inventories" "a doc inventory drops a hook"

setup
inject wire-missing-hook
expect_fail "settings.json hook wiring" "settings.json wires a hook that does not exist"

setup
inject drop-push-case
expect_fail "guard-push-main case coverage" "the guard-push-main matrix drops a known-bypass case"

setup
inject drop-hook-matrix
expect_fail "hooks have case matrices" "a safety hook loses its case matrix entirely"

setup
printf 'not json' > "$WORK/repo/templates/project/.claude/settings.json"
expect_fail "JSON validity" "a shipped JSON file stops parsing"

setup
inject heredoc-back-into-subshell
expect_fail "script syntax" "a hook folds its heredoc back inside \$( )"

setup
inject add-permissions-key
expect_fail "install.ps1 derives from settings.json" "a new permissions key never reaches install.ps1"

setup
inject drop-ps1-exit-code
expect_fail "install.ps1 derives from settings.json" "install.ps1 writes .ps1 hooks without re-raising the exit code"

setup
inject stop-hook-starts-blocking
expect_fail "hooks have case matrices" "the Stop hook matrix stops asserting it never blocks"

setup
inject diverge-seeded-lists
expect_fail "settings key classes" "the seeded key lists diverge between the installers"

setup
inject own-a-seeded-key
expect_fail "settings key classes" "a seeded preference is also declared owned"

setup
inject add-unclassified-key
expect_fail "settings key classes" "a top-level settings key is neither owned nor seeded"

setup
inject readd-if-gate
expect_fail "hook wiring" "a hook entry regains a prefix 'if' gate"

setup
inject revert-advisory-to-stderr
expect_fail "hook wiring" "an advisory hook stops emitting additionalContext"

setup
inject delete-central-agent
expect_fail "central artifact inventory" "a central agent is deleted outright"

setup
inject break-frontmatter
expect_fail "frontmatter validity" "an artifact's frontmatter fence is broken"

setup
inject pin-model-on-reviewer
expect_fail "frontmatter validity" "a reasoning agent pins a model against §7"

setup
inject wrap-mcp-fragment
expect_fail "MCP fragments" "an MCP fragment regains the 'mcpServers' wrapper"

setup
inject break-mcp-fragment-json
expect_fail "JSON validity" "an MCP fragment carries a JSON syntax error"

setup
inject delete-central-skill
expect_fail "central artifact inventory" "a central skill directory is deleted outright"

setup
inject obsolete-hits-shipped-hook
expect_fail "obsolete manifest" "obsolete.json names a hook dotclaude still ships"

setup
inject obsolete-broad-match
expect_fail "obsolete manifest" "an obsolete.json match also matches live hook commands"

setup
inject unwire-py-hook
expect_fail "hook wiring" "a Python hook ships but is wired to no event"

setup
inject undocument-opt-out
expect_fail "opt-outs documented" "a hook opt-out is missing from settings.local.json.example"

setup
inject mixed-wildcard-rule
expect_fail "install.ps1 derives from settings.json" "a permission rule mixes * with the :* suffix"

setup
inject drop-py-hook-kind
expect_fail "hook wiring" "a Python hook loses its hook-kind marker"

setup
inject rewrite-hook-without-matrix
expect_fail "hook wiring" "an input-rewriting hook loses its case matrix"

setup
inject wire-py-hook-without-interpreter
expect_fail "settings.json hook wiring" "a Python hook is wired without python3"

setup
inject py-hook-gains-shell-twin
expect_fail "hook .sh/.ps1 pairs" "a Python hook gains a .sh twin"

setup
inject lsp-entry-without-binary
expect_fail "LSP plugin catalog" "an LSP catalog entry loses its binary"

setup
inject drop-fork-from-verify
expect_fail "frontmatter validity" "a skill pins haiku without context: fork"

setup
rm "$WORK/repo/templates/project/init.ps1"
expect_fail "installer/deployer pairs" "the Windows deployer is deleted"

setup
printf '\nif true; then\n' >> "$WORK/repo/global/.claude/hooks/verify-on-edit.sh"
expect_fail "script syntax" "a hook gains a plain bash syntax error"

setup
printf '\ndef broken(:\n' >> "$WORK/repo/global/.claude/hooks/_lib/hookio.py"
expect_fail "script syntax" "the shared Python hook library stops compiling"

setup
inject unwire-shell-hook
expect_fail "hook wiring" "a safety .sh hook ships but is wired to no event"

setup
inject reinject-to-stderr
expect_fail "hook wiring" "the SessionStart digest moves to stderr"

setup
inject drop-skill-from-readme
expect_fail "doc inventories" "the skills inventory drops a skill named elsewhere in the doc"

setup
rm "$WORK/repo/templates/project/CLAUDE.md.template"
expect_fail "central artifact inventory" "a per-project template file is deleted"

setup
printf 'then run `bash -c "make"`\n' >> "$WORK/repo/global/.claude/skills/verify/SKILL.md"
expect_fail "skills avoid inline interpreters" "a central skill gains a bash -c one-liner"

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
