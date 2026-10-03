#!/usr/bin/env python3
"""Detect per-project drift for /init-project --update (update-mode.md §1e).

Lives in a FILE, not an inline `python3 -c`, because the central
guard-destructive hook blocks inline interpreters (DESIGN.md §5 justifies
`python3 -c` inside hooks, where no PreToolUse runs — not inside skills,
which are subject to it). Run from the project root:

    python3 ~/.claude/skills/init-project/scripts/detect-drift.py

Prints one `KEY=VALUE` line per check so the skill can read the result
without parsing prose. Never raises on a missing/corrupt file — a file that
cannot be read is reported as UNKNOWN, which the skill treats as "ask the
user" rather than "silently assume fine".
"""

import json
import os
import sys


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def check_obsolete():
    """Leftovers of artifacts dotclaude stopped shipping (templates/project/obsolete.json).

    Hook entries are normally already pruned by init.sh/init.ps1; a non-empty
    OBSOLETE_HOOKS means the deploy has not been re-run since. Servers and
    files are never removed automatically — the skill asks first.
    """
    template = os.environ.get("TEMPLATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "templates", "project")
    manifest = load_json(os.path.join(template, "obsolete.json"))
    if not isinstance(manifest, dict):
        return "UNKNOWN", "UNKNOWN", "UNKNOWN"
    matches = [h.get("match", "") for h in manifest.get("hooks", []) if h.get("match")]
    hooks = 0
    for name in ("settings.json", "settings.local.json"):
        settings = load_json(os.path.join(".claude", name)) or {}
        for groups in (settings.get("hooks") or {}).values():
            for group in groups:
                for hook in group.get("hooks", []):
                    if any(m in str(hook.get("command", "")) for m in matches):
                        hooks += 1
    servers = (load_json(".mcp.json") or {}).get("mcpServers", {})
    mcp = [s["name"] for s in manifest.get("mcpServers", []) if s.get("name") in servers]
    files = [f["path"] for f in manifest.get("files", []) if os.path.exists(f.get("path", ""))]
    return str(hooks), ",".join(mcp), ",".join(files)


def check_allow_push_main():
    """§8 verification: did the "todo en main" choice actually land?"""
    local = load_json(os.path.join(".claude", "settings.local.json"))
    if local is None:
        return "ABSENT"
    return "TRUE" if local.get("allowPushToMain") is True else "FALSE"


def main():
    obsolete_hooks, obsolete_mcp, obsolete_files = check_obsolete()
    for key, value in (
        ("OBSOLETE_HOOKS", obsolete_hooks),
        ("OBSOLETE_MCP", obsolete_mcp),
        ("OBSOLETE_FILES", obsolete_files),
        ("ALLOW_PUSH_MAIN", check_allow_push_main()),
    ):
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
