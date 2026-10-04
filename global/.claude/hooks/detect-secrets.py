# hook-kind: feedback
"""PostToolUse hook: warn when an edit touches a secret-bearing file or writes a literal credential.

The edit already happened (PostToolUse cannot undo it); the warning reaches
Claude through hookio.feedback so it can revert on the next turn.

What counts as a secret lives in _lib/secrets.py, shared with guard-commit,
which checks the same rules again before a commit. Specific to this hook:
  - The path rule judges the path inside the project, so a project that
    lives under a folder named "secrets" is not flagged file by file.
  - A secret-bearing path that git ignores is where a real value belongs
    (.env): it stays silent. One git would commit gets a warning saying so.

A warning names the line and the kind of value, never the value itself.
"""

import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import secretrules as rules  # noqa: E402

IGNORED = object()


def git_ignores(path):
    """True/False when git says whether it ignores `path`; None outside a repo or on any error."""
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        return None
    try:
        proc = subprocess.run(["git", "-C", folder, "check-ignore", "-q", "--", os.path.basename(path)],
                              capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return {0: True, 1: False}.get(proc.returncode)


def project_relative(path, payload):
    # realpath on both: macOS's /var is /private/var and Windows hands out
    # 8.3 short names (RUNNER~1), so the same folder can be spelled two ways.
    root = os.path.normcase(os.path.realpath(hookio.project_dir(payload)))
    full = os.path.normcase(os.path.realpath(path))
    return os.path.relpath(full, root) if full.startswith(root.rstrip(os.sep) + os.sep) else full


def path_warning(path, payload):
    """A warning for a secret-bearing path, IGNORED when git ignores it, or None."""
    if not rules.secret_path(project_relative(path, payload)):
        return None
    ignored = git_ignores(path)
    if ignored:
        return IGNORED
    if ignored is False:
        return (f"The edit was written to {path}, which looks like it holds secrets and is not "
                f"gitignored, so the next commit would include it. Add it to .gitignore, or keep only "
                f"placeholders in it.")
    return (f"The edit was written to {path}, which looks like it holds secrets. Make sure it is "
            f"gitignored before anything in it is committed.")


def content_warning(text, path):
    """A warning naming the line and kind of the first literal secret in `text`, or None."""
    hit = rules.first_secret(text)
    if not hit:
        return None
    lineno, found = hit
    return (f"The edit was written, and line {lineno} of the new text in {path or 'the file'} "
            f"holds {found}. Move the value to an environment variable or a gitignored file "
            f"and remove it from here.")


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    path = path if isinstance(path, str) else ""
    text = tool_input.get("new_string") or tool_input.get("content") or tool_input.get("new_source") or ""
    warning = path_warning(path, payload) if path else None
    if warning is IGNORED:
        return 0
    warning = warning or (content_warning(text, path) if isinstance(text, str) and text else None)
    return hookio.feedback(warning) if warning else 0


if __name__ == "__main__":
    hookio.entrypoint(main)
