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

import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

BLOCK, ALLOW = "BLOCK", "ALLOW"
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
    ("~/projects/dotclaude/global/.claude/hooks/f.sh", ALLOW,
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


def invoke(pwsh, home, tool_input, tool="Edit"):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": home}
    code, out, err = pyhook.run("guard-central-config", payload, cwd=home, pwsh=pwsh,
                                env={"HOME": home, "USERPROFILE": home})
    if code != 0 or err.strip():
        return f"CRASH(rc={code}, {err.strip()[-120:]!r})"
    return BLOCK if pyhook.decision(out) == "deny" else ALLOW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run every case through PowerShell too")
    args = ap.parse_args()

    home = tempfile.mkdtemp(prefix="fakehome-")
    os.makedirs(os.path.join(home, ".claude", "hooks"), exist_ok=True)
    with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
        fh.write("{}")
    link = os.path.join(home, "link-to-settings.json")
    os.symlink(os.path.join(home, ".claude", "settings.json"), link)
    linked_dir = os.path.join(home, "elsewhere")
    os.symlink(os.path.join(home, ".claude", "hooks"), linked_dir)

    failures = 0
    for path, want, why in CASES:
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
    shutil.rmtree(home, ignore_errors=True)

    print(f"\n{len(CASES)} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
