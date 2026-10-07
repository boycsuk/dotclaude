#!/usr/bin/env python3
"""Behavioural contract for guard-commit.py.

Run:  python3 tests/guard-commit-cases.py
      python3 tests/guard-commit-cases.py --pwsh PATH   # PowerShell command form too

The hook turns the commit conventions into decisions: deny trailers, emoji
and Spanish messages; ask on --amend, on main, on a missing CHANGELOG entry
and on a .sh/.ps1 pair committed half. Every guard hook in this repo shipped
defects that reading it did not reveal, so the false-
positive controls matter as much as the catches: a hook that blocks innocent
commits teaches the model to route around it.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

DENY, ASK, ALLOW = "deny", "ask", "allow"
git = pyhook.git
HEREDOC = "git commit -m \"$(cat <<'EOF'\n{}\nEOF\n)\""

# Default state: on a feature branch, app.py and CHANGELOG.md both staged —
# so only the message decides.
MESSAGE_CASES = [
    # Trailers, in every way they can be written.
    ('git commit -m "Add x" -m "Co-Authored-By: Claude <noreply@anthropic.com>"', DENY, "trailer in a second -m"),
    (HEREDOC.format("feat: add x\n\nCo-Authored-By: Claude <noreply@anthropic.com>"), DENY, "trailer inside a heredoc message"),
    (HEREDOC.format("feat: add x\n\nSigned-off-by: Dev <d@x>"), DENY, "Signed-off-by line"),
    ("git commit -s -m 'feat: add x'", DENY, "-s adds Signed-off-by"),
    ("git commit -sm 'feat: add x'", DENY, "-s clustered with -m"),
    ("git commit --signoff -m 'feat: add x'", DENY, "--signoff"),
    ("git commit --trailer 'Signed-off-by: x <x@y>' -m 'feat: add x'", DENY, "--trailer with an attribution key"),
    ("git commit --trailer=Co-authored-by=x -m 'feat: add x'", DENY, "--trailer= form, key=value"),
    ("git commit --trailer 'Closes: #12' -m 'feat: add x'", ALLOW, "a non-attribution trailer"),
    ("git -C . commit -m 'feat' -m 'co-authored-by: someone'", DENY, "lowercase trailer through git -C"),
    ("env GIT_EDITOR=true git commit -m 'x' -m 'Co-Authored-By: a'", DENY, "env wrapper"),
    ("git add -A && git commit -m 'x' -m 'Co-Authored-By: a'", DENY, "after git add in the same command"),
    ("ls # check\ngit commit -m 'feat: x' -m 'Co-Authored-By: a'", DENY,
     "a comment on an earlier line must not hide the commit"),
    ("ls # don't\ngit commit -m 'feat: x' -m 'Co-Authored-By: a'", DENY,
     "an apostrophe in a comment must not abort the parse"),
    ("cat > f <<EOF\n$(git commit -m 'feat: x' -m 'Co-Authored-By: a')\nEOF", DENY,
     "an unquoted heredoc runs its $( )"),
    ("git commit -F msg.txt", DENY, "-F file carrying a trailer (file written by the case)"),
    ("git commit -F - <<'EOF'\nfeat: x\n\nSigned-off-by: a <a@b>\nEOF", DENY, "-F - from a heredoc"),
    # Forms a review found walking past the first parser (all verified bypasses).
    ("timeout 60 git commit -s -m 'feat: x'", DENY, "timeout wrapper with its duration"),
    ("nice -n 5 git commit -s -m 'feat: x'", DENY, "nice with a valued flag"),
    ("env -u FOO git commit -s -m 'feat: x'", DENY, "env -u NAME"),
    ("echo x | xargs git commit -s -m", DENY, "xargs"),
    ("(git commit -s -m 'feat: x')", DENY, "subshell"),
    ("git com''mit --signoff -m 'feat: x'", DENY, "empty quotes split the subcommand past the prefilter"),
    ("g\"\"it commit -s -m 'feat: x'", DENY, "empty quotes split the program name"),
    ("GIT commit -s -m 'feat: x'", DENY, "case-insensitive filesystems resolve GIT to git"),
    ("cd $'a\\0b'; git commit -s -m 'feat: x'", DENY, "a NUL byte in the cd target must not crash the guard"),
    ("{ git commit -s -m 'feat: x'; }", DENY, "brace group"),
    ("if true; then git commit -s -m 'feat: x'; fi", DENY, "inside if/then"),
    ("bash -c \"git commit -s -m 'feat: x'\"", DENY, "bash -c string"),
    ("git commit --signo --mess 'feat: x'", DENY, "abbreviated long options git accepts"),
    ("git commit --mess 'feat: x' --mess 'Co-Authored-By: a'", DENY, "abbreviated --message with a trailer"),
    ("git commit -m $'feat: x\\n\\nCo-Authored-By: a <a@b>'", DENY, "ANSI-C quoted message"),
    (HEREDOC.format('fix: handle the "foo bar" case\n\nCo-Authored-By: a <a@b>'), DENY,
     "double quotes inside the heredoc body"),
    ("git commit -F - <<'EOF'\nfix: don't crash\n\nCo-Authored-By: a <a@b>\nEOF", DENY,
     "apostrophe in a -F - heredoc"),
    ("cat > /tmp/gc-msg <<'EOF'\nfeat: x\n\nSigned-off-by: a <a@b>\nEOF\ngit commit -F /tmp/gc-msg", DENY,
     "message file written earlier in the same command"),
    ("cat > notes.md <<'EOF'\nCo-Authored-By: x\nEOF\ngit commit -m 'feat: x'", ALLOW,
     "an unrelated heredoc carrying the words"),
    # Emoji.
    ("git commit -m 'feat: add login ✨'", DENY, "sparkles emoji"),
    ("git commit -m 'fix: 🐛 null check'", DENY, "bug emoji"),
    ("git commit -m 'docs: done ✅'", DENY, "check-mark emoji"),
    # Spanish.
    ("git commit -m 'Añade la validación de usuarios'", DENY, "Spanish with accents and function words"),
    (HEREDOC.format("fix: corrige el cálculo de la fecha"), DENY, "Spanish in a heredoc"),
    # Must pass: English, with the scary words used innocently.
    ("git commit -m 'feat(hooks): add guard-commit'", ALLOW, "plain English"),
    (HEREDOC.format("feat: add x\n\nExplains why co-authored commits are blocked."), ALLOW,
     "the words without a trailer line"),
    ("git commit -m 'docs: mention Signed-off-by policy in README'", ALLOW, "trailer name mid-line"),
    ("git commit -m 'fix: arrow → in output'", ALLOW, "arrow is not an emoji"),
    ("git commit -m 'feat: support café menus'", ALLOW, "one accented word is not Spanish"),
    ("git commit -m 'fix: Pokémon list de-dup and un-wrap'", ALLOW, "English hyphen prefixes are not Spanish words"),
    ("git commit -m 'fix: handle the de la Cruz surname'", ALLOW, "Spanish-looking words, no accent"),
    ("git commit -m 'fix: parse `añade` keyword' -m 'Adds support for the parser'", ALLOW, "Spanish only inside a code span"),
    ("git log --grep 'Co-Authored-By:'", ALLOW, "not a commit"),
    ("echo 'git commit -m \"Co-Authored-By: x\"' > notes.txt", ALLOW, "writes the words, commits nothing"),
    ("cat > notes.md <<'EOF'\ngit commit -s -m 'x'\nEOF", ALLOW, "heredoc that only writes a file"),
    ("git commit -S -m 'feat: signed with gpg'", ALLOW, "-S (GPG) is not -s"),
    ("git commit -m 'feat: x' --no-verify", ALLOW, "unrelated flag"),
]

# PowerShell command text (the hook receives it when the tool is PowerShell).
PS_CASES = [
    ('git commit -m "feat: x`n`nCo-Authored-By: a <a@b>"', DENY, "backtick-n newlines"),
    ("git commit -m @'\nfeat: don't break\n\nCo-Authored-By: a <a@b>\n'@", DENY, "single-quoted here-string with an apostrophe"),
    ('git commit -m @"\nfix: the "foo" case\n\nSigned-off-by: a <a@b>\n"@', DENY, "double-quoted here-string with quotes"),
    ('git commit -m "feat: add x"', ALLOW, "plain PowerShell commit"),
    ("git com`mit -s -m 'feat: x'", DENY, "a backtick escape splits the subcommand past the prefilter"),
]

# (command, expected, state, why) — state keys: branch, staged, modified, local
STATE_CASES = [
    ("git commit --amend --no-edit", ASK, {}, "--amend"),
    ("git -C . commit --amend -m 'feat: x'", ASK, {}, "--amend through git -C (the prefix ask rule missed it)"),
    ("git commit -m 'feat: x'", ASK, {"branch": "main"}, "commit on main"),
    ("git commit -m 'feat: x'", ALLOW, {"branch": "main", "local": {"allowPushToMain": True}}, "main opted out"),
    ("git commit -m 'feat: x'", ASK, {"staged": ["app.py"]}, "CHANGELOG.md not in the commit"),
    ("git commit -am 'feat: x'", ALLOW, {"staged": [], "modified": ["app.py", "CHANGELOG.md"]}, "-a picks up CHANGELOG"),
    ("git add -A && git commit -m 'feat: x'", ALLOW, {"staged": [], "modified": ["app.py", "CHANGELOG.md"]},
     "git add -A earlier in the same command stages CHANGELOG"),
    ("git add app.py && git commit -m 'feat: x'", ASK, {"staged": [], "modified": ["app.py", "CHANGELOG.md"]},
     "git add of one path leaves CHANGELOG out"),
    ("git commit -m 'feat: x'", ASK, {"staged": ["hooks/x.sh", "CHANGELOG.md"], "modified": ["hooks/x.sh", "CHANGELOG.md"]},
     ".sh committed without its .ps1 twin"),
    ("git commit -m 'feat: x'", ALLOW,
     {"staged": ["hooks/x.sh", "hooks/x.ps1", "CHANGELOG.md"], "modified": ["hooks/x.sh", "hooks/x.ps1", "CHANGELOG.md"]},
     "both twins committed"),
    ("git commit -s -m 'feat: x'", ALLOW, {"local": {"allowCommitTrailers": True}}, "trailers opted out"),
    ("git commit -m 'feat: x ✨'", DENY, {"local": {"allowCommitTrailers": True}}, "the trailer opt-out does not allow emoji"),
    ("git commit --amend -m 'x' -m 'Co-Authored-By: a'", DENY, {}, "deny wins over ask"),
    # Each of these was a mutation the matrix let through (2026-10-03 audit).
    ("git commit -m 'feat: x'", ASK, {"branch": "master"}, "commit on master, not only main"),
    ("git commit -m 'feat: x'", ASK, {"staged": ["hooks/x.ps1", "CHANGELOG.md"], "modified": ["hooks/x.ps1", "CHANGELOG.md"]},
     ".ps1 committed without its .sh twin"),
    ("git commit --all -m 'feat: x'", ALLOW, {"staged": [], "modified": ["app.py", "CHANGELOG.md"]},
     "--all picks up CHANGELOG like -a"),
    ("git commit --file=msg.txt", DENY, {}, "--file= reads the message file like -F"),
]


# Secret-shaped values are assembled at runtime so this file never trips the
# secret checks it tests.
KEY = "sk-live-" + "9f3b" * 6
GHP = "ghp_" + "a1B2" * 9
BECH32 = "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L"
AGE_KEY = "AGE-SECRET-KEY-" + "1" + BECH32 + BECH32[:26]
AGE_VALUES = ("schema = 1\n[[value]]\nname = \"DATABASE_URL\"\nciphertext = '''\n"
              "-----BEGIN AGE ENCRYPTED FILE-----\n"
              "YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSBEd1N0V0pXa3J0Zk5UNTJu\n"
              "-----END AGE ENCRYPTED FILE-----\n'''\n")
AEGIS_SOURCE = ("crates/engine/src/secrets/mod.rs", "crates/engine/src/catalogue/secrets.rs",
                "crates/engine/tests/secrets.rs", "crates/gui/src/screens/secrets/mod.rs",
                "docs/design/screens/secrets/README.md", "specs/phases/07-secrets.md")
AEGIS_STORE = (".aegis/secrets.toml", ".aegis/recipients.toml", ".aegis/secrets/development.toml",
               ".aegis/secrets/staging.toml", ".aegis/secrets/production.toml")

# (command, state, expected, text the ask must hold, why) — the ask must never echo a value.
SECRET_CASES = [
    ("git commit -m 'feat: x'", {"staged": [".env", "CHANGELOG.md"], "files": {".env": "DEBUG=1\n"}},
     ASK, ".env looks like it holds secrets", "a staged .env"),
    ("git add .env CHANGELOG.md && git commit -m 'feat: x'",
     {"staged": [], "modified": ["CHANGELOG.md"], "files": {".env": "DEBUG=1\n"}},
     ASK, ".env looks like it holds secrets", "a .env added in the same command"),
    ("git commit -m 'feat: x'", {"staged": [".env.example", "CHANGELOG.md"],
                                 "files": {".env.example": "API_KEY=changeme\n"}},
     ALLOW, None, "a placeholder file with a placeholder value"),
    ("git commit -m 'feat: x'", {"staged": ["deploy/server.key", "CHANGELOG.md"],
                                 "files": {"deploy/server.key": "x\n"}},
     ASK, "deploy/server.key looks like it holds secrets", "a key file by name"),
    ("git commit -m 'feat: x'", {"staged": ["config/secrets/prod.yaml", "CHANGELOG.md"],
                                 "files": {"config/secrets/prod.yaml": "db: x\n"}},
     ASK, "config/secrets/prod.yaml looks like it holds secrets", "a file in a secrets/ folder"),
    ("git commit -m 'feat: x'", {"staged": ["app.py", "CHANGELOG.md"],
                                 "files": {"app.py": f"x = 1\napi_key = '{KEY}'\n"}},
     ASK, "app.py line 2 adds a literal value assigned to 'api_key'", "a staged literal key"),
    ("git add app.py CHANGELOG.md && git commit -m 'feat: x'",
     {"staged": [], "modified": ["CHANGELOG.md"], "files": {"app.py": f"x = 1\nTOKEN={KEY}\n"}},
     ASK, "app.py line 2 adds", "a key written outside Edit, added in the same command"),
    ("git commit -am 'feat: x'", {"staged": [], "modified": ["CHANGELOG.md"],
                                  "files": {"app.py": f"x = 1\nsecret = '{KEY}'\n"}},
     ASK, "app.py line 2 adds", "-a includes a tracked file's unstaged key"),
    ("git commit -m 'feat: x'", {"staged": ["app.py", "CHANGELOG.md"],
                                 "files": {"app.py": "x = 1\nAPI_KEY=changeme\n"}},
     ALLOW, None, "a placeholder value is not a secret"),
    ("git commit -m 'feat: x'", {"staged": ["app.py", "CHANGELOG.md"],
                                 "files": {"app.py": "x = 1\ntoken = os.environ['TOKEN']\n"}},
     ALLOW, None, "an env-var read is not a secret"),
    ("git add -A && git commit -m 'feat: x'", {"staged": [], "modified": ["CHANGELOG.md"],
                                                "files": {"lib/new.py": f"a = 1\nb = 2\nc = '{GHP}'\n"}},
     ASK, "lib/new.py line 3 adds a GitHub token", "an untracked new file read whole"),
    ("git commit -m 'feat: x'", {"staged": ["app.py", "CHANGELOG.md"],
                                 "files": {"app.py": f"x = 1\nchange\npassword = '{KEY}'\n"}},
     ASK, "app.py line 3 adds", "the line number counts the file, not the hunk"),
    # Source and prose about secrets, and aegis's encrypted store, are committed by design (2026-10-08).
    ("git commit -m 'feat: x'", {"staged": [*AEGIS_SOURCE, "CHANGELOG.md"],
                                 "files": {p: "pub fn x() {}\n" for p in AEGIS_SOURCE}},
     ALLOW, None, "source and docs under a secrets/ folder or named secrets"),
    ("git commit -m 'feat: x'", {"staged": [*AEGIS_STORE, "CHANGELOG.md"],
                                 "files": {p: AGE_VALUES for p in AEGIS_STORE}},
     ALLOW, None, "aegis's store: names and age ciphertext"),
    ("git commit -m 'feat: x'", {"staged": [".aegis/secrets/production.toml", "CHANGELOG.md"],
                                 "files": {".aegis/secrets/production.toml": f"{AGE_VALUES}id = '{AGE_KEY}'\n"}},
     ASK, ".aegis/secrets/production.toml line 9 adds an age secret key", "an age identity in the store"),
    ("git commit -m 'feat: x'", {"staged": ["crates/engine/src/secrets/values.rs", "CHANGELOG.md"],
                                 "files": {"crates/engine/src/secrets/values.rs": f'const API_KEY: &str = "{KEY}";\n'}},
     ASK, "values.rs line 1 adds a literal value assigned to 'API_KEY'", "a typed Rust constant"),
    ("git commit -m 'feat: x'", {"staged": ["secrets/db_password.txt", "CHANGELOG.md"],
                                 "files": {"secrets/db_password.txt": "x\n"}},
     ASK, "secrets/db_password.txt looks like it holds secrets", "a value file in secrets/"),
]


def make_repo():
    repo = pyhook.git_repo(prefix="guard-commit-", files={
        "app.py": "x = 1\n", "CHANGELOG.md": "# Changelog\n", "hooks/x.sh": "echo\n", "hooks/x.ps1": "echo\n",
        "msg.txt": "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"})
    git(repo, "checkout", "-q", "-b", "feature/x")
    return repo


def set_state(repo, branch="feature/x", staged=("app.py", "CHANGELOG.md"),
              modified=None, local=None, files=None):
    """Reset `repo`, append a line to each modified path, write `files` {path: full text}, stage `staged`."""
    git(repo, "checkout", "-q", "-f", branch)
    git(repo, "reset", "-q", "--hard")
    git(repo, "clean", "-q", "-f", "-d", "-e", ".claude")
    for rel in (modified if modified is not None else staged):
        if rel in (files or {}):
            continue
        with open(os.path.join(repo, rel), "a") as fh:
            fh.write("change\n")
    for rel, text in (files or {}).items():
        os.makedirs(os.path.dirname(os.path.join(repo, rel)) or repo, exist_ok=True)
        with open(os.path.join(repo, rel), "w") as fh:
            fh.write(text)
    if staged:
        git(repo, "add", *staged)
    pyhook.local_settings(repo, local)


def decide(repo, command, pwsh, tool="Bash", cwd=None, with_reason=False):
    payload = pyhook.payload(tool, {"command": command}, cwd=cwd or repo)
    code, out, err = pyhook.run("guard-commit", payload, cwd=cwd or repo, pwsh=pwsh)
    got = pyhook.verdict(code, out, err)
    return (got, pyhook.reason(out)) if with_reason else got


def main():
    args = pyhook.cli()
    repo = make_repo()
    git(repo, "branch", "-q", "main-copy")
    git(repo, "branch", "-q", "master", "main")
    failures = total = 0
    try:
        for label, pwsh in pyhook.runners(args.pwsh):
            print(f"\n=== {label}")
            set_state(repo)
            for command, want, why in MESSAGE_CASES:
                got = decide(repo, command, pwsh)
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL want {want} got {got} | {command!r}  ({why})")
            for command, want, why in PS_CASES:
                got = decide(repo, command, pwsh, tool="PowerShell")
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL [PowerShell tool] want {want} got {got} | {command!r}  ({why})")
            for command, want, state, why in STATE_CASES:
                set_state(repo, **state)
                got = decide(repo, command, pwsh)
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL want {want} got {got} | {command!r}  ({why})")
            for command, state, want, must, why in SECRET_CASES:
                set_state(repo, **state)
                got, reason = decide(repo, command, pwsh, with_reason=True)
                total += 1
                problems = [] if got == want else [f"want {want} got {got}"]
                if must and must not in reason:
                    problems.append(f"the ask lacks {must!r}")
                if KEY in reason or GHP in reason or AGE_KEY in reason:
                    problems.append("the ask echoes the secret value")
                if problems:
                    failures += 1
                    print(f"  FAIL {'; '.join(problems)} | {command!r}  ({why}) {reason[:240]!r}")
            # Outside a git repo: never crash, still judge the message.
            outside = tempfile.mkdtemp(prefix="guard-commit-nogit-")
            for command, want in (("git commit -m 'feat: x'", ALLOW),
                                  ("git commit -m 'x ✨'", DENY)):
                got = decide(outside, command, pwsh)
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL outside a repo: want {want} got {got} | {command!r}")
            shutil.rmtree(outside, ignore_errors=True)
            # From a subdirectory, `git add <relative path>` must still count.
            set_state(repo, staged=[], modified=["hooks/x.sh", "hooks/x.ps1", "CHANGELOG.md"])
            got = decide(repo, "git add x.sh x.ps1 ../CHANGELOG.md && git commit -m 'feat: x'", pwsh,
                         cwd=os.path.join(repo, "hooks"))
            total += 1
            if got != ALLOW:
                failures += 1
                print(f"  FAIL subdirectory add: want allow got {got}")
            got = decide(repo, "git add x.sh && git commit -m 'feat: x'", pwsh, cwd=os.path.join(repo, "hooks"))
            total += 1
            if got != ASK:
                failures += 1
                print(f"  FAIL subdirectory add of one twin: want ask got {got}")
            # Committing a DIFFERENT repo than the session's: the branch and the
            # opt-outs belong to the repo committed to. The hook once read the
            # opt-out from the session project and ignored `cd` before commit.
            session = make_repo()
            try:
                set_state(session, local={"allowPushToMain": True, "allowCommitTrailers": True})
                set_state(repo, branch="main")
                repo_sh = repo.replace("\\", "/")    # as typed into Git Bash on Windows
                for command, want, why in (
                        (f"cd {repo_sh} && git commit -m 'feat: x'", ASK, "cd into a repo on main"),
                        (f"git -C {repo_sh} commit -m 'feat: x'", ASK,
                         "the session's opt-out does not cover another repo"),
                        (f"git -C {repo_sh} commit -m 'feat: x' -m 'Co-Authored-By: a'", DENY,
                         "nor does its trailer opt-out")):
                    got = decide(session, command, pwsh)
                    total += 1
                    if got != want:
                        failures += 1
                        print(f"  FAIL want {want} got {got} | {command!r}  ({why})")
                for command, want, why in (
                        (f"Set-Location {repo}; git commit -m 'feat: x'", ASK, "Set-Location into a repo on main"),
                        (f"sl {repo}; git commit -s -m 'feat: x'", DENY, "sl: the session's trailer opt-out does not apply"),
                        (f"Set-Location -Path {repo}; git commit -m 'feat: x'", ASK, "-Path names the directory"),
                        (f"Push-Location {repo}; git commit -m 'feat: x'", ASK, "Push-Location")):
                    got = decide(session, command, pwsh, tool="PowerShell")
                    total += 1
                    if got != want:
                        failures += 1
                        print(f"  FAIL [PowerShell tool] want {want} got {got} | {command!r}  ({why})")
                set_state(repo, branch="main", local={"allowPushToMain": True})
                got = decide(session, f"git -C {repo_sh} commit -m 'feat: x'", pwsh)
                total += 1
                if got != ALLOW:
                    failures += 1
                    print(f"  FAIL the target repo's own opt-out must apply: got {got}")
            finally:
                shutil.rmtree(session, ignore_errors=True)
            # Malformed payloads never crash.
            for bad in ({"tool_input": "git commit -s"}, {"tool_input": None}, {}):
                code, out, err = pyhook.run("guard-commit", bad, cwd=repo, pwsh=pwsh)
                total += 1
                if pyhook.verdict(code, out, err) != ALLOW or out is not None:
                    failures += 1
                    print(f"  FAIL malformed payload {bad}: exit {code}, out {out}, err {err.strip()[-120:]!r}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    return pyhook.finish("guard-commit", failures, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
