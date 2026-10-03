# hook-kind: guard
"""PreToolUse hook on Bash/PowerShell: block force pushes and direct pushes to main/master.

Deny, never opt-out (they rewrite or delete shared history):
  - a force push: -f / --force* (also bundled, `-uf`, or abbreviated), a
    leading '+' on a refspec, --mirror, or a refspec injected through
    `git -c remote.<name>.push=...`;
  - deleting remote main/master (--delete, -d, or an empty-src `:main`).
Deny unless the target repository opts out with "allowPushToMain": true in its
.claude/settings.local.json:
  - a push whose destination is main/master, named or resolved: a bare push or
    HEAD/@ resolves to the checked-out branch, `--all`/`--branches` include main.

Everything is decided from the parsed `git push` invocation (shellwords), never
from the raw string: matching text blocked a commit message containing "+main",
and matching surface syntax missed `HEAD:main` and glued operators
(DESIGN.md §18). The repository judged is the one the push acts on — the
payload's cwd, then any `cd` and `-C` — so a session project's opt-out never
covers another repo. A command that cannot be parsed but looks like a push is
blocked: an unbalanced quote must not be a way around the guard.
"""

import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import shellwords  # noqa: E402

MAIN_BRANCHES = ("main", "master")
GIT_TIMEOUT = 2
# Every long option of `git push`, so an abbreviation git accepts (`--mirro`)
# resolves the way git resolves it. True = takes a separate value.
LONG_OPTIONS = {
    "all": False, "branches": False, "mirror": False, "delete": False, "tags": False,
    "follow-tags": False, "no-follow-tags": False, "dry-run": False, "porcelain": False,
    "force": False, "force-with-lease": False, "no-force-with-lease": False,
    "force-if-includes": False, "no-force-if-includes": False, "repo": True,
    "set-upstream": False, "thin": False, "no-thin": False, "quiet": False, "verbose": False,
    "progress": False, "no-progress": False, "push-option": True, "receive-pack": True,
    "exec": True, "recurse-submodules": True, "no-recurse-submodules": False, "verify": False,
    "no-verify": False, "signed": False, "no-signed": False, "atomic": False, "no-atomic": False,
    "prune": False, "ipv4": False, "ipv6": False,
}
SHORT_WITH_VALUE = set("o")
FORCE = "force"
# Subcommands git ships; anything else may be an alias defined in git config.
BUILTINS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "checkout",
    "cherry-pick", "clean", "clone", "commit", "config", "describe", "diff", "fetch",
    "format-patch", "gc", "grep", "init", "log", "ls-files", "merge", "mv", "notes", "pull",
    "rebase", "reflog", "remote", "reset", "restore", "revert", "rev-parse", "rm", "show",
    "stash", "status", "submodule", "switch", "tag", "worktree",
}


def git_out(repo, *argv):
    try:
        out = subprocess.run(["git"] + list(argv), cwd=repo, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def canonical_long(raw):
    """`--mirro` -> `--mirror`, as git resolves a unique prefix; else unchanged."""
    bare = raw[2:]
    if bare in LONG_OPTIONS:
        return raw
    matches = [o for o in LONG_OPTIONS if o.startswith(bare)] if bare else []
    if len(matches) == 1:
        return "--" + matches[0]
    if matches and all(m.startswith(FORCE) for m in matches):
        return "--" + FORCE          # ambiguous, but every reading forces
    return raw


def parse_push(args):
    """(flags, positional) of `git push` args, with short flags unbundled."""
    flags, positional, i = set(), [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            raw, eq, _ = a.partition("=")
            name = canonical_long(raw)
            flags.add(name)
            if LONG_OPTIONS.get(name[2:]) and not eq:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 1):
                flags.add("-" + ch)
                if ch in SHORT_WITH_VALUE:
                    if j == len(a) - 1:
                        i += 1
                    break
        else:
            positional.append(a)
        i += 1
    return flags, positional


def alias_target(sub, opts, repo):
    """What a non-builtin subcommand expands to: a `-c alias.x=` value or git config."""
    for value in opts.get("-c", []):
        key, _, expansion = value.partition("=")
        if key.lower() == f"alias.{sub}".lower():
            return expansion
    if sub in BUILTINS or sub.startswith("-"):
        return ""
    return git_out(repo, "config", "--get", f"alias.{sub}")


def is_push(sub, opts, repo):
    if sub == "push":
        return True
    expansion = alias_target(sub, opts, repo).lstrip("!").strip()
    return bool(re.match(r"^(git\s+)?push\b", expansion))


def destination(spec):
    """The branch a refspec lands on: `HEAD:main`, `refs/heads/main`, `heads/main` -> main."""
    dst = spec.split(":")[-1].lstrip("+")
    dst = re.sub(r"^refs/", "", dst)
    return re.sub(r"^heads/", "", dst)


def judge_push(args, opts, repo):
    """(verdict, detail) for one push: FORCE, MIRROR, DELETE, MAIN, or (None, None)."""
    for value in opts.get("-c", []):
        if re.match(r"(?i)remote\.[^=]*\.(push|mirror)=", value):
            return "FORCE", "a refspec set through `git -c remote.<name>.push/mirror`"
    flags, positional = parse_push(args)
    if "-f" in flags or any(f.startswith("--" + FORCE) for f in flags):
        return "FORCE", "a force flag"
    if "--mirror" in flags:
        return "MIRROR", None
    refspecs = positional[1:]                      # positional[0] is the remote
    if any(s.startswith("+") for s in refspecs):
        return "FORCE", "a leading '+' on a refspec"

    deleting_all = bool(flags & {"--delete", "-d"})
    targets = []
    for spec in refspecs:
        dst = destination(spec)
        if deleting_all or (":" in spec and spec.split(":", 1)[0].lstrip("+") == ""):
            if dst in MAIN_BRANCHES:
                return "DELETE", dst
            continue
        targets.append(dst)
    if flags & {"--all", "--branches"}:
        targets.append("main")
    if (not refspecs and not targets) or any(t in ("HEAD", "@", "") for t in targets):
        branch = git_out(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
        targets = [t for t in targets if t not in ("HEAD", "@", "")] + ([branch] if branch else [])
    for t in targets:
        if t in MAIN_BRANCHES:
            return "MAIN", t
    return None, None


def start_dir(payload):
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()


def judge(command, payload):
    """The deny reason for `command`, or None to let it run."""
    segments = shellwords.segments(command, shellwords.shell_of(payload))
    if segments is None:
        if re.search(r"\bgit\b[^\n]*\bpush\b", command):
            return ("BLOCKED: this looks like a git push, but its quoting cannot be parsed, so "
                    "its target cannot be checked. Fix the quoting, or the user runs it manually.")
        return None
    cur = start_dir(payload)
    for seg in segments:
        words = shellwords.unwrap(seg)
        if words and words[0] in ("cd", "pushd"):
            target = next((w for w in words[1:] if w != "--"), "~")
            cur = os.path.normpath(os.path.join(cur, os.path.expanduser(target)))
            continue
        inv = shellwords.git_invocation(seg)
        if not inv:
            continue
        sub, args, opts = inv
        repo = cur
        for path in opts.get("-C", []):
            repo = os.path.normpath(os.path.join(repo, os.path.expanduser(path)))
        if not is_push(sub, opts, repo):
            continue
        if sub != "push":                          # an alias: judge what it expands to
            expansion = alias_target(sub, opts, repo).lstrip("!").strip()
            extra = shellwords.segments(expansion) or [[]]
            args = (shellwords.git_invocation(extra[0]) or ("push", extra[0][1:], {}))[1] + args
        verdict, detail = judge_push(args, opts, repo)
        if verdict == "FORCE":
            return (f"BLOCKED: force push detected ({detail}). "
                    "The user must run this manually if absolutely necessary.")
        if verdict == "MIRROR":
            return ("BLOCKED: 'git push --mirror' can rewrite or delete remote refs — equivalent "
                    "to a force push. The user must run this manually if absolutely necessary.")
        if verdict == "DELETE":
            return (f"BLOCKED: this would DELETE the remote '{detail}' branch — as destructive as "
                    "a force push. The user must run this manually if absolutely necessary.")
        if verdict == "MAIN":
            root = git_out(repo, "rev-parse", "--show-toplevel") or repo
            if hookio.local_opt_out(payload, "allowPushToMain", root=root):
                continue
            return (f"BLOCKED: direct push to main/master (target branch: {detail}). Use a feature "
                    "branch and a PR instead. If this project intentionally lives on main, set "
                    "\"allowPushToMain\": true in .claude/settings.local.json.")
    return None


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "git" not in command:
        return 0
    reason = judge(command, payload)
    if reason:
        hookio.deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
