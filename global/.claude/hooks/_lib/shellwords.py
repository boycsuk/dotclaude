"""Shell-aware command parsing shared by dotclaude's Python guard hooks.

A regex over the raw command line is wrong in both directions (DESIGN.md §18):
it blocks innocent text (a commit message that mentions "git push") and misses
real commands written in a wrapped form (`git -C /repo push`). These helpers
split a command into the commands it actually runs, with quotes resolved, so a
hook judges the arguments of the command itself. The core is ported from
guard-push-main.sh; the wrapper, subshell, `bash -c`, heredoc and PowerShell
handling exist because a review found each one bypassing guard-commit.
"""

import re
import shlex

# A heredoc fed to a shell runs as commands; any other heredoc (cat > file,
# git commit -F -, python) is data and must not be parsed as shell.
_HEREDOC = re.compile(r"<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SHELL_FED = re.compile(r"(^|[\s;&|(])(ba|z|k|da)?sh(\s|$)")
_WRITER_TARGET = re.compile(r"(?:\bcat\s*>{1,2}\s*|\btee\s+(?:-a\s+)?)([^\s|;&<>()]+)")
# "$(cat <<'EOF' ... EOF)" — the form Claude uses for multi-line messages. The
# body may hold quotes and apostrophes that shlex cannot balance, so the whole
# substitution is replaced by its body, quoted, before tokenising.
_CAT_SUBST = re.compile(
    r"(\"?)\$\(\s*cat\s+<<-?\s*(['\"]?)([A-Za-z_]\w*)\2[ \t]*\n(.*?)\n[ \t]*\3[ \t]*\n?\s*\)\1", re.S)
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
_ANSI_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "e": "\x1b", "0": "\0"}
_PS_HERESTRING = re.compile(r"@(['\"])[ \t]*\r?\n(.*?)\r?\n\1@", re.S)

SEPARATOR_CHARS = set(";&|()")
GIT_VALUED_GLOBALS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "fi", "done", "time"}
# Prefix commands that run another command, with the options of each that
# consume a value (`timeout -s KILL 60 cmd`, `nice -n 5 cmd`, `env -u X cmd`).
WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "command": set(), "builtin": set(), "exec": {"-a"}, "nohup": set(), "time": {"-f", "-o"},
    "nice": {"-n", "--adjustment"}, "ionice": {"-c", "-n", "-p"}, "chronic": set(),
    "stdbuf": {"-i", "-o", "-e"}, "caffeinate": {"-t", "-w"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-i", "-n", "-L", "-l", "-P", "-d", "-E", "-e", "-a", "-s", "--max-args",
              "--max-procs", "--delimiter", "--arg-file", "--replace"},
}
_POSITIONAL_ARG_WRAPPERS = {"timeout"}          # `timeout 60 cmd`: the duration comes first
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _quote(text):
    return shlex.quote(text)


def _decode_ansi_c(body):
    return re.sub(r"\\(.)", lambda m: _ANSI_ESCAPES.get(m.group(1), "\\" + m.group(1)), body)


def _from_powershell(cmd):
    """Rewrite the PowerShell syntax a command line commonly uses into POSIX form."""
    def herestring(m):
        body = m.group(2)
        if m.group(1) == '"':
            body = _ps_unescape(body)
        return _quote(body)
    cmd = _PS_HERESTRING.sub(herestring, cmd)
    cmd = re.sub(r"`\r?\n", " ", cmd)           # backtick line continuation
    return _ps_unescape(cmd)


def _ps_unescape(text):
    return (text.replace("`r`n", "\n").replace("`n", "\n").replace("`t", "\t")
            .replace('`"', '\\"').replace("``", "`"))


def normalize(cmd, shell="bash"):
    """Resolve the constructs shlex cannot: PowerShell syntax, cat-heredoc substitutions, $'...'."""
    if shell == "powershell":
        cmd = _from_powershell(cmd)
    cmd = _CAT_SUBST.sub(lambda m: _quote(m.group(4)), cmd)
    return _ANSI_C.sub(lambda m: _quote(_decode_ansi_c(m.group(1))), cmd)


def heredocs(cmd, shell="bash"):
    """Every data heredoc in `cmd`: dicts with header (its command line), body and writer target."""
    return _split_heredocs(normalize(cmd, shell))[1]


def _split_heredocs(cmd):
    lines = cmd.split("\n")
    kept, found, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        m = _HEREDOC.search(line)
        if not m:
            i += 1
            continue
        delim = m.group(2)
        j = i + 1
        while j < len(lines) and lines[j].strip() != delim:
            j += 1
        if j >= len(lines):                       # unterminated: leave it to the tokenizer
            i += 1
            continue
        if _SHELL_FED.search(line[:m.start()]):
            i += 1                                # executed: its body is more commands
            continue
        target = _WRITER_TARGET.search(line[:m.start()])
        found.append({"header": line, "body": "\n".join(lines[i + 1:j]),
                      "target": target.group(1) if target else None})
        i = j + 1
    return "\n".join(kept), found


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


def segments(cmd, shell="bash", _depth=0):
    """Split `cmd` into the token lists of the commands it runs.

    Subshells, braces and if/while bodies are flattened; `bash -c "..."` is
    parsed recursively. Returns None when the quoting is unbalanced: such a
    command cannot be judged reliably, and each caller decides whether that
    fails open or closed.
    """
    text = _split_heredocs(normalize(cmd, shell))[0]
    try:
        lexer = shlex.shlex(_newlines_to_separators(text), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    out, current = [], []
    for tok in tokens:
        if tok and set(tok) <= SEPARATOR_CHARS:
            out.append(current)
            current = []
        else:
            current.append(tok)
    out.append(current)
    result = []
    for seg in out:
        while seg and seg[0] in KEYWORDS:
            seg = seg[1:]
        if not seg:
            continue
        result.append(seg)
        inner = _shell_c_argument(seg)
        if inner is not None and _depth < 3:
            nested = segments(inner, "bash", _depth + 1)
            if nested:
                result.extend(nested)
    return result


def _shell_c_argument(seg):
    seg = unwrap(seg)
    if not seg or basename(seg[0]) not in SHELLS:
        return None
    for i, arg in enumerate(seg[1:], 1):
        if re.fullmatch(r"-[a-z]*c[a-z]*", arg) and i + 1 < len(seg):
            return seg[i + 1]
    return None


def unwrap(seg):
    """Drop leading env assignments and wrapper commands (`env`, `timeout 60`, `xargs`, ...)."""
    i = 0
    while i < len(seg):
        w = seg[i]
        name = basename(w)
        if _ASSIGNMENT.match(w):
            i += 1
            continue
        if name not in WRAPPERS:
            break
        valued = WRAPPERS[name]
        i += 1
        while i < len(seg) and seg[i].startswith("-"):
            flag = seg[i].split("=", 1)[0]
            i += 2 if flag in valued and "=" not in seg[i] else 1
        if name in _POSITIONAL_ARG_WRAPPERS and i < len(seg):
            i += 1
    return seg[i:]


def basename(word):
    """The program name of `word`: path and a trailing .exe removed."""
    name = re.split(r"[/\\]", word)[-1]
    return name[:-4] if name.lower().endswith(".exe") else name


def git_invocation(seg):
    """For a segment that runs git, return (subcommand, args, global_opts).

    `global_opts` maps each global flag to its values (`-C` -> [path]) so a hook
    can run its own git queries in the same repository. Returns None for
    anything that is not a git invocation.
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


def shell_of(payload):
    """'powershell' when the hook fired for Claude Code's PowerShell tool."""
    return "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
