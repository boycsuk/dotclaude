"""Which paths a shell command writes, shared by the guards that forbid writing somewhere.

guard-destructive forbids writes into the installed central config, and
guard-readonly-agents forbids a read-only subagent writes anywhere but the
temp folder. Both need the same answer to "what does this command write?",
so it lives here and each guard applies its own rule to the paths.
"""

import os
import re

HOME_TOKENS = ("$HOME", "${HOME}", "$env:USERPROFILE", "$env:HOME", "%USERPROFILE%")
REDIRECT = re.compile(r"^(\d*|&)>>?\|?(.*)$")
PS_REMOVE = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}
PS_WRITERS = {"set-content", "add-content", "out-file", "clear-content", "new-item", "sc", "ac"}
PS_COPIES = {"copy-item", "move-item", "cpi", "mi", "copy", "move", "cp", "mv"}
# Every positional argument is a path the command writes, deletes or re-modes.
PATH_WRITERS = {"tee", "rm", "truncate", "chmod", "chown", "shred", "unlink", "ln", "link",
                "touch", "mkdir", "rmdir"}
PS_PATH_FLAGS = ("path", "literalpath", "filepath")
PS_VALUED_FLAGS = ("value", "encoding", "inputobject", "itemtype", "name", "width")


def home():
    return os.path.expanduser("~").replace("\\", "/")


def canonical_home(word):
    """`word` with a leading home spelling ($HOME, ${HOME}, $env:USERPROFILE) as `~`."""
    w = word.replace("\\", "/")
    for token in HOME_TOKENS:
        if w == token or w.startswith(token + "/"):
            return "~" + w[len(token):]
    return w


def absolute(word, cwd):
    """`word` as an absolute, normalised, forward-slash path, resolving `~` and home spellings."""
    w = canonical_home(word)
    if w == "~" or w.startswith("~/"):
        w = home() + w[1:]
    if not (w.startswith("/") or re.match(r"^[A-Za-z]:/", w)):
        w = cwd.replace("\\", "/").rstrip("/") + "/" + w
    return os.path.normpath(w).replace("\\", "/")


def split_args(args):
    """(flags, positional, redirect targets) of a command's arguments."""
    flags, positional, redirects, i = [], [], [], 0
    while i < len(args):
        a = args[i]
        m = REDIRECT.match(a)
        if m and not a.startswith("-"):
            target = m.group(2) or (args[i + 1] if i + 1 < len(args) else "")
            if not m.group(2):
                i += 1
            if not target.startswith("&"):
                redirects.append(target)
        elif a == "<" or a == "<<<":
            i += 1
        elif a.startswith("-") and len(a) > 1 and a != "--":
            flags.append(a)
        else:
            positional.append(a)
        i += 1
    return flags, positional, redirects


def short_bundle(flag, letters):
    return flag.startswith("-") and not flag.startswith("--") and any(c in flag[1:] for c in letters)


def ps_flag(flag, name, minimum=2):
    """True when `flag` is an abbreviation PowerShell accepts for -`name`."""
    f = flag.lower().lstrip("-")
    return len(f) >= minimum and name.startswith(f)


def _value_of(args, names):
    return next((args[i + 1] for i, a in enumerate(args[:-1])
                 if a.startswith("-") and any(ps_flag(a, n, 1) for n in names)), None)


def _edited_files(lower, flags, positional):
    """The files `sed -i` / `perl -i` rewrite: the positionals after its scripts."""
    if lower == "sed":
        scripts = sum(1 for f in flags if f in ("-e", "-f", "--expression", "--file"))
        inline = any(f.startswith(("--expression=", "--file=")) for f in flags)
        return positional[scripts if (scripts or inline) else 1:]
    scripts = sum(1 for f in flags if short_bundle(f, "e"))
    return positional[scripts:]


def _ps_write_path(args):
    path = _value_of(args, PS_PATH_FLAGS)
    if path:
        return [path]
    valued = {i + 1 for i, a in enumerate(args) if a.startswith("-") and any(ps_flag(a, n, 1) for n in PS_VALUED_FLAGS)}
    rest = [a for i, a in enumerate(args) if i not in valued and not a.startswith("-")]
    return rest[:1]


def targets(name, args, shell):
    """The paths command `name args` writes, deletes or re-modes, as written (not resolved).

    Covers redirects, the file utilities, `sed -i` / `perl -i`, `dd of=`,
    cp/mv/install/rsync (a move also removes its sources, and a link copy
    exposes them), and PowerShell's removers, writers and copies. A program
    that writes on its own (a script, a compiler) is not seen.
    """
    # `2>&1` reaches here as a `2>` with no target (the parser splits at `&`).
    return [t for t in _targets(name, args, shell) if t]


def _targets(name, args, shell):
    flags, positional, redirects = split_args(args)
    found = list(redirects)
    lower = name.lower()
    if lower in PATH_WRITERS or (shell == "powershell" and lower in PS_REMOVE):
        return found + positional
    if lower == "sed" and any(f.startswith("-i") or f.startswith("--in-place") for f in flags):
        return found + _edited_files(lower, flags, positional)
    if lower == "perl" and any(short_bundle(f, "i") for f in flags):
        return found + _edited_files(lower, flags, positional)
    if lower == "dd":
        return found + [a[3:] for a in args if a.startswith("of=")]
    if shell == "powershell" and lower in PS_WRITERS:
        return found + _ps_write_path(args)
    if shell == "powershell" and lower in PS_COPIES:
        dest = _value_of(args, ("destination",)) or (positional[1] if len(positional) > 1 else None)
        moved = positional[:1] if lower in ("move-item", "mi", "move", "mv") else []
        return found + ([dest] if dest else []) + moved
    if lower in ("cp", "mv", "install", "rsync"):
        target = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-t", "--target-directory")), None)
        target = target or next((a.split("=", 1)[1] for a in args if a.startswith("--target-directory=")), None)
        sources = positional if target else positional[:-1]
        target = target or (positional[-1] if len(positional) > 1 else None)
        linked = lower == "cp" and any(f in ("-l", "--link", "-s", "--symbolic-link") or short_bundle(f, "ls")
                                       for f in flags)
        exposed = sources if (lower == "mv" or linked) else []
        return found + ([target] if target else []) + exposed
    return found
