#!/usr/bin/env bash
# statusLine command: prints "<model> · <context>% ctx" below the prompt.
#
# Context percentage is the point: the number that decides when compaction hits
# is otherwise invisible until it happens, and compaction is what reinject-rules
# exists to repair. Seeing it climb is the difference between planning a commit
# and being interrupted by a summary.
#
# Runs on every assistant message, after /compact, and on permission-mode
# changes, so it must be cheap and must never fail loudly: a status line that
# errors prints its error where the status belongs. Every failure path exits 0
# with no output, leaving the built-in footer alone.
#
# python3 rather than the docs' jq (DESIGN.md §5): jq is a dependency this setup
# deliberately avoids, and an absent jq would fail silently on every refresh.
# python3 is already a hard requirement of every hook here.

set -uo pipefail

INPUT=$(cat)
[ -n "$INPUT" ] || exit 0

INPUT="$INPUT" python3 <<'PY' 2>/dev/null || exit 0
import json, os, sys

try:
    d = json.loads(os.environ.get("INPUT", "") or "{}")
except ValueError:
    sys.exit(0)

parts = []

model = (d.get("model") or {}).get("display_name")
if model:
    parts.append(str(model))

# used_percentage is null before the first API call and again right after
# /compact until the next one — exactly when someone glances at the bar. Show
# nothing rather than a misleading 0%.
ctx = d.get("context_window") or {}
pct = ctx.get("used_percentage")
if isinstance(pct, (int, float)):
    pct = int(pct)
    # A 1M-context session sits at single digits for most of a long run, so the
    # threshold is on remaining headroom, not a fixed percentage.
    size = ctx.get("context_window_size") or 0
    warn = pct >= 70 or (size and size - size * pct / 100 < 40000)
    parts.append(f"{'!' if warn else ''}{pct}% ctx")

if parts:
    print(" · ".join(parts))
PY

exit 0
