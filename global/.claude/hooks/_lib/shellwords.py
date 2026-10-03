"""Shell-aware command parsing shared by dotclaude's Python guard hooks.

A regex over the raw command line is wrong in both directions (DESIGN.md §18):
it blocks innocent text (a commit message that mentions "git push") and misses
real commands written in a wrapped form (`git -C /repo push`). These helpers
split a command into the commands it actually runs, with quotes resolved, so a
hook judges the arguments of the command itself. Ported from
guard-push-main.sh, whose case matrix found every rule below the hard way.
"""

import re
import shlex

# A heredoc body piped into `cat > file` / `tee file` is data being written,
# not executed; one fed to an interpreter (`bash <<EOF`) runs, so it is kept.
# Unknown shapes fail closed: the body stays in the scanned text.
_WRITER = re.compile(r"""
    ^\s*
    (?:cat\s*>{1,2}\s*[^\s|;&<>()]+
      |tee\s+(?:-a\s+)?[^\s|;&<>()]+)
    \s*<<-?\s*["']?[A-Za-z_][A-Za-z0-9_]*["']?\s*$
""", re.X)
_UNSAFE = re.compile(r"[|`]|\$\(|;|&&|\|\||\bsh\b|\bbash\b|\bzsh\b|\bssh\b|\bdocker\b"
                     r"|\bkubectl\b|\beval\b|\bpython[0-9.]*\b|\bnode\b|\bperl\b|\bruby\b")
_HEREDOC = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")

OPERATORS = ("&&", "||", ";", "|", "&")
GIT_VALUED_GLOBALS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
# Prefix commands that run the next word as the real command.
WRAPPERS = ("env", "command", "nohup", "time", "nice", "exec", "builtin")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def strip_writer_heredocs(cmd):
    """Drop the bodies of heredocs that only write a file; keep executed ones."""
    lines = cmd.split("\n")
    kept, i = [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        m = _HEREDOC.search(line)
        if not m or not _WRITER.match(line) or _UNSAFE.search(line):
            i += 1
            continue
        delim = m.group(1)
        j = i + 1
        while j < len(lines) and lines[j].strip() != delim:
            j += 1
        if j >= len(lines):
            i += 1
            continue
        kept.append(lines[j])
        i = j + 1
    return "\n".join(kept)


def _newlines_to_separators(cmd):
    # shlex folds newlines into whitespace, which once merged `git add -A` and a
    # following `git push origin main` into one command judged by its first word.
    res, quote, k, n = [], None, 0, len(cmd)
    while k < n:
        ch = cmd[k]
        if quote:
            if ch == "\\" and quote == '"' and k + 1 < n:
                res.append(ch)
                res.append(cmd[k + 1])
                k += 2
                continue
            if ch == quote:
                quote = None
            res.append(ch)
            k += 1
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "\\" and k + 1 < n and cmd[k + 1] == "\n":
            res.append(" ")
            k += 2
            continue
        elif ch == "\n":
            res.append(" ; ")
            k += 1
            continue
        res.append(ch)
        k += 1
    return "".join(res)


def segments(cmd):
    """Split `cmd` into the token lists of the commands it runs.

    Returns None when the quoting is unbalanced: such a command cannot be
    judged reliably, and each caller decides whether that fails open or closed.
    """
    text = _newlines_to_separators(strip_writer_heredocs(cmd))
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    out, current = [], []
    for tok in tokens:
        if tok in OPERATORS or (tok and set(tok) <= set(";&|")):
            out.append(current)
            current = []
        else:
            current.append(tok)
    out.append(current)
    return [s for s in out if s]


def unwrap(seg):
    """Drop leading env assignments and wrapper commands (`env`, `command`, ...)."""
    i = 0
    while i < len(seg):
        w = seg[i]
        if _ASSIGNMENT.match(w):
            i += 1
        elif basename(w) in WRAPPERS:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1
        else:
            break
    return seg[i:]


def basename(word):
    """The program name of `word`: path and a trailing .exe removed."""
    name = re.split(r"[/\\]", word)[-1]
    return name[:-4] if name.lower().endswith(".exe") else name


def git_invocation(seg):
    """For a segment that runs git, return (subcommand, args, global_opts).

    `global_opts` maps each global flag to its value (`-C` -> path) so a hook can
    run its own git queries in the same repository. Returns None for anything
    that is not a git invocation.
    """
    seg = unwrap(seg)
    if not seg or basename(seg[0]) != "git":
        return None
    rest = seg[1:]
    opts, i = {}, 0
    while i < len(rest):
        w = rest[i]
        if not w.startswith("-"):
            return w, rest[i + 1:], opts
        if w in GIT_VALUED_GLOBALS and i + 1 < len(rest):
            opts.setdefault(w, []).append(rest[i + 1])
            i += 2
            continue
        i += 1
    return None
