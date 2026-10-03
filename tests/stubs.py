"""Portable fake binaries and minimal PATHs for the deployer and installer matrices.

The matrices once wrote `#!/bin/sh` stubs and symlinked system tools into a
scrubbed PATH. Neither works on Windows: it runs no shebang script, finds no
command without a PATHEXT extension, and needs a privilege to create a
symlink. So init.ps1 and install.ps1 — the scripts that most need Windows
PowerShell 5.1 — could only ever be tested through pwsh on Linux.
"""

import os
import shutil
import stat
import sys

WINDOWS = os.name == "nt"


def write_stub(bindir, name, out="", code=0, sleep=0, log=None):
    """A command `name` on PATH that prints `out`, waits `sleep` seconds and exits `code`.

    With `log`, it appends its arguments (space-joined) to that file first.
    Written in Python so it runs on every OS: an executable with a shebang on
    POSIX, a `name.cmd` launcher next to the script on Windows.
    """
    os.makedirs(bindir, exist_ok=True)
    body = ("import sys, time\n"
            + (f"open({log!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n" if log else "")
            + f"time.sleep({sleep})\nsys.stdout.write({out!r})\nsys.stdout.flush()\nsys.exit({code})\n")
    if WINDOWS:
        with open(os.path.join(bindir, name + ".stub.py"), "w") as fh:
            fh.write(body)
        with open(os.path.join(bindir, name + ".cmd"), "w") as fh:
            fh.write(f'@"{sys.executable}" "%~dp0{name}.stub.py" %*\n')
        return
    path = os.path.join(bindir, name)
    with open(path, "w") as fh:
        fh.write(f"#!{sys.executable}\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


def minimal_path(bindir, tools):
    """A PATH holding `bindir` plus only what the scripts under test need.

    POSIX: `tools` are symlinked into `bindir`, so a probe for a missing
    binary (npx, codebase-memory-mcp) really finds nothing. Windows: the
    directories of Python and git plus System32, since symlinks need a
    privilege there; none of them holds the binaries the cases stub out.
    """
    os.makedirs(bindir, exist_ok=True)
    if WINDOWS:
        dirs = [bindir, os.path.dirname(sys.executable), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")]
        git = shutil.which("git")
        if git:
            dirs.append(os.path.dirname(git))
        return os.pathsep.join(dirs)
    for tool in tools:
        src = shutil.which(tool)
        dst = os.path.join(bindir, tool)
        if src and not os.path.exists(dst):
            os.symlink(src, dst)
    return bindir


def shell_targets(pwsh):
    """(pwsh, label) pairs to run: the .sh scripts are Unix-only, so Windows runs only the .ps1."""
    return ([] if WINDOWS else [(None, "sh")]) + ([(pwsh, "ps1")] if pwsh else [])
