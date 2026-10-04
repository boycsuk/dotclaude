#!/usr/bin/env python3
"""Prove every hook matrix can fail: run it against a hook that does nothing.

Run:  python3 tests/vacuity-check.py [hook ...]

A matrix that still passes when its hook is replaced by a no-op tests
nothing. That happens silently: a refactor of the harness, a fixture that
bypasses the hook, a helper that swallows the result. For each hook (or the
ones named), this copies the tracked repo to a scratch folder, replaces the
hook with a stub that reads its input and exits 0 without a word, and runs
every matrix that names the hook there. At least one of them must FAIL; a
matrix that only mentions the hook in passing (an installer test that runs
it once to prove it is wired) may pass, and is listed as incidental.

A silent exit 0 is the wrong answer for every hook kind: a guard should deny
or ask, an advisory hook add context, a feedback hook exit 2, a rewrite hook
return updatedInput, a notice print a systemMessage, the status line print a
line. Slower than a matrix (one repo copy per hook), so it is run after a
change to the harness or a matrix, not on every commit.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "global", ".claude", "hooks")
STUB = "import sys\nsys.stdin.read()\n"
TIMEOUT = 600


def tracked_files():
    out = subprocess.run(["git", "-C", REPO, "ls-files", "-z"], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def matrices_naming(hook):
    """The tests/*-cases.py files that mention `hook` as a quoted name or a file name."""
    found = []
    for path in sorted(glob.glob(os.path.join(REPO, "tests", "*-cases.py"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if any(token in text for token in (f'"{hook}"', f"'{hook}'", f"{hook}.py")):
            found.append(os.path.basename(path))
    return found


def copy_repo(files, dest):
    for rel in files:
        src = os.path.join(REPO, rel)
        if not os.path.isfile(src):
            continue
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)


def main():
    hooks = sys.argv[1:] or sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HOOKS, "*.py")))
    files = tracked_files()
    vacuous, unmatched = [], []
    for hook in hooks:
        matrices = matrices_naming(hook)
        if not matrices:
            unmatched.append(hook)
            print(f"  ?  {hook}: no matrix names it")
            continue
        work = tempfile.mkdtemp(prefix=f"vacuity-{hook}-")
        caught = []
        try:
            copy_repo(files, work)
            with open(os.path.join(work, "global", ".claude", "hooks", f"{hook}.py"), "w") as fh:
                fh.write(STUB)
            for matrix in matrices:
                try:
                    proc = subprocess.run([sys.executable, os.path.join(work, "tests", matrix)],
                                          capture_output=True, text=True, timeout=TIMEOUT, cwd=work)
                    failed = proc.returncode != 0
                except subprocess.TimeoutExpired:
                    failed = True
                print(f"  {'fails' if failed else 'passes (incidental)'}  {hook} -> {matrix}")
                if failed:
                    caught.append(matrix)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if not caught:
            vacuous.append(hook)
            print(f"  VACUOUS  {hook}: every matrix naming it passes with a no-op hook")
    if vacuous or unmatched:
        print(f"vacuity-check: {len(vacuous)} hook(s) with no matrix that can fail"
              + (f", {len(unmatched)} hook(s) no matrix names" if unmatched else ""))
        return 1
    print(f"vacuity-check: all {len(hooks)} hooks have a matrix that fails against a no-op hook")
    return 0


if __name__ == "__main__":
    sys.exit(main())
