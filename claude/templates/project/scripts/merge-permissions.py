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
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)):
        print(f"  ! {path} goes through a symlink; not writing through it", file=sys.stderr)
        return 0
    try:
        with open(sys.argv[1], encoding="utf-8-sig") as fh:
            wanted = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"  ! permission template unreadable ({exc}); nothing merged", file=sys.stderr)
        return 0
    try:
        # utf-8-sig: settings saved by Notepad or PowerShell 5.1 start with a BOM.
        with open(path, encoding="utf-8-sig") as fh:
            settings = json.load(fh)
    except FileNotFoundError:
        settings = {}
    except (OSError, ValueError) as exc:
        print(f"  ! {path} is not readable JSON ({exc}); add these permissions by hand: "
              f"{sorted(r for k in LISTS for r in wanted.get(k, []))}", file=sys.stderr)
        return 0

    rules_wanted = sorted(r for k in LISTS for r in wanted.get(k, []))
    if not isinstance(settings, dict) or not isinstance(settings.get("permissions", {}), dict):
        print(f"  ! {path} has an unexpected shape; add these permissions by hand: {rules_wanted}",
              file=sys.stderr)
        return 0
    permissions = settings.setdefault("permissions", {})
    added = []
    for key in LISTS:
        if not wanted.get(key):
            continue
        current = permissions.get(key)
        if current is None:
            current = permissions[key] = []
        if not isinstance(current, list):
            print(f"  ! {path} permissions.{key} is not a list; add by hand: {wanted[key]}", file=sys.stderr)
            continue
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
            json.dump(settings, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError as exc:
        print(f"  ! could not write {path} ({exc}); add by hand: {added}", file=sys.stderr)
        return 0
    print(f"  - merged {len(added)} permission rule(s) into {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
