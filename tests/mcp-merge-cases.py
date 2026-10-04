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
the NEXT re-deploy fails, which is exactly the path /init-project --update uses
to reconcile drift. Neither was caught by reading the scripts, so the cases go in
the matrix before the fix.

(--serena itself was removed later; the composition contract it exposed is
pinned below with the flags that remain.)

Each case builds a throwaway project dir, stubs the host probes (uname/xcrun/
npx) via a PATH prefix so the cases are hermetic on any OS, runs the real init
script, and asserts on the resulting .mcp.json. Probe-failure cases scrub PATH
down to a minimal tail so "omit a stub" really removes the binary — otherwise
the machine's own npx leaks in and exit 7 is untestable.
"""

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "templates/project/init.sh")
PS1 = os.path.join(REPO, "templates/project/init.ps1")
TEMPLATE_DIR = os.path.join(REPO, "templates/project")

def make_bin(tmp, omit=(), uname_out="Darwin", xcrun_fail=False):
    """Stub the host probes so a Linux CI box can act like a Mac (or fail
    like a host missing a prerequisite)."""
    bindir = os.path.join(tmp, "bin")
    if "uname" not in omit:
        stubs.write_stub(bindir, "uname", uname_out + "\n")
    for name, code in (("xcrun", 1 if xcrun_fail else 0), ("npx", 0), ("codebase-memory-mcp", 0)):
        if name not in omit:
            stubs.write_stub(bindir, name, code=code)
    return bindir


_SYSPATH = None


def syspath():
    """Minimal PATH tail with only the tools the init scripts themselves need.
    Used by probe-failure cases: with the full machine PATH, omitting the npx
    stub proves nothing because the real npx answers instead."""
    global _SYSPATH
    if _SYSPATH is None:
        _SYSPATH = tempfile.mkdtemp(prefix="mcp-syspath-")
        atexit.register(shutil.rmtree, _SYSPATH, True)
        _SYSPATH = stubs.minimal_path(_SYSPATH, ("bash", "sh", "python3", "cp", "mkdir", "grep", "cmp",
                                                 "dirname", "basename", "cat", "sed", "chmod", "env", "tr",
                                                 "tail", "git"))
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
        # cannot reach it — the script exposes two escape hatches so either
        # verdict is reachable from either runner. Leaving them unset was not
        # enough: on a real Mac $IsMacOS is true, so the exit-5 "non-mac host"
        # case inverted and passed only because CI happened to run on Linux.
        env.pop("MCP_FORCE_DARWIN", None)
        env.pop("MCP_FORCE_NON_DARWIN", None)
        if uname_out == "Darwin":
            env["MCP_FORCE_DARWIN"] = "1"
        else:
            env["MCP_FORCE_NON_DARWIN"] = "1"
        cmd = [pwsh, "-NoProfile", "-File", PS1] + args
    else:
        cmd = ["bash", SH] + args
    p = subprocess.run(cmd, cwd=tmp, env=env,
                       capture_output=True, encoding="utf-8", errors="replace")
    return p.returncode


def servers(tmp):
    path = os.path.join(tmp, ".mcp.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return set(json.load(fh).get("mcpServers", {}).keys())


def case(name, steps, expect_servers, expect_last_code=0, extra=None):
    """steps: list of arg-lists run in order in one throwaway project."""
    return dict(name=name, steps=steps, servers=expect_servers,
                code=expect_last_code, extra=extra)


CASES = [
    case("xcode alone", [["--xcode"]], {"xcode"}),
    case("ui alone", [["--ui"]], {"playwright"}),
    case("xcode then ui", [["--xcode"], ["--ui"]], {"xcode", "playwright"}),
    case("ui then xcode", [["--ui"], ["--xcode"]], {"xcode", "playwright"}),
    case("both flags at once", [["--xcode", "--ui"]], {"xcode", "playwright"}),
    case("re-run xcode is idempotent",
         [["--xcode"], ["--xcode"]], {"xcode"}),
    case("re-run ui is idempotent", [["--ui"], ["--ui"]], {"playwright"}),
    # The regression that motivated the refactor: a later --update naming one
    # flag must still succeed once another flag's server is present.
    case("update --ui after xcode",
         [["--xcode"], ["--ui"], ["--update", "--ui"]], {"xcode", "playwright"}),
    # An --update that does not name a flag must not strip that flag's server.
    case("bare --update preserves everything",
         [["--xcode", "--ui"], ["--update"]], {"xcode", "playwright"}),
    case("bare --update preserves ui",
         [["--ui"], ["--update"]], {"playwright"}),
    case("codebase-memory alone", [["--codebase-memory"]], {"codebase-memory-mcp"},
         extra=lambda tmp: readonly_permissions(tmp)),
    case("codebase-memory with the other flags, re-run",
         [["--codebase-memory", "--ui"], ["--xcode"], ["--update", "--codebase-memory"]],
         {"codebase-memory-mcp", "playwright", "xcode"},
         extra=lambda tmp: readonly_permissions(tmp)),
    # --serena is gone entirely: like any unknown flag it deploys nothing.
    case("removed --serena is an unknown flag", [["--serena"]], None, expect_last_code=9),
]

# The prerequisite probes each abort with a documented exit code the skill
# keys its remediation on. The stubs above always exist, so these branches had
# zero coverage — a typo'd binary name in a probe would have shipped green.
#   (name, args, run-kwargs, expected exit code)
PROBES = [
    ("--xcode on a non-mac host aborts: exit 5", ["--xcode"],
     dict(uname_out="Linux"), 5),
    ("xcrun without mcpbridge aborts: exit 6", ["--xcode"],
     dict(xcrun_fail=True), 6),
    ("missing npx aborts --ui: exit 7", ["--ui"],
     dict(omit={"npx"}, scrub_path=True), 7),
    ("missing codebase-memory-mcp aborts: exit 8", ["--codebase-memory"],
     dict(omit={"codebase-memory-mcp"}, scrub_path=True), 8),
    ("unknown flag aborts before deploying: exit 9", ["--update", "--recursve"], {}, 9),
    ("directory without --recursive aborts: exit 9", ["--update", "."], {}, 9),
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


CBM_WRITERS = ("index_repository", "delete_project", "manage_adr", "ingest_traces")


def readonly_permissions(tmp):
    """--codebase-memory allows the read-only graph tools by exact name, once
    each, and never a wildcard or a tool that writes or deletes."""
    with open(os.path.join(tmp, ".claude", "settings.json"), encoding="utf-8") as fh:
        allow = json.load(fh).get("permissions", {}).get("allow", [])
    cbm = [r for r in allow if r.startswith("mcp__codebase-memory-mcp")]
    if "mcp__codebase-memory-mcp__trace_path" not in cbm:
        return f"read-only graph tools not allowed: {cbm}"
    if len(cbm) != len(set(cbm)):
        return "a re-run duplicated permission rules"
    bad = [r for r in cbm if r.endswith("*") or r.split("__")[-1] in CBM_WRITERS]
    if bad:
        return f"write-capable or wildcard rules allowed: {bad}"
    return None


THIRD_PARTY = {"command": "my-mcp", "args": ["--flag"], "env": {"K": "v"}}


def third_party_survives(tmp):
    """A server the template knows nothing about must never be dropped."""
    with open(os.path.join(tmp, ".mcp.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    if "mine" not in cfg.get("mcpServers", {}):
        return "third-party 'mine' server was dropped"
    if cfg["mcpServers"]["mine"] != THIRD_PARTY:
        return "third-party server was mutated"
    return None


def seed_third_party(tmp):
    with open(os.path.join(tmp, ".mcp.json"), "w", encoding="utf-8") as fh:
        json.dump({"mcpServers": {"mine": THIRD_PARTY}}, fh)


def seed_hand_added_playwright(tmp):
    with open(os.path.join(tmp, ".mcp.json"), "w", encoding="utf-8") as fh:
        json.dump({"mcpServers": {
            "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"], "env": {}}
        }}, fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh")
    args = ap.parse_args()

    targets = stubs.shell_targets(args.pwsh)

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
                if problem is None and want == 9 and os.listdir(tmp) != ["bin"]:
                    problem = f"exit 9 must deploy nothing, found {sorted(os.listdir(tmp))}"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            report(label, name, problem)

        # A corrupt .mcp.json must warn and leave the file alone, never abort
        # the deploy or clobber the user's bytes.
        tmp = tempfile.mkdtemp(prefix="mcpcase-")
        try:
            with open(os.path.join(tmp, ".mcp.json"), "w", encoding="utf-8") as fh:
                fh.write("this is not json {")
            code = run(tmp, ["--ui"], pwsh)
            with open(os.path.join(tmp, ".mcp.json"), encoding="utf-8") as fh:
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
            run(tmp, ["--xcode"], pwsh)
            run(tmp, ["--ui"], pwsh)
            problem = third_party_survives(tmp)
            got = servers(tmp)
            if problem is None and got != {"mine", "xcode", "playwright"}:
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
            with open(os.path.join(tmp, ".mcp.json"), "w", encoding="utf-8") as fh:
                json.dump({"mcpServers": {
                    "custom": {"command": "custom-mcp", "args": [], "env": {}}
                }}, fh)
            run(tmp, ["--xcode"], pwsh)
            with open(os.path.join(tmp, ".mcp.json"), encoding="utf-8") as fh:
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
            seed_hand_added_playwright(tmp)
            run(tmp, ["--ui"], pwsh)
            with open(os.path.join(tmp, ".mcp.json"), encoding="utf-8") as fh:
                spec = json.load(fh)["mcpServers"].get("playwright", {})
            problem = None
            with open(os.path.join(TEMPLATE_DIR, "mcp", "playwright.json"), encoding="utf-8") as fh:
                shipped = json.load(fh)["playwright"]
            if spec.get("args") != shipped["args"]:
                problem = f"hand-added playwright not adopted by --ui: {spec}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        report(label, "--ui adopts a hand-added playwright", problem)

    print(f"\nmcp-merge: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
