#!/usr/bin/env python3
"""Behavioural contract for hooks/_lib/bootstrap.py, the hooks' per-user bytecode cache.

Run:  python3 tests/bootstrap-cases.py

The cache must land in the per-user folder for the OS, be created private,
and be refused, leaving bytecode off, when anyone else could write it: a
.pyc planted there would run inside every hook. Each case imports bootstrap in
a fresh interpreter under a fake home and reports what it set.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

LIB = os.path.join(pyhook.HOOKS, "_lib")
PROBE = ("import json, sys\nsys.dont_write_bytecode = True\nsys.path.insert(0, sys.argv[1])\nimport bootstrap\n"
         "print(json.dumps({'prefix': sys.pycache_prefix, 'off': sys.dont_write_bytecode}))\n")


def probe(home, extra=None):
    script = os.path.join(home, "probe.py")
    with open(script, "w") as fh:
        fh.write(PROBE)
    env = dict(os.environ, **pyhook.home_env(home))
    env.update(extra or {})
    proc = subprocess.run([sys.executable, script, LIB], capture_output=True, text=True, env=env, timeout=60)
    return json.loads(proc.stdout or "{}"), proc


def expected(home):
    if os.name == "nt":
        return os.path.join(home, "AppData", "Local", "dotclaude", "pycache")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "dotclaude", "pycache")
    return os.path.join(home, ".cache", "dotclaude", "pycache")


def main():
    failures = total = 0

    def check(label, ok, detail=""):
        nonlocal failures, total
        total += 1
        if not ok:
            failures += 1
            print(f"  FAIL {label}{' | ' + detail if detail else ''}")

    home = tempfile.mkdtemp(prefix="bootstrap-")
    try:
        got, proc = probe(home)
        want = expected(home)
        check("a fresh home turns the cache on in the per-user folder",
              got.get("prefix") == want and got.get("off") is False, f"{got} stderr={proc.stderr[-160:]!r}")
        if os.name != "nt":
            mode = stat.S_IMODE(os.stat(want).st_mode)
            check("the cache folder is created private (0700)", mode == 0o700, oct(mode))
            os.chmod(want, 0o777)
            got, _ = probe(home)
            check("a folder others can write is refused: bytecode stays off",
                  got.get("prefix") is None and got.get("off") is True, str(got))
            os.chmod(want, 0o700)
        got, _ = probe(home)
        check("a second run reuses the same folder", got.get("prefix") == want, str(got))
        if sys.platform.startswith("linux"):
            custom = os.path.join(home, "xdg")
            got, _ = probe(home, {"XDG_CACHE_HOME": custom})
            check("XDG_CACHE_HOME is honoured on Linux",
                  got.get("prefix") == os.path.join(custom, "dotclaude", "pycache"), str(got))
        script = subprocess.run([sys.executable, os.path.join(LIB, "bootstrap.py")], capture_output=True, text=True,
                                env=dict(os.environ, **pyhook.home_env(home)))
        check("run as a script it prints the folder the installers clear", script.stdout.strip() == want,
              script.stdout.strip())
        check("importing bootstrap writes no __pycache__ next to it",
              not os.path.exists(os.path.join(LIB, "__pycache__")))
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return pyhook.finish("bootstrap", failures, total, has_windows_form=False)


if __name__ == "__main__":
    sys.exit(main())
