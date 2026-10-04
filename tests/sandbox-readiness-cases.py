#!/usr/bin/env python3
"""Behavioural contract for scripts/sandbox-readiness.py, the installers' sandbox line.

Run:  python3 tests/sandbox-readiness-cases.py

The line must name exactly what is missing and the command for the package
manager present, never claim the sandbox is ready when a prerequisite is
absent, and never fail the install. PATH holds only stub binaries, so the
machine's own bwrap or apt-get cannot decide a case. The Linux cases run on
Linux; macOS and Windows each check their own line.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402
import stubs  # noqa: E402

SCRIPT = os.path.join(pyhook.REPO, "scripts", "sandbox-readiness.py")

# (stub binaries on PATH, text the line must hold, text it must not hold, why)
LINUX_CASES = [
    (["bwrap", "socat", "apt-get"], "are installed", "needs", "both prerequisites present"),
    (["apt-get"], "sudo apt-get install bubblewrap socat", "are installed", "both missing, Debian/Ubuntu"),
    (["bwrap", "dnf"], "sudo dnf install socat", "bubblewrap", "only socat missing, Fedora"),
    (["socat", "pacman"], "sudo pacman -S bubblewrap", "socat -", "only bubblewrap missing, Arch"),
    (["zypper"], "sudo zypper install bubblewrap socat", "are installed", "openSUSE"),
    ([], "install bubblewrap socat with your package manager", "sudo", "no known package manager"),
]


def run(path):
    env = dict(os.environ, PATH=path)
    return subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, env=env, timeout=60)


def main():
    failures = total = 0
    if os.name == "nt" or sys.platform == "darwin":
        expected = "native Windows" if os.name == "nt" else "nothing to install"
        proc = run(os.environ.get("PATH", ""))
        total = 1
        if proc.returncode != 0 or expected not in proc.stdout:
            failures = 1
            print(f"  FAIL this platform's line: exit {proc.returncode}, out {proc.stdout.strip()!r}")
        return pyhook.finish("sandbox-readiness", failures, total, has_windows_form=False)
    for binaries, must, must_not, why in LINUX_CASES:
        total += 1
        bindir = tempfile.mkdtemp(prefix="sandbox-readiness-")
        for name in binaries:
            stubs.write_stub(bindir, name)
        proc = run(bindir)
        out = proc.stdout
        problems = []
        if proc.returncode != 0:
            problems.append(f"exit {proc.returncode}")
        if must not in out:
            problems.append(f"lacks {must!r}")
        if must_not in out:
            problems.append(f"holds {must_not!r}")
        if len(out.strip().splitlines()) != 1:
            problems.append("not exactly one line")
        if problems:
            failures += 1
            print(f"  FAIL {why}: {', '.join(problems)} | {out.strip()!r}")
    return pyhook.finish("sandbox-readiness", failures, total, has_windows_form=False)


if __name__ == "__main__":
    sys.exit(main())
