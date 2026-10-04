"""Turn on a per-user bytecode cache for the hooks, outside the manifest-owned hooks/ tree.

Imported first by every hook, while sys.dont_write_bytecode is still True, so
this module itself never writes a __pycache__. Without a cache every hook
recompiled _lib on every run; a __pycache__ under ~/.claude/hooks would be
files the installer's manifest never removes. So compiled files go to:

  Linux    $XDG_CACHE_HOME/dotclaude/pycache, else ~/.cache/dotclaude/pycache
  macOS    ~/Library/Caches/dotclaude/pycache
  Windows  %LOCALAPPDATA%\\dotclaude\\pycache

Never a shared temp folder, where another user could plant a .pyc the hooks
would execute: the folder is created 0700 and, on POSIX, used only when the
current user owns it and nobody else can write it. Any failure leaves bytecode
off, which is only slower. Run as a script, it prints the folder, so both
installers clear exactly that path before copying new hooks.
"""

import os
import sys


def cache_dir():
    """The per-user folder for the hooks' compiled bytecode, or None when the OS gives no base."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "dotclaude", "pycache") if base else None


def trusted(path):
    """True when only the current user can write `path` (always True on Windows, per-user by location)."""
    if os.name == "nt":
        return os.access(path, os.W_OK)
    st = os.stat(path)
    return st.st_uid == os.getuid() and not st.st_mode & 0o022


def enable():
    try:
        folder = cache_dir()
        if not folder:
            return
        os.makedirs(folder, mode=0o700, exist_ok=True)
        if trusted(folder):
            sys.pycache_prefix = folder
            sys.dont_write_bytecode = False
    except (OSError, ValueError, AttributeError):
        pass


if __name__ == "__main__":
    print(cache_dir() or "")
else:
    enable()
