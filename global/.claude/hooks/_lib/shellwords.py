"""Shell-aware command parsing shared by dotclaude's Python guard hooks.

A regex over the raw command line is wrong in both directions:
it blocks innocent text (a commit message that mentions "git push") and misses
real commands written in a wrapped form (`git -C /repo push`). These helpers
split a command into the commands it actually runs, with quotes resolved, so a
hook judges the arguments of the command itself. The wrapper, subshell,
`bash -c`, heredoc and PowerShell handling exist because a review found each
one bypassing guard-commit; comment, substitution and heredoc-allowlist
handling because an audit found each one bypassing guard-push-main.
"""

import re
import shlex

# A heredoc body is DATA only when the command it feeds is known to read it as
# data: a file writer (`cat > f`, `tee f`) or `git commit -F -`. Anything else
# — a shell, ssh, docker exec, an interpreter, an unknown program — may run it,
# so its body stays in the parsed text: unknown shapes fail closed. Even a data body runs its $( ) and backticks when the delimiter is
# unquoted; those are extracted and parsed as commands.
_HEREDOC = re.compile(r"(?<!<)<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1")
_WRITER_TARGET = re.compile(r"(?:\bcat\s*>{1,2}\s*|\btee\s+(?:-a\s+)?)([^\s|;&<>()]+)")
_COMMIT_STDIN = re.compile(r"\bcommit\b.*(?:\s-[A-Za-z]*F\s*-(?:\s|$)|\s--file(?:=|\s+)-(?:\s|$))")
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
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir", "-h", "--host",
             "-p", "--prompt", "-r", "--role", "-t", "--type", "-U", "--other-user", "-T",
             "--command-timeout"},
    "doas": {"-u", "-C"},
}
_POSITIONAL_ARG_WRAPPERS = {"timeout"}          # `timeout 60 cmd`: the duration comes first
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _quote(text):
    return shlex.quote(text)


def _decode_ansi_c(body):
    return re.sub(r"\\(.)", lambda m: _ANSI_ESCAPES.get(m.group(1), "\\" + m.group(1)), body)


def _from_powershell(cmd):
    """Rewrite the PowerShell syntax a command line commonly uses into POSIX form."""
    # A backslash is an ordinary character in PowerShell (C:\Users\x); POSIX
    # tokenizing would read it as an escape and mangle every Windows path.
    cmd = cmd.replace("\\", "\\\\")

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
    executed = []

    def cat_subst(m):
        # The body becomes one quoted word, but with an unquoted delimiter its
        # own $( ) still runs: those are appended as commands of their own.
        if not m.group(2):
            executed.extend(substitutions(m.group(4), in_heredoc=True))
        return _quote(m.group(4))
    cmd = _CAT_SUBST.sub(cat_subst, cmd)
    cmd = _ANSI_C.sub(lambda m: _quote(_decode_ansi_c(m.group(1))), cmd)
    return "\n".join([cmd] + executed)


def heredocs(cmd, shell="bash"):
    """Every data heredoc in `cmd`: dicts with header (its command line), body and writer target."""
    return _split_heredocs(normalize(cmd, shell))[1]


def _split_heredocs(cmd):
    """(text with data-heredoc bodies removed, the data heredocs found)."""
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
        header = line[:m.start()]
        target = _WRITER_TARGET.search(header)
        body = "\n".join(lines[i + 1:j])
        rest = "\n".join(lines[j + 1:])
        if (not target and not _COMMIT_STDIN.search(header)) or \
                (target and _runs_file(target.group(1), rest)):
            i += 1                                # executed: its body is more commands
            continue
        found.append({"header": line, "body": body, "target": target.group(1) if target else None})
        if not m.group(1):                        # unquoted: $( ) in the body still runs
            kept.extend(substitutions(body, in_heredoc=True))
        i = j + 1
    return "\n".join(kept), found


def _runs_file(path, text):
    """True when `text` executes the file `path` (written by a heredoc earlier in the command)."""
    name = re.escape(path)
    base = re.escape(re.split(r"[/\\]", path)[-1])
    return bool(re.search(
        rf"(^|[\s;&|(])((ba|z|da|k)?sh|source|\.|python[0-9.]*|perl|ruby|node)\s+(-\S+\s+)*(\./)?{name}(\s|$|;)"
        rf"|(^|[\s;&|(])\./{base}(\s|$|;)", text))


def substitutions(text, in_heredoc=False):
    """The inner text of every top-level `$( )` and backtick substitution in `text`.

    Single-quoted text is inert; double-quoted text is not, which is why a
    tokenizer alone misses `echo "$(git push origin main)"`. Arithmetic `$((`
    is skipped. With `in_heredoc`, quotes are literal characters, as they are
    in an unquoted heredoc body.
    """
    found, quote, i, n = [], None, 0, len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if not in_heredoc and ch == "'" and quote is None:
            quote = "'"
        elif not in_heredoc and ch == '"':
            quote = None if quote == '"' else '"'
        elif text.startswith("$((", i):
            i += 3
            continue
        elif text.startswith("$(", i):
            end = _closing_paren(text, i + 2)
            found.append(text[i + 2:end])
            i = end + 1
            continue
        elif ch == "`":
            end = text.find("`", i + 1)
            end = n if end == -1 else end
            found.append(text[i + 1:end])
            i = end + 1
            continue
        i += 1
    return [f for f in found if f.strip()]


def _closing_paren(text, start):
    depth, quote, i = 1, None, start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"':
                i += 1
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


def _newlines_to_separators(cmd):
    # shlex folds newlines into whitespace, which once merged `git add -A` and a
    # following `git push origin main` into one command judged by its first word.
    # Comments end at their own newline: left to shlex (whose commenter runs to
    # the end of the whole input once newlines are separators), `ls # x` hid
    # every later line, and an apostrophe in one aborted the parse.
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
        elif ch == "#" and (k == 0 or cmd[k - 1].isspace() or cmd[k - 1] in ";&|()"):
            while k < n and cmd[k] != "\n":
                k += 1
            continue
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

    Subshells, braces and if/while bodies are flattened; `bash -c "..."` and
    every `$( )` / backtick substitution are parsed recursively. Returns None
    when the quoting is unbalanced: such a command cannot be judged reliably,
    and each caller decides whether that fails open or closed.
    """
    text = _split_heredocs(normalize(cmd, shell))[0]
    try:
        lexer = shlex.shlex(_newlines_to_separators(text), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        lexer.commenters = ""
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
    if _depth < 3:
        for inner in substitutions(_newlines_to_separators(text)):
            nested = segments(inner, "bash", _depth + 1)
            if nested is None:
                return None
            result.extend(s for s in nested if s not in result)
    return result


def code_text(cmd, shell="bash"):
    """`cmd` as the shell will run it: data-heredoc bodies and comments removed, one line.

    For the checks that need the raw shape a token list loses, such as a
    process substitution `bash <(curl ...)`.
    """
    return _newlines_to_separators(_split_heredocs(normalize(cmd, shell))[0])


def pipelines(cmd, shell="bash"):
    """`cmd` split into pipelines, each a list of the segments joined by `|`.

    Returns None when the quoting is unbalanced. Substitutions are not
    descended into; `segments` covers those.
    """
    try:
        lexer = shlex.shlex(code_text(cmd, shell), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    result, pipeline, current = [], [], []
    for tok in tokens + [";"]:
        if tok in ("|", "|&"):
            pipeline.append(current)
            current = []
        elif tok and set(tok) <= SEPARATOR_CHARS:
            pipeline.append(current)
            result.append([seg for seg in pipeline if seg])
            pipeline, current = [], []
        else:
            current.append(tok)
    return [p for p in result if p]


def _shell_c_argument(seg):
    seg = unwrap(seg)
    if seg and seg[0] == "eval":
        return " ".join(seg[1:])                  # eval runs its arguments as a command line
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
