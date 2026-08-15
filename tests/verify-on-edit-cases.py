#!/usr/bin/env python3
"""Behavioural contract for verify-on-edit.{sh,ps1}.

Run:  python3 tests/verify-on-edit-cases.py
      python3 tests/verify-on-edit-cases.py --pwsh PATH   # verify parity

This hook runs the project's linter/typechecker after edits. It joined the
matrix club because its siblings diverged in ways reading them did not reveal
(same story as guard-push-main and detect-secrets, DESIGN.md §26):

  - The .ps1 accepted sibling directories sharing a prefix (root C:\\proj also
    matched C:\\proj-other\\x.ts) where the .sh required a separator.
  - A check exceeding the internal timeout was reported as a LINT FAILURE,
    so Claude tried to "fix" errors that do not exist — cry-wolf.
  - The JS branch called npm without checking it exists; every other branch
    guards its binary.

Each case builds a throwaway project fixture and pipes real hook JSON through
both scripts. Binaries are stubbed via a PATH prefix dir so the cases are
hermetic; VERIFY_TIMEOUT shrinks the per-check budget so the timeout case
does not take 15 real seconds.
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "global/.claude/hooks/verify-on-edit.sh")
PS1 = os.path.join(REPO, "global/.claude/hooks/verify-on-edit.ps1")

FAIL, QUIET = "FAIL", "QUIET"          # FAIL = exit 2 (errors surfaced)


def write_stub(bindir, name, body):
    """A fake binary on PATH. Body is POSIX sh; a .cmd twin covers Windows."""
    path = os.path.join(bindir, name)
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def build_fixture(kind):
    root = tempfile.mkdtemp()
    bindir = os.path.join(root, "_bin")
    os.makedirs(bindir)
    if kind == "js-lint-fails":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm", 'echo "1 problem (1 error)"; exit 1')
    elif kind == "js-lint-passes":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm", "exit 0")
    elif kind == "js-no-scripts":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write("{}")
        write_stub(bindir, "npm", "exit 1")
    elif kind == "js-lint-in-deps":
        # "lint"/"typecheck" appear only as dependency names: the old
        # whole-file grep matched them and ran scripts that do not exist.
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"dependencies": {"lint": "1.0.0", "typecheck": "2.0.0"}}')
        write_stub(bindir, "npm", 'echo "Missing script"; exit 1')
    elif kind == "js-no-npm":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        # no npm stub: PATH holds no npm at all
    elif kind == "js-hanging-lint":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm", "sleep 30; exit 1")
    elif kind == "py-no-tools":
        with open(os.path.join(root, "pyproject.toml"), "w") as fh:
            fh.write("[tool.ruff]\n")
        # no ruff/mypy stubs on PATH
    elif kind == "empty":
        pass
    return root, bindir


# (case_name, fixture_kind, rel_file_path_or_ABS, expected, why)
CASES = [
    ("failing lint surfaces", "js-lint-fails", "src/app.ts", FAIL,
     "a real lint failure must reach Claude"),
    ("passing lint is silent", "js-lint-passes", "src/app.ts", QUIET,
     "nothing to report"),
    ("no scripts, no run", "js-no-scripts", "src/app.ts", QUIET,
     "package.json without typecheck/lint scripts"),
    ("script names in deps only", "js-lint-in-deps", "src/app.ts", QUIET,
     "'lint' as a dependency is not a script — pseudo-failure otherwise"),
    ("npm missing is not an error", "js-no-npm", "src/app.ts", QUIET,
     "bun/pnpm-only environments: every other branch guards its binary"),
    ("hanging check is skipped, not reported", "js-hanging-lint", "src/app.ts", QUIET,
     "a timeout is the budget's fault, not the code's — cry-wolf otherwise"),
    ("mts triggers the JS branch", "js-lint-fails", "src/app.mts", FAIL,
     "TS 4.7 module extension"),
    ("pyi triggers the Python branch", "py-no-tools", "src/stubs.pyi", QUIET,
     "stub files are checkable; here no tools installed, so quiet"),
    ("file outside the project", "js-lint-fails", "/elsewhere/app.ts", QUIET,
     "edits outside CLAUDE_PROJECT_DIR are not ours to check"),
    ("sibling dir sharing a prefix", "js-lint-fails", "SIBLING", QUIET,
     "root /x must not match /x-other — the .ps1 once did"),
    ("unknown extension", "empty", "notes.txt", QUIET, "no stack, no checks"),
]


_SYSPATH = None


def syspath():
    """A dir of symlinks to the tools the hooks themselves need — and nothing
    else. Prepending the real PATH would leak the machine's npm/ruff into the
    fixtures and the 'binary missing' cases would silently test nothing."""
    global _SYSPATH
    if _SYSPATH is None:
        _SYSPATH = tempfile.mkdtemp(prefix="verify-syspath-")
        for tool in ("bash", "sh", "python3", "timeout", "grep", "sleep", "cat", "env"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, os.path.join(_SYSPATH, tool))
    return _SYSPATH


def invoke(runner, root, bindir, file_path):
    env = dict(os.environ,
               CLAUDE_PROJECT_DIR=root,
               PATH=bindir + os.pathsep + syspath(),
               VERIFY_TIMEOUT="2")
    payload = {"tool_input": {"file_path": file_path}}
    proc = subprocess.run(runner, input=json.dumps(payload),
                          capture_output=True, text=True, timeout=60,
                          cwd=root, env=env)
    return FAIL if proc.returncode == 2 else QUIET


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify .sh/.ps1 parity")
    args = ap.parse_args()

    runners = [("sh", ["bash", SH])]
    if args.pwsh:
        runners.append(("ps1", [args.pwsh, "-NoProfile", "-File", PS1]))

    failures = 0
    for name, kind, rel, want, why in CASES:
        root, bindir = build_fixture(kind)
        if rel == "SIBLING":
            sibling = root + "-other"
            os.makedirs(os.path.join(sibling, "src"), exist_ok=True)
            file_path = os.path.join(sibling, "src", "app.ts")
        elif os.path.isabs(rel):
            file_path = rel
        else:
            file_path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(file_path) or root, exist_ok=True)
            with open(file_path, "w") as fh:
                fh.write("// x\n")
        results = {}
        for rname, runner in runners:
            try:
                results[rname] = invoke(runner, root, bindir, file_path)
            except subprocess.TimeoutExpired:
                results[rname] = "TIMEOUT"
        if any(got != want for got in results.values()):
            failures += 1
            detail = ", ".join(f"{n}={g}" for n, g in results.items())
            print(f"  FAIL want {want} got {detail} | {name}   ({why})")

    print(f"\n{len(CASES)} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "bash + powershell" if args.pwsh else "bash only (pass --pwsh for parity)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
