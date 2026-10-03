"""Run every tests/*-cases.py matrix and fail if any of them does.

usage: python3 tests/run-matrices.py [--pwsh PATH]

With --pwsh, every matrix that accepts it also runs the PowerShell side
through that executable (`pwsh`, or `powershell` for Windows PowerShell 5.1).
Exists so CI runs the same set on every OS without a shell-specific loop.
"""

import argparse
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="PowerShell executable to pass to the matrices that take one")
    args = ap.parse_args()

    failed = []
    for path in sorted(glob.glob(os.path.join(HERE, "*-cases.py"))):
        name = os.path.basename(path)
        cmd = [sys.executable, "-u", path]
        with open(path, encoding="utf-8") as fh:
            if args.pwsh and "--pwsh" in fh.read():
                cmd += ["--pwsh", args.pwsh]
        start = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
        lines = proc.stdout.strip().splitlines()
        summary = lines[-1] if lines else "(no output)"
        print(f"{name}: exit {proc.returncode} in {time.monotonic() - start:.0f}s — {summary}", flush=True)
        if proc.returncode != 0:
            failed.append(name)
            print(proc.stdout + proc.stderr, flush=True)

    print(f"\n{len(failed)} matrix(es) failed" + (f": {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
