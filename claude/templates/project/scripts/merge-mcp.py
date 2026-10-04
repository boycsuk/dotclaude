#!/usr/bin/env python3
"""Compose a project's .mcp.json from the template's per-server fragments.

Run by init.sh and init.ps1 (one implementation for both, like
merge-permissions.py):

    python3 merge-mcp.py <project-dir> <fragment.json> [...]

The file is COMPOSED, never copied: each fragment owns only its own server
key and every other key is left alone — including servers the user added by
hand. Merging by key makes re-runs idempotent and the flags order-independent.
The PowerShell twin compared servers by serialized key order (so an
equivalent entry counted as "updated") and rewrote the file through
ConvertTo-Json, reformatting a committed .mcp.json.

Exit 1 when the existing file cannot be read or written, so the caller can
warn; the deploy itself never aborts on it.
"""

import json
import os
import sys


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    project, fragments = sys.argv[1], sys.argv[2:]
    dst = os.path.join(project, ".mcp.json")
    if os.path.islink(dst):
        print(f"  ! {dst} is a symlink; not writing through it", file=sys.stderr)
        return 1
    cfg = {}
    if os.path.exists(dst):
        try:
            # utf-8-sig: a file saved by Notepad or PowerShell 5.1 starts with a BOM.
            with open(dst, encoding="utf-8-sig") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"  ! {dst} exists but is not readable JSON ({exc}) — merge the", file=sys.stderr)
            print("    server fragments manually from the template's mcp/ directory", file=sys.stderr)
            return 1
    if not isinstance(cfg, dict) or not isinstance(cfg.setdefault("mcpServers", {}), dict):
        print(f"  ! {dst} has no mcpServers object; merge the fragments manually", file=sys.stderr)
        return 1
    servers = cfg["mcpServers"]
    added, updated, skipped = [], [], []
    for frag_path in fragments:
        with open(frag_path, encoding="utf-8") as fh:
            for name, spec in json.load(fh).items():
                if servers.get(name) == spec:
                    skipped.append(name)
                    continue
                (updated if name in servers else added).append(name)
                servers[name] = spec
    if added or updated:
        try:
            with open(dst, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, indent=2)
                fh.write("\n")
        except OSError as exc:
            print(f"  ! could not write {dst} ({exc})", file=sys.stderr)
            return 1
    for label, names in (("merged", added), ("updated", updated), ("skip", skipped)):
        if names:
            print(f"  - {label}: {', '.join(sorted(names))} in ./.mcp.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
