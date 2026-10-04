#!/usr/bin/env python3
"""Behavioural contract for read-before-write.py.

Run:  python3 tests/read-before-write-cases.py
      python3 tests/read-before-write-cases.py --pwsh PATH   # PowerShell command form too

When Claude creates a new code file in a folder it has not read or edited this
session, the hook names 2-3 siblings to read and align the file with. It is
advisory: additionalContext on stdout, exit 0, never a decision. The controls
matter as much as the catches: a note on every write, or on a folder already
read, teaches the model to skip it.
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

prompt, call, transcript = pyhook.transcript_prompt, pyhook.transcript_call, pyhook.write_transcript
NOTE, QUIET = "NOTE", "QUIET"


def project(tmp, files):
    root = os.path.join(tmp, "proj")
    for rel in files:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x = 1\n")
        time.sleep(0.01)                     # distinct mtimes: newest siblings come first
    os.makedirs(root, exist_ok=True)
    return root


def run(pwsh, root, tmp, target, entries=None, tool="Write", session=None, agent=None, agent_entries=None):
    path = transcript(tmp, [prompt("go")] + (entries or [])) if entries is not None else None
    if agent and agent_entries is not None:
        folder = os.path.join(tmp, "session", "subagents")
        os.makedirs(folder, exist_ok=True)
        transcript(folder, agent_entries, name=f"agent-{agent}.jsonl")
    tool_input = {"file_path": os.path.join(root, target), "content": "y = 2\n"}
    extra = {"cwd": root}
    if path:
        extra["transcript_path"] = path
    if session:
        extra["session_id"] = session
    if agent:
        extra.update(agent_id=agent, agent_type="general-purpose")
    payload = pyhook.payload(tool, tool_input, **extra)
    code, out, err = pyhook.run("read-before-write", payload, cwd=root, pwsh=pwsh)
    verdict = pyhook.verdict(code, out, err)
    if verdict.startswith(("CRASH", "TIMEOUT")):
        return verdict, ""
    if pyhook.decision(out) != "allow":
        return f"DECISION {pyhook.decision(out)}", ""
    ctx, event = pyhook.context(out)
    if ctx and event != "PreToolUse":
        return f"wrong hookEventName {event}", ""
    return (NOTE if ctx else QUIET), ctx or ""


def read(root, rel):
    return call("Read", file_path=os.path.join(root, rel))


# (label, files on disk, new file, transcript entries (callable root -> list) or None, expected, must name, must not name)
CASES = [
    ("a new file in an unread folder names its siblings", ["src/a.py", "src/b.py"], "src/new.py",
     lambda r: [], NOTE, ["a.py", "b.py"], []),
    ("a folder read this session: silent", ["src/a.py", "src/b.py"], "src/new.py",
     lambda r: [read(r, "src/a.py")], QUIET, [], []),
    ("a folder edited this session: silent", ["src/a.py", "src/b.py"], "src/new.py",
     lambda r: [call("Edit", file_path=os.path.join(r, "src", "b.py"), old_string="x", new_string="z")], QUIET, [], []),
    ("a read in ANOTHER folder does not count", ["src/a.py", "lib/c.py"], "src/new.py",
     lambda r: [read(r, "lib/c.py")], NOTE, ["a.py"], ["c.py"]),
    ("writing an existing file: silent", ["src/a.py", "src/b.py"], "src/a.py", lambda r: [], QUIET, [], []),
    ("a new README is not code", ["src/a.py"], "src/README.md", lambda r: [], QUIET, [], []),
    ("a new config file is not code", ["src/a.py"], "src/settings.json", lambda r: [], QUIET, [], []),
    ("an empty new folder borrows the parent's siblings", ["src/a.py", "src/b.py"], "src/feature/x.py",
     lambda r: [], NOTE, ["a.py"], []),
    ("empty folder and empty parent: silent", ["other/z.py"], "src/feature/x.py", lambda r: [], QUIET, [], []),
    ("siblings prefer the same extension", ["web/styles.css", "web/app.ts", "web/util.ts"], "web/new.ts",
     lambda r: [], NOTE, ["app.ts", "util.ts"], ["styles.css"]),
    ("no transcript: advisory note, no crash", ["src/a.py"], "src/new.py", None, NOTE, ["a.py"], []),
]


def main():
    args = pyhook.cli()
    failures = total = 0
    for name, pwsh in pyhook.runners(args.pwsh):
        for label, files, target, entries, want, must, must_not in CASES:
            total += 1
            tmp = tempfile.mkdtemp(prefix="rbw-")
            try:
                root = project(tmp, files)
                got, ctx = run(pwsh, root, tmp, target, entries(root) if entries else None)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            problems = [] if got == want else [f"want {want} got {got}"]
            problems += [f"does not name {m}" for m in must if m not in ctx]
            problems += [f"names {m}" for m in must_not if m in ctx]
            if problems:
                failures += 1
                print(f"  FAIL [{name}] {label}: {'; '.join(problems)} {ctx[:160]!r}")

        # Once per folder per session.
        total += 1
        tmp = tempfile.mkdtemp(prefix="rbw-")
        try:
            root = project(tmp, ["src/a.py"])
            session = "rbw-" + os.path.basename(tmp)
            first, _ = run(pwsh, root, tmp, "src/one.py", [], session=session)
            second, _ = run(pwsh, root, tmp, "src/two.py", [], session=session)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if (first, second) != (NOTE, QUIET):
            failures += 1
            print(f"  FAIL [{name}] once per folder per session: got {first}, {second}")

        # A subagent's own reads count for its writes.
        total += 1
        tmp = tempfile.mkdtemp(prefix="rbw-")
        try:
            root = project(tmp, ["src/a.py"])
            got, ctx = run(pwsh, root, tmp, "src/new.py", [], agent="a1", agent_entries=[read(root, "src/a.py")])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if got != QUIET:
            failures += 1
            print(f"  FAIL [{name}] a subagent that read the folder: got {got} {ctx[:120]!r}")

        # Windows separators in the path resolve the same folder.
        total += 1
        tmp = tempfile.mkdtemp(prefix="rbw-")
        try:
            root = project(tmp, ["src/a.py"])
            entries = [call("Read", file_path=os.path.join(root, "src", "a.py").replace("/", "\\"))]
            got, ctx = run(pwsh, root, tmp, "src/new.py", entries) if os.name == "nt" else (QUIET, "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if got != QUIET:
            failures += 1
            print(f"  FAIL [{name}] a read spelled with backslashes: got {got}")
    return pyhook.finish("read-before-write", failures, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
