# hook-kind: notice
"""Stop hook: say so when a turn ends with code changed but CHANGELOG.md untouched.

ADVISORY BY CONSTRUCTION. It emits `systemMessage` and exits 0, never
`decision: "block"`, exit 2 or `additionalContext` — on Stop all three CONTINUE
the conversation, and a Stop hook cannot tell a finished task from a half-done
one (it fires on every turn), so anything that resumes the turn would interrupt
legitimate mid-task work. Being advisory makes stop_hook_active moot; it is
still honoured so a future blocking path cannot forget it.

A repo without CHANGELOG.md has not opted into keeping one, and docs, config
and lockfiles are not the "code changed" this is about: saying so anyway would
cry wolf and teach the model to ignore the reminder.
"""

import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

GIT_TIMEOUT = 2          # an unbounded git on a huge or locked repo would sit in the turn-end path
NOT_CODE = re.compile(r"\.(md|txt|lock|json|ya?ml|toml|cfg|ini)$|(^|/)(CHANGELOG|README|LICENSE)")


def git(cwd, *argv):
    try:
        out = subprocess.run(["git"] + list(argv), cwd=cwd, capture_output=True, text=True,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def changed_paths(top):
    """Paths in `git status --porcelain`, relative to the repo root."""
    paths = []
    for line in (git(top, "status", "--porcelain") or "").splitlines():
        path = line[3:].strip()
        if " -> " in path:                       # a rename: the new name is the change
            path = path.split(" -> ", 1)[1]
        if path:
            paths.append(path.strip('"'))
    return paths


def main():
    payload = hookio.read_payload()
    if payload.get("stop_hook_active"):
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if not os.path.isdir(cwd):
        return 0
    top = (git(cwd, "rev-parse", "--show-toplevel") or "").strip()
    # Looked up at the repo root: a session in a subdirectory once stayed silent.
    if not top or not os.path.isfile(os.path.join(top, "CHANGELOG.md")):
        return 0
    changed = changed_paths(top)
    if not changed or "CHANGELOG.md" in changed:
        return 0
    code = [p for p in changed if not NOT_CODE.search(p)]
    if not code:
        return 0
    hookio.notice(f"CHANGELOG.md not updated — {len(code)} changed file(s): {' '.join(code[:3])} "
                  "(A task is done only when it compiles, passes tests, and is logged in CHANGELOG.md.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
