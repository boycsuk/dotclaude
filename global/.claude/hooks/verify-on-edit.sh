#!/usr/bin/env bash
# PostToolUse hook: runs the project's linter/typechecker after edits.
# Auto-detects the stack. Silent if nothing applicable. Exit 2 with stderr if checks fail
# so Claude sees the error and corrects in the next turn. Timeout configured in settings.json.

set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")
[[ -z "$FILE" ]] && exit 0
case "$FILE" in
  "$ROOT"/*) ;;
  *) exit 0 ;;
esac

EXT="${FILE##*.}"
ERRORS=""

# Per-check budget. VERIFY_TIMEOUT is an env override for the test matrix;
# production default is 15s per check, under the 60s per-hook timeout in
# settings.json (two checks max 30s, headroom for the wrapper).
CHECK_TIMEOUT="${VERIFY_TIMEOUT:-15}"

run() {
  local desc="$1"; shift
  local out rc
  out=$(timeout "$CHECK_TIMEOUT" "$@" 2>&1) && return 0
  rc=$?
  # 124 = the check itself timed out. That is the budget's fault, not the
  # code's: reporting it as a lint failure makes Claude "fix" errors that do
  # not exist — the cry-wolf failure DESIGN.md §26 warns about. Skip silently.
  [[ "$rc" -eq 124 ]] && return 0
  ERRORS+="$desc failed:\n$out\n\n"
  return 1
}

case "$EXT" in
  ts|tsx|mts|cts|js|jsx|mjs|cjs)
    [[ -f package.json ]] || exit 0
    # Prefer the runner the project actually uses (lockfile evidence); fall
    # back to npm, and bail out quietly if not even npm exists — a bun/pnpm-
    # only PATH must not turn every .ts edit into "npm: command not found".
    RUNNER=npm
    if [[ -f bun.lockb || -f bun.lock ]] && command -v bun >/dev/null 2>&1; then RUNNER=bun
    elif [[ -f pnpm-lock.yaml ]] && command -v pnpm >/dev/null 2>&1; then RUNNER=pnpm
    elif [[ -f yarn.lock ]] && command -v yarn >/dev/null 2>&1; then RUNNER=yarn
    fi
    [[ "$RUNNER" == "npm" ]] && ! command -v npm >/dev/null 2>&1 && exit 0
    # Look under "scripts" specifically: a grep over the whole file also
    # matched dependency names, running scripts that do not exist.
    has_script() {
      SCRIPT_NAME="$1" python3 -c 'import json, os, sys; sys.exit(0 if os.environ["SCRIPT_NAME"] in (json.load(open("package.json")).get("scripts") or {}) else 1)' 2>/dev/null
    }
    if has_script typecheck; then
      run "typecheck" "$RUNNER" run typecheck --silent || true
    fi
    if has_script lint; then
      run "lint" "$RUNNER" run lint --silent || true
    fi
    ;;
  py|pyi)
    if command -v ruff >/dev/null 2>&1 && { [[ -f pyproject.toml ]] || [[ -f ruff.toml ]] || [[ -f .ruff.toml ]]; }; then
      run "ruff" ruff check "$FILE" || true
    fi
    if command -v mypy >/dev/null 2>&1 && [[ -f pyproject.toml ]] && grep -q '\[tool.mypy\]' pyproject.toml 2>/dev/null; then
      run "mypy" mypy "$FILE" || true
    fi
    ;;
  rs)
    [[ -f Cargo.toml ]] || exit 0
    if command -v cargo >/dev/null 2>&1; then
      run "clippy" cargo clippy --quiet --message-format=short -- -D warnings || true
    fi
    ;;
  go)
    [[ -f go.mod ]] || exit 0
    if command -v go >/dev/null 2>&1; then
      run "go vet" go vet ./... || true
    fi
    ;;
  *)
    exit 0
    ;;
esac

if [[ -n "$ERRORS" ]]; then
  printf "Verification failed after editing %s:\n%b" "$FILE" "$ERRORS" >&2
  exit 2
fi
exit 0
