#!/usr/bin/env python3
"""Behavioural contract for changelog-reminder.py.

Run:  python3 tests/changelog-reminder-cases.py
      python3 tests/changelog-reminder-cases.py --pwsh PATH   # also through PowerShell

The hook is ADVISORY: it must emit `systemMessage` and exit 0, and must never
emit `decision` or exit 2. On Stop, `decision: "block"`, exit 2 AND
`hookSpecificOutput.additionalContext` all continue the conversation — the docs
give additionalContext "the same loop protections as decision: block". A Stop
hook fires on every turn and cannot tell a finished task from a half-done one,
so a hook that resumes the turn interrupts legitimate work. That distinction is
invisible to a test that only asserts "something was printed", which is how
three advisory hooks sat inert on the dead stderr channel for months.

Each case builds a throwaway git repo, pipes one Stop payload through the hook,
and asserts on the parsed stdout.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402



def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False)


def make_repo(tmp, files, changelog=True, commit_first=True):
    git(tmp, "init", "-q")
    git(tmp, "config", "user.email", "t@t.t")
    git(tmp, "config", "user.name", "t")
    if changelog:
        with open(os.path.join(tmp, "CHANGELOG.md"), "w") as fh:
            fh.write("# Changelog\n")
    if commit_first:
        git(tmp, "add", "-A")
        git(tmp, "commit", "-qm", "init")
    for name, body in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True) if "/" in name else None
        with open(path, "w") as fh:
            fh.write(body)
    return tmp


def run_hook(repo, pwsh=None, stop_hook_active=False, session_cwd=None, session=None):
    payload = json.dumps({
        "cwd": session_cwd or repo,
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        # A fresh session per call unless a case shares one: the notice
        # speaks once per change set within a session.
        "session_id": session or uuid.uuid4().hex,
        "last_assistant_message": "done",
    })
    cmd = pyhook.argv("changelog-reminder", pwsh)
    p = subprocess.run(cmd, input=payload, capture_output=True, text=True, cwd=repo)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def parse(out):
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return "UNPARSEABLE"


def expect_silent(repo, pwsh, why, **kw):
    rc, out, _ = run_hook(repo, pwsh, **kw)
    if rc != 0:
        return f"{why}: exited {rc}, must always exit 0"
    if out:
        return f"{why}: spoke when it should stay silent — {out[:120]}"
    return None


def expect_message(repo, pwsh, why, must_mention=None, **kw):
    rc, out, _ = run_hook(repo, pwsh, **kw)
    if rc != 0:
        return f"{why}: exited {rc}, must always exit 0"
    data = parse(out)
    if data is None:
        return f"{why}: said nothing when it should warn"
    if data == "UNPARSEABLE":
        return f"{why}: stdout is not valid JSON — {out[:120]}"
    if "systemMessage" not in data:
        return f"{why}: no systemMessage key — {out[:120]}"
    # The whole point: advisory, never resuming the turn.
    if "decision" in data:
        return f"{why}: emitted a `decision` field — that blocks the turn"
    if "hookSpecificOutput" in data:
        return (f"{why}: emitted hookSpecificOutput — additionalContext on Stop "
                f"continues the conversation, which this hook must never do")
    if must_mention and must_mention not in data["systemMessage"]:
        return f"{why}: message never mentions {must_mention!r} — {data['systemMessage'][:120]}"
    return None


def case_code_without_changelog(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    return expect_message(repo, pwsh, "code changed, CHANGELOG untouched",
                          must_mention="app.py")


def case_session_in_subdirectory(tmp, pwsh):
    # The session's cwd is a subdirectory while the process starts at the
    # root: the CHANGELOG lookup used the cwd and stayed silent.
    repo = make_repo(tmp, {"src/app.py": "x = 1\n"})
    return expect_message(repo, pwsh, "session in src/, code changed",
                          must_mention="src", session_cwd=os.path.join(repo, "src"))


def case_changelog_updated(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n", "CHANGELOG.md": "# Changelog\n- x\n"})
    return expect_silent(repo, pwsh, "CHANGELOG was updated alongside the code")


def case_docs_only(tmp, pwsh):
    repo = make_repo(tmp, {"README.md": "hi\n", "notes.txt": "n\n"})
    return expect_silent(repo, pwsh, "only docs changed")


def case_clean_tree(tmp, pwsh):
    repo = make_repo(tmp, {})
    return expect_silent(repo, pwsh, "nothing changed at all")


def case_no_changelog_file(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n"}, changelog=False)
    return expect_silent(repo, pwsh, "repo keeps no CHANGELOG.md")


def case_not_a_repo(tmp, pwsh):
    with open(os.path.join(tmp, "CHANGELOG.md"), "w") as fh:
        fh.write("# Changelog\n")
    with open(os.path.join(tmp, "app.py"), "w") as fh:
        fh.write("x = 1\n")
    return expect_silent(tmp, pwsh, "not a git repo")


def case_stop_hook_active(tmp, pwsh):
    """Already continuing because of a stop hook: never pile on."""
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    return expect_silent(repo, pwsh, "stop_hook_active is true",
                         stop_hook_active=True)


def case_untracked_code(tmp, pwsh):
    """An untracked new file is still a code change."""
    repo = make_repo(tmp, {"newmod.py": "y = 2\n"})
    return expect_message(repo, pwsh, "untracked code file", must_mention="newmod.py")


def case_lockfile_only(tmp, pwsh):
    repo = make_repo(tmp, {"package-lock.json": "{}\n", "poetry.lock": "x\n"})
    return expect_silent(repo, pwsh, "only lockfiles/config changed")


def case_missing_cwd(tmp, pwsh):
    """A payload without cwd must not crash or warn about the wrong repo."""
    cmd = pyhook.argv("changelog-reminder", pwsh)
    p = subprocess.run(cmd, input='{"hook_event_name":"Stop"}',
                       capture_output=True, text=True, cwd=tmp)
    if p.returncode != 0:
        return f"payload without cwd: exited {p.returncode}, must exit 0"
    return None


def case_once_per_change_set(tmp, pwsh):
    """The same changed files at the next turn end say nothing; a new one speaks again."""
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    session = uuid.uuid4().hex
    problem = (expect_message(repo, pwsh, "first turn end", must_mention="/commit", session=session)
               or expect_silent(repo, pwsh, "same change set, next turn end", session=session))
    if problem:
        return problem
    with open(os.path.join(repo, "other.py"), "w") as fh:
        fh.write("y = 2\n")
    return expect_message(repo, pwsh, "a new changed file", must_mention="2 changed", session=session)


def case_garbage_input(tmp, pwsh):
    cmd = pyhook.argv("changelog-reminder", pwsh)
    p = subprocess.run(cmd, input="not json at all", capture_output=True,
                       text=True, cwd=tmp)
    if p.returncode != 0:
        return f"garbage stdin: exited {p.returncode}, must exit 0"
    return None


CASES = [
    ("code changed without CHANGELOG warns", case_code_without_changelog),
    ("CHANGELOG updated stays silent", case_changelog_updated),
    ("docs-only change stays silent", case_docs_only),
    ("clean tree stays silent", case_clean_tree),
    ("repo without CHANGELOG.md stays silent", case_no_changelog_file),
    ("non-git directory stays silent", case_not_a_repo),
    ("stop_hook_active stays silent", case_stop_hook_active),
    ("untracked code file warns", case_untracked_code),
    ("lockfile-only change stays silent", case_lockfile_only),
    ("payload without cwd exits cleanly", case_missing_cwd),
    ("a session in a subdirectory still warns", case_session_in_subdirectory),
    ("garbage stdin exits cleanly", case_garbage_input),
    ("speaks once per change set in a session", case_once_per_change_set),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()

    targets = [(None, "py")]
    if args.pwsh:
        targets.append((args.pwsh, "ps1"))

    total = bad = 0
    for pwsh, label in targets:
        for name, fn in CASES:
            tmp = tempfile.mkdtemp(prefix="changelog-case-")
            try:
                problem = fn(tmp, pwsh)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            total += 1
            if problem:
                bad += 1
            status = "ok  " if problem is None else "BAD "
            print(f"  {status}[{label}] {name}" + (f" — {problem}" if problem else ""))

    suffix = "" if args.pwsh else " — python only (pass --pwsh for the Windows form)"
    print(f"\nchangelog-reminder: {total - bad} ok, {bad} bad{suffix}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
