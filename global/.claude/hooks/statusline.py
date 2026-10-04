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
import os
import re
import sys

sys.dont_write_bytecode = True

HEADROOM_FLOOR = 40000      # tokens; below this the warning shows whatever the percentage
PERCENT_WARN = 70
EXEC_FORM_SINCE = (2, 1, 139)
GUARDS_OFF = "!guards off: Claude Code too old for this install - update it or re-run the installer"


def exec_hooks_unsupported(version):
    """True when Claude Code `version` predates hook `args` and settings.json wires a hook with them.

    Such a Claude Code runs a bare python.exe for every exec-form hook, which
    exits 1 without blocking, so every guard is off. The hooks cannot report
    it, since they are what fails; this line, wired without `args`, still runs.
    """
    m = re.match(r"\s*(\d+)\.(\d+)\.(\d+)", str(version or ""))
    if not m or tuple(map(int, m.groups())) >= EXEC_FORM_SINCE:
        return False
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    try:
        with open(os.path.join(config, "settings.json"), encoding="utf-8-sig") as fh:
            hooks = json.load(fh).get("hooks") or {}
    except (OSError, ValueError, AttributeError):
        return False
    return any(isinstance(h, dict) and isinstance(h.get("args"), list)
               for groups in hooks.values() if isinstance(groups, list)
               for g in groups if isinstance(g, dict)
               for h in g.get("hooks") or [])


def line(data):
    parts = [GUARDS_OFF] if exec_hooks_unsupported(data.get("version")) else []
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
