# hook-kind: guard
"""PreToolUse hook on Bash/PowerShell: enforce the commit conventions the rules only asked for.

Deny (the commit would break a hard rule):
  - an attribution trailer: Co-Authored-By / Signed-off-by lines, -s,
    --signoff, or --trailer with one of those keys. Opt-out:
    "allowCommitTrailers": true in .claude/settings.local.json (e.g. a project
    that requires DCO sign-off);
  - an emoji in the message;
  - a message written in Spanish (strong signal only: two or more Spanish
    function words AND an accented letter, ñ, ¿ or ¡).
Ask (legitimate, but the user decides):
  - --amend (rewrites the last commit);
  - committing on main/master, unless "allowPushToMain" opts the project out;
  - the repo has a CHANGELOG.md and the commit does not include it;
  - X.sh is committed without its existing X.ps1 twin, or the reverse.

Everything is judged on the parsed `git commit` invocation (shellwords), so a
message that merely mentions these words, or a heredoc that only writes a file,
is never mistaken for the real thing. Known gap: a
message piped in from another command (`printf ... | git commit -F -`) is not
read.
"""

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import bootstrap  # noqa: E402,F401
import hookio  # noqa: E402

ATTRIBUTION_KEYS = ("co-authored-by", "signed-off-by")
TRAILER_LINE = re.compile(r"(?im)^\s*(co-authored-by|signed-off-by)\s*:")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
SPANISH_WORDS = {
    "de", "del", "la", "las", "el", "los", "que", "para", "por", "con", "una", "un",
    "se", "al", "como", "pero", "sin", "sobre", "cuando", "también", "añade", "añadir",
    "corrige", "arregla", "actualiza", "elimina", "mejora", "cambia", "nuevo", "nueva",
}
SPANISH_MARKS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
SHORT_WITH_VALUE = set("mFCct")      # git commit short options that take a value
# Every long option of `git commit`, so an abbreviation git would accept
# (`--signo`, `--mess`) resolves exactly as git resolves it: a unique prefix.
LONG_OPTIONS = {
    "all": False, "patch": False, "reuse-message": True, "reedit-message": True, "fixup": True,
    "squash": True, "reset-author": False, "short": False, "branch": False, "porcelain": False,
    "long": False, "null": False, "file": True, "author": True, "date": True, "message": True,
    "template": True, "signoff": False, "no-signoff": False, "trailer": True, "no-verify": False,
    "verify": False, "allow-empty": False, "allow-empty-message": False, "cleanup": True,
    "edit": False, "no-edit": False, "amend": False, "no-post-rewrite": False, "include": False,
    "only": False, "pathspec-from-file": True, "pathspec-file-nul": False,
    "untracked-files": False, "verbose": False, "quiet": False, "dry-run": False,
    "status": False, "no-status": False, "gpg-sign": False, "no-gpg-sign": False,
}
ALL_PATHS = {"-A", "--all", ".", "-u", "--update", ":/", "*"}
GIT_TIMEOUT = 3
HUNK = re.compile(r"^@@ -\S+ \+(\d+)")
SCAN_LIMIT = 200_000                 # characters of added text scanned per path


def canonical_long(name):
    """Resolve `--signo` to `--signoff` the way git does; unknown/ambiguous stay as given."""
    bare = name[2:]
    if bare in LONG_OPTIONS:
        return name
    matches = [o for o in LONG_OPTIONS if o.startswith(bare)] if bare else []
    return "--" + matches[0] if len(matches) == 1 else name


def parse_commit(args):
    """Split `git commit` args into (flags, messages, -F files, --trailer values)."""
    flags, messages, files, trailers = set(), [], [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            raw, eq, value = a.partition("=")
            name = canonical_long(raw)
            flags.add(name)
            if LONG_OPTIONS.get(name[2:]) and not eq:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if name == "--message":
                messages.append(value)
            elif name == "--file":
                files.append(value)
            elif name == "--trailer":
                trailers.append(value)
        elif a.startswith("-") and len(a) > 1:
            j = 1
            while j < len(a):
                ch = a[j]
                flags.add("-" + ch)
                if ch == "S":
                    break                       # -S[keyid]: the rest is its value
                if ch in SHORT_WITH_VALUE:
                    value = a[j + 1:]
                    if not value:
                        value = args[i + 1] if i + 1 < len(args) else ""
                        i += 1
                    if ch == "m":
                        messages.append(value)
                    elif ch == "F":
                        files.append(value)
                    break
                j += 1
        i += 1
    return flags, messages, files, trailers


def git(opts, cwd, *argv):
    import subprocess                            # only once the prefilter saw a commit
    cmd = ["git"]
    for flag in ("-C", "--git-dir", "--work-tree"):
        for value in opts.get(flag, []):
            cmd += [flag, value]
    try:
        out = subprocess.run(cmd + list(argv), cwd=cwd, capture_output=True, text=True,
                             timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return out.stdout if out.returncode == 0 else None


def read_message_file(path, docs, base):
    """The text of `-F <path>`: a heredoc for `-`, a file written earlier in the command, or disk."""
    if path == "-":
        return "\n".join(d["body"] for d in docs
                         if "commit" in d["header"] and d["target"] is None)
    for doc in docs:
        if doc["target"] and os.path.normpath(doc["target"]) == os.path.normpath(path):
            return doc["body"]
    try:
        with open(os.path.join(base, path), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def is_spanish(message):
    if not SPANISH_MARKS.search(message):
        return False
    # Whole words only: "de-duplicate" and "un-wrap" are English prefixes.
    words = set(re.findall(r"(?<![\w-])[a-záéíóúñü]+(?![\w-])", re.sub(r"`[^`]*`", " ", message.lower())))
    return len(words & SPANISH_WORDS) >= 2


def _z_paths(text):
    return [p for p in (text or "").split("\0") if p]


def repo_state(opts, cwd, root):
    """Branch and changed paths of the repo, from one `git status --porcelain=v2 --branch` call.

    Untracked files are listed one by one: `?? lib/` would hide lib/new.py
    from the checks. Paths are relative to the repo root.
    """
    state = {"branch": "", "staged": set(), "worktree": set(), "tracked_modified": set()}
    if not root:
        return state
    records = _z_paths(git(opts, cwd, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"))
    skip = False
    for rec in records:
        if skip:                                # the original path of a rename or copy
            skip = False
            continue
        if rec.startswith("# branch.head "):
            state["branch"] = rec[len("# branch.head "):]
            continue
        kind = rec[:1]
        if kind == "?":
            state["worktree"].add(rec[2:])
            continue
        fields = {"1": 8, "2": 9, "u": 10}.get(kind)
        parts = rec.split(" ", fields) if fields else []
        if len(parts) <= (fields or 0):
            continue
        xy, path = parts[1], parts[fields]
        state["worktree"].add(path)
        if xy[0] != ".":
            state["staged"].add(path)
        if xy[1] in "MD":
            state["tracked_modified"].add(path)
        skip = kind == "2"
    return state


def changed_paths(state, prefix, flags, earlier_adds):
    """Root-relative paths the commit will include, counting `git add` earlier in the command."""
    paths = set(state["staged"])
    worktree = state["worktree"]
    if "-a" in flags or "--all" in flags:
        paths |= state["tracked_modified"]
    for add_args in earlier_adds:
        specs = [a for a in add_args if not a.startswith("-") or a in ALL_PATHS]
        if not specs or any(s in ALL_PATHS for s in specs):
            paths |= worktree
            continue
        for spec in specs:
            spec = os.path.normpath(os.path.join(prefix, spec)).replace("\\", "/")
            paths |= {p for p in worktree if p == spec or p.startswith(spec + "/")}
    return paths


def added_lines(diff):
    """(path, new-file line number, text) for each added line of a unified diff."""
    path, lineno = None, 0
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = HUNK.match(line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            yield path, lineno, line[1:]
            lineno += 1
        elif line.startswith(" "):
            lineno += 1


def secret_problems(paths, opts, cwd, root, staged):
    """What in this commit looks secret: a secret-bearing path, or an added line holding a literal secret.

    What gets committed is the index for a staged path and the working tree for
    one an earlier `git add` or `-a` will stage, so each is read from there; an
    untracked file is read whole. Messages name the file, line and kind, never
    the value.
    """
    problems, scanned, found = [], {}, {}
    import secretrules
    flagged = sorted(p for p in paths if secretrules.secret_path(p))
    problems += [f"{p} looks like it holds secrets and would be committed" for p in flagged]
    rest = sorted(set(paths) - set(flagged))
    if not rest:
        return problems

    def scan(path, lineno, text):
        if path in found or scanned.get(path, 0) > SCAN_LIMIT:
            return
        scanned[path] = scanned.get(path, 0) + len(text)
        kind = secretrules.line_secret(text)
        if kind:
            found[path] = (lineno, kind)

    for source, chosen in (("--cached", [p for p in rest if p in staged]),
                           ("HEAD", [p for p in rest if p not in staged])):
        if not chosen:
            continue
        diff = git(opts, cwd, "-c", "core.quotepath=false", "diff", source, "-U0", "--no-color", "--",
                   *[f":(top,literal){p}" for p in chosen])
        for path, lineno, text in added_lines(diff):
            scan(path, lineno, text)
        if source == "HEAD":
            seen = {p for p, _, _ in added_lines(diff)}
            for path in chosen:
                if path not in seen:
                    for lineno, text in untracked_lines(root, path):
                        scan(path, lineno, text)
    problems += [f"{p} line {n} adds {kind}" for p, (n, kind) in sorted(found.items())]
    return problems


def untracked_lines(root, path):
    """(line number, text) of a file git does not track yet; nothing for a binary or unreadable one."""
    try:
        with open(os.path.join(root, path), "rb") as fh:
            data = fh.read(SCAN_LIMIT)
    except OSError:
        return []
    if b"\0" in data:
        return []
    return list(enumerate(data.decode("utf-8", "replace").splitlines(), 1))


def twin_problems(paths, root):
    problems = []
    for path in sorted(paths):
        stem, ext = os.path.splitext(path)
        twin_ext = {".sh": ".ps1", ".ps1": ".sh"}.get(ext)
        if not twin_ext:
            continue
        twin = stem + twin_ext
        if twin not in paths and root and os.path.exists(os.path.join(root, twin)):
            problems.append(f"{path} is committed without its twin {twin}")
    return problems


def judge(segment_args, opts, docs, cwd, payload, earlier_adds):
    flags, messages, files, trailers = parse_commit(segment_args)
    base = (opts.get("-C") or [cwd])[-1]
    base = base if os.path.isabs(base) else os.path.join(cwd, base)
    message = "\n".join(messages + [read_message_file(f, docs, base) for f in files])
    # The opt-outs belong to the repository being committed to, not to the
    # session's project — the bug 016b17b fixed for pushes.
    top = (git(opts, cwd, "rev-parse", "--show-toplevel", "--show-prefix") or "").split("\n")
    root, prefix = top[0].strip(), (top[1].strip() if len(top) > 1 else "")

    denials = []
    if not hookio.local_opt_out(payload, "allowCommitTrailers", root=root or None):
        attribution_trailer = any(t.split(":", 1)[0].split("=", 1)[0].strip().lower() in ATTRIBUTION_KEYS
                                  for t in trailers)
        if TRAILER_LINE.search(message) or flags & {"-s", "--signoff"} or attribution_trailer:
            denials.append("it adds an attribution trailer (Co-Authored-By / Signed-off-by / "
                           "--signoff). Remove it — commits carry no AI or sign-off trailer. A "
                           "project that requires one is the user's call: they set "
                           "\"allowCommitTrailers\": true in .claude/settings.local.json themselves")
    if EMOJI.search(message):
        denials.append("the message contains an emoji; commit messages are plain text")
    if is_spanish(message):
        denials.append("the message is in Spanish; commit messages are written in English")
    if denials:
        return "deny", "BLOCKED commit: " + "; ".join(denials) + "."

    asks = []
    if "--amend" in flags:
        asks.append("--amend rewrites the previous commit (prefer a new commit)")
    state = repo_state(opts, cwd, root)
    branch = state["branch"]
    if branch in ("main", "master") and not hookio.local_opt_out(payload, "allowPushToMain", root=root or None):
        asks.append(f"this commits directly on {branch} (work on a feature/fix branch)")
    paths = changed_paths(state, prefix, flags, earlier_adds) if root else set()
    if paths and os.path.exists(os.path.join(root, "CHANGELOG.md")) and "CHANGELOG.md" not in paths:
        asks.append("the repo keeps a CHANGELOG.md but this commit does not update it")
    asks += twin_problems(paths, root)
    asks += secret_problems(paths, opts, cwd, root, state["staged"]) if paths else []
    if asks:
        return "ask", "Confirm this commit: " + "; ".join(asks) + "."
    return None, None


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not hookio.mentions(command, "commit"):
        return 0
    import shellwords                            # loaded only past the prefilter: most commands never get here
    shell = shellwords.shell_of(payload)
    segments = shellwords.segments(command, shell)
    if not segments:
        return 0
    docs = shellwords.heredocs(command, shell)
    cwd = payload.get("cwd") or hookio.project_dir(payload)
    earlier_adds, verdicts = [], []
    for seg in segments:
        target = shellwords.chdir_target(shellwords.unwrap(seg))
        if target is not None:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        inv = shellwords.git_invocation(seg)
        if not inv:
            continue
        sub, args, opts = inv
        if sub == "add":
            earlier_adds.append(args)
        elif sub == "commit":
            verdicts.append(judge(args, opts, docs, cwd, payload, earlier_adds))
    for decision, reason in verdicts:
        if decision == "deny":
            hookio.deny(reason)
            return 0
    asks = [reason for decision, reason in verdicts if decision == "ask"]
    if asks:
        hookio.ask(" ".join(asks))
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
