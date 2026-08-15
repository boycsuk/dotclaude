#!/usr/bin/env python3
"""Detect per-project drift for /init-project --update (SKILL.md §1e gaps).

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


def check_serena_hooks():
    """Gap 1: the project's settings.json should wire `serena-hooks remind`."""
    settings = load_json(os.path.join(".claude", "settings.json"))
    if settings is None:
        return "UNKNOWN"
    for event in settings.get("hooks", {}).values():
        for group in event:
            for hook in group.get("hooks", []):
                if "serena-hooks" in str(hook.get("command", "")):
                    return "HAS_HOOKS"
    return "NO_HOOKS"


def check_mcp():
    """Gap 2: graphify launched via the broken `python -m`, or serena's
    dashboard left on. Two independent sub-checks."""
    mcp = load_json(".mcp.json")
    if mcp is None:
        return "UNKNOWN", "UNKNOWN"
    servers = mcp.get("mcpServers", {})
    graphify = "GRAPHIFY_BROKEN" if servers.get("graphify", {}).get("command") == "python" else "GRAPHIFY_OK"
    serena_args = servers.get("serena", {}).get("args", [])
    dashboard = "DASH_OFF" if "--open-web-dashboard" in serena_args else "DASH_ON"
    return graphify, dashboard


def check_graphify_integrated():
    """Gap 3: Serena present but Graphify never set up — no graphify-out/ AND
    no `## graphify` block in CLAUDE.md.

    The shell one-liner this replaces (`test -d graphify-out || grep -q ... &&
    echo A || echo B`) happened to produce the right answer in all four
    boundary cases despite its unparenthesised `||`/`&&` chain. It is spelled
    out here because the intent should not depend on that coincidence.
    """
    has_dir = os.path.isdir("graphify-out")
    has_block = False
    try:
        with open("CLAUDE.md") as fh:
            text = fh.read().lower()
        # The template writes "### Graphify (graph-level companion…)"; the old
        # marker looked for "## graphify" exactly, which the template never
        # emits — so this returned GRAPHIFY_ABSENT forever, re-offering an
        # already-closed gap on every --update. Both spellings are accepted:
        # the H3 heading dotclaude ships, and the H2 block `graphify install`
        # appends in projects that ran it directly.
        has_block = "### graphify" in text or "## graphify" in text
    except Exception:
        pass
    return "GRAPHIFY_PRESENT" if (has_dir or has_block) else "GRAPHIFY_ABSENT"


def check_allow_push_main():
    """§8 verification: did the "todo en main" choice actually land?"""
    local = load_json(os.path.join(".claude", "settings.local.json"))
    if local is None:
        return "ABSENT"
    return "TRUE" if local.get("allowPushToMain") is True else "FALSE"


def main():
    graphify_mcp, dashboard = check_mcp()
    for key, value in (
        ("SERENA_HOOKS", check_serena_hooks()),
        ("GRAPHIFY_MCP", graphify_mcp),
        ("SERENA_DASHBOARD", dashboard),
        ("GRAPHIFY_INTEGRATED", check_graphify_integrated()),
        ("ALLOW_PUSH_MAIN", check_allow_push_main()),
    ):
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
