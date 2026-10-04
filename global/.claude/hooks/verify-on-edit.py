# hook-kind: feedback
"""PostToolUse hook: run the project's linter/typechecker on an edited file and report failures.

Auto-detects the stack (JS/TS scripts `typecheck`/`lint` with the runner the
lockfile names, ruff/mypy, clippy, go vet). Silent when nothing applies, when a
tool is missing, and when a check times out: a timeout is the budget's fault,
not the code's, and reporting it makes Claude "fix" errors that do not exist.
Failures go back to Claude
through hookio.feedback (exit 2), so it corrects them on the next turn.

Each check is bounded by VERIFY_TIMEOUT seconds (default 15; the matrix
overrides it), under the 60s per-hook timeout in settings.json. The shell
version needed a `timeout` binary stock macOS does not ship.
"""

import json
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

JS = {"ts", "tsx", "mts", "cts", "js", "jsx", "mjs", "cjs"}
LOCK_RUNNERS = (("bun.lockb", "bun"), ("bun.lock", "bun"), ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"))


def run(desc, argv, root, errors):
    exe = shutil.which(argv[0])
    if not exe:
        return
    try:
        proc = subprocess.run([exe] + argv[1:], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=int(os.environ.get("VERIFY_TIMEOUT") or 15))
    except subprocess.TimeoutExpired:
        return
    except OSError:
        return
    if proc.returncode != 0:
        errors.append(f"{desc} failed:\n{(proc.stdout + proc.stderr).rstrip()}\n")


def js_checks(root, errors):
    if not os.path.isfile(os.path.join(root, "package.json")):
        return
    runner = next((r for lock, r in LOCK_RUNNERS
                   if os.path.exists(os.path.join(root, lock)) and shutil.which(r)), "npm")
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8-sig") as fh:
            scripts = json.load(fh).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return
    # Under "scripts" specifically: a grep over the whole file once matched
    # dependency names and ran scripts that do not exist.
    for name in ("typecheck", "lint"):
        if name in scripts:
            run(name, [runner, "run", name, "--silent"], root, errors)


def python_checks(root, file, errors):
    pyproject = os.path.join(root, "pyproject.toml")
    if any(os.path.exists(os.path.join(root, f)) for f in ("pyproject.toml", "ruff.toml", ".ruff.toml")):
        run("ruff", ["ruff", "check", file], root, errors)
    try:
        with open(pyproject, encoding="utf-8") as fh:
            has_mypy = "[tool.mypy]" in fh.read()
    except OSError:
        has_mypy = False
    if has_mypy:
        run("mypy", ["mypy", file], root, errors)


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
    errors = []
    if ext in JS:
        js_checks(root, errors)
    elif ext in ("py", "pyi"):
        python_checks(root, file, errors)
    elif ext == "rs" and os.path.isfile(os.path.join(root, "Cargo.toml")):
        run("clippy", ["cargo", "clippy", "--quiet", "--message-format=short", "--", "-D", "warnings"], root, errors)
    elif ext == "go" and os.path.isfile(os.path.join(root, "go.mod")):
        run("go vet", ["go", "vet", "./..."], root, errors)
    if errors:
        return hookio.feedback(f"Verification failed after editing {file}:\n" + "\n".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
