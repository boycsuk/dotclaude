# hook-kind: guard
"""PreToolUse hook on Edit|Write|NotebookEdit: block edits to the installed central config.

The reusable artifacts (hooks, agents, skills, rules, output-styles) and the
settings registry that wires them live in ~/.claude/ and apply to every
project; editing them from inside a project silently changes behaviour
everywhere, and install.sh overwrites templates/ wholesale. The source of truth
is the dotclaude repo (global/.claude/): change it there and run ./install.sh.
~/.claude/settings.local.json, CLAUDE.md and projects/ stay editable.

The path is resolved the way the filesystem will resolve the write — `~`,
`..`, and every symlink along the way, including a symlinked parent directory
the old .ps1 twin never followed — and compared case-insensitively where the
filesystem is (Windows, macOS), exactly where it is not (Linux).
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

GUARDED_DIRS = ("agents", "rules", "skills", "hooks", "output-styles")
CASE_INSENSITIVE = os.name == "nt" or sys.platform == "darwin"


def canonical(path):
    path = os.path.realpath(os.path.expanduser(path))
    return path.lower() if CASE_INSENSITIVE else path


def verdict(file_path):
    target = canonical(file_path)
    home = canonical(os.path.join("~", ".claude"))
    if target == os.path.join(home, "settings.json"):
        return ("is the central settings registry (~/.claude/settings.json). It wires every "
                "central hook and permission — editing it from inside a project can disable the "
                "deterministic safety layer for ALL your projects. Edit global/.claude/settings.json "
                "in the dotclaude repo and run ./install.sh instead")
    if target.startswith(os.path.join(home, "templates") + os.sep):
        return ("is the installed per-project template (~/.claude/templates/), which install.sh "
                "overwrites wholesale, so the edit would be lost. Edit templates/project/... in the "
                "dotclaude repo and run ./install.sh instead")
    if any(target.startswith(os.path.join(home, d) + os.sep) for d in GUARDED_DIRS):
        return ("is central dotclaude config (~/.claude/), shared by every project. Don't edit the "
                "installed copy from inside a project — edit the source in the dotclaude repo "
                "(global/.claude/...) and run ./install.sh instead")
    return None


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(file_path, str) or not file_path:
        return 0
    if not os.path.isabs(os.path.expanduser(file_path)) and isinstance(payload.get("cwd"), str):
        file_path = os.path.join(payload["cwd"], file_path)
    reason = verdict(file_path)
    if reason:
        hookio.deny(f"BLOCKED: '{tool_input.get('file_path') or tool_input.get('notebook_path')}' {reason}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
