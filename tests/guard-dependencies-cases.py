#!/usr/bin/env python3
"""Behavioural contract for guard-dependencies.py.

Run:  python3 tests/guard-dependencies-cases.py
      python3 tests/guard-dependencies-cases.py --pwsh PATH   # PowerShell command form too

The hook replaces prefix `ask` rules (`Bash(npm install:*)`, ...) that every
wrapper and synonym walked past: `npm i`, `pnpm add`, `pip3 install`,
`python -m pip install`, `uv add`, `env X=1 npm install`. It must ask on all
of those, stay silent on lockfile installs and lookalikes, and catch a
dependency added by editing a manifest — the path no Bash rule can see.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

ASK, ALLOW = "ask", "allow"

BASH_CASES = [
    # Adds a named package — ask, in every spelling.
    ("npm install lodash", ASK, "npm install <pkg>"),
    ("ls # list\nnpm install left-pad", ASK, "a comment on an earlier line must not hide the install"),
    ('echo "$(npm install left-pad)"', ASK, "a substitution inside double quotes runs"),
    ("cat > f <<EOF\n$(npm install left-pad)\nEOF", ASK, "an unquoted heredoc runs its $( )"),
    ("ssh host <<EOF\nnpm install left-pad\nEOF", ASK, "a heredoc fed to anything but a file writer runs"),
    ("cat > notes.md <<'EOF'\n$(npm install left-pad)\nEOF", ALLOW, "a quoted delimiter leaves $( ) inert"),
    ("npm i lodash", ASK, "npm i shorthand (missed by Bash(npm install:*))"),
    ("npm add -D vitest", ASK, "npm add with a flag"),
    ("pnpm add zod", ASK, "pnpm add"),
    ("pnpm i zod", ASK, "pnpm i <pkg>"),
    ("yarn add react", ASK, "yarn add"),
    ("bun add hono", ASK, "bun add"),
    ("pip install requests", ASK, "pip install"),
    ("pip3 install requests==2.32.3", ASK, "pip3 (missed by Bash(pip install:*))"),
    ("python -m pip install httpx", ASK, "python -m pip"),
    ("python3 -m pip install --upgrade httpx", ASK, "python3 -m pip with a flag"),
    ("uv add fastapi", ASK, "uv add"),
    ("uv pip install fastapi", ASK, "uv pip install"),
    ("poetry add django", ASK, "poetry add"),
    ("cargo add serde --features derive", ASK, "cargo add with a valued flag"),
    ("go get github.com/pkg/errors@v0.9.1", ASK, "go get"),
    ("gem install rails", ASK, "gem install"),
    ("bundle add pry", ASK, "bundle add"),
    ("composer require guzzlehttp/guzzle", ASK, "composer require"),
    ("dotnet add package Newtonsoft.Json", ASK, "dotnet add package"),
    ("env CI=1 npm install left-pad", ASK, "env wrapper"),
    ("cd web && npm install axios", ASK, "after cd in a compound command"),
    ("git pull\nnpm i lodash", ASK, "second line of a multi-line command"),
    ("/usr/bin/pip3 install requests", ASK, "absolute path to pip"),
    # Forms a review found walking past the first version (all verified bypasses).
    ("npm i -s lodash", ASK, "-s is a flag for npm, not a valued option"),
    ("pnpm add -w lodash", ASK, "-w is a flag for pnpm"),
    ("pnpm -w add lodash", ASK, "global flag before the subcommand"),
    ("npm --prefix web install lodash", ASK, "valued global option before the subcommand"),
    ("pip3 install -v requests", ASK, "-v is verbose for pip"),
    ("pip install -e git+https://github.com/x/y.git#egg=y", ASK, "editable VCS package"),
    ("py -3 -m pip install requests", ASK, "Windows py launcher"),
    ("yarn global add lodash", ASK, "yarn global add"),
    ("timeout 600 npm install lodash", ASK, "timeout wrapper"),
    ("bash -c 'npm i lodash'", ASK, "bash -c string"),
    # Installs nothing new, or is not an install at all — allow.
    ("npm install ../shared-lib", ALLOW, "local path package"),
    ("go get -u ./...", ALLOW, "updates the module's own packages"),
    ("npm ci", ALLOW, "lockfile install"),
    ("npm install", ALLOW, "bare install from package.json"),
    ("pnpm install --frozen-lockfile", ALLOW, "pnpm lockfile install"),
    ("yarn install", ALLOW, "yarn lockfile install"),
    ("uv sync", ALLOW, "uv sync"),
    ("poetry install", ALLOW, "poetry install from the lockfile"),
    ("pip install -r requirements.txt", ALLOW, "declared requirements"),
    ("pip install -e .", ALLOW, "editable install of the project itself"),
    ("pip list", ALLOW, "not an install"),
    ("npm run install-hooks", ALLOW, "a script that merely has install in its name"),
    ("npm test", ALLOW, "not an install"),
    ("echo 'run npm install lodash' > notes.txt", ALLOW, "writes the words"),
    ("cat > notes.md <<'EOF'\npip install requests\nEOF", ALLOW, "heredoc that only writes a file"),
    ("go get", ALLOW, "go get with no package"),
    ("git commit -m 'npm install lodash'", ALLOW, "words inside a commit message"),
]

PACKAGE_JSON = {"name": "app", "dependencies": {"react": "18.3.1"}, "devDependencies": {}}
PYPROJECT = '[project]\nname = "app"\ndependencies = [\n  "httpx==0.27.0",\n]\n'
CARGO = '[package]\nname = "app"\n\n[dependencies]\nserde = "1"\n'


def write(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def edit_cases(tmp):
    pkg = os.path.join(tmp, "package.json")
    pyproj = os.path.join(tmp, "pyproject.toml")
    cargo = os.path.join(tmp, "Cargo.toml")
    reqs = os.path.join(tmp, "requirements-dev.txt")
    readme = os.path.join(tmp, "README.md")
    write(pkg, json.dumps(PACKAGE_JSON, indent=2))
    write(pyproj, PYPROJECT)
    write(cargo, CARGO)
    write(reqs, "pytest==8.3.3\n")
    write(readme, "# app\n")
    added = dict(PACKAGE_JSON, dependencies={"react": "18.3.1", "lodash": "^4.17.21"})
    bumped = dict(PACKAGE_JSON, dependencies={"react": "18.3.2"})
    return [
        ("Write", {"file_path": pkg, "content": json.dumps(added, indent=2)}, ASK, "package.json gains lodash"),
        ("Write", {"file_path": pkg, "content": json.dumps(bumped, indent=2)}, ALLOW, "version bump adds nothing"),
        ("Edit", {"file_path": pkg, "old_string": '"devDependencies": {}',
                  "new_string": '"devDependencies": {"vitest": "2.1.0"}'}, ASK, "Edit adds a devDependency"),
        ("Edit", {"file_path": pkg, "old_string": '"name": "app"', "new_string": '"name": "web"'},
         ALLOW, "Edit that renames the package"),
        ("Edit", {"file_path": pyproj, "old_string": '  "httpx==0.27.0",\n',
                  "new_string": '  "httpx==0.27.0",\n  "rich>=13",\n'}, ASK, "pyproject gains rich"),
        ("Edit", {"file_path": cargo, "old_string": 'serde = "1"', "new_string": 'serde = "1"\ntokio = "1"'},
         ASK, "Cargo.toml gains tokio"),
        ("Edit", {"file_path": reqs, "old_string": "pytest==8.3.3\n", "new_string": "pytest==8.3.3\nhypothesis\n"},
         ASK, "requirements-dev.txt gains hypothesis"),
        ("Edit", {"file_path": reqs, "old_string": "pytest==8.3.3", "new_string": "pytest==8.3.4"},
         ALLOW, "requirements pin bump"),
        ("Edit", {"file_path": pkg, "old_string": "not in the file", "new_string": "x"},
         ALLOW, "Edit that will fail on its own"),
        ("Write", {"file_path": readme, "content": "npm install lodash\n"}, ALLOW, "not a manifest"),
        ("Write", {"file_path": os.path.join(tmp, "new", "package.json"),
                   "content": json.dumps(PACKAGE_JSON)}, ASK, "new manifest with dependencies"),
    ]


PS_CASES = [
    ("pnpm add left-pad", ASK, "PowerShell tool name"),
    ("npm i lodash; npm test", ASK, "PowerShell statement separator"),
    ("npm ci", ALLOW, "lockfile install under PowerShell"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()
    failures = total = 0
    for label, pwsh in pyhook.runners(args.pwsh):
        tmp = tempfile.mkdtemp(prefix="guard-deps-")
        try:
            print(f"\n=== {label}")
            for command, want, why in BASH_CASES:
                payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": tmp,
                           "tool_input": {"command": command}}
                code, out, err = pyhook.run("guard-dependencies", payload, cwd=tmp, pwsh=pwsh)
                got = pyhook.decision(out) if code == 0 else f"exit {code}: {err.strip()[-150:]}"
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL want {want} got {got} | {command!r}  ({why})")
            for command, want, why in PS_CASES:
                payload = {"hook_event_name": "PreToolUse", "tool_name": "PowerShell", "cwd": tmp,
                           "tool_input": {"command": command}}
                code, out, err = pyhook.run("guard-dependencies", payload, cwd=tmp, pwsh=pwsh)
                got = pyhook.decision(out) if code == 0 else f"exit {code}: {err.strip()[-150:]}"
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL [PowerShell tool] want {want} got {got} | {command!r}  ({why})")
            cases = edit_cases(tmp)
            for tool, tool_input, want, why in cases:
                payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": tmp,
                           "tool_input": tool_input}
                code, out, err = pyhook.run("guard-dependencies", payload, cwd=tmp, pwsh=pwsh)
                got = pyhook.decision(out) if code == 0 else f"exit {code}: {err.strip()[-150:]}"
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL want {want} got {got} | {tool} {os.path.basename(tool_input['file_path'])}  ({why})")
            # Without tomllib (Python < 3.11) a version bump must not read as a new
            # dependency, and a real addition must still be caught.
            no_toml = os.path.join(tmp, "no-tomllib")
            os.makedirs(no_toml, exist_ok=True)
            write(os.path.join(no_toml, "tomllib.py"), "raise ImportError('simulated Python < 3.11')\n")
            cargo = os.path.join(tmp, "Cargo.toml")
            pyproj = os.path.join(tmp, "pyproject.toml")
            write(cargo, CARGO)
            write(pyproj, PYPROJECT)
            for tool_input, want, why in (
                ({"file_path": cargo, "old_string": 'name = "app"', "new_string": 'name = "app"\nrust-version = "1.75"'},
                 ALLOW, "package metadata, not a dependency"),
                ({"file_path": cargo, "old_string": 'serde = "1"', "new_string": 'serde = "1"\nrand = "0.8"'},
                 ASK, "new [dependencies] key"),
                ({"file_path": pyproj, "old_string": 'name = "app"', "new_string": 'name = "app"\nversion = "0.2"'},
                 ALLOW, "version bump"),
                ({"file_path": pyproj, "old_string": '  "httpx==0.27.0",\n', "new_string": '  "httpx==0.27.0",\n  "rich>=13",\n'},
                 ASK, "new entry in the dependencies array"),
            ):
                payload = {"tool_name": "Edit", "cwd": tmp, "tool_input": tool_input}
                code, out, err = pyhook.run("guard-dependencies", payload, cwd=tmp, pwsh=pwsh,
                                            env={"PYTHONPATH": no_toml})
                got = pyhook.decision(out) if code == 0 else f"exit {code}: {err.strip()[-150:]}"
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL [no tomllib] want {want} got {got} ({why})")
            for bad in ({"tool_name": "Bash", "tool_input": "npm i x"}, {"tool_name": "Edit", "tool_input": None}):
                code, out, _ = pyhook.run("guard-dependencies", bad, cwd=tmp, pwsh=pwsh)
                total += 1
                if code != 0 or out is not None:
                    failures += 1
                    print(f"  FAIL malformed payload {bad}: exit {code}, out {out}")
            # The reason must be actionable: names, pinning, the audit command.
            payload = {"tool_name": "Bash", "cwd": tmp, "tool_input": {"command": "npm i lodash"}}
            _, out, _ = pyhook.run("guard-dependencies", payload, cwd=tmp, pwsh=pwsh)
            text = (out or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            total += 1
            if not all(s in text for s in ("lodash", "Not pinned", "npm audit")):
                failures += 1
                print(f"  FAIL reason not actionable: {text!r}")
            print(f"  {len(BASH_CASES) + len(PS_CASES) + len(cases) + 7} cases checked")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{failures} of {total} case(s) FAILED")
        return 1
    print(f"All {total} cases pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
