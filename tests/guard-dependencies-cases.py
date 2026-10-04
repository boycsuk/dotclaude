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
    # Runners fetch a package and execute it; outside a terminal npx assumes --yes.
    ("npx some-tool", ASK, "npx downloads and runs a registry package"),
    ("npx -y create-vite@5 app", ASK, "npx -y"),
    ("npx --no-install tsc --noEmit", ALLOW, "--no-install never downloads"),
    ("npx localtool", ALLOW, "a tool already in node_modules/.bin runs locally"),
    ("bunx cowsay hi", ASK, "bunx"),
    ("pnpm dlx create-vite", ASK, "pnpm dlx"),
    ("yarn dlx create-react-app x", ASK, "yarn dlx"),
    ("npm exec --package=cowsay -- cowsay hi", ASK, "npm exec --package"),
    ("uvx ruff check .", ASK, "uvx"),
    ("uv tool install ruff", ASK, "uv tool install"),
    ("uv tool run black .", ASK, "uv tool run"),
    ("pipx run black .", ASK, "pipx run"),
    ("pipx install poetry", ASK, "pipx install"),
    ("cargo install ripgrep", ASK, "cargo install"),
    ("go install golang.org/x/tools/gopls@latest", ASK, "go install of a remote module"),
    ("go install ./...", ALLOW, "go install of the local module"),
    ("cargo build --release", ALLOW, "cargo build adds nothing"),
    ("uv run pytest", ALLOW, "uv run runs the project"),
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
    ("pdm add httpx", ASK, "pdm add"),
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
    nb = os.path.join(tmp, "analysis.ipynb")
    write(pkg, json.dumps(PACKAGE_JSON, indent=2))
    write(pyproj, PYPROJECT)
    write(cargo, CARGO)
    write(reqs, "pytest==8.3.3\n")
    write(readme, "# app\n")
    gomod = os.path.join(tmp, "go.mod")
    gemfile = os.path.join(tmp, "Gemfile")
    composer = os.path.join(tmp, "composer.json")
    csproj = os.path.join(tmp, "App.csproj")
    poetry = os.path.join(tmp, "poetry", "pyproject.toml")
    write(gomod, "module app\n\ngo 1.22\n\nrequire (\n\tgithub.com/a/b v1.0.0\n)\n")
    write(gemfile, "source 'https://rubygems.org'\ngem 'rails', '7.1.0'\n")
    write(composer, json.dumps({"require": {"php": ">=8.2"}}, indent=2))
    write(csproj, '<Project>\n  <ItemGroup>\n  </ItemGroup>\n</Project>\n')
    os.makedirs(os.path.dirname(poetry))
    write(poetry, '[tool.poetry.dependencies]\npython = "^3.12"\n')
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
        # One per manifest type and section, each a mutation that used to pass.
        ("Edit", {"file_path": gomod, "old_string": "\tgithub.com/a/b v1.0.0\n",
                  "new_string": "\tgithub.com/a/b v1.0.0\n\tgithub.com/c/d v2.1.0\n"}, ASK, "go.mod gains a module"),
        ("Edit", {"file_path": gemfile, "old_string": "gem 'rails', '7.1.0'\n",
                  "new_string": "gem 'rails', '7.1.0'\ngem 'devise'\n"}, ASK, "Gemfile gains a gem"),
        ("Edit", {"file_path": composer, "old_string": '"php": ">=8.2"',
                  "new_string": '"php": ">=8.2",\n    "guzzlehttp/guzzle": "^7.0"'}, ASK, "composer.json gains a package"),
        ("Edit", {"file_path": csproj, "old_string": "  <ItemGroup>\n",
                  "new_string": '  <ItemGroup>\n    <PackageReference Include="Serilog" Version="3.1.1" />\n'},
         ASK, "a .csproj gains a PackageReference"),
        ("Edit", {"file_path": poetry, "old_string": 'python = "^3.12"\n',
                  "new_string": 'python = "^3.12"\nrequests = "^2.32"\n'}, ASK, "a poetry table gains a package"),
        ("Edit", {"file_path": pyproj, "old_string": "]\n",
                  "new_string": ']\n\n[project.optional-dependencies]\ndev = ["pytest==8.3.3"]\n'},
         ASK, "an optional-dependencies group"),
        ("Edit", {"file_path": cargo, "old_string": 'serde = "1"', "new_string": 'serde = "1"\nrand = "0.8"',
                  "replace_all": True}, ASK, "replace_all still adds the crate"),
        # A notebook cell installs with a shell or magic line; judged like the same command in Bash.
        ("NotebookEdit", {"notebook_path": nb, "new_source": "!pip install requests\nimport requests\n"},
         ASK, "a !pip install line in a cell"),
        ("NotebookEdit", {"notebook_path": nb, "new_source": "%pip install -q httpx==0.27.0"},
         ASK, "a %pip magic, pinned or not"),
        ("NotebookEdit", {"notebook_path": nb, "new_source": "!uv pip install rich"}, ASK, "!uv pip install"),
        ("NotebookEdit", {"notebook_path": nb, "new_source": "%pip install -r requirements.txt"},
         ALLOW, "installing from a manifest adds nothing, as in Bash"),
        ("NotebookEdit", {"notebook_path": nb, "new_source": "import requests\nrequests.get(url)\n"},
         ALLOW, "code that imports a package"),
        ("NotebookEdit", {"notebook_path": nb, "cell_type": "markdown",
                          "new_source": "Run `pip install requests` first.\n"},
         ALLOW, "prose that mentions pip install"),
        ("NotebookEdit", {"notebook_path": nb, "new_source": "# pip install requests\n"},
         ALLOW, "a commented-out install"),
    ]


PS_CASES = [
    ("pnpm add left-pad", ASK, "PowerShell tool name"),
    ("npm i lodash; npm test", ASK, "PowerShell statement separator"),
    ("npm ci", ALLOW, "lockfile install under PowerShell"),
]


def judge(pwsh, tmp, tool, tool_input, env=None):
    code, out, err = pyhook.run("guard-dependencies", pyhook.payload(tool, tool_input, cwd=tmp),
                                cwd=tmp, pwsh=pwsh, env=env)
    return pyhook.verdict(code, out, err), out


def main():
    args = pyhook.cli()
    failures = total = 0
    for label, pwsh in pyhook.runners(args.pwsh):
        tmp = tempfile.mkdtemp(prefix="guard-deps-")
        os.makedirs(os.path.join(tmp, "node_modules", ".bin"))
        open(os.path.join(tmp, "node_modules", ".bin", "localtool"), "w").close()
        try:
            print(f"\n=== {label}")
            for tool, cases in (("Bash", BASH_CASES), ("PowerShell", PS_CASES)):
                for command, want, why in cases:
                    got, _ = judge(pwsh, tmp, tool, {"command": command})
                    total += 1
                    if got != want:
                        failures += 1
                        print(f"  FAIL [{tool}] want {want} got {got} | {command!r}  ({why})")
            for tool, tool_input, want, why in edit_cases(tmp):
                got, _ = judge(pwsh, tmp, tool, tool_input)
                total += 1
                if got != want:
                    failures += 1
                    target = tool_input.get("file_path") or tool_input.get("notebook_path")
                    print(f"  FAIL want {want} got {got} | {tool} {os.path.basename(target)}  ({why})")
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
                got, _ = judge(pwsh, tmp, "Edit", tool_input, env={"PYTHONPATH": no_toml})
                total += 1
                if got != want:
                    failures += 1
                    print(f"  FAIL [no tomllib] want {want} got {got} ({why})")
            for bad in ({"tool_name": "Bash", "tool_input": "npm i x"}, {"tool_name": "Edit", "tool_input": None}):
                code, out, err = pyhook.run("guard-dependencies", bad, cwd=tmp, pwsh=pwsh)
                total += 1
                if pyhook.verdict(code, out, err) != ALLOW or out is not None:
                    failures += 1
                    print(f"  FAIL malformed payload {bad}: exit {code}, out {out}, err {err.strip()[-120:]!r}")
            # The reason must be actionable: names, pinning, the audit command.
            _, out = judge(pwsh, tmp, "Bash", {"command": "npm i lodash"})
            text = pyhook.reason(out)
            total += 1
            if not all(s in text for s in ("lodash", "Not pinned", "npm audit")):
                failures += 1
                print(f"  FAIL reason not actionable: {text!r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return pyhook.finish("guard-dependencies", failures, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
