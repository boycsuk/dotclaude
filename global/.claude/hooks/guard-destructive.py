# hook-kind: guard
"""PreToolUse hook on Bash/PowerShell: block commands that destroy data or run unreviewed code.

Deny:
  - recursive delete of a dangerous path: /, system directories, home or
    anything under it, `*`, `.`, `..` (rm in any flag spelling, find
    -delete / -exec rm, PowerShell Remove-Item -Recurse and its aliases);
  - `git reset --hard` with no ref or onto main/master/HEAD~;
  - a download piped or substituted into a shell or interpreter
    (`curl … | sh`, `bash <(curl …)`, `irm … | iex`);
  - an inline interpreter (`python3 -c`, `node -e`, `bash -c`, `pwsh -c`,
    -EncodedCommand): code the allowlist cannot inspect belongs in a file;
  - a write into the installed central config (~/.claude settings.json,
    hooks, agents, skills, rules, output-styles, templates) through Bash —
    guard-central-config covers Edit/Write, this covers redirects, tee, sed
    -i, cp/mv/install/rsync into it, rm, chmod and links out of it.
Ask:
  - `git clean` that force-deletes directories or ignored files, and
    `git checkout -- .` / `git restore .`, which discard uncommitted work.

Every rule judges the command the shell will actually run (shellwords): a
heredoc body written to a file is data, a commit message that names a
pattern is not the pattern, but an unquoted heredoc's $( ) and a quoted
"$( )" do run (DESIGN.md §26, §38). A command whose quoting cannot be parsed
falls back to the text patterns, so an unbalanced quote fails closed.
"""

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import shellwords  # noqa: E402

HOME_TOKENS = ("$HOME", "${HOME}", "$env:USERPROFILE", "$env:HOME", "%USERPROFILE%")
SYSTEM_DIRS = re.compile(r"^/(etc|home|usr|var|opt|root|boot|bin|sbin|lib|lib64|Users|System|Library)(/|$)")
WINDOWS_DANGER = re.compile(r"^[a-z]:/?$|^[a-z]:/(windows|users|program files[^/]*)(/|$)", re.I)
CENTRAL_TAIL = r"/\.claude/(settings\.json|(hooks|agents|skills|rules|output-styles|templates)(/.*)?)$"
DOWNLOADERS = {"curl", "wget", "fetch", "http", "https", "aria2c", "iwr", "irm",
               "invoke-webrequest", "invoke-restmethod"}
INTERPRETERS = re.compile(r"^((ba|z|da|k)?sh|fish|python[0-9.]*|py|perl|ruby|node|nodejs|php|bun|deno"
                          r"|pwsh|powershell|iex|invoke-expression)$", re.I)
PS_REMOVE = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}
PS_WRITERS = {"set-content", "add-content", "out-file", "clear-content", "new-item", "sc", "ac"}
PS_COPIES = {"copy-item", "move-item", "cpi", "mi", "copy", "move", "cp", "mv"}
CD = {"cd", "pushd", "chdir", "set-location", "sl"}
REDIRECT = re.compile(r"^(\d*|&)>>?\|?(.*)$")

# Used only when the quoting cannot be parsed: the patterns of the old
# text-matching guard, so an unbalanced quote never opens a hole.
FALLBACK = [
    re.compile(r"\brm\s+(-\S+\s+)*(-[A-Za-z]*[rR][A-Za-z]*|--recursive)\s+(-\S+\s+)*"
               r"(/(\s|$|\*)|/(etc|home|usr|var|opt|root|boot|bin|sbin|lib)(\s|/|$)|~(\s|/|$)"
               r"|\$\{?HOME\}?(\s|/|$)|\*(\s|$)|\./\*|\.\*|\.\.(\s|/|$))"),
    re.compile(r"\bgit\b.*\breset\s+--hard\b"),
    re.compile(r"\b(curl|wget|iwr|irm)\b.*\|\s*\S*(sh|bash|python[0-9.]*|perl|ruby|node|iex)\b", re.I),
    re.compile(r"\b(python[0-9.]*|perl|ruby|node)\s+-[A-Za-z]*[ce]\b|\b(ba|z|da|k)?sh\s+-[A-Za-z]*c\b"),
    re.compile(r"\.claude/(settings\.json|hooks|agents|skills|rules|output-styles|templates)"),
]


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
    w = canonical_home(word)
    if w == "~" or w.startswith("~/"):
        w = home() + w[1:]
    if not (w.startswith("/") or re.match(r"^[A-Za-z]:/", w)):
        w = cwd.replace("\\", "/").rstrip("/") + "/" + w
    return os.path.normpath(w).replace("\\", "/")


def dangerous_target(word):
    w = canonical_home(word).rstrip("/") or "/"
    if w in ("/", "/*", "~", "*", ".", "./*", ".*", "..") or w.startswith(("~/", "../")):
        return True
    return bool(SYSTEM_DIRS.match(w) or WINDOWS_DANGER.match(w))


def is_central(word, cwd):
    homes = rf"{re.escape(home())}|/home/[^/]+|/Users/[^/]+"
    return bool(re.match(rf"^({homes}){CENTRAL_TAIL}", absolute(word, cwd)))


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


def judge_rm(name, args, shell):
    flags, positional, _ = split_args(args)
    if shell == "powershell" and name in PS_REMOVE:
        # A POSIX bundle (`rm -rf`) typed into PowerShell counts too: erring
        # toward "recursive" only ever blocks a delete of a dangerous path.
        recursive = any(ps_flag(f, "recurse", 1) or short_bundle(f, "rR") for f in flags)
    else:
        recursive = any(f == "--recursive" or short_bundle(f, "rR") for f in flags)
    if recursive and any(dangerous_target(p) for p in positional):
        return "deny", "recursive delete of a dangerous path"
    return None


def judge_find(args):
    roots = []
    for a in args:
        if a.startswith(("-", "(", "!")):
            break
        roots.append(a)
    deletes = "-delete" in args or any(
        a in ("-exec", "-execdir", "-ok") and i + 1 < len(args) and shellwords.basename(args[i + 1]) == "rm"
        for i, a in enumerate(args))
    if deletes and any(dangerous_target(r) for r in roots or ["."]):
        return "deny", "find deleting under a dangerous path"
    return None


def judge_git(seg):
    inv = shellwords.git_invocation(seg)
    if not inv:
        return None
    sub, args, _ = inv
    flags, positional, _ = split_args(args)
    if sub == "reset" and "--hard" in flags:
        ref = positional[0] if positional else ""
        if not ref or re.match(r"^(origin/)?(main|master)$|^(HEAD|@)[~^]", ref):
            return "deny", "git reset --hard discards commits or work on a main branch"
    if sub == "clean" and any(short_bundle(f, "f") or f == "--force" for f in flags) \
            and any(short_bundle(f, "dx") for f in flags):
        return "ask", "git clean force-deletes untracked directories or ignored files"
    if sub in ("checkout", "restore") and ("." in positional or ":/" in positional) \
            and not any(f in ("--staged", "-S") for f in flags):
        return "ask", f"git {sub} . discards every uncommitted change"
    return None


def judge_interpreter(name, args):
    lower = name.lower()
    head = []
    for a in args:
        if not a.startswith("-") or a == "-m":
            break
        head.append(a)
    if re.fullmatch(r"python[0-9.]*|py", lower) and any(short_bundle(a, "c") for a in head):
        return True
    if lower in ("node", "nodejs", "bun") and any(
            a in ("-e", "--eval", "-p", "--print") or short_bundle(a, "ep") for a in head):
        return True
    if lower == "deno" and args[:1] == ["eval"]:
        return True
    if lower in ("ruby", "perl") and any(short_bundle(a, "e") for a in head):
        return True
    if lower == "php" and "-r" in head:
        return True
    if lower in shellwords.SHELLS + ("fish",) and any(short_bundle(a, "c") for a in head):
        return True
    if lower in ("pwsh", "powershell"):
        return any(ps_flag(a, "command", 1) or ps_flag(a, "encodedcommand", 1) or a.lower() == "-ec"
                   for a in args if a.startswith("-"))
    return False


def judge_central(name, args, shell, cwd):
    flags, positional, redirects = split_args(args)
    if any(is_central(r, cwd) for r in redirects):
        return True
    lower = name.lower()
    central = [p for p in positional if is_central(p, cwd)]
    if lower in ("tee", "rm", "truncate", "chmod", "chown", "shred", "unlink", "ln", "link"):
        return bool(central)
    if lower == "sed" and any(f.startswith("-i") or f.startswith("--in-place") for f in flags):
        return bool(central)
    if lower == "perl" and any(short_bundle(f, "i") for f in flags):
        return bool(central)
    if lower == "dd":
        return any(a.startswith("of=") and is_central(a[3:], cwd) for a in args)
    if shell == "powershell" and lower in PS_REMOVE | PS_WRITERS:
        return bool(central)
    if shell == "powershell" and lower in PS_COPIES:
        dest = next((args[i + 1] for i, a in enumerate(args[:-1]) if ps_flag(a, "destination", 1)), None)
        dest = dest or (positional[1] if len(positional) > 1 else None)
        return bool(dest and is_central(dest, cwd))
    if lower in ("cp", "mv", "install", "rsync"):
        if lower == "cp" and any(f in ("-l", "--link", "-s", "--symbolic-link") or short_bundle(f, "ls")
                                 for f in flags) and central:
            return True
        target = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-t", "--target-directory")), None)
        target = target or next((a.split("=", 1)[1] for a in args if a.startswith("--target-directory=")), None)
        target = target or (positional[-1] if len(positional) > 1 else None)
        return bool(target and is_central(target, cwd))
    return False


def judge_downloads(command, shell):
    for pipeline in shellwords.pipelines(command, shell) or []:
        names = [shellwords.basename((shellwords.unwrap(s) or [""])[0]).lower() for s in pipeline]
        for i, name in enumerate(names):
            if name in DOWNLOADERS and any(INTERPRETERS.match(n) for n in names[i + 1:]):
                return True
    text = shellwords.code_text(command, shell)
    if re.search(r"(^|[\s;&|(])(source|\.|(ba|z|da|k)?sh|python[0-9.]*|perl|ruby|node)\s+<\(\s*"
                 r"(curl|wget|fetch)\b", text):
        return True
    return bool(re.search(r"\b(iex|invoke-expression)\b", text, re.I)
                and re.search(r"downloadstring|\biwr\b|\birm\b|invoke-webrequest|invoke-restmethod"
                              r"|webclient", text, re.I))


def judge(command, payload):
    """(decision, reason) for `command`, or (None, None) to let it run."""
    shell = shellwords.shell_of(payload)
    segments = shellwords.segments(command, shell)
    if segments is None:
        text = shellwords.code_text(command, shell)
        if any(p.search(text) for p in FALLBACK):
            return "deny", ("its quoting cannot be parsed and it matches a destructive pattern "
                            "(recursive delete, reset --hard, download into a shell, inline "
                            "interpreter or a write into ~/.claude)")
        return None, None
    if judge_downloads(command, shell):
        return "deny", "piping a network download into a shell or interpreter (remote code execution)"
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    asks = []
    for seg in segments:
        words = shellwords.unwrap(seg)
        if not words:
            continue
        name = shellwords.basename(words[0])
        lower, args = name.lower(), words[1:]
        if lower in CD:
            cwd = absolute(next((a for a in args if a != "--"), "~"), cwd)
            continue
        if judge_central(name, args, shell, cwd):
            return "deny", ("writing to the installed central config (~/.claude/...) through the shell. "
                            "It is shared by every project and overwritten by install.sh: edit the "
                            "source in the dotclaude repo (global/.claude/...) and run ./install.sh")
        verdict = None
        if lower == "rm" or (shell == "powershell" and lower in PS_REMOVE):
            verdict = judge_rm(lower, args, shell)
        elif lower == "find":
            verdict = judge_find(args)
        elif lower == "git":
            verdict = judge_git(seg)
        elif judge_interpreter(name, args):
            verdict = ("deny", "inline interpreter execution (python3 -c, node -e, bash -c, pwsh -c): "
                               "put the code in a reviewable file")
        if verdict and verdict[0] == "deny":
            return verdict
        if verdict:
            asks.append(verdict[1])
    if asks:
        return "ask", "; ".join(asks)
    return None, None


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    decision, reason = judge(command, payload)
    if decision == "deny":
        hookio.deny(f"BLOCKED: {reason}. The user must run this manually if intentional.")
    elif decision == "ask":
        hookio.ask(f"Confirm: {reason}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
