# hook-kind: notice
"""Stop hook: at the end of a turn, tell the user what the turn left undone, in one line.

Three reminders, each turning a prose rule into a notice:
  - code changed but CHANGELOG.md untouched (a repo without CHANGELOG.md has
    not opted into keeping one);
  - code edited this turn with no test command run after the last edit, in a
    repo that has a test setup (`/verify` and a subagent's test run count);
  - WebSearch or WebFetch used this turn and the reply cites no `Sources:`.

ADVISORY BY CONSTRUCTION. It emits `systemMessage`, which the user sees, and
exits 0, never `decision: "block"`, exit 2 or `additionalContext`: on Stop all
three CONTINUE the conversation, and a Stop hook cannot tell a finished task
from a half-done one (it fires on every turn), so anything that resumes the
turn would interrupt legitimate mid-task work. stop_hook_active is still
honoured so a future blocking path cannot forget it.

Docs, config and lockfiles are not the "code" this is about, and a reminder
repeats only for a new set of files in a session: crying wolf teaches the
reader to ignore it. The turn is read from the session transcript, an internal
format with no stability promise, so every read tolerates missing keys and
odd lines and falls back to saying nothing. Only its last ~2 MB are read.
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import shellwords  # noqa: E402
from transcript import last_turn, subagents_dir, tail_entries, tool_calls  # noqa: E402

GIT_TIMEOUT = 2          # an unbounded git on a huge or locked repo would sit in the turn-end path
NOT_CODE = re.compile(r"\.(md|txt|lock|json|ya?ml|toml|cfg|ini)$|(^|/)(CHANGELOG|README|LICENSE)")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
WEB_TOOLS = ("WebSearch", "WebFetch")
SOURCES = re.compile(r"^[\s>#*_-]*sources\s*[*_]*\s*:", re.I | re.M)
RUNNERS = {"pytest", "py.test", "tox", "nox", "vitest", "jest", "rspec", "phpunit", "nextest"}
REPO_CHECKS = re.compile(r"(^|/)(run-matrices\.py|[\w.-]+-cases\.py|check\.py|check-selftest\.sh)$")


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


def changelog_finding(payload, top):
    if not top or not os.path.isfile(os.path.join(top, "CHANGELOG.md")):
        return None
    changed = changed_paths(top)
    if not changed or "CHANGELOG.md" in changed:
        return None
    code = [p for p in changed if not NOT_CODE.search(p)]
    if not code or not hookio.first_time(payload, top + "\0" + "\0".join(sorted(code))):
        return None
    return f"CHANGELOG.md not updated — {len(code)} changed file(s): {' '.join(code[:3])}. /commit drafts the entry"


def runs_tests(command, shell="bash"):
    """True when a shell command runs a known test runner or this repo's checks."""
    for seg in shellwords.segments(command, shell) or []:
        words = shellwords.unwrap(seg)
        if not words:
            continue
        name, args = shellwords.basename(words[0]).lower(), words[1:]
        if name in ("npx", "bunx") or (name == "pnpm" and args[:1] == ["dlx"]):
            args = args[1:] if name == "pnpm" else args
            name, args = (shellwords.basename(args[0]).lower(), args[1:]) if args else ("", [])
        first = args[0] if args else ""
        if name in RUNNERS:
            return True
        if re.fullmatch(r"python[0-9.]*|py", name):
            if args[:1] == ["-m"] and args[1:2] and args[1] in ("pytest", "unittest", "tox", "nox"):
                return True
            if any(REPO_CHECKS.search(a.replace("\\", "/")) for a in args[:1]):
                return True
        if name in ("bash", "sh") and any(REPO_CHECKS.search(a.replace("\\", "/")) for a in args[:1]):
            return True
        if name in ("npm", "pnpm", "yarn", "bun") and (first in ("test", "t") or
                                                       (first == "run" and args[1:2] and args[1].startswith("test"))):
            return True
        if (name == "cargo" and first in ("test", "nextest")) or (name in ("go", "dotnet") and first == "test"):
            return True
        if name == "make" and any(a in ("test", "check") for a in args):
            return True
        if name in ("mvn", "mvnw") and any(a in ("test", "verify") for a in args):
            return True
        if name in ("gradle", "gradlew") and any(a in ("test", "check") for a in args):
            return True
        if name == "bundle" and args[:2] == ["exec", "rspec"]:
            return True
    return False


def ran_tests(calls):
    for name, inp, _ in calls:
        if name in ("Bash", "PowerShell") and isinstance(inp.get("command"), str):
            if runs_tests(inp["command"], "powershell" if name == "PowerShell" else "bash"):
                return True
        if name == "Skill" and str(inp.get("skill", "")).split(":")[-1] == "verify":
            return True
    return False


def epoch(timestamp):
    try:
        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def subagent_ran_tests(transcript_path, since):
    """True when a subagent transcript written after `since` (epoch seconds) ran tests."""
    folder = subagents_dir(transcript_path)
    if since is None or not folder:
        return False
    for path in glob.glob(os.path.join(folder, "agent-*.jsonl")):
        try:
            if os.path.getmtime(path) <= since:
                continue
        except OSError:
            continue
        if ran_tests(tool_calls(tail_entries(path))):
            return True
    return False


def has_test_setup(root):
    exists = lambda *p: os.path.exists(os.path.join(root, *p))  # noqa: E731
    if any(exists(f) for f in ("Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
                               "pytest.ini", "tox.ini", "noxfile.py")) or exists("tests") or exists("test"):
        return True
    for name, marker in (("pyproject.toml", "[tool.pytest"), ("setup.cfg", "[tool:pytest]"), ("Makefile", "\ntest:")):
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                if marker in "\n" + fh.read():
                    return True
        except OSError:
            pass
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8-sig") as fh:
            test = (json.load(fh).get("scripts") or {}).get("test", "")
        return bool(test) and "no test specified" not in test
    except (OSError, ValueError, AttributeError):
        return False


def tests_finding(payload, root, calls):
    edits = [(i, str(inp.get("file_path") or inp.get("notebook_path") or ""), ts)
             for i, (name, inp, ts) in enumerate(calls) if name in EDIT_TOOLS]
    edits = [(i, path, ts) for i, path, ts in edits if path and not NOT_CODE.search(path.replace("\\", "/"))]
    if not edits or not has_test_setup(root):
        return None
    last, _, last_ts = edits[-1]
    if ran_tests(calls[last + 1:]) or subagent_ran_tests(str(payload.get("transcript_path") or ""), epoch(last_ts)):
        return None
    files = sorted({os.path.basename(path) for _, path, _ in edits})
    if not hookio.first_time(payload, "tests\0" + "\0".join(sorted({p for _, p, _ in edits}))):
        return None
    return f"{len(files)} code file(s) edited with no test run after the last edit: {' '.join(files[:3])}. Run the tests (or /verify)"


def sources_finding(payload, calls):
    if not any(name in WEB_TOOLS for name, _, _ in calls):
        return None
    reply = payload.get("last_assistant_message")
    if isinstance(reply, str) and SOURCES.search(reply):
        return None
    return "the reply used web research but cites no sources (a Sources: section with links)"


def main():
    payload = hookio.read_payload()
    if payload.get("stop_hook_active"):
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if not os.path.isdir(cwd):
        return 0
    # Looked up at the repo root: a session in a subdirectory once stayed silent.
    top = (git(cwd, "rev-parse", "--show-toplevel") or "").strip()
    calls = tool_calls(last_turn(tail_entries(payload.get("transcript_path"))))
    findings = [f for f in (changelog_finding(payload, top),
                            tests_finding(payload, top or cwd, calls),
                            sources_finding(payload, calls)) if f]
    if findings:
        hookio.notice(" · ".join(findings) + ".")
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
