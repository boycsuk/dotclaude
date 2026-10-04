#!/usr/bin/env python3
"""Detect per-project drift for /init-project --update.

Lives in a FILE, not an inline `python3 -c`, because the central
guard-destructive hook blocks inline interpreters (hooks may use
them because no PreToolUse runs on a hook; skills are subject to it). Run from the project root:

    python3 ~/.claude/skills/init-project/scripts/detect-drift.py

Prints one `KEY=VALUE` line per check so the skill can read the result
without parsing prose. Never raises on a missing/corrupt file — a file that
exists but cannot be read is reported as UNKNOWN, which the skill treats as
"ask the user" rather than "silently assume fine".

Obsolete-hook detection is imported from the template's prune-obsolete.py,
the script the deploy itself prunes with, so the two cannot disagree.
"""

import importlib.util
import os
import re
import sys

sys.dont_write_bytecode = True

UNKNOWN = "UNKNOWN"
DESIGN_DOC_NAME = re.compile(
    r"(^|[-_. ])(ui|ux|design|designs|style|styles|styleguide|theme|theming|tokens|brand|branding"
    r"|components|screens|wireframes?|mockups?)([-_. ]|$)", re.I)
DESIGN_DOC_SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "out", "target", "venv", "__pycache__"}
DESIGN_DOC_MAX_DEPTH = 4


def template_dir():
    return os.environ.get("TEMPLATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "templates", "project")


def load_prune():
    path = os.path.join(template_dir(), "scripts", "prune-obsolete.py")
    try:
        spec = importlib.util.spec_from_file_location("prune_obsolete", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError):
        return None


def read_json(prune, path):
    """(data, ok): ok is False only when the file exists and cannot be read."""
    try:
        return prune.load(path), True
    except FileNotFoundError:
        return None, True
    except (OSError, ValueError):
        return None, False


def check_obsolete(prune):
    """Leftovers of artifacts dotclaude stopped shipping (claude/templates/project/obsolete.json).

    Hook entries are normally already pruned by init.sh/init.ps1; a non-empty
    OBSOLETE_HOOKS means the deploy has not been re-run since. Servers and
    files are never removed automatically — the skill asks first.
    """
    manifest, _ = read_json(prune, os.path.join(template_dir(), "obsolete.json"))
    if not isinstance(manifest, dict):
        return UNKNOWN, UNKNOWN, UNKNOWN
    hooks = prune.count_obsolete_hooks(".", prune.hook_matches(manifest))
    mcp_data, mcp_ok = read_json(prune, ".mcp.json")
    servers = mcp_data.get("mcpServers") if isinstance(mcp_data, dict) else None
    if not mcp_ok:
        mcp = UNKNOWN
    else:
        servers = servers if isinstance(servers, dict) else {}
        mcp = ",".join(s["name"] for s in manifest.get("mcpServers", [])
                       if isinstance(s, dict) and s.get("name") in servers)
    files = ",".join(f["path"] for f in manifest.get("files", [])
                     if isinstance(f, dict) and os.path.exists(f.get("path", "")))
    return (UNKNOWN if hooks is None else str(hooks)), mcp, files


def check_allow_push_main(prune):
    """Post-deploy check: did the "todo en main" choice actually land?"""
    local, ok = read_json(prune, os.path.join(".claude", "settings.local.json"))
    if not ok or (local is not None and not isinstance(local, dict)):
        return UNKNOWN
    if local is None:
        return "ABSENT"
    return "TRUE" if local.get("allowPushToMain") is True else "FALSE"


def check_mcp_servers(prune):
    """Post-deploy check: the servers actually in .mcp.json (a failed merge only WARNs)."""
    data, ok = read_json(prune, ".mcp.json")
    if not ok or (data is not None and not isinstance(data, dict)):
        return UNKNOWN
    servers = (data or {}).get("mcpServers")
    return ",".join(sorted(servers)) if isinstance(servers, dict) else ""


def check_example_drift():
    """Report example drift here: the deploy prints it on the user's terminal, which the skill never sees."""
    mine = os.path.join(".claude", "settings.local.json.example")
    ours = os.path.join(template_dir(), ".claude", "settings.local.json.example")
    try:
        with open(mine, "rb") as fh:
            local = fh.read().replace(b"\r\n", b"\n")
    except FileNotFoundError:
        return "ABSENT"
    except OSError:
        return UNKNOWN
    try:
        with open(ours, "rb") as fh:
            # Line endings are no edit: a Windows checkout holds the same text with CRLF.
            return "NO" if fh.read().replace(b"\r\n", b"\n") == local else "YES"
    except OSError:
        return UNKNOWN


def has_markdown(path):
    """True when `path` holds a Markdown file at any depth (src/components/ with code only does not)."""
    for _, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in DESIGN_DOC_SKIP_DIRS and not d.startswith(".")]
        if any(f.lower().endswith(".md") for f in filenames):
            return True
    return False


def check_legacy_design_docs():
    """Markdown files whose name reads as design, outside docs/design/: candidates /implement-ui offers to migrate.

    Names only: reading every file's headings is the skill's job, where a
    person chooses. Comma-separated paths, empty when none, UNKNOWN when the
    project root cannot be listed; an unreadable subdirectory (a root-owned
    Docker volume) is skipped rather than sinking the whole scan.
    """
    found = []

    def fail(err):
        if os.path.normpath(err.filename or ".") == ".":
            raise err

    try:
        for dirpath, dirnames, filenames in os.walk(".", onerror=fail):
            rel = os.path.relpath(dirpath, ".").replace("\\", "/")
            depth = 0 if rel == "." else rel.count("/") + 1
            keep = []
            for d in ([] if depth >= DESIGN_DOC_MAX_DEPTH else sorted(dirnames)):
                if d in DESIGN_DOC_SKIP_DIRS or d.startswith(".") or (rel == "docs" and d == "design"):
                    continue
                sub = d if rel == "." else f"{rel}/{d}"
                if DESIGN_DOC_NAME.search(d) and has_markdown(sub):
                    found.append(sub + "/")       # a design folder is one candidate, not a file list
                else:
                    keep.append(d)
            dirnames[:] = keep
            for name in filenames:
                stem, ext = os.path.splitext(name)
                if ext.lower() == ".md" and DESIGN_DOC_NAME.search(stem):
                    found.append(name if rel == "." else f"{rel}/{name}")
    except OSError:
        return UNKNOWN
    return ",".join(sorted(found))


def main():
    prune = load_prune()
    if prune is None:
        obsolete_hooks = obsolete_mcp = obsolete_files = allow_push = servers = UNKNOWN
    else:
        obsolete_hooks, obsolete_mcp, obsolete_files = check_obsolete(prune)
        allow_push = check_allow_push_main(prune)
        servers = check_mcp_servers(prune)
    for key, value in (
        ("OBSOLETE_HOOKS", obsolete_hooks),
        ("OBSOLETE_MCP", obsolete_mcp),
        ("OBSOLETE_FILES", obsolete_files),
        ("ALLOW_PUSH_MAIN", allow_push),
        ("MCP_SERVERS", servers),
        ("SETTINGS_EXAMPLE_DRIFT", check_example_drift()),
        ("LEGACY_DESIGN_DOCS", check_legacy_design_docs()),
    ):
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
