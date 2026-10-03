#!/usr/bin/env python3
"""Remove hook entries dotclaude no longer ships from a project's settings.

Run by init.sh and init.ps1 on every deploy (one implementation for both, so
the pruning rules cannot drift between them):

    python3 prune-obsolete.py <obsolete.json> [project-dir] [--remove-mcp]

Why it exists: removing a hook from dotclaude deletes its script from
~/.claude/hooks/ on the next install, but projects deployed earlier still wire
it in .claude/settings.json, so every matching tool call then reports a hook
error. The deploy merge only ever ADDS entries; this is the matching removal.

Hook entries are pruned in place (they point at files that no longer exist).
Obsolete MCP servers are reported on stdout as `OBSOLETE_MCP=` lines, and with
--remove-mcp (the user's explicit choice, passed by init --remove-obsolete-mcp)
they are removed from .mcp.json together with their `mcp__<name>` permission
rules. Obsolete directories are only ever reported (`OBSOLETE_FILES=`): they
may hold committed content, such as .serena/memories.
Never fatal: an unreadable file is reported and skipped, exit code is 0.

It is also the one implementation of "which hooks are obsolete":
update-projects.py and the skill's detect-drift.py import `hook_matches` and
`count_obsolete_hooks` from here. Three hand-written copies had drifted, and
the recursive updater planned "pruned" for hooks the deploy then kept.
"""

import json
import os
import re
import subprocess
import sys

SETTINGS_FILES = ("settings.json", "settings.local.json")


def load(path):
    # utf-8-sig: settings saved by Notepad or PowerShell 5.1 start with a BOM.
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def hook_matches(manifest):
    """The substrings that mark a hook command as obsolete."""
    return [h["match"] for h in manifest.get("hooks", []) if isinstance(h, dict) and h.get("match")]


def _commands(settings):
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    for groups in hooks.values() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for entry in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(entry, dict):
                    yield str(entry.get("command", ""))


def count_obsolete_hooks(project, matches):
    """Obsolete hook entries wired in a project's settings files.

    Returns None when a settings file exists but cannot be read, so a caller
    can say "unknown" instead of reporting a clean project.
    """
    count = 0
    for name in SETTINGS_FILES:
        path = os.path.join(project, ".claude", name)
        try:
            settings = load(path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return None
        count += sum(1 for c in _commands(settings) if any(m in c for m in matches))
    return count


def prune_hooks(settings, matches):
    """Drop hook commands containing any of `matches`; return the removed commands."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    removed = []
    for event in list(hooks):
        groups = hooks[event] if isinstance(hooks[event], list) else []
        kept_groups = []
        for group in groups:
            entries = group.get("hooks", []) if isinstance(group, dict) else []
            kept = []
            for entry in entries:
                command = str(entry.get("command", "")) if isinstance(entry, dict) else ""
                if any(m in command for m in matches):
                    removed.append(command)
                else:
                    kept.append(entry)
            if kept:
                group["hooks"] = kept
                kept_groups.append(group)
            elif not entries:
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return removed


def prune_settings_file(path, matches):
    try:
        settings = load(path)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        print(f"  ! {path} is not readable JSON ({exc}); obsolete hooks not checked", file=sys.stderr)
        return
    if not isinstance(settings, dict):
        return
    removed = prune_hooks(settings, matches)
    if not removed:
        return
    try:
        _write(path, settings)
    except OSError as exc:
        print(f"  ! could not write {path} ({exc}); remove these hooks by hand: {removed}", file=sys.stderr)
        return
    for command in removed:
        print(f"  - pruned obsolete hook from {path}: {command}", file=sys.stderr)


def prune_allow_rules(path, rules):
    """Drop exact `rules` from a settings file's permissions.allow (never from deny)."""
    try:
        settings = load(path)
    except (OSError, ValueError):
        return
    perms = settings.get("permissions") if isinstance(settings, dict) else None
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if not isinstance(allow, list):
        return
    kept = [r for r in allow if r not in rules]
    if len(kept) == len(allow):
        return
    perms["allow"] = kept
    try:
        _write(path, settings)
    except OSError as exc:
        print(f"  ! could not write {path} ({exc}); remove {sorted(set(allow) - set(kept))} by hand",
              file=sys.stderr)
        return
    for rule in sorted(set(allow) - set(kept)):
        print(f"  - removed obsolete permission from {path}: {rule}", file=sys.stderr)


def _write(path, data):
    # Never through a symlink: it can point outside the project, and
    # --recursive deploys into every project under a directory.
    if os.path.islink(path) or os.path.islink(os.path.dirname(path) or "."):
        raise OSError("it goes through a symlink")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def remove_mcp(project, names):
    """Delete obsolete servers from .mcp.json and every settings reference to them.

    The settings are cleaned for all `names`, not only the servers removed in
    this run: a later run must still clear a leftover `mcp__serena__*` rule or
    an `enabledMcpjsonServers` entry (the per-server approval Claude Code keeps
    in settings.local.json) whose server is already gone.
    """
    mcp_path = os.path.join(project, ".mcp.json")
    try:
        mcp = load(mcp_path)
        servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    except (OSError, ValueError):
        servers = None
    gone = [n for n in names if isinstance(servers, dict) and n in servers]
    if gone:
        for name in gone:
            del servers[name]
        try:
            _write(mcp_path, mcp)
            print(f"  - removed obsolete MCP server(s) from .mcp.json: {', '.join(gone)}", file=sys.stderr)
        except OSError as exc:
            print(f"  ! could not write {mcp_path} ({exc}); remove {gone} by hand", file=sys.stderr)
            return
    if not names:
        return
    rule = re.compile(r"^mcp__(%s)(__.*)?$" % "|".join(re.escape(n) for n in names))
    for settings_name in SETTINGS_FILES:
        path = os.path.join(project, ".claude", settings_name)
        try:
            settings = load(path)
        except (OSError, ValueError):
            continue
        if not isinstance(settings, dict):
            continue
        dropped = []
        perms = settings.get("permissions")
        if isinstance(perms, dict):
            for key in ("allow", "ask", "deny"):
                rules = perms.get(key)
                if isinstance(rules, list):
                    kept = [r for r in rules if not (isinstance(r, str) and rule.match(r))]
                    dropped += [r for r in rules if r not in kept]
                    perms[key] = kept
        for key in ("enabledMcpjsonServers", "disabledMcpjsonServers"):
            listed = settings.get(key)
            if isinstance(listed, list):
                kept = [n for n in listed if n not in names]
                dropped += [f"{key}:{n}" for n in listed if n in names]
                settings[key] = kept
        if dropped:
            try:
                _write(path, settings)
                print(f"  - removed references from {path}: {', '.join(dropped)}", file=sys.stderr)
            except OSError as exc:
                print(f"  ! could not write {path} ({exc}); remove {dropped} by hand", file=sys.stderr)


def prune_git_hooks(project, entries):
    """Strip obsolete tool blocks from the repo's git hooks (e.g. graphify's rebuild hooks).

    Only the block between the entry's start marker and its matching end
    marker is removed; a hook left with nothing but its shebang is deleted.
    A block without an end marker is reported and left alone: guessing where
    someone else's script ends could cut the user's own hook code.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=project,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return
    if out.returncode != 0:
        return
    hooks_dir = os.path.join(project, out.stdout.strip())
    for entry in entries:
        start, end = entry.get("start", ""), entry.get("end", "")
        path = os.path.join(hooks_dir, entry.get("file", ""))
        if not start or not end or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if start not in text:
            continue
        i, j = text.index(start), text.find(end, text.index(start))
        if j == -1:
            print(f"  ! {path} holds an obsolete block ({entry.get('reason', '')}) without its end "
                  f"marker; remove it by hand", file=sys.stderr)
            continue
        line_start = text.rfind("\n", 0, i) + 1
        line_end = text.find("\n", j)
        rest = text[:line_start] + (text[line_end + 1:] if line_end != -1 else "")
        meaningful = [l for l in rest.splitlines() if l.strip() and not l.startswith("#!")]
        try:
            if meaningful:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(rest)
                print(f"  - removed obsolete block from git hook {path}", file=sys.stderr)
            else:
                os.remove(path)
                print(f"  - removed obsolete git hook {path}", file=sys.stderr)
        except OSError as exc:
            print(f"  ! could not update {path} ({exc})", file=sys.stderr)


def obsolete_mcp(project, names):
    try:
        servers = load(os.path.join(project, ".mcp.json")).get("mcpServers", {})
    except (OSError, ValueError, AttributeError):
        return []
    return [n for n in names if n in servers]


def main():
    args = [a for a in sys.argv[1:] if a != "--remove-mcp"]
    if len(args) not in (1, 2):
        print(__doc__, file=sys.stderr)
        return 0
    project = args[1] if len(args) == 2 else "."
    try:
        manifest = load(args[0])
    except (OSError, ValueError) as exc:
        print(f"  ! obsolete manifest unreadable ({exc}); nothing pruned", file=sys.stderr)
        return 0

    matches = hook_matches(manifest)
    rules = [p["rule"] for p in manifest.get("permissions", []) if isinstance(p, dict) and p.get("rule")]
    prune_git_hooks(project, manifest.get("gitHooks", []))
    for name in SETTINGS_FILES:
        prune_settings_file(os.path.join(project, ".claude", name), matches)
        if rules:
            prune_allow_rules(os.path.join(project, ".claude", name), rules)

    names = [s["name"] for s in manifest.get("mcpServers", [])]
    if "--remove-mcp" in sys.argv[1:]:
        remove_mcp(project, names)
    servers = obsolete_mcp(project, names)
    files = [f["path"] for f in manifest.get("files", [])
             if os.path.exists(os.path.join(project, f["path"]))]
    print("OBSOLETE_MCP=" + ",".join(servers))
    print("OBSOLETE_FILES=" + ",".join(files))
    if servers or files:
        print("  ! obsolete leftovers (remove when you no longer need them): "
              + ", ".join([f".mcp.json:{s}" for s in servers] + files), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
