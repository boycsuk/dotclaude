# hook-kind: guard
"""PreToolUse hook on Bash: enforce the commit conventions the rules only asked for.

Deny (the commit would break a hard rule):
  - an attribution trailer: Co-Authored-By / Signed-off-by lines, -s,
    --signoff, --trailer. Opt-out: "allowCommitTrailers": true in
    .claude/settings.local.json (e.g. a project that requires DCO sign-off);
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
is never mistaken for the real thing (DESIGN.md §18, §35).
"""

import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import shellwords  # noqa: E402

TRAILER_LINE = re.compile(r"(?im)^\s*(co-authored-by|signed-off-by)\s*:")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
SPANISH_WORDS = {
    "de", "del", "la", "las", "el", "los", "que", "para", "por", "con", "una", "un",
    "se", "al", "como", "pero", "sin", "sobre", "cuando", "también", "añade", "añadir",
    "corrige", "arregla", "actualiza", "elimina", "mejora", "cambia", "nuevo", "nueva",
}
SPANISH_MARKS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
SHORT_WITH_VALUE = set("mFCct")      # git commit short options that take a value
LONG_WITH_VALUE = {"--message", "--file", "--reuse-message", "--reedit-message",
                   "--template", "--author", "--date", "--cleanup", "--fixup", "--squash",
                   "--pathspec-from-file", "--trailer", "--gpg-sign"}
HEREDOC_BODY = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?[^\n]*\n(.*?)\n\s*\1\s*(?:\n|$|\))", re.S)
ALL_PATHS = {"-A", "--all", ".", "-u", "--update", ":/", "*"}


def parse_commit(args):
    """Split `git commit` args into (flags set, message parts, -F files)."""
    flags, messages, files = set(), [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            flags.add(name)
            if name in LONG_WITH_VALUE and not eq:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if name == "--message":
                messages.append(value)
            elif name == "--file":
                files.append(value)
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
    return flags, messages, files


def unwrap_message(text):
    """`$(cat <<'EOF' ... EOF)` command substitutions carry the body inline."""
    bodies = [m.group(2) for m in HEREDOC_BODY.finditer(text)]
    return "\n".join(bodies) if bodies else text


def git(opts, cwd, *argv):
    cmd = ["git"]
    for flag in ("-C", "--git-dir", "--work-tree"):
        for value in opts.get(flag, []):
            cmd += [flag, value]
    try:
        out = subprocess.run(cmd + list(argv), cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def read_message_file(path, raw_cmd, base):
    if path == "-":
        return "\n".join(m.group(2) for m in HEREDOC_BODY.finditer(raw_cmd))
    try:
        with open(os.path.join(base, path), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def is_spanish(message):
    if not SPANISH_MARKS.search(message):
        return False
    words = set(re.findall(r"[a-záéíóúñü]+", re.sub(r"`[^`]*`", " ", message.lower())))
    return len(words & SPANISH_WORDS) >= 2


def changed_paths(opts, cwd, flags, earlier_adds):
    """Paths the commit will include, counting `git add` run earlier in the same command."""
    paths = set((git(opts, cwd, "diff", "--cached", "--name-only") or "").split())
    status = git(opts, cwd, "status", "--porcelain") or ""
    worktree = {line[3:].split(" -> ")[-1].strip('"') for line in status.splitlines() if len(line) > 3}
    tracked_modified = {line[3:].strip('"') for line in status.splitlines()
                        if len(line) > 3 and line[1] in "MD"}
    if "-a" in flags or "--all" in flags:
        paths |= tracked_modified
    for add_args in earlier_adds:
        specs = [a for a in add_args if not a.startswith("-") or a in ALL_PATHS]
        if not specs or any(s in ALL_PATHS for s in specs):
            paths |= worktree
        else:
            for spec in specs:
                spec = spec.rstrip("/")
                paths |= {p for p in worktree if p == spec or p.startswith(spec + "/")}
    return paths


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


def judge(segment_args, opts, raw_cmd, cwd, payload, earlier_adds):
    flags, messages, files = parse_commit(segment_args)
    base = (opts.get("-C") or [cwd])[-1]
    base = base if os.path.isabs(base) else os.path.join(cwd, base)
    message = "\n".join([unwrap_message(m) for m in messages]
                        + [read_message_file(f, raw_cmd, base) for f in files])

    denials = []
    if not hookio.local_opt_out(payload, "allowCommitTrailers"):
        if TRAILER_LINE.search(message) or flags & {"-s", "--signoff", "--trailer"}:
            denials.append("it adds an attribution trailer (Co-Authored-By / Signed-off-by / "
                           "--signoff / --trailer). Remove it — commits carry no AI or sign-off "
                           "trailer (set \"allowCommitTrailers\": true in .claude/settings.local.json "
                           "if this project requires one)")
    if EMOJI.search(message):
        denials.append("the message contains an emoji; commit messages are plain text")
    if is_spanish(message):
        denials.append("the message is in Spanish; commit messages are written in English")
    if denials:
        return "deny", "BLOCKED commit: " + "; ".join(denials) + "."

    asks = []
    if "--amend" in flags:
        asks.append("--amend rewrites the previous commit (prefer a new commit)")
    branch = (git(opts, cwd, "symbolic-ref", "--quiet", "--short", "HEAD") or "").strip()
    if branch in ("main", "master") and not hookio.local_opt_out(payload, "allowPushToMain"):
        asks.append(f"this commits directly on {branch} (work on a feature/fix branch)")
    root = (git(opts, cwd, "rev-parse", "--show-toplevel") or "").strip()
    paths = changed_paths(opts, cwd, flags, earlier_adds) if root else set()
    if paths and os.path.exists(os.path.join(root, "CHANGELOG.md")) and "CHANGELOG.md" not in paths:
        asks.append("the repo keeps a CHANGELOG.md but this commit does not update it")
    asks += twin_problems(paths, root)
    if asks:
        return "ask", "Confirm this commit: " + "; ".join(asks) + "."
    return None, None


def main():
    payload = hookio.read_payload()
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or "commit" not in command:
        return 0
    segments = shellwords.segments(command)
    if not segments:
        return 0
    cwd = hookio.project_dir(payload) if not payload.get("cwd") else payload["cwd"]
    earlier_adds = []
    verdicts = []
    for seg in segments:
        inv = shellwords.git_invocation(seg)
        if not inv:
            continue
        sub, args, opts = inv
        if sub == "add":
            earlier_adds.append(args)
        elif sub == "commit":
            verdicts.append(judge(args, opts, command, cwd, payload, earlier_adds))
    for decision, reason in verdicts:
        if decision == "deny":
            hookio.deny(reason)
            return 0
    asks = [reason for decision, reason in verdicts if decision == "ask"]
    if asks:
        hookio.ask(" ".join(asks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
