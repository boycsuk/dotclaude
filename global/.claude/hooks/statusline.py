"""statusLine command: print "<model> · <context>% ctx" below the prompt.

Context percentage is the point: the number that decides when compaction hits
is otherwise invisible until it happens, and compaction is what reinject-rules
exists to repair.

Runs on every assistant message, so it must be cheap and must never fail
loudly: whatever it prints lands where the status belongs. Every failure path
exits 0 with no output. Not a hook — wired through the statusLine settings key,
so it carries no hook-kind.
"""

import json
import sys

sys.dont_write_bytecode = True

HEADROOM_FLOOR = 40000      # tokens; below this the warning shows whatever the percentage
PERCENT_WARN = 70


def line(data):
    parts = []
    model = (data.get("model") or {}).get("display_name")
    if model:
        parts.append(str(model))
    # used_percentage is null before the first API call and right after
    # /compact — exactly when someone glances at the bar. Show nothing then,
    # never a fabricated 0%.
    ctx = data.get("context_window") or {}
    pct = ctx.get("used_percentage")
    if isinstance(pct, (int, float)) and not isinstance(pct, bool):
        pct = int(pct)                      # truncate: 69.6% is not yet 70%
        size = ctx.get("context_window_size") or 0
        warn = pct >= PERCENT_WARN or (size and size - size * pct / 100 < HEADROOM_FLOOR)
        parts.append(f"{'!' if warn else ''}{pct}% ctx")
    return " · ".join(parts)


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        text = line(data) if isinstance(data, dict) else ""
    except Exception:  # noqa: BLE001 — a status line must never print a traceback
        return 0
    if text:
        out = sys.stdout.buffer
        out.write((text + "\n").encode("utf-8"))
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
