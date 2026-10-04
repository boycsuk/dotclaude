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
    -EncodedCommand), and the same program spelled another way: a heredoc,
    here-string or echo/printf pipe feeding python/node/perl/ruby/php, or a
    file a heredoc writes and one of them runs in the same command. Code the
    allowlist cannot inspect belongs in a file written first. A shell fed a
    heredoc or echoed text is not blocked, because that text is judged as
    commands. Known gap: a runner the wrappers list does not know
    (`uv run python - <<EOF`);
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
"$( )" do run. A command whose quoting cannot be parsed
falls back to the text patterns, so an unbalanced quote fails closed.
"""

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import bootstrap  # noqa: E402,F401
import hookio  # noqa: E402
import shellwords  # noqa: E402
import writes  # noqa: E402
from writes import PS_REMOVE, absolute, canonical_home, home, ps_flag, short_bundle, split_args  # noqa: E402

SYSTEM_DIRS = re.compile(r"^/(etc|home|usr|var|opt|root|boot|bin|sbin|lib|lib64|Users|System|Library)(/|$)")
WINDOWS_DANGER = re.compile(r"^[a-z]:/?$|^[a-z]:/(windows|users|program files[^/]*)(/|$)", re.I)
CENTRAL_TAIL = r"/\.claude/(settings\.json|(hooks|agents|skills|rules|output-styles|templates)(/.*)?)$"
DOWNLOADERS = {"curl", "wget", "fetch", "http", "https", "aria2c", "iwr", "irm",
               "invoke-webrequest", "invoke-restmethod"}
INTERPRETERS = re.compile(r"^((ba|z|da|k)?sh|fish|python[0-9.]*|py|perl|ruby|node|nodejs|php|bun|deno"
                          r"|pwsh|powershell|iex|invoke-expression)$", re.I)
PROGRAM_PRODUCERS = {"echo", "printf"}
INLINE_REASON = ("inline interpreter execution (python3 -c, node -e, bash -c, pwsh -c, or a program "
                 "fed on stdin or written and run in the same command). Instead: write the code to a "
                 "file with the Write tool, then run that file in a separate command")
USER_RUNS = "If it really is intended, the user runs it in their own terminal"

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


def dangerous_target(word):
    w = canonical_home(word).rstrip("/") or "/"
    if w in ("/", "/*", "~", "*", ".", "./*", ".*", "..") or w.startswith(("~/", "../")):
        return True
    return bool(SYSTEM_DIRS.match(w) or WINDOWS_DANGER.match(w))


def is_central(word, cwd):
    homes = rf"{re.escape(home())}|/home/[^/]+|/Users/[^/]+"
    return bool(re.match(rf"^({homes}){CENTRAL_TAIL}", absolute(word, cwd)))


def judge_rm(name, args, shell):
    flags, positional, _ = split_args(args)
    if shell == "powershell" and name in PS_REMOVE:
        # A POSIX bundle (`rm -rf`) typed into PowerShell counts too: erring
        # toward "recursive" only ever blocks a delete of a dangerous path.
        recursive = any(ps_flag(f, "recurse", 1) or short_bundle(f, "rR") for f in flags)
    else:
        recursive = any(f == "--recursive" or short_bundle(f, "rR") for f in flags)
    hit = next((p for p in positional if dangerous_target(p)), None) if recursive else None
    if hit is not None:
        return "deny", (f"recursive delete of a dangerous path ({hit}: the root, the working "
                        f"directory, a parent, a system directory, or anything under the home "
                        f"directory). Instead: give a path relative to the project, such as "
                        f"node_modules or ./build. {USER_RUNS}")
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
    hit = next((r for r in roots or ["."] if dangerous_target(r)), None) if deletes else None
    if hit is not None:
        return "deny", (f"find deleting under a dangerous path ({hit}). Instead: start find from a "
                        f"narrower directory inside the project. {USER_RUNS}")
    return None


def git_option(flags, option, short=""):
    """True when a flag is `option`, a prefix of it, or a short bundle holding `short`.

    git accepts any unambiguous prefix of a long option (`--har` is --hard); a
    prefix git would reject as ambiguous only ever blocks a failing command.
    """
    for f in flags:
        name = f.split("=", 1)[0]
        if name.startswith("--") and len(name) > 2 and option.startswith(name):
            return True
        if short and short_bundle(f, short):
            return True
    return False


def prunes_now(flags, options):
    return any(f.endswith(("=now", "=all")) and git_option([f], o) for f in flags for o in options)


def judge_git(seg):
    inv = shellwords.git_invocation(seg)
    if not inv:
        return None
    sub, args, _ = inv
    flags, positional, _ = split_args(args)
    action = positional[0] if positional else ""
    force = git_option(flags, "--force", "f")
    if sub == "reset" and git_option(flags, "--hard"):
        if not action or re.match(r"^(origin/)?(main|master)$|^(HEAD|@)[~^]", action):
            return "deny", (f"git reset --hard discards commits or work on a main branch. Instead: "
                            f"git stash, or reset on a feature branch. {USER_RUNS}")
        if action not in ("HEAD", "@"):
            return "ask", "git reset --hard to another commit discards uncommitted work and can drop commits"
    if sub == "clean" and force and any(short_bundle(f, "dx") for f in flags):
        return "ask", "git clean force-deletes untracked directories or ignored files"
    if sub == "branch" and (any(short_bundle(f, "D") for f in flags)
                            or (git_option(flags, "--delete", "d") and force)):
        return "deny", ("git branch -D force-deletes a branch whether or not it is merged. Instead: "
                        f"git branch -d, which refuses an unmerged branch. {USER_RUNS}")
    if sub == "stash" and action in ("clear", "drop"):
        return "ask", f"git stash {action} discards stashed work"
    if (sub == "checkout" and force) or (sub == "switch" and (force or git_option(flags, "--discard-changes"))):
        return "ask", f"git {sub} --force discards uncommitted changes"
    if sub in ("checkout", "restore") and ("." in positional or ":/" in positional) \
            and not any(f in ("--staged", "-S") for f in flags):
        return "ask", f"git {sub} . discards every uncommitted change"
    if (sub == "reflog" and action == "expire" and prunes_now(flags, ("--expire", "--expire-unreachable"))) \
            or (sub == "gc" and prunes_now(flags, ("--prune",))):
        return "ask", f"git {sub} with an immediate expiry makes lost commits unrecoverable"
    if sub == "update-ref" and "-d" in flags:
        return "ask", "git update-ref -d deletes a ref with no safety check"
    if sub == "worktree" and action == "remove" and force:
        return "ask", "git worktree remove --force discards the worktree's uncommitted changes"
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


def inline_program(command, shell):
    """True when a program reaches an interpreter through a here-string or an echo/printf pipe."""
    for pipeline in shellwords.pipelines(command, shell) or []:
        for i, seg in enumerate(pipeline):
            if not shellwords.reads_program_from_stdin(seg):
                continue
            producer = shellwords.unwrap(pipeline[i - 1]) if i else []
            if "<<<" in seg or (producer and shellwords.basename(producer[0]) in PROGRAM_PRODUCERS):
                return True
    return False


def judge_central(name, args, shell, cwd):
    return any(is_central(t, cwd) for t in writes.targets(name, args, shell))


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
    if any(doc["runner"] for doc in shellwords.heredocs(command, shell)) or inline_program(command, shell):
        return "deny", INLINE_REASON
    segments = shellwords.segments(command, shell)
    if segments is None:
        text = shellwords.code_text(command, shell)
        if any(p.search(text) for p in FALLBACK):
            return "deny", ("its quoting cannot be parsed and it matches a destructive pattern "
                            "(recursive delete, reset --hard, download into a shell, inline "
                            "interpreter or a write into ~/.claude). Instead: fix the quoting so "
                            "the command can be checked")
        return None, None
    if judge_downloads(command, shell):
        return "deny", ("piping a network download into a shell or interpreter (remote code "
                        "execution). Instead: download it to a file, read it, then run the file")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    asks = []
    for seg in segments:
        words = shellwords.unwrap(seg)
        if not words:
            continue
        name = shellwords.basename(words[0])
        lower, args = name.lower(), words[1:]
        target = shellwords.chdir_target(words)
        if target is not None:
            cwd = absolute(target, cwd)
            continue
        if judge_central(name, args, shell, cwd):
            return "deny", ("writing to the installed central config (~/.claude/...) through the shell. "
                            "It is shared by every project and overwritten by install.sh. Instead: edit "
                            "the source in the dotclaude repo (claude/...) and run ./install.sh")
        verdict = None
        if lower == "rm" or (shell == "powershell" and lower in PS_REMOVE):
            verdict = judge_rm(lower, args, shell)
        elif lower == "find":
            verdict = judge_find(args)
        elif lower == "git":
            verdict = judge_git(seg)
        elif judge_interpreter(name, args):
            verdict = ("deny", INLINE_REASON)
        if verdict and verdict[0] == "deny":
            return verdict
        if verdict:
            asks.append(verdict[1])
    key = hookio.granted_opt_out(command)
    if key:
        asks.append(f"it sets \"{key}\": true, which switches a guard off for this project — "
                    f"that is the user's decision, not the model's")
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
        hookio.deny(f"BLOCKED: {reason}.")
    elif decision == "ask":
        hookio.ask(f"Confirm: {reason}.")
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
