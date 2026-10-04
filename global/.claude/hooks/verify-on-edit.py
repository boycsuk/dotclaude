# hook-kind: feedback
"""PostToolUse hook: run the project's linter/typechecker on an edited file and report failures.

Auto-detects the stack (JS/TS scripts `typecheck`/`lint` with the runner the
lockfile names, ruff/mypy, clippy, go vet). Silent when nothing applies, when a
tool is missing, and when a check times out: a timeout is the budget's fault,
not the code's, and reporting it makes Claude "fix" errors that do not exist.
Failures go back to Claude
through hookio.feedback (exit 2), so it corrects them on the next turn.

Each check is bounded by VERIFY_TIMEOUT seconds (default 15; the matrix
overrides it), under the 60s per-hook timeout in settings.json, and the checks
of one edit run concurrently, so the wait is the slowest check, not the sum.
A report is capped at MAX_LINES per check, keeping the edited file's lines
first: a project with existing lint debt otherwise re-injected its whole
report on every edit, and whole-project checks are labelled as such so Claude
does not "fix" files the edit never touched.
"""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import bootstrap  # noqa: E402,F401
import hookio  # noqa: E402

JS = {"ts", "tsx", "mts", "cts", "js", "jsx", "mjs", "cjs"}
LOCK_RUNNERS = (("bun.lockb", "bun"), ("bun.lock", "bun"), ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"))
MAX_LINES = 40
WHOLE, THIS_FILE = "whole project", "this file"


def trim(output, file):
    """`output` cut to MAX_LINES, the lines naming the edited file kept first, order preserved."""
    lines = output.splitlines()
    if len(lines) <= MAX_LINES:
        return output
    name = os.path.basename(file)
    ranked = sorted(range(len(lines)), key=lambda i: (name not in lines[i], i))
    kept = sorted(ranked[:MAX_LINES])
    cut = len(lines) - len(kept)
    return "\n".join(lines[i] for i in kept) + f"\n... {cut} more line(s) cut; run /verify for the full report"


def run(check, root, file):
    """The failure report of one (label, scope, argv) check, or None when it passes or cannot run."""
    label, scope, argv = check
    exe = shutil.which(argv[0])
    if not exe:
        return None
    try:
        proc = subprocess.run([exe] + argv[1:], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=int(os.environ.get("VERIFY_TIMEOUT") or 15))
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode == 0:
        return None
    return f"{label} ({scope}) failed:\n{trim((proc.stdout + proc.stderr).rstrip(), file)}\n"


def js_checks(root):
    if not os.path.isfile(os.path.join(root, "package.json")):
        return []
    runner = next((r for lock, r in LOCK_RUNNERS
                   if os.path.exists(os.path.join(root, lock)) and shutil.which(r)), "npm")
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8-sig") as fh:
            scripts = json.load(fh).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return []
    # Under "scripts" specifically: a grep over the whole file once matched
    # dependency names and ran scripts that do not exist.
    return [(name, WHOLE, [runner, "run", name, "--silent"])
            for name in ("typecheck", "lint") if name in scripts]


def python_checks(root, file):
    checks = []
    if any(os.path.exists(os.path.join(root, f)) for f in ("pyproject.toml", "ruff.toml", ".ruff.toml")):
        checks.append(("ruff", THIS_FILE, ["ruff", "check", file]))
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
            if "[tool.mypy]" in fh.read():
                checks.append(("mypy", THIS_FILE, ["mypy", file]))
    except OSError:
        pass
    return checks


def checks_for(root, file, ext):
    if ext in JS:
        return js_checks(root)
    if ext in ("py", "pyi"):
        return python_checks(root, file)
    if ext == "rs" and os.path.isfile(os.path.join(root, "Cargo.toml")):
        return [("clippy", WHOLE, ["cargo", "clippy", "--quiet", "--message-format=short", "--", "-D", "warnings"])]
    if ext == "go" and os.path.isfile(os.path.join(root, "go.mod")):
        return [("go vet", WHOLE, ["go", "vet", "./..."])]
    return []


def inside(file, root):
    """True when `file` is under `root` (separator-anchored; case-folded where the FS is)."""
    f, r = os.path.normcase(os.path.abspath(file)), os.path.normcase(os.path.abspath(root))
    return f.startswith(r.rstrip(os.sep) + os.sep)


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    file = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not isinstance(file, str) or not file or not os.path.isdir(root) or not inside(file, root):
        return 0
    ext = file.rsplit(".", 1)[-1].lower() if "." in os.path.basename(file) else ""
    checks = checks_for(root, file, ext)
    if not checks:
        return 0
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        errors = [e for e in pool.map(lambda c: run(c, root, file), checks) if e]
    if not errors:
        return 0
    header = f"Checks failed after editing {file}."
    if any(f"({WHOLE})" in e for e in errors):
        header += (" Whole-project checks also report problems in files this edit did not touch: "
                   "fix what this edit caused unless asked to do more.")
    return hookio.feedback(header + "\n" + "\n".join(errors))


if __name__ == "__main__":
    hookio.entrypoint(main)
