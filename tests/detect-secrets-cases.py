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

import os
import shutil
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
BECH32 = "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L"     # Bech32's alphabet, upper-case as age prints it
AGE_KEY = "AGE-SECRET-KEY-" + "1" + BECH32 + BECH32[:26]          # 58 characters after the "1"
AGE_PQ_KEY = "AGE-SECRET-KEY-PQ-" + "1" + BECH32[::-1] + BECH32[:26]

# aegis's committed secret store (specs/phases/07-secrets.md): names, recipients' public keys, and one age
# ciphertext per value.
AEGIS_MANIFEST = ('schema = 1\n[[secret]]\nname = "DATABASE_URL"\ndescription = "Postgres for local dev"\n'
                  'environments = ["development"]\nagent_visible = false\n')
AEGIS_RECIPIENTS = ('schema = 1\n[[recipient]]\n'
                    'key = "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqs3290gq"\n'
                    'label = "cosmin (laptop)"\n')
AEGIS_VALUES = ("schema = 1\n[[value]]\nname = \"DATABASE_URL\"\nciphertext = '''\n"
                "-----BEGIN AGE ENCRYPTED FILE-----\n"
                "YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSBEd1N0V0pXa3J0Zk5UNTJu\n"
                "Rk9lRnl2L3pQb1pMOHhjV0lKR3VKK0F6ckE4CjBtM2Z5S0x0cW1ZZ3dzQ0JjT2hr\n"
                "-----END AGE ENCRYPTED FILE-----\n'''\n"
                'changed_by = { human = "Cosmin B." }\nchanged_at = "2026-10-06T12:05:00Z"\n')

# Written out here rather than imported, so a name dropped from the hook's list fails a case.
CODE_EXTENSIONS = ("rs", "py", "pyi", "js", "mjs", "cjs", "jsx", "ts", "mts", "cts", "tsx", "vue", "svelte",
                   "go", "java", "kt", "kts", "scala", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "rb",
                   "ex", "exs", "dart", "lua", "zig")
PROSE_EXTENSIONS = ("md", "mdx", "rst")

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
    ("/p/secrets/prod.md", "anything\n", QUIET,
     "prose inside secrets/ documents the store; its content is still scanned (2026-10-08)"),
    ("/p/secrets/prod.md", f"API_KEY={KEY}\n", WARN, "a key pasted into that prose"),

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

    # --- source and prose are named for what they handle, not what they hold (2026-10-08) ---
    # A secrets feature lives in src/secrets/ and secrets.rs; warning on every edit taught the
    # model to gitignore source code.
    *[(f"/p/crates/engine/src/secrets/{name}.rs", "pub fn load() {}\n", QUIET, "aegis's secrets module")
      for name in ("mod", "manifest", "recipients", "values", "identity", "pins", "ci")],
    ("/p/crates/engine/src/catalogue/secrets.rs", "pub fn list() {}\n", QUIET, "a source file named secrets"),
    ("/p/crates/engine/tests/secrets.rs", "#[test]\nfn binds() {}\n", QUIET, "a test file named secrets"),
    ("/p/crates/gui/src/screens/secrets/mod.rs", "pub fn view() {}\n", QUIET, "a screen module in secrets/"),
    ("/p/docs/design/screens/secrets/README.md", "# Secrets screen\n", QUIET, "a design spec in secrets/"),
    ("/p/specs/phases/07-secrets.md", "# Secrets\n", QUIET, "a spec named secrets"),
    *[(f"/p/src/secrets/store.{ext}", "x = 1\n", QUIET, f"a .{ext} source file inside secrets/")
      for ext in CODE_EXTENSIONS],
    *[(f"/p/credentials/guide.{ext}", "How rotation works.\n", QUIET, f".{ext} prose inside credentials/")
      for ext in PROSE_EXTENSIONS],

    # --- aegis's committed store holds names and age ciphertext, never a plaintext value ---
    ("/p/.aegis/secrets.toml", AEGIS_MANIFEST, QUIET, "the manifest holds names only"),
    ("/p/.aegis/recipients.toml", AEGIS_RECIPIENTS, QUIET, "recipients are public keys"),
    *[(f"/p/.aegis/secrets/{env}.toml", AEGIS_VALUES, QUIET, f"the {env} values are age ciphertext")
      for env in ("development", "staging", "production")],
    ("/p/.aegis/secrets/production.toml", f'[[value]]\nname = "X"\napi_key = "{KEY}"\n', WARN,
     "a plaintext value in the store is still caught by its content"),
    ("/p/.aegis/secrets/production.json", "{}\n", WARN, "the store exemption covers .toml only"),
    ("/p/.aegis/secrets.toml.bak", "x\n", WARN, "a copy of the manifest is not the manifest"),
    ("/p/.aegis/secrets/.env.toml", "x\n", WARN, "a dotfile in the store is not an environment's values"),

    # --- still secret-bearing by path: data, config and scripts, not source ---
    ("/p/.env.local", "DEBUG=1\n", WARN, "a .env variant"),
    ("/p/.env.ts", "export default {}\n", WARN, "a .env.* name stays secret-bearing whatever its extension"),
    ("/p/secrets.json", "{}\n", WARN, "a secrets file in JSON"),
    ("/p/secrets.yaml", "db: x\n", WARN, "a secrets file in YAML"),
    ("/p/config/secrets.toml", "db = 1\n", WARN, "secrets.toml outside .aegis/"),
    ("/p/secrets/db_password.txt", "x\n", WARN, "a value file inside secrets/"),
    ("/p/credentials/service-account.json", "{}\n", WARN, "a key file inside credentials/"),
    ("/p/secrets.sh", "export DB=1\n", WARN, "a shell file sourced for its exports is a .env by another name"),
    ("/p/secrets/env.ps1", "$env:DB = 1\n", WARN, "the PowerShell spelling of the same"),
    ("/p/config/secrets.php", "<?php return [];\n", WARN,
     "a PHP config returning an array; its '=>' form escapes the content scan"),

    # --- the content of an exempt source file is still scanned ---
    ("/p/crates/engine/src/secrets/values.rs", f'let api_key = "{KEY}";\n', WARN, "a literal key in a .rs"),
    ("/p/crates/engine/src/secrets/values.rs", f'const API_KEY: &str = "{KEY}";\n', WARN,
     "Rust's typed constant: the type sits between the label and '='"),
    ("/p/crates/engine/src/secrets/values.rs", f"static TOKEN: &'static str = \"{KEY}\";\n", WARN,
     "a lifetime in the type"),
    ("/p/crates/engine/src/secrets/values.rs", f'let password: String = "{KEY}".into();\n', WARN,
     "a bare type name must not be split off as an assignment of its own"),
    ("/p/src/secrets/client.ts", f'const apiKey: string = "{KEY}";\n', WARN, "TypeScript's annotation"),
    ("/p/src/Config.kt", f'val token: String = "{KEY}"\n', WARN, "Kotlin's annotation"),
    ("/p/src/settings.py", f'api_key: str = "{KEY}"\n', WARN, "a Python type hint"),
    ("/p/src/settings.py", f'api_key: str | None = "{KEY}"\n', WARN, "a union type, spaces inside it"),
    ("/p/src/settings.py", f'api_key = "{KEY}"  # default = "changeme"\n', WARN,
     "a spaced '=' in a comment still splits off its placeholder"),
    ("/p/src/settings.py", f'self.api_key: str = "{KEY}"\n', WARN, "an annotated attribute"),
    ("/p/src/client.py", f'def connect(self, api_key: str = "{KEY}"):\n', WARN, "an annotated default argument"),
    ("/p/src/secrets/values.rs", f'pub(crate) const GITHUB_TOKEN: &str = "{KEY}";\n', WARN,
     "the label inside a longer name, behind pub(crate)"),
    # The annotation rewrite once took any `word:` as a declaration and ate the label after it.
    ("/p/src/settings.py", f'else: password = "{KEY}"\n', WARN, "a one-line else before the assignment"),
    ("/p/src/env.ts", f'    case "prod": token = "{KEY}"; break;\n', WARN, "a switch case before the assignment"),
    ("/p/README.md", f'# note: api_key = "{KEY}"\n', WARN, "prose with a colon before the assignment"),
    ("/p/src/client.py", "if token: headers = build_authorization_header(token)\n", QUIET,
     "a label used as a condition is not a declaration"),
    ("/p/src/env.ts", "case 'token': kind = 'authentication_header_name';\n", QUIET,
     "a label used as a case value is not a declaration"),
    ("/p/cmd/main.go", f'apiKey := "{KEY}"\n', WARN, "Go's short declaration"),
    ("/p/crates/engine/src/secrets/values.rs", "let password: String = String::new();\n", QUIET,
     "a typed declaration of an empty value"),
    ("/p/crates/engine/src/secrets/values.rs", "pub token: Option<String>,\n", QUIET, "a typed field, no value"),
    ("/p/src/secrets/client.ts", "interface Auth { apiKey: string; }\n", QUIET, "a type with no value"),
    ("/p/src/settings.py", 'api_key: str = "your-api-key-goes-here"\n', QUIET, "a typed placeholder"),

    # --- age identities: the private half of aegis's keys (C2SP age spec: Bech32, 32 bytes) ---
    ("/p/crates/engine/tests/secrets.rs", f'const IDENTITY: &str = "{AGE_KEY}";\n', WARN,
     "an age secret key under a label the scan does not know"),
    ("/p/key.txt", f"# created: 2026-10-08T12:00:00Z\n{AGE_KEY}\n", WARN, "age-keygen's output file"),
    ("/p/.aegis/secrets/production.toml", f"{AEGIS_VALUES}identity = '{AGE_KEY}'\n", WARN,
     "an age secret key in the committed store"),
    ("/p/key.txt", f"{AGE_PQ_KEY}\n", WARN, "age's post-quantum identity, age-keygen -pq"),
    ("/p/docs/secrets.md", "Identities start with AGE-SECRET-KEY-1... and recipients with age1...\n", QUIET,
     "documentation naming the prefix"),
    ("/p/key.txt", f"{AGE_KEY[:-1]}\n", QUIET, "one character short is not an age key"),
]


def invoke(runner, file_path, content):
    # A dict content is a raw tool_input fragment (Edit's old/new_string, or
    # NotebookEdit's notebook_path+new_source — that one deliberately gets
    # NO file_path so the fallback is what is being tested); a string is the
    # plain Write/Edit `content` field.
    if isinstance(content, dict):
        tool_input = dict(content)
        tool = "NotebookEdit" if "notebook_path" in tool_input else "Edit"
        if tool == "Edit":
            tool_input["file_path"] = file_path
    else:
        tool, tool_input = "Write", pyhook.edit_input(file_path, content, "Write")
    code, out, err = pyhook.run("detect-secrets", pyhook.payload(tool, tool_input, event="PostToolUse"),
                                pwsh=runner)
    got = pyhook.verdict(code, out, err, feedback=True)
    return {"feedback": WARN, "quiet": QUIET}.get(got, got)


def message_cases(runners):
    """What the warning says, and the gitignore check on secret-bearing paths."""
    repo = tempfile.mkdtemp(prefix="detect-secrets-")
    failures = 0
    try:
        pyhook.git(repo, "init", "-q")
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
            payload = pyhook.payload("Write", pyhook.edit_input(path, content, "Write"), event="PostToolUse",
                                     cwd=repo)
            for name, pwsh in runners:
                code, out, err = pyhook.run("detect-secrets", payload, cwd=repo, pwsh=pwsh)
                problems = []
                if code != want_code:
                    problems.append(f"exit {code}")
                if must and must not in err:
                    problems.append(f"no {must!r}")
                if must_not and must_not in err:
                    problems.append("the secret value is echoed")
                if want_code == 2 and "was written" not in err:
                    problems.append("does not say the edit was written")
                if want_code == 0 and err.strip():
                    problems.append("stderr at exit 0")
                if problems:
                    failures += 1
                    print(f"  FAIL ({name}) {os.path.basename(path)}: {', '.join(problems)}   ({why}) "
                          f"{err.strip()[:200]!r}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        if os.path.islink(repo + "-link"):
            os.remove(repo + "-link")
    return failures, len(cases)


def main():
    args = pyhook.cli()
    runners = pyhook.runners(args.pwsh)
    failures = 0
    for path, content, want, why in CASES:
        results = {name: invoke(pwsh, path, content) for name, pwsh in runners}
        if any(got != want for got in results.values()):
            failures += 1
            detail = ", ".join(f"{n}={g}" for n, g in results.items())
            print(f"  FAIL want {want} got {detail} | {path}   ({why})")
    message_failures, message_total = message_cases(runners)
    return pyhook.finish("detect-secrets", failures + message_failures, len(CASES) + message_total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
