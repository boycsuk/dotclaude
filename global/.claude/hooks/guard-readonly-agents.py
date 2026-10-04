# hook-kind: guard
"""PreToolUse hook on Bash/PowerShell: a read-only subagent may not write through the shell.

An agent whose definition gives it no Write or Edit (`disallowedTools` naming
both, or a `tools` list naming neither) is read-only by design: researcher,
code-reviewer, debugger, db-inspector, or a project's own. Without this guard
its Bash could still `sed -i`, redirect into a file, check out a branch or
install a package, and "read-only" was only a line in its prompt.

When the payload's `agent_type` names such an agent, deny:
  - a write outside the temp folder and the session scratchpad (redirects,
    tee, sed -i, cp/mv/rm and the rest that _lib/writes.py knows, PowerShell
    writers included);
  - any git command that is not read-only (an allowlist: status, diff, log,
    show, listing branches or stashes, reading config...);
  - a package install, update or removal.

The main thread carries no `agent_type`, and an agent whose definition is not
found (built-ins such as Explore, plugin agents) is not judged. SQL is not
parsed: db-inspector's read-only queries stay a rule of its prompt. A script
the agent runs can still write on its own; that is the price of letting the
debugger reproduce a failure.
"""

import glob
import os
import re
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import bootstrap  # noqa: E402,F401
import hookio  # noqa: E402
import shellwords  # noqa: E402
import writes  # noqa: E402

AGENT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
EDIT_TOOLS = {"Write", "Edit"}
NOT_A_FILE = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "$null"}

READ_GIT = {"status", "diff", "log", "show", "blame", "annotate", "grep", "ls-files", "ls-tree", "ls-remote",
            "rev-parse", "rev-list", "describe", "shortlog", "cat-file", "show-ref", "for-each-ref",
            "merge-base", "name-rev", "whatchanged", "check-ignore", "check-attr", "count-objects", "help",
            "version", "var", "diff-tree", "diff-files", "diff-index", "range-diff", "cherry"}
# Subcommands that only read when their first argument is one of these.
READ_GIT_ACTIONS = {"stash": {"list", "show"}, "worktree": {"list"}, "notes": {"list", "show"},
                    "submodule": {"status", "summary"}, "remote": {"show", "get-url"}, "reflog": {"show"}}
BRANCH_WRITE_FLAGS = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-u",
                      "--set-upstream-to", "--unset-upstream", "--edit-description", "-f", "--force",
                      "-t", "--track", "--no-track"}
BRANCH_QUERY_FLAGS = {"--list", "-l", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
CONFIG_WRITE_FLAGS = ("--unset", "--add", "--replace-all", "--rename-section", "--remove-section", "--edit", "-e")

INSTALL_COMMON = {"install", "i", "add", "remove", "rm", "uninstall", "un", "update", "up", "upgrade",
                  "link", "ci", "prune", "dedupe", "sync", "lock", "require", "reinstall", "purge", "get"}
INSTALLERS = {"npm", "pnpm", "yarn", "bun", "pip", "pip3", "uv", "poetry", "pipenv", "cargo", "go", "gem",
              "bundle", "brew", "apt", "apt-get", "composer", "conda", "mamba"}


def frontmatter(text):
    """The YAML frontmatter of an agent file as {key: str or [str]}; {} when there is none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data, key = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        item = re.match(r"^\s+-\s*(.+)$", line)
        if item and key:
            data[key] = (data[key] if isinstance(data[key], list) else []) + [item.group(1).strip()]
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            data[key] = m.group(2).strip()
    return data


def tool_names(value):
    items = value if isinstance(value, list) else value.strip().strip("[]").split(",")
    return {i.strip().strip("'\"").split("(", 1)[0].strip() for i in items if i.strip()}


def definition(agent, payload):
    """The frontmatter of `agent`'s definition, project first, then the user's; None when not found."""
    if not AGENT_NAME.match(agent):
        return None
    for folder in (os.path.join(hookio.project_dir(payload), ".claude", "agents"),
                   os.path.join(os.path.expanduser("~"), ".claude", "agents")):
        exact = os.path.join(folder, f"{agent}.md")
        candidates = [exact] + sorted(p for p in glob.glob(os.path.join(folder, "**", "*.md"), recursive=True)
                                      if p != exact)
        for path in candidates:
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as fh:
                    meta = frontmatter(fh.read())
            except OSError:
                continue
            if meta.get("name", agent if path == exact else None) == agent:
                return meta
    return None


def read_only(meta):
    disallowed = tool_names(meta.get("disallowedTools") or "")
    if EDIT_TOOLS <= disallowed:
        return True
    tools = meta.get("tools")
    return bool(tools) and not (tool_names(tools) & EDIT_TOOLS) and "*" not in tool_names(tools)


def scratch_roots(payload):
    roots = [tempfile.gettempdir(), payload.get("scratchpad_dir")]
    return [os.path.normcase(os.path.realpath(r)) for r in roots if isinstance(r, str) and r]


def expand_vars(word):
    """`word` with $NAME, ${NAME}, ${NAME:-default} and PowerShell's $env:NAME resolved from the environment.

    The hook runs in the environment the command will, so "${TMPDIR:-/tmp}/x"
    names the temp folder. A variable that resolves to nothing stays as
    written, and the path is then judged as a relative one: unknown is never
    assumed to be scratch space.
    """
    def braced(m):
        value = os.environ.get(m.group(1))
        return value if value else (m.group(2) if m.group(2) is not None else m.group(0))
    word = re.sub(r"\$\{(\w+)(?::?-([^}]*))?\}", braced, word)
    return re.sub(r"\$(?:env:)?(\w+)", lambda m: os.environ.get(m.group(1)) or m.group(0), word)


def outside_scratch(target, cwd, roots):
    if target.strip().lower() in NOT_A_FILE:
        return False
    path = os.path.normcase(os.path.realpath(writes.absolute(expand_vars(target), cwd)))
    return not any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def git_writes(seg):
    """The git subcommand when `seg` runs one that is not read-only, else None."""
    inv = shellwords.git_invocation(seg)
    if not inv:
        return None
    sub, args, _ = inv
    flags, positional, _ = writes.split_args(args)
    action = positional[0] if positional else ""
    if sub in READ_GIT:
        return None
    if sub in READ_GIT_ACTIONS and (action in READ_GIT_ACTIONS[sub] or (not action and sub != "stash")):
        return None
    if sub == "branch":
        names = {f.split("=", 1)[0] for f in flags}
        bundled = any(writes.short_bundle(f, "dDmMcCfut") for f in flags if not f.startswith("--"))
        if not (names & BRANCH_WRITE_FLAGS or bundled) and (not positional or names & BRANCH_QUERY_FLAGS
                                                              or "--show-current" in names):
            return None
    if sub == "tag" and not any(f in ("-d", "--delete", "-f", "--force") for f in flags) \
            and (not positional or any(f in ("-l", "--list") for f in flags)):
        return None
    if sub == "config":
        reads = any(f.startswith("--get") or f in ("--list", "-l") for f in flags)
        if not any(f.startswith(CONFIG_WRITE_FLAGS) for f in flags) and (reads or len(positional) <= 1):
            return None
    if sub == "symbolic-ref" and len(positional) <= 1:
        return None
    # fetch moves only remote-tracking refs, which a reviewer needs to compare
    # with origin; a refspec with a destination (main:main) writes a local branch.
    if sub == "fetch" and not any(":" in p for p in positional) and "--update-head-ok" not in flags:
        return None
    return sub


def installs(words):
    """'<program> <action>' when `words` installs, updates or removes packages, else None."""
    name = shellwords.basename(words[0]).lower()
    args = words[1:]
    if re.fullmatch(r"python[0-9.]*|py", name) and args[:2] == ["-m", "pip"]:
        name, args = "pip", args[2:]
    if name not in INSTALLERS:
        return None
    positional = [a for a in args if not a.startswith("-")]
    action = positional[0] if positional else ""
    if name == "uv" and action == "pip":
        action = positional[1] if len(positional) > 1 else ""
    if name == "go" and action == "mod":
        return "go mod" if len(positional) > 1 and positional[1] in ("tidy", "download", "vendor", "edit") else None
    if name == "yarn" and not action:
        return "yarn"
    return f"{name} {action}" if action in INSTALL_COMMON else None


def judge(command, payload):
    shell = shellwords.shell_of(payload)
    segments = shellwords.segments(command, shell)
    if segments is None:
        return "its quoting cannot be parsed, so what it writes cannot be checked"
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    roots = scratch_roots(payload)
    for seg in segments:
        words = shellwords.unwrap(seg)
        if not words:
            continue
        target = shellwords.chdir_target(words)
        if target is not None:
            cwd = writes.absolute(target, cwd)
            continue
        written = [t for t in writes.targets(shellwords.basename(words[0]), words[1:], shell)
                   if outside_scratch(t, cwd, roots)]
        if written:
            return f"writes {written[0]}"
        sub = git_writes(seg)
        if sub:
            return f"runs git {sub}, which changes the repository"
        package = installs(words)
        if package:
            return f"runs {package}, which changes the installed packages"
    return None


def main():
    payload = hookio.read_payload()
    agent = payload.get("agent_type")
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(agent, str) or not agent or not isinstance(command, str) or not command.strip():
        return 0
    meta = definition(agent, payload)
    if meta is None or not read_only(meta):
        return 0
    what = judge(command, payload)
    if what:
        hookio.deny(f"BLOCKED: {agent} is a read-only agent (its definition gives it no Write or Edit), "
                    f"and this command {what}. Instead: describe the change, or return it as a diff for "
                    f"the caller to apply. Scratch files may go in the temp folder or the session scratchpad.")
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
