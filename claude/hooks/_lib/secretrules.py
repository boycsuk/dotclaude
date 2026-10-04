"""What counts as a secret, shared by detect-secrets (after an edit) and guard-commit (before a commit).

One set of rules, so a calibration change lands at both checkpoints. Each
rule was learned from a measured false result:
  - Placeholder files (*.example, *.sample, *.template, *.dist, infix forms)
    and markup prose (*.md, *.rst) are exempt from the PATH rule, but their
    CONTENT is still scanned. A file inside secrets/ or credentials/ is never
    exempt; hook sources and detect-secrets' own matrix are.
  - Content is matched case-insensitively and without requiring quotes, one
    assignment at a time, so a placeholder dropped on a line never takes a
    real value with it.
  - Env-var reads and obvious placeholders in the VALUE position are not
    secrets; a mention elsewhere on the line grants no immunity.
  - Unmistakable token prefixes are scanned on the unfiltered line, minus
    AWS's documented example key.
"""

import os
import re
import sys

import writes

STORE_DIR = re.compile(r"(^|/)(secrets|credentials)/")
EXEMPT = re.compile(r"\.(example|sample|template|dist)(\.[^/]*)?$|\.(md|mdx|rst)$|/hooks/|detect-secrets-cases")
SECRET_PATH = re.compile(r"\.env$|\.env\.|secrets|credentials|private.*key|\.pem$|\.p12$|\.pfx$|\.key$"
                         r"|(^|/)id_(rsa|ed25519|ecdsa|dsa)$")
# Credential stores under the home directory, matching the central Read deny list.
CREDENTIAL_DIRS = (".ssh", ".aws", ".gnupg", ".kube", ".config/gh", ".config/gcloud", ".azure")
CREDENTIAL_FILES = (".netrc", ".npmrc", ".pypirc", ".git-credentials", ".docker/config.json",
                    ".claude/.credentials.json")
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


def secret_path(rel_path):
    """True when a project-relative path looks like it holds secrets and is not a placeholder or prose."""
    lower = rel_path.replace("\\", "/").lower()
    if not STORE_DIR.search(lower) and EXEMPT.search(lower):
        return False
    return bool(SECRET_PATH.search(lower))


def credential_file(abs_path):
    """True for a credential store under the home directory (~/.ssh/..., ~/.netrc, ...)."""
    home = writes.home().rstrip("/")
    path = abs_path.replace("\\", "/")
    if os.name == "nt" or sys.platform == "darwin":       # case-insensitive filesystems
        home, path = home.lower(), path.lower()
    if not path.startswith(home + "/"):
        return False
    rel = path[len(home) + 1:]
    return rel in CREDENTIAL_FILES or any(rel == d or rel.startswith(d + "/") for d in CREDENTIAL_DIRS)


def sensitive(word, cwd):
    """True when a path as written in a command, run from `cwd`, names a secret-bearing file."""
    full = writes.absolute(word, cwd)
    if credential_file(full):
        return True
    base = writes.absolute(".", cwd).rstrip("/")
    rel = full[len(base) + 1:] if full.startswith(base + "/") else full
    return secret_path(rel)


def line_secret(line):
    """The kind of literal secret on one line ("a GitHub token", ...), or None."""
    units = [u for u in UNIT_SPLIT.split(line) if u and not DROP.search(u)]
    labelled = next((m for m in map(LABELLED.search, units) if m), None)
    if labelled:
        return f"a literal value assigned to '{labelled.group(1)}'"
    return next((kind for rx, kind in TOKENS if rx.search(AWS_EXAMPLE.sub("", line))), None)


def first_secret(text):
    """(line number, kind) of the first literal secret in `text`, or None. Never returns the value."""
    for lineno, line in enumerate(text.splitlines(), 1):
        kind = line_secret(line)
        if kind:
            return lineno, kind
    return None
