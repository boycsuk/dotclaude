# hook-kind: advisory
"""PostToolUse hook: when a rules *.md file is edited, remind that its portable mirror may be stale.

The mirrors exist so tools that do not run Claude Code still follow the same
conventions; docs/conventions.md is the repo-versioned copy and the rules file
is the copy Claude Code loads (DESIGN.md §17). Delivered as additionalContext:
editing a rule is legitimate and must never be gated, and stderr with exit 0
never reaches the model. Fires only on rule edits, which are rare and each one
genuinely carries the sync obligation, so there is no debounce.
"""

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

# A project's own .claude/rules/ or the dotclaude source global/.claude/rules/
# (the installed ~/.claude/rules/ copy is not editable: guard-central-config).
RULE = re.compile(r"\.claude/rules/.+\.md$")


def note_for(path):
    name = os.path.basename(path)
    note = (f"NOTE: you edited a rule ({path}). Its portable mirror may now be stale. Reflect the change "
            "in the conventions mirror: templates/project/docs/conventions.md when editing the dotclaude "
            "repo, docs/conventions.md inside a deployed project.")
    if name == "ai-collaboration.md":
        note += (" If you changed a tone/language/output convention, also update the output style (repo "
                 "source: global/.claude/output-styles/dotclaude.md, installed as ~/.claude/output-styles/).")
    if name in ("workflow.md", "ai-collaboration.md"):
        note += (" If you changed a non-negotiable convention, also update the post-compaction digest in "
                 "hooks/reinject-rules.py.")
    return note


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if isinstance(path, str) and RULE.search(path.replace("\\", "/")):
        hookio.context("PostToolUse", note_for(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
