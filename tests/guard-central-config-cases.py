#!/usr/bin/env python3
"""Behavioural contract for guard-central-config.py.

Run:  python3 tests/guard-central-config-cases.py
      python3 tests/guard-central-config-cases.py --pwsh PATH   # also through PowerShell

This hook protects the ENTIRE deterministic layer: if an edit slips through it,
every other guarantee can be rewritten from inside a project. It joined the
matrix club after review found the old .ps1 comparing case-SENSITIVELY on
case-insensitive filesystems (a lower-case drive letter dodged the guard on
Windows), and an audit found that .ps1 resolving a symlink only when the file
itself was one — an edit through a symlinked parent directory passed.

Cases run against a fake HOME so the real ~/.claude is never involved.

Case-sensitivity is platform semantics: the hook folds case where the
filesystem does (Windows, macOS) and matches exactly on Linux, where
~/.Claude genuinely is a different path.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

BLOCK, ASK, ALLOW = "BLOCK", "ASK", "ALLOW"
FOLDS_CASE = sys.platform == "darwin" or os.name == "nt"

# (file_path relative to fake HOME unless a special marker, expected, why)
CASES = [
    # --- the registry and every guarded subtree -----------------------------
    ("~/.claude/settings.json",                    BLOCK, "the central registry"),
    ("~/.claude/hooks/guard-destructive.py",       BLOCK, "central hook"),
    ("~/.claude/agents/researcher.md",             BLOCK, "central agent"),
    ("~/.claude/rules/workflow.md",                BLOCK, "central rule"),
    ("~/.claude/skills/verify/SKILL.md",           BLOCK, "central skill"),
    ("~/.claude/output-styles/dotclaude.md",       BLOCK, "central output style"),
    ("~/.claude/templates/project/init.sh",        BLOCK, "installed template — install overwrites it"),

    # --- what stays editable ------------------------------------------------
    ("~/.claude/settings.local.json",              ALLOW, "personal per-machine override"),
    ("~/.claude/CLAUDE.md",                        ALLOW, "user's global memory file"),
    ("~/.claude/projects/x/memory/note.md",        ALLOW, "auto-memory is not config"),
    ("~/projects/app/.claude/settings.json",       ALLOW, "a PROJECT's stub, not the central one"),
    ("~/projects/dotclaude/claude/hooks/f.sh", ALLOW,
     "the repo SOURCE is exactly where edits belong"),
    ("~/.claude-backup/settings.json",             ALLOW, "sibling dir sharing the prefix"),

    # --- dodging attempts ---------------------------------------------------
    ("~/.claude/hooks/../settings.json",           BLOCK, "../ traversal resolves inside"),
    ("~/projects/../.claude/settings.json",        BLOCK, "traversal from elsewhere"),
    ("~/.Claude/settings.json",                    BLOCK if FOLDS_CASE else ALLOW,
     "case variant: same file on APFS/NTFS, distinct path on ext4"),
    ("SYMLINK",                                    BLOCK,
     "a symlink pointing at the guarded file is the guarded file"),
    ("SYMLINKED_DIR",                              BLOCK,
     "a file reached through a symlinked parent directory"),
    ("NOTEBOOK",                                   BLOCK,
     "NotebookEdit sends notebook_path, not file_path"),
]

# The opt-outs switch a guard off for one project; they are the user's choice,
# so a write that grants one asks even though the file itself is editable.
# (file_path relative to fake HOME, tool, extra tool_input, expected, why)
OPT_OUT_CASES = [
    ("~/app/.claude/settings.local.json", "Write", {"content": '{\n  "allowPushToMain": true\n}'},
     ASK, "Write granting allowPushToMain"),
    ("~/app/.claude/settings.local.json", "Edit",
     {"old_string": "{", "new_string": '{\n  "allowCommitTrailers":true,'},
     ASK, "Edit granting allowCommitTrailers"),
    ("~/app/.claude/settings.json", "Edit", {"old_string": "{", "new_string": '{"disableAllHooks": true,'},
     ASK, "disableAllHooks turns every hook off"),
    ("~/.claude/settings.local.json", "Write", {"content": '{"disableAllHooks": true}'},
     ASK, "the personal file too"),
    ("~/app/.claude/settings.local.json", "Edit",
     {"old_string": '"allowPushToMain": true', "new_string": '"allowPushToMain": false'},
     ALLOW, "revoking an opt-out"),
    ("~/app/.claude/settings.local.json", "Write", {"content": '{"permissions": {"allow": []}}'},
     ALLOW, "an unrelated settings change"),
    ("~/app/docs/opt-outs.md", "Write", {"content": '`"allowPushToMain": true` in settings.local.json'},
     ALLOW, "documentation that quotes the key"),
]


def invoke(pwsh, home, tool_input, tool="Edit"):
    code, out, err = pyhook.run("guard-central-config", pyhook.payload(tool, tool_input, cwd=home),
                                cwd=home, pwsh=pwsh, env=pyhook.home_env(home))
    got = pyhook.verdict(code, out, err)
    return {"deny": BLOCK, "ask": ASK, "allow": ALLOW}.get(got, got)


def main():
    args = pyhook.cli()

    home = tempfile.mkdtemp(prefix="fakehome-")
    os.makedirs(os.path.join(home, ".claude", "hooks"), exist_ok=True)
    with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
        fh.write("{}")
    link = os.path.join(home, "link-to-settings.json")
    linked_dir = os.path.join(home, "elsewhere")
    try:
        os.symlink(os.path.join(home, ".claude", "settings.json"), link)
        os.symlink(os.path.join(home, ".claude", "hooks"), linked_dir, target_is_directory=True)
        skipped = set()
    except OSError:                    # Windows without Developer Mode cannot create one
        skipped = {"SYMLINK", "SYMLINKED_DIR"}
        print("  (symlink cases skipped: this account cannot create symlinks)")

    failures = 0
    for path, want, why in CASES:
        if path in skipped:
            continue
        tool = "Edit"
        if path == "SYMLINK":
            tool_input = {"file_path": link}
        elif path == "SYMLINKED_DIR":
            tool_input = {"file_path": os.path.join(linked_dir, "new-hook.py")}
        elif path == "NOTEBOOK":
            tool, tool_input = "NotebookEdit", {"notebook_path": os.path.join(home, ".claude", "hooks", "n.ipynb"),
                                                "new_source": "x"}
        else:
            tool_input = {"file_path": path.replace("~", home)}
        for name, pwsh in pyhook.runners(args.pwsh):
            got = invoke(pwsh, home, tool_input, tool)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {path}   ({why})")
    for path, tool, extra, want, why in OPT_OUT_CASES:
        tool_input = dict(extra, file_path=path.replace("~", home))
        for name, pwsh in pyhook.runners(args.pwsh):
            got = invoke(pwsh, home, tool_input, tool)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {tool} {path}   ({why})")
    shutil.rmtree(home, ignore_errors=True)
    total = len(CASES) - len(skipped) + len(OPT_OUT_CASES)
    return pyhook.finish("guard-central-config", failures, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
