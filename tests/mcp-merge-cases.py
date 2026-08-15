#!/usr/bin/env python3
"""Behavioural contract for .mcp.json composition in init.{sh,ps1}.

Run:  python3 tests/mcp-merge-cases.py
      python3 tests/mcp-merge-cases.py --pwsh PATH   # verify parity

`.mcp.json` is COMPOSED, not copied: each flag owns its own server keys and
must leave every other key alone. This matrix exists because the previous
design mixed the two models — `--serena` did `cp` + a whole-file `cmp`, while
`--xcode` merged — and the combination was broken in both orders:

    init.sh --xcode && init.sh --update --serena   -> exit 3
    init.sh --serena && init.sh --xcode            -> ok, but every later
                                                      --update --serena -> exit 3

The second one is the dangerous shape: the project ends up correct, and only
the NEXT re-deploy fails, which is exactly the path update-mode.md §1e uses to
reconcile drift. Neither was caught by reading the scripts, so the cases go in
the matrix before the fix (DESIGN.md §26).

Each case builds a throwaway project dir, stubs the host probes (uname/xcrun/
serena/npx) via a PATH prefix so the cases are hermetic on any OS, runs the
real init script, and asserts on the resulting .mcp.json. Probe-failure cases
scrub PATH down to a minimal tail so "omit a stub" really removes the binary —
otherwise the machine's own npx/serena leaks in and exits 4/7 are untestable.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "templates/project/init.sh")
PS1 = os.path.join(REPO, "templates/project/init.ps1")
TEMPLATE_DIR = os.path.join(REPO, "templates/project")

SERENA = {"serena", "graphify"}


def write_stub(bindir, name, body):
    path = os.path.join(bindir, name)
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, 0o755)


def make_bin(tmp, omit=(), uname_out="Darwin", xcrun_fail=False):
    """Stub the host probes so a Linux CI box can act like a Mac (or fail
    like a host missing a prerequisite)."""
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    stubs = {
        "uname": "#!/bin/sh\necho %s\n" % uname_out,
        "xcrun": "#!/bin/sh\nexit 1\n" if xcrun_fail else "#!/bin/sh\nexit 0\n",
        "serena": "#!/bin/sh\nexit 0\n",
        "graphify": "#!/bin/sh\nexit 0\n",
        "npx": "#!/bin/sh\nexit 0\n",
    }
    for name, body in stubs.items():
        if name not in omit:
            write_stub(bindir, name, body)
    return bindir


_SYSPATH = None


def syspath():
    """Minimal PATH tail with only the tools the init scripts themselves need.
    Used by probe-failure cases: with the full machine PATH, omitting the npx
    stub proves nothing because the real npx answers instead."""
    global _SYSPATH
    if _SYSPATH is None:
        _SYSPATH = tempfile.mkdtemp(prefix="mcp-syspath-")
        for tool in ("bash", "sh", "python3", "cp", "mkdir", "grep", "cmp",
                     "dirname", "basename", "cat", "sed", "chmod", "env"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, os.path.join(_SYSPATH, tool))
    return _SYSPATH


def run(tmp, args, pwsh=None, omit=(), uname_out="Darwin", xcrun_fail=False,
        scrub_path=False):
    env = dict(os.environ)
    env["TEMPLATE_DIR"] = TEMPLATE_DIR
    bindir = make_bin(tmp, omit, uname_out, xcrun_fail)
    tail = syspath() if scrub_path else env["PATH"]
    env["PATH"] = bindir + os.pathsep + tail
    if pwsh:
        # $IsMacOS is an engine variable, not a PATH lookup, so the uname stub
        # cannot reach it — the script exposes this escape hatch for the matrix.
        # A case simulating a non-Mac host simply leaves it unset.
        if uname_out == "Darwin":
            env["MCP_FORCE_DARWIN"] = "1"
        else:
            env.pop("MCP_FORCE_DARWIN", None)
        cmd = [pwsh, "-NoProfile", "-File", PS1] + args
    else:
        cmd = ["bash", SH] + args
    p = subprocess.run(cmd, cwd=tmp, env=env,
                       capture_output=True, text=True)
    return p.returncode


def servers(tmp):
    path = os.path.join(tmp, ".mcp.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return set(json.load(fh).get("mcpServers", {}).keys())


def case(name, steps, expect_servers, expect_last_code=0, extra=None):
    """steps: list of arg-lists run in order in one throwaway project."""
    return dict(name=name, steps=steps, servers=expect_servers,
                code=expect_last_code, extra=extra)


CASES = [
    case("serena alone", [["--serena"]], SERENA),
    case("xcode alone", [["--xcode"]], {"xcode"}),
    case("serena then xcode", [["--serena"], ["--xcode"]], SERENA | {"xcode"}),
    case("xcode then serena", [["--xcode"], ["--serena"]], SERENA | {"xcode"}),
    case("both flags at once", [["--serena", "--xcode"]], SERENA | {"xcode"}),
    case("re-run serena is idempotent",
         [["--serena"], ["--serena"]], SERENA),
    case("re-run xcode is idempotent",
         [["--xcode"], ["--xcode"]], {"xcode"}),
    # The regression that motivated the refactor: a later --update --serena
    # must still succeed once xcode is present.
    case("update --serena after xcode",
         [["--xcode"], ["--serena"], ["--update", "--serena"]],
         SERENA | {"xcode"}),
    case("update --serena after both",
         [["--serena", "--xcode"], ["--update", "--serena"]],
         SERENA | {"xcode"}),
    # An --update that does not name a flag must not strip that flag's server.
    case("bare --update preserves everything",
         [["--serena", "--xcode"], ["--update"]], SERENA | {"xcode"}),
    case("ui alone", [["--ui"]], {"playwright"}),
    case("re-run ui is idempotent", [["--ui"], ["--ui"]], {"playwright"}),
    case("all three flags at once",
         [["--serena", "--xcode", "--ui"]], SERENA | {"xcode", "playwright"}),
    case("bare --update preserves ui",
         [["--ui"], ["--update"]], {"playwright"}),
]

# The prerequisite probes each abort with a documented exit code the skill
# keys its remediation on. The stubs above always exist, so these branches had
# zero coverage — a typo'd binary name in a probe would have shipped green.
#   (name, args, run-kwargs, expected exit code)
PROBES = [
    ("missing serena aborts: exit 4", ["--serena"],
     dict(omit={"serena"}, scrub_path=True), 4),
    ("--xcode on a non-mac host aborts: exit 5", ["--xcode"],
     dict(uname_out="Linux"), 5),
    ("xcrun without mcpbridge aborts: exit 6", ["--xcode"],
     dict(xcrun_fail=True), 6),
    ("missing npx aborts --ui: exit 7", ["--ui"],
     dict(omit={"npx"}, scrub_path=True), 7),
]


def run_case(c, pwsh=None):
    tmp = tempfile.mkdtemp(prefix="mcpcase-")
    try:
        code = 0
        for step in c["steps"]:
            code = run(tmp, step, pwsh)
        got = servers(tmp)
        if code != c["code"]:
            return f"exit {code}, want {c['code']}"
        if got != c["servers"]:
            return f"servers {sorted(got or [])}, want {sorted(c['servers'])}"
        if c["extra"]:
            problem = c["extra"](tmp)
            if problem:
                return problem
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def third_party_survives(tmp):
    """A server the template knows nothing about must never be dropped."""
    with open(os.path.join(tmp, ".mcp.json")) as fh:
        cfg = json.load(fh)
    if "playwright" not in cfg.get("mcpServers", {}):
        return "third-party 'playwright' server was dropped"
    if cfg["mcpServers"]["playwright"].get("command") != "npx":
        return "third-party server was mutated"
    return None


def seed_third_party(tmp):
    with open(os.path.join(tmp, ".mcp.json"), "w") as fh:
        json.dump({"mcpServers": {
            "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"], "env": {}}
        }}, fh)


def serena_hooks_shape(tmp, is_ps1):
    """The settings.json hook merge is the most intricate code in either init
    script and had no assertions at all. After two --serena runs: parseable,
    de-duplicated, and in a form the OS can actually execute (a bare .ps1 path
    under the default hook shell is inert — the Windows bug this pins)."""
    path = os.path.join(tmp, ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        if raw.startswith("﻿"):
            return "settings.json carries a UTF-8 BOM"
        cfg = json.loads(raw)
    except (OSError, ValueError) as e:
        return f"settings.json unreadable: {e}"
    cmds = [h.get("command", "")
            for groups in cfg.get("hooks", {}).values()
            for g in groups for h in g.get("hooks", [])]
    prefer = [c for c in cmds if "prefer-serena-bash" in c]
    if len(prefer) != 1:
        return f"prefer-serena-bash appears {len(prefer)} times, want 1 (dedup)"
    if is_ps1:
        if not prefer[0].startswith('& "') or not prefer[0].endswith('.ps1"'):
            return f"ps1 hook not in executable form: {prefer[0]}"
        entry = [h for groups in cfg["hooks"].values() for g in groups
                 for h in g.get("hooks", []) if "prefer-serena-bash" in h.get("command", "")][0]
        if entry.get("shell") != "powershell":
            return "ps1 hook entry lacks shell: powershell"
    elif not prefer[0].endswith(".sh"):
        return f"sh hook does not point at the .sh form: {prefer[0]}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh")
    args = ap.parse_args()

    targets = [(None, "sh")]
    if args.pwsh:
        targets.append((args.pwsh, "ps1"))

    total = bad = 0

    def report(label, name, problem):
        nonlocal total, bad
        total += 1
        if problem:
            bad += 1
        status = "ok  " if problem is None else "BAD "
        print(f"  {status}[{label}] {name}" + (f" — {problem}" if problem else ""))

    for pwsh, label in targets:
        for c in CASES:
            report(label, c["name"], run_case(c, pwsh))

        for name, pargs, kw, want in PROBES:
            tmp = tempfile.mkdtemp(prefix="mcpcase-")
            try:
                code = run(tmp, pargs, pwsh, **kw)
                problem = None if code == want else f"exit {code}, want {want}"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            report(label, name, problem)

        # A corrupt .mcp.json must warn and leave the file alone, never abort
        # the deploy or clobber the user's bytes.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            with open(os.path.join(tmp, ".mcp.json"), "w") as fh:
                fh.write("this is not json {")
            code = run(tmp, ["--ui"], pwsh)
            with open(os.path.join(tmp, ".mcp.json")) as fh:
                content = fh.read()
            problem = None
            if code != 0:
                problem = f"exit {code}, want 0 (warn and continue)"
            elif content != "this is not json {":
                problem = "corrupt .mcp.json was rewritten"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "broken .mcp.json warns and continues", problem)

        # Third-party preservation needs a pre-seeded file, so it runs outside
        # the table.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            seed_third_party(tmp)
            run(tmp, ["--serena"], pwsh)
            run(tmp, ["--xcode"], pwsh)
            problem = third_party_survives(tmp)
            got = servers(tmp)
            if problem is None and got != SERENA | {"xcode", "playwright"}:
                problem = f"servers {sorted(got)}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "third-party server survives both flags", problem)

        # PS 5.1's ConvertFrom-Json collapses [] to $null: a hand-added server
        # with "args": [] must survive a merge as [], not "args": null. pwsh 7
        # preserves [] natively, so this only bites on Windows PowerShell —
        # the case still pins the contract wherever the matrix runs.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            with open(os.path.join(tmp, ".mcp.json"), "w") as fh:
                json.dump({"mcpServers": {
                    "custom": {"command": "custom-mcp", "args": [], "env": {}}
                }}, fh)
            run(tmp, ["--serena"], pwsh)
            with open(os.path.join(tmp, ".mcp.json")) as fh:
                sargs = json.load(fh)["mcpServers"]["custom"].get("args")
            problem = None if sargs == [] else f"empty args became {sargs!r}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "empty args array survives a merge", problem)

        # --ui OWNS the 'playwright' key: a hand-added entry with a different
        # spec is adopted (updated to the template's), not duplicated or kept
        # stale. This is the flip side of third-party preservation above.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            seed_third_party(tmp)
            run(tmp, ["--ui"], pwsh)
            with open(os.path.join(tmp, ".mcp.json")) as fh:
                spec = json.load(fh)["mcpServers"].get("playwright", {})
            problem = None
            if "@playwright/mcp@latest" not in spec.get("args", []):
                problem = f"hand-added playwright not adopted by --ui: {spec}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "--ui adopts a hand-added playwright", problem)

        # The serena-hooks settings merge, asserted after an idempotency
        # double-run.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            run(tmp, ["--serena"], pwsh)
            run(tmp, ["--serena"], pwsh)
            problem = serena_hooks_shape(tmp, is_ps1=pwsh is not None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "serena hooks merge: executable form, deduped", problem)

    print(f"\nmcp-merge: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
