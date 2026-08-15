#!/usr/bin/env python3
"""Behavioural contract for guard-push-main.{sh,ps1}.

Run:  python3 tests/guard-push-main-cases.py            # bash only
      python3 tests/guard-push-main-cases.py --pwsh PATH # also PowerShell

This exists because the hook was twice wrong in ways that reading it did not
reveal (DESIGN.md §18):
  - v1 grepped for the literal string "main" and the --force flag, and let
    seven of ten dangerous push forms through.
  - v2 fixed those but judged the whole command line, so a commit message
    containing "+main" — or a heredoc merely writing the words "git push" —
    was blocked as a force push.
Both were found by running the matrix below, not by review. Any change to
either hook must keep every case green, and a newly discovered form belongs
here first.

The `.sh` and `.ps1` hooks must agree on every case: that is the lockstep
guarantee CLAUDE.md asks for, and `--pwsh` is how you actually verify it
rather than eyeballing two files.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "global/.claude/hooks/guard-push-main.sh")
PS1 = os.path.join(REPO, "global/.claude/hooks/guard-push-main.ps1")

BLOCK, ALLOW = "BLOCK", "ALLOW"

# (command, expected, why)
ON_MAIN = [
    # Force push — never opt-out, by flag or by refspec.
    ("git push --force origin x",                BLOCK, "force flag"),
    ("git push -f origin x",                     BLOCK, "short force flag"),
    ("git push --force-with-lease origin x",     BLOCK, "a lease is still a force"),
    ("git push origin +main:main",               BLOCK, "force via leading '+'"),
    ("git push origin +HEAD:refs/heads/main",    BLOCK, "force via '+', long form"),
    ("git push origin +feature/x",               BLOCK, "force on a feature branch"),
    # Reaching main without the word appearing as a plain trailing token.
    ("git push",                                 BLOCK, "bare push while on main"),
    ("git push origin",                          BLOCK, "remote only, while on main"),
    ("git push origin HEAD",                     BLOCK, "HEAD resolves to main"),
    ("git push -u origin HEAD",                  BLOCK, "HEAD with -u"),
    ("git push origin @",                        BLOCK, "@ is HEAD"),
    ("git push origin HEAD:main",                BLOCK, "refspec destination"),
    ("git push origin main:main",                BLOCK, "src:dst"),
    ("git push origin refs/heads/main",          BLOCK, "fully qualified ref"),
    ('git push origin "main"',                   BLOCK, "double-quoted branch"),
    ("git push origin 'main'",                   BLOCK, "single-quoted branch"),
    ("git push origin main",                     BLOCK, "plain"),
    ("git push -u origin main",                  BLOCK, "with -u"),
    ("git -C /repo push origin main",            BLOCK, "git -C wrapper"),
    ("git push origin feature/x main",           BLOCK, "second refspec targets main"),
    ("git push origin main --force-with-lease",  BLOCK, "flag after the branch"),
    ("git push --repo=origin main",              BLOCK, "--repo= form"),
    ("git push -o ci.skip origin main",          BLOCK, "-o consumes a value"),
    ("git add -A\ngit commit -m x\ngit push origin main", BLOCK,
     "newline-separated commands — the most common multi-line form"),
    ("git commit -m x && git push origin main",  BLOCK,
     "compound command — the ps1 once flattened segments and missed this"),
    ("git.exe push origin main",                 BLOCK, "git.exe, the explicit Windows form"),
    ("git push origin :main",                    BLOCK, "deleting remote main via empty-src refspec"),
    ("git push origin --delete main",            BLOCK, "deleting remote main via flag"),
    ("bash <<EOF\ngit push origin main\nEOF",    BLOCK, "heredoc EXECUTED by an interpreter"),
    # Legitimate — blocking these teaches the model the hook is noise.
    ("git push origin feature/x",                ALLOW, "feature branch"),
    ("git push origin feature/main-refactor",    ALLOW, "branch name merely contains 'main'"),
    ("git push origin HEAD:feature/x",           ALLOW, "refspec to a feature branch"),
    ('git commit -m "fix +main flag" && git push origin feature/x', ALLOW,
     "'+main' is a commit message, not a refspec"),
    ('echo "git log && echo push notes"',        ALLOW, "no push at all"),
    ("git log --oneline",                        ALLOW, "not a push"),
    ("git pull origin main",                     ALLOW, "pull, not push"),
    ("echo 'git push origin main' > notes.txt",  ALLOW, "writes the words, does not push"),
    ("git fetch origin main",                    ALLOW, "fetch"),
    ("git add -A\ngit commit -m x\ngit push origin feature/x", ALLOW,
     "newline-separated commands pushing to a feature branch"),
    ("cat > notes.md <<'EOF'\ngit push origin main\nEOF", ALLOW,
     "heredoc that only WRITES a file — its body is data, not a push"),
    ("git commit -m 'multi\nline message' && git push origin feature/x", ALLOW,
     "a newline inside quotes is part of the message, not a separator"),
    ("git push origin --delete feature/old",     ALLOW, "deleting a feature branch is legitimate"),
]

ON_FEATURE = [
    ("git push",                                 ALLOW, "bare push on a feature branch"),
    ("git push origin HEAD",                     ALLOW, "HEAD resolves to the feature branch"),
    ("git push -u origin feature/z",             ALLOW, "explicit feature branch"),
    ("git push origin main",                     BLOCK, "explicitly targets main"),
    ("git push origin +feature/z",               BLOCK, "force is never allowed"),
    ("git push --signed origin HEAD:main",       BLOCK, "--signed is boolean — must not swallow the remote"),
    ("git push --all origin",                    BLOCK, "--all pushes every branch, main included"),
    ("git push --mirror origin",                 BLOCK, "--mirror can rewrite/delete remote refs"),
]

OPTOUT_ON_MAIN = [
    ("git push",                                 ALLOW, "opt-out permits main"),
    ("git push origin main",                     ALLOW, "opt-out permits main"),
    ("git push origin HEAD",                     ALLOW, "opt-out permits main"),
    ("git push origin +main:main",               BLOCK, "force stays blocked under opt-out"),
    ("git push --force origin main",             BLOCK, "force stays blocked under opt-out"),
    ("git push --mirror origin",                 BLOCK, "mirror stays blocked under opt-out"),
    ("git push origin :main",                    BLOCK, "deleting main stays blocked under opt-out"),
    ("git push origin --delete main",            BLOCK, "deleting main stays blocked under opt-out"),
    ("git push --all origin",                    ALLOW, "--all just pushes branches; opt-out permits main"),
]


def make_repo():
    path = tempfile.mkdtemp()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "init", "-q", "-b", "main", path], check=True)
    subprocess.run(["git", "-C", path, "commit", "-q", "--allow-empty", "-m", "x"],
                   check=True, env=env)
    return path


def set_optout(repo, enabled):
    claude = os.path.join(repo, ".claude")
    os.makedirs(claude, exist_ok=True)
    path = os.path.join(claude, "settings.local.json")
    if enabled:
        with open(path, "w") as fh:
            fh.write('{"allowPushToMain": true}')
    elif os.path.exists(path):
        os.remove(path)


def invoke(runner, cmd, cwd):
    proc = subprocess.run(runner, input=json.dumps({"tool_input": {"command": cmd}}),
                          capture_output=True, text=True, cwd=cwd,
                          env=dict(os.environ, CLAUDE_PROJECT_DIR=cwd))
    return BLOCK if proc.returncode == 2 else ALLOW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify .sh/.ps1 parity too")
    args = ap.parse_args()

    runners = [("sh", ["bash", SH])]
    if args.pwsh:
        runners.append(("ps1", [args.pwsh, "-NoProfile", "-File", PS1]))

    repo = make_repo()
    failures = 0

    suites = [("on main", ON_MAIN, "main", False),
              ("on feature/z", ON_FEATURE, "feature/z", False),
              ("on main, opt-out", OPTOUT_ON_MAIN, "main", True)]

    for title, cases, branch, optout in suites:
        if branch == "main":
            subprocess.run(["git", "-C", repo, "checkout", "-q", "main"], check=True)
        else:
            subprocess.run(["git", "-C", repo, "checkout", "-q", "-B", branch], check=True)
        set_optout(repo, optout)
        print(f"\n=== {title}")
        for cmd, want, why in cases:
            results = {name: invoke(runner, cmd, repo) for name, runner in runners}
            wrong = [n for n, got in results.items() if got != want]
            if wrong:
                failures += 1
                detail = ", ".join(f"{n}={results[n]}" for n in results)
                print(f"  FAIL want {want} got {detail} | {cmd}   ({why})")
        print(f"  {len(cases)} cases checked")

    # A non-git directory must not hang or crash.
    nongit = tempfile.mkdtemp()
    print("\n=== outside a git repo")
    for cmd, want in (("git push", ALLOW), ("git push origin main", BLOCK)):
        for name, runner in runners:
            got = invoke(runner, cmd, nongit)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {cmd}")
    print("  2 cases checked")

    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        return 1
    scope = "bash + powershell" if args.pwsh else "bash only (pass --pwsh for parity)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
