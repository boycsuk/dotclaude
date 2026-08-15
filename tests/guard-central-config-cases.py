#!/usr/bin/env python3
"""Behavioural contract for guard-central-config.{sh,ps1}.

Run:  python3 tests/guard-central-config-cases.py
      python3 tests/guard-central-config-cases.py --pwsh PATH   # verify parity

This hook protects the ENTIRE deterministic layer: if an edit slips through it,
every other guarantee can be rewritten from inside a project. It joined the
matrix club after review found the .ps1 comparing case-SENSITIVELY on
case-insensitive filesystems (a lower-case drive letter dodged the guard on
Windows) — the fourth hook in a row whose defect reading did not reveal.

Cases run against a fake HOME so the real ~/.claude is never involved.

Case-sensitivity is platform semantics, not a bug to unify: the .sh matches
exactly (correct for ext4; folds on Darwin at runtime), the .ps1 folds always
(correct for NTFS/APFS). The CASE_VARIANT case therefore expects different
verdicts per runner when this matrix runs on Linux.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "global/.claude/hooks/guard-central-config.sh")
PS1 = os.path.join(REPO, "global/.claude/hooks/guard-central-config.ps1")

BLOCK, ALLOW = "BLOCK", "ALLOW"

# (file_path relative to fake HOME unless absolute, expected, why)
# expected may be a dict {"sh": ..., "ps1": ...} for platform-semantic splits.
CASES = [
    # --- the registry and every guarded subtree -----------------------------
    ("~/.claude/settings.json",                    BLOCK, "the central registry"),
    ("~/.claude/hooks/guard-destructive.sh",       BLOCK, "central hook"),
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
    ("~/.Claude/settings.json", {"sh": ALLOW, "ps1": BLOCK},
     "case variant: distinct path on ext4 (sh on Linux), same file on NTFS/APFS (ps1)"),
    ("SYMLINK",                                    BLOCK,
     "a symlink pointing at the guarded file is the guarded file"),
]


def invoke(runner, file_path, home):
    env = dict(os.environ, HOME=home)
    payload = {"tool_input": {"file_path": file_path}}
    proc = subprocess.run(runner, input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30, env=env)
    return BLOCK if proc.returncode == 2 else ALLOW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify .sh/.ps1 parity")
    args = ap.parse_args()

    runners = [("sh", ["bash", SH])]
    if args.pwsh:
        runners.append(("ps1", [args.pwsh, "-NoProfile", "-File", PS1]))

    home = tempfile.mkdtemp(prefix="fakehome-")
    os.makedirs(os.path.join(home, ".claude", "hooks"), exist_ok=True)
    with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
        fh.write("{}")
    link = os.path.join(home, "link-to-settings.json")
    os.symlink(os.path.join(home, ".claude", "settings.json"), link)

    failures = 0
    for path, want, why in CASES:
        file_path = link if path == "SYMLINK" else path.replace("~", home)
        for name, runner in runners:
            expected = want[name] if isinstance(want, dict) else want
            try:
                got = invoke(runner, file_path, home)
            except subprocess.TimeoutExpired:
                got = "TIMEOUT"
            if got != expected:
                failures += 1
                print(f"  FAIL want {expected} got {got} ({name}) | {path}   ({why})")

    print(f"\n{len(CASES)} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "bash + powershell" if args.pwsh else "bash only (pass --pwsh for parity)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
