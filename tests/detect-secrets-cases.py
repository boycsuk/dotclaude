#!/usr/bin/env python3
"""Behavioural contract for detect-secrets.py.

Run:  python3 tests/detect-secrets-cases.py
      python3 tests/detect-secrets-cases.py --pwsh PATH   # also through PowerShell

This hook warns on edits that touch a secret-bearing file or that contain a
literal credential. Both halves were miscalibrated in opposite directions,
which is why the matrix covers both:

  - False positives: the path rule fired on `.env.example` — a file the
    template itself ships and .gitignore explicitly whitelists — on prose about
    credentials, and on this very hook (whose path contains "secrets"). A
    warning that fires on files which by definition hold no secret teaches the
    model to ignore the warning that matters.
  - False negatives: the content pattern was case-sensitive and required
    quotes, so `API_KEY=sk-live-...` — the universal spelling in a .env file —
    was not detected at all.

Secret-looking values are assembled at runtime so this file is not itself
flagged by the hook it tests.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WARN, QUIET = "WARN", "QUIET"

# Assembled at runtime: a literal here would trip the hook on every edit.
KEY = "sk-live-" + "9f3b" * 6
JWT = "eyJhbGciOi" + "A" * 30
AKIA = "AKIA" + "0123456789ABCDEF"          # AWS access key id shape
GHP = "ghp_" + "a1B2" * 9                   # GitHub PAT shape (36 after prefix)
XOXB = "xoxb-" + "1234567890-abcdefghij"    # Slack bot token shape
PEM = "-----BEGIN RSA PRIVATE " + "KEY-----"

# (file_path, content, expected, why)
CASES = [
    # --- must stay quiet: placeholders, prose, and the tooling itself -------
    ("/p/.env.example", "API_KEY=your-key-here\n", QUIET,
     "the template ships this file and .gitignore whitelists it"),
    ("/p/.env.sample", "TOKEN=changeme\n", QUIET, "same role, different name"),
    ("/p/config.env.template", "DB_PASSWORD=\n", QUIET, "template placeholder"),
    ("/p/docs/credentials-policy.md", "Never commit an API key.\n", QUIET,
     "prose ABOUT secrets holds none"),
    ("/p/.claude/hooks/detect-secrets.sh", "case $PATH in *secrets*)\n", QUIET,
     "the detector's own path contains 'secrets'"),
    ("/p/src/main.py", "def load_config():\n    return {}\n", QUIET,
     "ordinary source"),
    ("/p/README.md", "Set API_KEY in your environment.\n", QUIET,
     "docs naming the variable without a value"),

    # --- must warn: a real secret, wherever it appears ----------------------
    ("/p/.env", f"API_KEY={KEY}\n", WARN, "the real .env file"),
    ("/p/config/app.env", f"API_KEY={KEY}\n", WARN,
     "upper-case and unquoted — the common .env spelling"),
    ("/p/src/main.py", f'API_KEY = "{KEY}"\n', WARN,
     "upper-case constant in source"),
    ("/p/src/main.py", f'api_key = "{KEY}"\n', WARN, "lower-case in source"),
    ("/p/src/auth.js", f'const token = "{JWT}"\n', WARN, "a JWT-looking token"),
    ("/p/settings.yaml", f'secret: "{KEY}"\n', WARN, "yaml secret"),
    ("/p/id_rsa.pem", "-----BEGIN PRIVATE KEY-----\n", WARN, "a key file"),
    ("/p/secrets/prod.txt", "anything\n", WARN, "a secrets/ directory"),
    # Content still scanned even in an exempt path: a real key in a
    # placeholder is exactly the mistake worth catching.
    ("/p/.env.example", f"API_KEY={KEY}\n", WARN,
     "a REAL key pasted into the placeholder is still caught"),

    # --- exemptions that were too broad in the first draft ------------------
    ("/p/notes.txt", f"the key is API_KEY={KEY}\n", WARN,
     ".txt is the classic place to paste a key — not exempt"),
    ("/p/.claude/settings.local.json", f'"GITHUB_TOKEN": "{KEY}"\n', WARN,
     "JSON shape: the quote precedes the colon"),
    ("/p/SECRETS/prod.txt", "anything\n", WARN,
     "upper-case dir: the .sh case arms are case-folded to match PowerShell"),
    ("/p/secrets/prod.md", "anything\n", WARN,
     "markup inside secrets/ is still a secret store"),

    # --- reading a secret FROM the environment is the DESIRED pattern -------
    ("/p/src/config.js", "token: process.env.GITHUB_TOKEN_FOR_RELEASES\n", QUIET,
     "an env-var reference is not a literal"),
    ("/p/src/config.py", 'api_key = os.environ["OPENAI_API_KEY_PRODUCTION"]\n', QUIET,
     "same, Python spelling"),
    ("/p/.github/workflows/ci.yml", "token: ${{ secrets.RELEASE_TOKEN }}\n", QUIET,
     "a CI secret reference is not a literal"),
    ("/p/src/auth.py", "password_hash = bcrypt.hashpw(pw, bcrypt.gensalt())\n", QUIET,
     "hashing a password is not storing one"),

    # --- single quotes: Python's default string style -----------------------
    ("/p/src/main.py", f"api_key = '{KEY}'\n", WARN,
     "single-quoted — the .sh [\\x27] class was not a hex escape in ERE"),

    # --- compound labels the suffix-anchored pattern missed -----------------
    ("/p/src/settings.py", f'SECRET_KEY = "{KEY}"\n', WARN,
     "Django's SECRET_KEY — 'secret' followed by another word"),
    ("/p/config/app.conf", f"AWS_SECRET_ACCESS_KEY={KEY}\n", WARN,
     "among the most-leaked secrets in real repos"),
    ("/p/config/app.conf", f"ENCRYPTION_KEY={KEY}\n", WARN, "compound *_KEY label"),

    # --- unmistakable prefixes, unattached to any label ---------------------
    ("/p/scripts/upload.sh", f"ACCESS_ID={AKIA}\n", WARN,
     "AKIA prefix — the label 'ACCESS_ID' matches nothing"),
    ("/p/deploy_key", PEM + "\n", WARN, "PEM block in a neutrally-named file"),
    ("/p/src/notify.js", f'fetch(url, auth("{XOXB}"))\n', WARN,
     "Slack token inside a call, no label at all"),
    ("/p/src/gh.py", f'gh = "{GHP}"\n', WARN,
     "GitHub PAT assigned to a variable not named token"),

    # --- Edit's own field: new_string ---------------------------------------
    ("/p/src/main.py", {"old_string": "x", "new_string": f'password = "{KEY}"\n'}, WARN,
     "Edit sends new_string, never content"),

    # --- a placeholder elsewhere on the line grants no immunity (2026-10-03) -
    ("/p/config.json", f'{{"api_key": "{KEY}", "docs": "https://example.com"}}\n', WARN,
     "the JSON line also holds an example URL"),
    ("/p/run.sh", f"API_KEY={KEY} DEFAULT_PW=changeme\n", WARN,
     "two assignments, the second a placeholder"),
    ("/p/aws.py", f'AWS = "{AKIA}"  # see: replace_me\n', WARN,
     "a prefixed token next to a placeholder word"),
    ("/p/aws.py", 'key = "AKIA' + 'IOSFODNN7EXAMPLE"\n', QUIET,
     "AWS's documented example key"),
    ("/p/config.yml", f"password:\n  {KEY}\n", QUIET,
     "a value on the next line is not this label's — the .ps1 once read across lines"),

    # --- the env-reference drop must apply to the VALUE position only -------
    ("/p/src/main.py", f'api_key = "{KEY}"  # was process.env before\n', WARN,
     "a literal secret is not immunised by a comment naming process.env"),

    # --- descriptive placeholders in .example files are not secrets ---------
    ("/p/.env.example", "TOKEN=your-token-goes-here-please-replace\n", QUIET,
     "20+ char placeholder — recommended practice, not a leak"),
    ("/p/.env.example", "API_KEY=<paste-your-real-key-here>\n", QUIET,
     "angle-bracket placeholder"),

    # --- the hook's own test matrix contains 'secrets' in its name ----------
    ("/repo/tests/detect-secrets-cases.py", "CASES = []\n", QUIET,
     "editing the matrix must not cry wolf — same rationale as */hooks/*"),

    # --- key files by name, aligned with the Read deny list -----------------
    ("/p/deploy/server.key", "not a pem header\n", WARN, "a .key file"),
    ("/p/keys/id_ed25519", "x\n", WARN, "an ssh private key by name"),
    ("/p/src/monkey.py", "x = 1\n", QUIET, "a name merely ending in 'key' is not a key file"),

    # --- NotebookEdit payload: notebook_path + new_source -------------------
    ("/p/analysis.ipynb", {"notebook_path": "/p/analysis.ipynb",
                           "new_source": f'api_key = "{KEY}"\n'}, WARN,
     "a key pasted into a notebook cell must be scanned too"),
]


def invoke(runner, file_path, content):
    # A dict content is a raw tool_input fragment (Edit's old/new_string, or
    # NotebookEdit's notebook_path+new_source — that one deliberately gets
    # NO file_path so the fallback is what is being tested); a string is the
    # plain Write/Edit `content` field.
    if isinstance(content, dict):
        tool_input = dict(content)
        if "notebook_path" not in tool_input:
            tool_input["file_path"] = file_path
    else:
        tool_input = {"file_path": file_path, "content": content}
    payload = {"tool_input": tool_input}
    proc = subprocess.run(runner, input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30)
    return WARN if proc.returncode == 2 else QUIET if proc.returncode == 0 else f"CRASH(rc={proc.returncode})"


def message_cases(runners):
    """What the warning says, and the gitignore check on secret-bearing paths."""
    repo = tempfile.mkdtemp(prefix="detect-secrets-")
    failures = 0
    try:
        subprocess.run(["git", "init", "-q", repo], check=True)
        with open(os.path.join(repo, ".gitignore"), "w") as fh:
            fh.write(".env\n")
        os.makedirs(os.path.join(repo, "config"))
        env, store, src = (os.path.join(repo, p) for p in (".env", "config/secrets.yaml", "app.py"))
        for p in (env, store, src):
            open(p, "w").close()
        # (path, content, expected exit, text the message must hold, text it must not, why)
        cases = [
            (env, f"API_KEY={KEY}\n", 0, None, None,
             "a gitignored .env is where a real value belongs"),
            (store, "db: x\n", 2, "not gitignored", None,
             "a secret-bearing file git would commit"),
            (src, f"import os\n\napi_key = '{KEY}'\n", 2, "line 3", KEY,
             "the warning names the line and never echoes the value"),
            (src, f"x = 1\n{GHP}\n", 2, "GitHub token", GHP, "a token prefix is named by its kind"),
        ]
        # The same folder spelled through a symlink (macOS's /var is
        # /private/var) must still read as inside the project.
        link = repo + "-link"
        try:
            os.symlink(repo, link, target_is_directory=True)
            cases.append((os.path.join(link, "app.py"), f"a = 1\nb = 2\ntoken = '{KEY}'\n", 2, "line 3", KEY,
                          "a path through a symlink to the project is still project-relative"))
        except OSError:
            pass
        for path, content, want_code, must, must_not, why in cases:
            payload = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
            for name, runner in runners:
                proc = subprocess.run(runner, input=json.dumps(payload), capture_output=True,
                                      text=True, encoding="utf-8", timeout=30, cwd=repo)
                problems = []
                if proc.returncode != want_code:
                    problems.append(f"exit {proc.returncode}")
                if must and must not in proc.stderr:
                    problems.append(f"no {must!r}")
                if must_not and must_not in proc.stderr:
                    problems.append("the secret value is echoed")
                if want_code == 2 and "was written" not in proc.stderr:
                    problems.append("does not say the edit was written")
                if problems:
                    failures += 1
                    print(f"  FAIL ({name}) {os.path.basename(path)}: {', '.join(problems)}   ({why}) "
                          f"{proc.stderr.strip()[:200]!r}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        if os.path.islink(repo + "-link"):
            os.remove(repo + "-link")
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()

    runners = [(label, pyhook.argv("detect-secrets", pwsh)) for label, pwsh in pyhook.runners(args.pwsh)]

    failures = 0
    for path, content, want, why in CASES:
        results = {}
        for name, runner in runners:
            try:
                results[name] = invoke(runner, path, content)
            except subprocess.TimeoutExpired:
                results[name] = "TIMEOUT"
        if any(got != want for got in results.values()):
            failures += 1
            detail = ", ".join(f"{n}={g}" for n, g in results.items())
            print(f"  FAIL want {want} got {detail} | {path}   ({why})")

    failures += message_cases(runners)

    print(f"\n{len(CASES) + 4} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
