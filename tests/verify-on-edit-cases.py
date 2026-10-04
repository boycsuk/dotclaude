#!/usr/bin/env python3
"""Behavioural contract for verify-on-edit.py.

Run:  python3 tests/verify-on-edit-cases.py
      python3 tests/verify-on-edit-cases.py --pwsh PATH   # also through PowerShell

This hook runs the project's linter/typechecker after edits. It joined the
matrix club because its old .sh/.ps1 twins diverged in ways reading them did
not reveal (same story as guard-push-main and detect-secrets):

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

import atexit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402
from stubs import write_stub  # noqa: E402

FAIL, QUIET = "FAIL", "QUIET"          # FAIL = exit 2 (errors surfaced)


def build_fixture(kind):
    root = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, root, True)
    atexit.register(shutil.rmtree, root + "-other", True)
    bindir = os.path.join(root, "_bin")
    os.makedirs(bindir)
    if kind == "js-lint-fails":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm", "1 problem (1 error)\n", 1)
    elif kind == "js-lint-passes":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm")
    elif kind == "js-no-scripts":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write("{}")
        write_stub(bindir, "npm", code=1)
    elif kind == "js-lint-in-deps":
        # "lint"/"typecheck" appear only as dependency names: the old
        # whole-file grep matched them and ran scripts that do not exist.
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"dependencies": {"lint": "1.0.0", "typecheck": "2.0.0"}}')
        write_stub(bindir, "npm", "Missing script\n", 1)
    elif kind == "js-no-npm":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        # no npm stub: PATH holds no npm at all
    elif kind == "js-hanging-lint":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        write_stub(bindir, "npm", code=1, sleep=30)
    elif kind == "py-no-tools":
        with open(os.path.join(root, "pyproject.toml"), "w") as fh:
            fh.write("[tool.ruff]\n")
        # no ruff/mypy stubs on PATH
    elif kind == "py-ruff-fails":
        # A Windows path in linter output: printf %b once read `\c` as "stop
        # output here" and dropped everything after it.
        with open(os.path.join(root, "pyproject.toml"), "w") as fh:
            fh.write("[tool.ruff]\n")
        write_stub(bindir, "ruff", 'error in "C:\\code\\x.py"\nTAIL-MARKER\n', 1)
    elif kind == "py-mypy-fails":
        with open(os.path.join(root, "pyproject.toml"), "w") as fh:
            fh.write("[tool.mypy]\n")
        write_stub(bindir, "mypy", "error: Incompatible types\n", 1)
    elif kind == "js-typecheck-fails":
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"typecheck": "x"}}')
        write_stub(bindir, "npm", "TS2322\n", 1)
    elif kind == "js-pnpm-project":
        # The lockfile picks the runner: pnpm fails, npm would pass.
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        open(os.path.join(root, "pnpm-lock.yaml"), "w").close()
        write_stub(bindir, "npm")
        write_stub(bindir, "pnpm", "1 problem\n", 1)
    elif kind == "rs-clippy-fails":
        open(os.path.join(root, "Cargo.toml"), "w").close()
        write_stub(bindir, "cargo", "warning: unused\n", 1)
    elif kind == "go-vet-fails":
        open(os.path.join(root, "go.mod"), "w").close()
        write_stub(bindir, "go", "vet: unreachable code\n", 1)
    elif kind == "js-lint-floods":
        # A project with existing lint debt: every edit used to re-inject the
        # whole report, and the edited file's own error came last.
        with open(os.path.join(root, "package.json"), "w") as fh:
            fh.write('{"scripts": {"lint": "x"}}')
        flood = "".join(f"src/old{i}.ts: 1:1 error no-unused-vars\n" for i in range(120))
        write_stub(bindir, "npm", flood + "src/app.ts: 3:1 error EDITED-FILE-MARKER\n", 1)
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
    # The Python hook bounds each check with its own subprocess timeout, so this
    # holds on every OS; the .sh twin needed a `timeout` binary stock macOS lacks.
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
    ("ruff failure surfaces", "py-ruff-fails", "src/app.py", FAIL, "the Python lint branch"),
    ("mypy failure surfaces", "py-mypy-fails", "src/app.py", FAIL, "the Python type branch"),
    ("typecheck script failure surfaces", "js-typecheck-fails", "src/app.ts", FAIL,
     "the typecheck script, not only lint"),
    ("the lockfile's runner is used", "js-pnpm-project", "src/app.ts", FAIL,
     "pnpm-lock.yaml selects pnpm; npm would have passed"),
    ("clippy failure surfaces", "rs-clippy-fails", "src/main.rs", FAIL, "the Rust branch"),
    ("go vet failure surfaces", "go-vet-fails", "main.go", FAIL, "the Go branch"),
]


def invoke(runner, root, bindir, file_path, stderr=None):
    env = dict(CLAUDE_PROJECT_DIR=root,
               # Only the stubs: the machine's own npm/ruff would otherwise answer
               # and the "binary missing" cases would test nothing. The hook and
               # the stubs run on absolute interpreter paths, so nothing else is needed.
               PATH=bindir,
               VERIFY_TIMEOUT="2")
    payload = pyhook.payload("Edit", pyhook.edit_input(file_path, "x"), event="PostToolUse")
    code, out, err = pyhook.run("verify-on-edit", payload, cwd=root, env=env, pwsh=runner)
    if stderr is not None:
        stderr.append(err)
    got = pyhook.verdict(code, out, err, feedback=True)
    return {"feedback": FAIL, "quiet": QUIET}.get(got, got)


def main():
    args = pyhook.cli()
    runners = pyhook.runners(args.pwsh)

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
        results = {rname: invoke(runner, root, bindir, file_path) for rname, runner in runners}
        # `want` is a dict when the two runners legitimately differ, the way
        # guard-central-config-cases.py expresses platform-dependent verdicts.
        bad = any(got != (want[n] if isinstance(want, dict) else want)
                  for n, got in results.items())
        if bad:
            failures += 1
            detail = ", ".join(f"{n}={g}" for n, g in results.items())
            print(f"  FAIL want {want} got {detail} | {name}   ({why})")

    # The whole linter report must reach Claude, backslashes and all.
    root, bindir = build_fixture("py-ruff-fails")
    target = os.path.join(root, "app.py")
    open(target, "w").close()
    for rname, runner in runners:
        err = []
        invoke(runner, root, bindir, target, err)
        if "TAIL-MARKER" not in err[0]:
            failures += 1
            print(f"  FAIL ({rname}) linter output was cut at a backslash: {err[0][-200:]!r}")

    # A flood is capped, keeps the edited file's lines, says it was cut, and
    # labels the check as whole-project so Claude does not chase other files.
    root, bindir = build_fixture("js-lint-floods")
    target = os.path.join(root, "src", "app.ts")
    os.makedirs(os.path.dirname(target))
    open(target, "w").close()
    for rname, runner in runners:
        err = []
        invoke(runner, root, bindir, target, err)
        text = err[0]
        problems = [p for p, bad in (
            ("over 60 lines", text.count("\n") > 60),
            ("the edited file's error is missing", "EDITED-FILE-MARKER" not in text),
            ("no note that output was cut", "/verify" not in text),
            ("not labelled whole-project", "whole project" not in text)) if bad]
        if problems:
            failures += 1
            print(f"  FAIL ({rname}) flood: {', '.join(problems)}")
    # A per-file check is labelled as such.
    root, bindir = build_fixture("py-ruff-fails")
    target = os.path.join(root, "app.py")
    open(target, "w").close()
    for rname, runner in runners:
        err = []
        invoke(runner, root, bindir, target, err)
        if "this file" not in err[0] or "whole project" in err[0]:
            failures += 1
            print(f"  FAIL ({rname}) ruff must be labelled as checking this file: {err[0][:200]!r}")

    return pyhook.finish("verify-on-edit", failures, len(CASES) + 3, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
