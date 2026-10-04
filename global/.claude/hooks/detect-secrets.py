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
"""

import os
import re
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
PREFIXES = re.compile(r"BEGIN[A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}"
                      r"|xox[baprs]-[A-Za-z0-9-]{10,}|glpat-[A-Za-z0-9_-]{20}")
AWS_EXAMPLE = re.compile(r"AKIA[0-9A-Z]{9}EXAMPLE")
CONTENT_WARNING = "WARNING: the edit appears to contain a literal secret. Use environment variables instead."


def path_warning(path):
    lower = path.replace("\\", "/").lower()
    if not STORE_DIR.search(lower) and EXEMPT.search(lower):
        return None
    if SECRET_PATH.search(lower):
        return f"WARNING: edited {path} — verify no secrets are being committed."
    return None


def content_warning(text):
    units = [u for u in UNIT_SPLIT.split(text) if u and not DROP.search(u)]
    if any(LABELLED.search(u) for u in units) or PREFIXES.search(AWS_EXAMPLE.sub("", text)):
        return CONTENT_WARNING
    return None


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    text = tool_input.get("new_string") or tool_input.get("content") or tool_input.get("new_source") or ""
    warning = (path_warning(path) if isinstance(path, str) and path else None) or \
        (content_warning(text) if isinstance(text, str) and text else None)
    return hookio.feedback(warning) if warning else 0


if __name__ == "__main__":
    hookio.entrypoint(main)
