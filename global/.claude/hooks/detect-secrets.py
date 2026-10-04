# hook-kind: feedback
"""PostToolUse hook: warn when an edit touches a secret-bearing file or writes a literal credential.

The edit already happened (PostToolUse cannot undo it); the warning reaches
Claude through hookio.feedback so it can revert on the next turn.

Calibration, each rule learned from a measured false result:
  - Placeholder files (*.example, *.sample, *.template, *.dist, infix forms)
    and markup prose (*.md, *.rst) are exempt from the PATH rule — warning on
    every edit of a `.env.example` teaches the model this hook is noise — but
    their CONTENT is still scanned. A file inside secrets/ or credentials/ is
    never exempt; hook sources and this hook's own matrix are.
  - Content is matched case-insensitively and without requiring quotes
    (`API_KEY=` is the universal spelling), one assignment at a time, so a
    placeholder dropped on a line never takes a real value with it.
  - Env-var reads and obvious placeholders in the VALUE position are not
    secrets; a mention elsewhere on the line grants no immunity.
  - Unmistakable token prefixes are scanned on the unfiltered content, minus
    AWS's documented example key.
  - The path rule judges the path inside the project, so a project that
    lives under a folder named "secrets" is not flagged file by file.
  - A secret-bearing path that git ignores is where a real value belongs
    (.env): it stays silent. One git would commit gets a warning saying so.

A warning names the line and the kind of value, never the value itself.
"""

import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

STORE_DIR = re.compile(r"(^|/)(secrets|credentials)/")
EXEMPT = re.compile(r"\.(example|sample|template|dist)(\.[^/]*)?$|\.(md|mdx|rst)$|/hooks/|detect-secrets-cases")
SECRET_PATH = re.compile(r"\.env$|\.env\.|secrets|credentials|private.*key|\.pem$|\.p12$")
UNIT_SPLIT = re.compile(r"\r?\n|[,;]|[ \t]+(?=[A-Za-z_][\w.-]*[ \t]*=)")
DROP = re.compile(
    r"[:=]\s*[\"']?(process\.env|os\.environ|getenv|ENV\[)"
    r"|\$\{\{\s*secrets\."
    r"|[:=]\s*\$\{?[A-Z_]+\}?\s*$"
    r"|[:=]\s*[\"']?[^\"' ]*(your[-_]|changeme|change[-_]me|replace|example|placeholder|dummy|xxxx)"
    r"|[:=]\s*[\"']?<[^>]+>", re.I)
LABELS = (r"api[_-]?key|secret[_-]?access[_-]?key|secret[_-]?key|access[_-]?key|encryption[_-]?key"
          r"|signing[_-]?key|secret|token|password|passwd|bearer|private[_-]?key")
LABELLED = re.compile(rf"[\"']?({LABELS})[\"']?[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9_/+.-]{{20,}}[\"']?", re.I)
TOKENS = ((re.compile(r"BEGIN[A-Z ]*PRIVATE KEY"), "a private key block"),
          (re.compile(r"AKIA[0-9A-Z]{16}"), "an AWS access key id"),
          (re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}"), "a GitHub token"),
          (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
          (re.compile(r"glpat-[A-Za-z0-9_-]{20}"), "a GitLab token"))
AWS_EXAMPLE = re.compile(r"AKIA[0-9A-Z]{9}EXAMPLE")
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
    root = os.path.abspath(hookio.project_dir(payload))
    full = os.path.abspath(path)
    return os.path.relpath(full, root) if full.startswith(root.rstrip(os.sep) + os.sep) else full


def path_warning(path, payload):
    """A warning for a secret-bearing path, IGNORED when git ignores it, or None."""
    lower = project_relative(path, payload).replace("\\", "/").lower()
    if not STORE_DIR.search(lower) and EXEMPT.search(lower):
        return None
    if not SECRET_PATH.search(lower):
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
    for lineno, line in enumerate(text.splitlines(), 1):
        units = [u for u in UNIT_SPLIT.split(line) if u and not DROP.search(u)]
        labelled = next((m for m in map(LABELLED.search, units) if m), None)
        found = (f"a literal value assigned to '{labelled.group(1)}'" if labelled else
                 next((kind for rx, kind in TOKENS if rx.search(AWS_EXAMPLE.sub("", line))), None))
        if found:
            return (f"The edit was written, and line {lineno} of the new text in {path or 'the file'} "
                    f"holds {found}. Move the value to an environment variable or a gitignored file "
                    f"and remove it from here.")
    return None


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
