#!/usr/bin/env python3
"""Add permission rules from a template file to a project's settings.json.

Run by init.sh and init.ps1 (one implementation for both):

    python3 merge-permissions.py <permissions.json> [project-dir]

`permissions.json` holds {"allow": [...], "ask": [...], "deny": [...]} (any
subset). Each rule is appended to the same list in .claude/settings.json only
if absent, so re-runs are idempotent and the user's own rules are never
reordered or removed. Never fatal: an unreadable settings file is reported and
left untouched, exit code is 0.
"""

import json
import os
import sys

LISTS = ("allow", "ask", "deny")


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 0
    project = sys.argv[2] if len(sys.argv) == 3 else "."
    path = os.path.join(project, ".claude", "settings.json")
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            wanted = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"  ! permission template unreadable ({exc}); nothing merged", file=sys.stderr)
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            settings = json.load(fh)
    except FileNotFoundError:
        settings = {}
    except (OSError, ValueError) as exc:
        print(f"  ! {path} is not readable JSON ({exc}); add these permissions by hand: "
              f"{sorted(r for k in LISTS for r in wanted.get(k, []))}", file=sys.stderr)
        return 0

    permissions = settings.setdefault("permissions", {})
    added = []
    for key in LISTS:
        current = permissions.setdefault(key, []) if wanted.get(key) else permissions.get(key)
        for rule in wanted.get(key, []):
            if rule not in current:
                current.append(rule)
                added.append(f"{key}:{rule}")
    if not added:
        print(f"  - skip: permissions already present in {path}", file=sys.stderr)
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        print(f"  ! could not write {path} ({exc}); add by hand: {added}", file=sys.stderr)
        return 0
    print(f"  - merged {len(added)} permission rule(s) into {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
