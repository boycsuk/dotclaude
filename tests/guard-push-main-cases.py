#!/usr/bin/env python3
"""Behavioural contract for guard-push-main.py.

Run:  python3 tests/guard-push-main-cases.py
      python3 tests/guard-push-main-cases.py --pwsh PATH # also through PowerShell

This exists because the hook was twice wrong in ways that reading it did not
reveal:
  - v1 grepped for the literal string "main" and the --force flag, and let
    seven of ten dangerous push forms through.
  - v2 fixed those but judged the whole command line, so a commit message
    containing "+main" — or a heredoc merely writing the words "git push" —
    was blocked as a force push.
  - v3 (a .sh/.ps1 pair) split commands only on operators surrounded by
    spaces and let `true&&git push origin main`, `(git push origin main)`,
    `-uf`, `--mirro`, `git -c alias.p=push p` and an apostrophe in a comment
    through — a 2026-10-03 audit, reproduced against a local bare remote.
Both were found by running the matrix below, not by review. Any change to
the hook must keep every case green, and a newly discovered form belongs
here first. `--pwsh` runs every case through the exact PowerShell command
form install.ps1 writes.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

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
    # Shapes the space-split v3 parser let through (2026-10-03 audit).
    ("true&&git push origin main",               BLOCK, "operator glued to the push"),
    ("cd .;git push origin main",                BLOCK, "';' glued to the push"),
    ('git commit -m "fix: x"; git push origin main', BLOCK, "commit then push, the natural agent form"),
    ("(git push origin main)",                   BLOCK, "subshell"),
    ("{ git push origin main; }",                BLOCK, "brace group"),
    ("git push origin main|cat",                 BLOCK, "pipe glued to the push"),
    ("echo $(git push origin main)",             BLOCK, "command substitution"),
    ('echo "$(git push origin main)"',           BLOCK, "command substitution inside double quotes"),
    ("echo `git push origin main`",              BLOCK, "backtick substitution"),
    ("git push origin main # don't",             BLOCK, "an apostrophe in a comment must not abort the parse"),
    ("# push it (it's ready)\ngit push origin main", BLOCK, "a comment line hides nothing after it"),
    ("cat > f.txt <<EOF\n$(git push origin main)\nEOF", BLOCK,
     "an unquoted heredoc runs its $( ) while being written"),
    ("ssh host <<EOF\ngit push origin main\nEOF", BLOCK, "a heredoc fed to anything but a file writer runs"),
    ("python3 -m quopri -d <<'EOF' | bash\ngit push origin main\nEOF", BLOCK,
     "an interpreter running a script passes the body through to a shell"),
    ("bash -s >&/tmp/python3 x <<'EOF'\ngit push origin main\nEOF", BLOCK,
     "a >& redirect target named like an interpreter is not the consumer"),
    ("git push origin HEAD:heads/main",          BLOCK, "git expands heads/main to refs/heads/main"),
    ("git push origin main 'x",                  BLOCK, "unparseable push fails closed"),
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
    ("git push --branches origin",               BLOCK, "--branches is --all's new name"),
    ("git push --recurse-submodules check origin main", BLOCK, "a valued option must not swallow the remote"),
    ("git push --recurse-submodules check origin feature/z", ALLOW, "same option, feature branch"),
    ("tee notes.md <<'EOF'\ngit push origin main\nEOF", ALLOW, "a tee heredoc only writes"),
    ("git push -uf origin feature/z",            BLOCK, "bundled short flags hide -f"),
    ("git push -fu origin feature/z",            BLOCK, "bundled short flags, other order"),
    ("git push --mirro origin",                  BLOCK, "git accepts an unambiguous prefix of --mirror"),
    ("git push --forc origin feature/z",         BLOCK, "a prefix of the force options"),
    ("git -c remote.origin.push=+HEAD:refs/heads/main push origin", BLOCK,
     "a refspec injected through -c forces main"),
    ("git -c alias.p=push p origin main",        BLOCK, "a -c alias that pushes"),
    ("git -c alias.p='!git push' p origin main", BLOCK, "a shell alias that pushes"),
    ("git push origin HEAD:heads/main",          BLOCK, "heads/main is main"),
    ("git push --force origin feature/z 'x",     BLOCK, "unparseable push fails closed"),
    ("echo git push origin main",                ALLOW, "echo prints the words, it does not push"),
    ("git push -u origin feature/z # it's done", ALLOW, "an apostrophe in a comment is fine"),
    ("cat > notes.md <<'EOF'\n$(git push origin main)\nEOF", ALLOW,
     "a quoted heredoc delimiter leaves $( ) inert"),
    ("python3 notes.py 'it''s' # git push origin main", ALLOW, "the push is inside a comment"),
]

# Run as the PowerShell tool: the command line is PowerShell syntax.
POWERSHELL_ON_FEATURE = [
    ('git commit -m "say `"hi`""; git push origin main', BLOCK,
     "backtick-escaped quote, then a push to main"),
    ("git push origin feature/z",                ALLOW, "feature branch"),
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


def invoke(pwsh, cmd, cwd, tool="Bash", payload_cwd=None):
    payload = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": payload_cwd or cwd}
    code, out, err = pyhook.run("guard-push-main", payload, cwd=cwd, pwsh=pwsh)
    if code != 0 or err.strip():
        return f"CRASH(rc={code}, {err.strip()[-120:]!r})"
    return BLOCK if pyhook.decision(out) == "deny" else ALLOW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run every case through PowerShell too")
    args = ap.parse_args()

    runners = pyhook.runners(args.pwsh)

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

    print("\n=== PowerShell tool, on feature/z")
    subprocess.run(["git", "-C", repo, "checkout", "-q", "-B", "feature/z"], check=True)
    set_optout(repo, False)
    for cmd, want, why in POWERSHELL_ON_FEATURE:
        for name, runner in runners:
            got = invoke(runner, cmd, repo, tool="PowerShell")
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {cmd}   ({why})")
    # An alias defined in the repo's own config, not on the command line.
    subprocess.run(["git", "-C", repo, "config", "alias.pp", "push"], check=True)
    for name, runner in runners:
        got = invoke(runner, "git pp origin main", repo)
        if got != BLOCK:
            failures += 1
            print(f"  FAIL want BLOCK got {got} ({name}) | git pp origin main   (configured alias for push)")
    subprocess.run(["git", "-C", repo, "config", "--unset", "alias.pp"], check=True)
    print(f"  {len(POWERSHELL_ON_FEATURE) + 1} cases checked")

    # Pushing a DIFFERENT repo than the session's project. The opt-out and the
    # checked-out branch belong to the repo being pushed: reading them from the
    # session project let a project with allowPushToMain push main of any
    # other repo through `git -C`, and a bare `git -C other push` resolved HEAD
    # in the wrong repository. Found pushing eight projects from a dotclaude
    # session.
    print("\n=== pushing another repo")
    session = make_repo()                       # the session's project...
    subprocess.run(["git", "-C", session, "checkout", "-q", "-B", "feature/s"], check=True)
    set_optout(session, True)                   # ...lives on main by choice
    other = make_repo()                         # target: on main, no opt-out
    # As typed into Git Bash on Windows: an unquoted backslash is an escape
    # there, so a real command spells C:/Users/..., never C:\Users\...
    other_sh = other.replace("\\", "/")
    cross = [
        (f"git -C {other_sh} push origin main", BLOCK, "session opt-out must not cover another repo"),
        (f"git -C {other_sh} push", BLOCK, "bare push resolves HEAD in the -C repo (main), not the session's"),
        (f"cd {other_sh} && git push", BLOCK, "cd into another repo, then a bare push"),
        (f"cd {other_sh} && git push origin feature/x", ALLOW, "feature branch in another repo"),
        (f"pushd {other_sh} && git push", BLOCK, "pushd into another repo, then a bare push"),
        ("git push", ALLOW, "the session repo itself is on a feature branch"),
    ]
    for cmd, want, why in cross:
        for name, runner in runners:
            got = invoke(runner, cmd, session)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {cmd}   ({why})")
    set_optout(session, False)
    set_optout(other, True)
    for cmd, want, why in ((f"git -C {other_sh} push origin main", ALLOW, "the target repo's own opt-out applies"),
                           (f"cd {other_sh}/.claude && git push origin main", ALLOW, "opt-out found from a subdirectory")):
        for name, runner in runners:
            got = invoke(runner, cmd, session)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {cmd}   ({why})")
    print(f"  {len(cross) + 2} cases checked")

    # The hook runs where the harness starts it, which need not be the
    # session's directory: the payload's cwd is where the command runs.
    print("\n=== payload cwd differs from the process cwd")
    set_optout(other, False)
    for name, runner in runners:
        got = invoke(runner, "git push", session, payload_cwd=other)
        if got != BLOCK:
            failures += 1
            print(f"  FAIL want BLOCK got {got} ({name}) | git push   (payload cwd is a repo on main)")
    print("  1 case checked")

    # A non-git directory must not hang or crash.
    nongit = tempfile.mkdtemp()
    print("\n=== outside a git repo")
    for cmd, want in (("git push", ALLOW), ("git push origin main", BLOCK), ("ls", ALLOW)):
        for name, runner in runners:
            got = invoke(runner, cmd, nongit)
            if got != want:
                failures += 1
                print(f"  FAIL want {want} got {got} ({name}) | {cmd}")
    print("  3 cases checked")
    for path in (repo, session, other, nongit):
        shutil.rmtree(path, ignore_errors=True)

    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        return 1
    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
