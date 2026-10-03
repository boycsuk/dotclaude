#!/usr/bin/env python3
"""Behavioural contract for --lsp=<plugin> in init.{sh,ps1}.

Run:  python3 tests/lsp-plugin-cases.py
      python3 tests/lsp-plugin-cases.py --pwsh PATH   # through init.ps1 too

The flag installs an official LSP plugin at project scope through the real
`claude plugin install` CLI. Every failure mode is a WARN, never an abort: a
deploy must not die because a language server or the CLI is missing. These
cases stub `claude` and the language-server binaries on a scrubbed PATH, so
they are hermetic and never touch the machine's real plugin state.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(REPO, "templates/project")
SH = os.path.join(TEMPLATE_DIR, "init.sh")
PS1 = os.path.join(TEMPLATE_DIR, "init.ps1")
SYSTEM_TOOLS = ("bash", "sh", "python3", "cp", "mkdir", "grep", "cmp", "dirname",
                "basename", "cat", "sed", "chmod", "env", "printf")


def make_path(tmp, stubs):
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    log = os.path.join(tmp, "claude-calls.log")
    for name in stubs:
        body = (f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n' if name == "claude"
                else "#!/bin/sh\nexit 0\n")
        path = os.path.join(bindir, name)
        with open(path, "w") as fh:
            fh.write(body)
        os.chmod(path, 0o755)
    for tool in SYSTEM_TOOLS:
        src = shutil.which(tool)
        if src and not os.path.exists(os.path.join(bindir, tool)):
            os.symlink(src, os.path.join(bindir, tool))
    return bindir, log


def run(tmp, args, stubs, pwsh):
    bindir, log = make_path(tmp, stubs)
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=bindir)
    cmd = [pwsh, "-NoProfile", "-File", PS1] + args if pwsh else ["bash", SH] + args
    proc = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)
    calls = open(log).read().splitlines() if os.path.exists(log) else []
    return proc.returncode, proc.stderr, calls


INSTALL = "plugin install {}@claude-plugins-official --scope project"

# (name, args, stubs on PATH, expected claude calls, substrings expected in stderr)
CASES = [
    ("installs at project scope",
     ["--lsp=pyright-lsp"], {"claude", "pyright-langserver"},
     [INSTALL.format("pyright-lsp")], []),
    ("missing language server warns with the install hint, still installs",
     ["--lsp=gopls-lsp"], {"claude"},
     [INSTALL.format("gopls-lsp")], ["'gopls' is not in PATH", "go install golang.org/x/tools/gopls@latest"]),
    ("repeatable for polyglot repos",
     ["--lsp=typescript-lsp", "--lsp=pyright-lsp"], {"claude", "typescript-language-server", "pyright-langserver"},
     [INSTALL.format("typescript-lsp"), INSTALL.format("pyright-lsp")], []),
    ("unknown plugin is skipped with a warning",
     ["--lsp=bash-lsp"], {"claude"},
     [], ["not an official LSP plugin"]),
    ("missing claude CLI warns with the /plugin command",
     ["--lsp=rust-analyzer-lsp"], {"rust-analyzer"},
     [], ["/plugin install rust-analyzer-lsp@claude-plugins-official"]),
    ("no --lsp flag never calls claude",
     [], {"claude"},
     [], []),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run init.ps1 too")
    args = ap.parse_args()
    targets = [(None, "sh")] + ([(args.pwsh, "ps1")] if args.pwsh else [])
    total = bad = 0
    for pwsh, label in targets:
        for name, flags, stubs, want_calls, want_err in CASES:
            tmp = tempfile.mkdtemp(prefix="lsp-case-")
            try:
                code, err, calls = run(tmp, flags, stubs, pwsh)
                problem = None
                if code != 0:
                    problem = f"exit {code}, want 0 — stderr: {err.strip()[-300:]}"
                elif calls != want_calls:
                    problem = f"claude calls {calls}, want {want_calls}"
                else:
                    missing = [w for w in want_err if w not in err]
                    if missing:
                        problem = f"stderr lacks {missing}: {err.strip()[-300:]}"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            total += 1
            bad += bool(problem)
            print(f"  {'ok  ' if not problem else 'BAD '}[{label}] {name}"
                  + (f" — {problem}" if problem else ""))
    print(f"\nlsp-plugin: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
