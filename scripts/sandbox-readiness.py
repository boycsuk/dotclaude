#!/usr/bin/env python3
"""Say in one line whether Claude Code's Bash sandbox can run on this machine, and what to install if not.

Run last by both installers. It never installs anything and never uses sudo:
installing system packages is the user's decision, made from their own
terminal, so it prints the exact command for the package manager it finds.
The sandbox stays opt-in (enabled with /sandbox); this only says whether it
could be.

  macOS          Seatbelt is built in: nothing to install.
  Linux / WSL2   needs bubblewrap (the `bwrap` binary) and socat.
  WSL1           unsupported: the sandbox requires WSL2.
  Windows        unsupported natively: run Claude Code in WSL2 or a dev container.

Always exits 0: a missing optional prerequisite must never fail an install.
"""

import os
import shutil
import sys

DOCS = "https://code.claude.com/docs/en/sandboxing"
PACKAGES = (("bubblewrap", "bwrap"), ("socat", "socat"))
# Package manager binary -> install command prefix, in the order they are tried.
MANAGERS = (("apt-get", "sudo apt-get install"), ("dnf", "sudo dnf install"),
            ("pacman", "sudo pacman -S"), ("zypper", "sudo zypper install"))


def is_wsl1():
    """True on WSL1, whose kernel string says Microsoft without WSL2's "microsoft-standard"."""
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            version = fh.read()
    except OSError:
        return False
    return "Microsoft" in version and "microsoft-standard" not in version.lower()


def linux_line():
    if is_wsl1():
        return "sandbox: not available on WSL1 - convert this distribution to WSL2 to use it"
    missing = [package for package, binary in PACKAGES if not shutil.which(binary)]
    if not missing:
        return "sandbox available (optional): bubblewrap and socat are installed - enable it with /sandbox in Claude Code"
    names = " ".join(missing)
    command = next((f"{prefix} {names}" for manager, prefix in MANAGERS if shutil.which(manager)), None)
    how = f"run `{command}`" if command else f"install {names} with your package manager"
    return f"sandbox available (optional, stronger than the guards): needs {' and '.join(missing)} - {how}, then enable it with /sandbox ({DOCS})"


def main():
    if os.name == "nt":
        line = "sandbox: not available on native Windows - run Claude Code in WSL2, or in a dev container"
    elif sys.platform == "darwin":
        line = "sandbox available (optional): nothing to install on macOS - enable it with /sandbox in Claude Code"
    else:
        line = linux_line()
    print(f"  - {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
