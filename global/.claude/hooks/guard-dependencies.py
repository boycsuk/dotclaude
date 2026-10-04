# hook-kind: guard
"""PreToolUse hook on Bash and Edit|Write|NotebookEdit: ask before any new dependency.

Every dependency is attack surface (rules/security.md), and the old safety
net — prefix `ask` rules such as `Bash(npm install:*)` — missed `npm i`,
`pnpm add`, `pip3 install`, `python -m pip install`, `uv add` and anything
behind a wrapper. This hook asks the user whenever:
  - a package-manager command would add or install a NAMED package
    (bare lockfile installs such as `npm ci`, `npm install`, `uv sync`,
    `pip install -r requirements.txt` pass: they add nothing new);
  - an Edit/Write adds a dependency entry to a manifest (package.json,
    pyproject.toml, requirements*.txt, Cargo.toml, go.mod, Gemfile,
    composer.json, *.csproj);
  - a runner fetches a package to execute or install it outside any
    manifest: npx / bunx / pnpm dlx / yarn dlx / npm exec (unless the tool
    is in node_modules/.bin or --no-install is given), uvx / uv tool,
    pipx run|install, cargo install, go install of a remote module;
  - a NotebookEdit writes a cell whose `!pip install x` / `%pip install x`
    line would add a package, judged exactly as that command in Bash.
The reason names the packages, flags unpinned version specs, and gives the
ecosystem's audit command. It never denies: adding a dependency is often
right; it is the user's call.
"""

import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402
import shellwords  # noqa: E402

AUDIT = {"npm": "npm audit", "python": "pip-audit", "cargo": "cargo audit",
         "go": "govulncheck ./...", "ruby": "bundle audit", "php": "composer audit",
         "dotnet": "dotnet list package --vulnerable"}
# Per tool: the subcommands that add packages, and the options that consume
# the next token as their value. One shared list swallowed package names: `-s`
# is --save-silent for npm but --source for gem, `-w` is a flag for pnpm.
TOOLS = {
    "npm":      ("npm", {"i", "install", "add", "isntall"},
                 {"--prefix", "--registry", "-w", "--workspace", "--tag", "--cache", "--userconfig", "--loglevel"}),
    "pnpm":     ("npm", {"i", "install", "add"},
                 {"--filter", "-F", "--dir", "-C", "--registry", "--reporter", "--config", "--workspace"}),
    "yarn":     ("npm", {"add"}, {"--cwd", "--registry", "--network-timeout"}),
    "bun":      ("npm", {"i", "install", "add"}, {"--cwd", "--registry", "--backend", "--cache-dir"}),
    "pip":      ("python", {"install"},
                 {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url",
                  "-t", "--target", "--prefix", "--root", "--python-version", "--platform", "-f",
                  "--find-links", "--log", "--cache-dir", "--src", "--upgrade-strategy", "--implementation"}),
    "uv":       ("python", {"add"},
                 {"--group", "--optional", "--package", "--python", "-p", "--index", "--extra", "--rev",
                  "--tag", "--branch", "--directory", "--project"}),
    "poetry":   ("python", {"add"}, {"--group", "-G", "--python", "--platform", "--source", "--extras", "-E",
                                     "--directory", "-C"}),
    "pdm":      ("python", {"add"}, {"--group", "-G", "-p", "--project"}),
    "cargo":    ("cargo", {"add"}, {"--features", "-F", "--rename", "--package", "-p", "--path", "--git",
                                    "--branch", "--tag", "--rev", "--registry", "--manifest-path"}),
    "go":       ("go", {"get"}, {"-C"}),
    "gem":      ("ruby", {"install"}, {"-v", "--version", "-s", "--source", "-i", "--install-dir", "-n", "--bindir"}),
    "bundle":   ("ruby", {"add"}, {"-v", "--version", "-g", "--group", "-s", "--source", "-r", "--require",
                                   "--git", "--branch", "--path"}),
    "composer": ("php", {"require"}, {"-d", "--working-dir"}),
}
LOCAL_SPEC = re.compile(r"^(\.|/|~|file:|link:|workspace:)|\.(tgz|tar\.gz|whl|gem)$")
NOTEBOOK_SHELL = re.compile(r"^\s*[!%]+\s*(\S.*)$")   # Jupyter's `!cmd` shell escape and `%pip` magic


def split_options(args, valued):
    """Return (positionals, raw option tokens) of `args`, skipping option values."""
    out, opts, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and a != "-":
            opts.append(a)
            i += 2 if a.split("=", 1)[0] in valued and "=" not in a else 1
            continue
        out.append(a)
        i += 1
    return out, opts


def _editable_packages(args):
    """`pip install -e git+https://...` installs a package; `-e .` installs the project itself."""
    pkgs = []
    for i, a in enumerate(args):
        if a in ("-e", "--editable") and i + 1 < len(args) and "://" in args[i + 1]:
            pkgs.append(args[i + 1])
        elif a.startswith("--editable=") and "://" in a:
            pkgs.append(a.split("=", 1)[1])
    return pkgs


# Commands that fetch a package and run or install it without touching a
# manifest: (ecosystem, the subcommand path that selects that mode). Outside
# a terminal npx assumes --yes, so `npx some-tool` downloads and executes
# registry code with no prompt at all.
RUNNERS = {
    "npx": ("npm", []), "bunx": ("npm", []), "pnpx": ("npm", []),
    "pnpm": ("npm", ["dlx"]), "yarn": ("npm", ["dlx"]), "npm": ("npm", ["exec"]),
    "uvx": ("python", []), "pipx": ("python", None),
    "uv": ("python", ["tool"]), "cargo": ("cargo", ["install"]), "go": ("go", ["install"]),
}
RUNNER_VALUED = {"-p", "--package", "--from", "--with", "--python", "-c", "--call", "--registry",
                 "--cache", "--index", "--git", "--branch", "--tag", "--rev", "--version", "--root"}
LOCAL_BIN_DIR = os.path.join("node_modules", ".bin")
CWD = [os.getcwd()]


def runner_additions(prog, args):
    """(ecosystem, [packages]) for a command that fetches and runs or installs a package."""
    if prog not in RUNNERS:
        return None
    ecosystem, path = RUNNERS[prog]
    if prog == "pipx":
        path = [args[0]] if args[:1] and args[0] in ("run", "install") else None
    if path is None or args[:len(path)] != path:
        return None
    rest = args[len(path):]
    if prog == "uv":
        if not rest or rest[0] not in ("run", "install"):
            return None
        rest = rest[1:]
    if any(a in ("--no-install", "--offline") for a in rest):
        return None
    pkgs, _ = split_options(rest, RUNNER_VALUED)
    named = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-p", "--package", "--from")]
    named += [a.split("=", 1)[1] for a in rest if a.startswith(("--package=", "--from="))]
    target = named or pkgs[:1]
    if not target or LOCAL_SPEC.search(target[0]) or (prog == "go" and not re.search(r"[./]", target[0])):
        return None
    if ecosystem == "npm" and not named and os.path.exists(os.path.join(CWD[0], LOCAL_BIN_DIR, target[0])):
        return None                               # a locally installed tool runs without a download
    return ecosystem, target


def bash_additions(seg):
    """Return (ecosystem, [packages]) when the segment adds named packages."""
    seg = shellwords.unwrap(seg)
    if not seg:
        return None
    prog, args = shellwords.basename(seg[0]), seg[1:]
    if prog == "py":
        while args and re.fullmatch(r"-[23](\.\d+)?(-\d+)?", args[0]):
            args = args[1:]
    if re.fullmatch(r"python[0-9.]*|py", prog) and args[:2] == ["-m", "pip"]:
        prog, args = "pip", args[2:]
    if prog == "uv" and args[:1] == ["pip"]:
        prog, args = "pip", args[1:]
    if re.fullmatch(r"pip[0-9.]*", prog):
        prog = "pip"
    if prog == "yarn" and args[:1] == ["global"]:
        args = args[1:]
    if prog == "dotnet":
        if args[:1] == ["add"] and "package" in args:
            pkgs, _ = split_options(args[args.index("package") + 1:], {"-v", "--version", "-s", "--source", "-f", "--framework"})
            return ("dotnet", pkgs[:1]) if pkgs else None
        return None
    runner = runner_additions(prog, args)
    if runner:
        return runner
    if prog not in TOOLS:
        return None
    ecosystem, subcommands, valued = TOOLS[prog]
    # Global options may come before the subcommand: `npm --prefix web install x`.
    positional, _ = split_options(args, valued)
    if not positional or positional[0] not in subcommands:
        return None
    after = args[args.index(positional[0]) + 1:]
    pkgs, _ = split_options(after, valued | ({"-e", "--editable"} if prog == "pip" else set()))
    pkgs = [p for p in pkgs if not LOCAL_SPEC.search(p)]
    if prog == "pip":
        pkgs += _editable_packages(after)
    return (ecosystem, pkgs) if pkgs else None


# --- Manifest diffing ----------------------------------------------------------

def _json_deps(text, keys):
    data = json.loads(text) if text.strip() else {}
    out = {}
    for key in keys:
        section = data.get(key) if isinstance(data, dict) else None
        if isinstance(section, dict):
            out.update({k: str(v) for k, v in section.items()})
    return out


def _toml(text):
    if not text.strip():
        return {}
    try:
        import tomllib
    except ImportError:          # Python < 3.11 (e.g. macOS system Python 3.9)
        return _toml_lite(text)
    return tomllib.loads(text)


def _toml_lite(text):
    """Tables, string keys, string values and string arrays — enough for dependency tables.

    Without it, the pre-3.11 fallback compared raw lines and asked "new
    dependency?" for any edit, including a version bump.
    """
    data, pending_key, pending = {}, None, ""
    data_root = table = data
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not pending_key else raw.strip()
        if pending_key:
            pending += " " + line
            if pending.count("[") <= pending.count("]"):
                table[pending_key] = re.findall(r"""["']([^"']*)["']""", pending)
                pending_key, pending = None, ""
            continue
        if not line:
            continue
        header = re.fullmatch(r"\[\s*([^\[\]]+?)\s*\]", line)
        if header:
            table = data_root
            for part in [p.strip().strip("\"'") for p in header.group(1).split(".")]:
                table = table.setdefault(part, {})
            continue
        if line.startswith("[["):
            table = {}
            continue
        key, eq, value = line.partition("=")
        if not eq:
            continue
        key, value = key.strip().strip("\"'"), value.strip()
        if value.startswith("[") and value.count("[") > value.count("]"):
            pending_key, pending = key, value
        elif value.startswith("["):
            table[key] = re.findall(r"""["']([^"']*)["']""", value)
        else:
            table[key] = value.strip("\"'")
    return data


def _req_name(spec):
    return re.split(r"[\s<>=!~;\[@]", spec.strip(), maxsplit=1)[0].lower()


def _pyproject_deps(text):
    data = _toml(text)
    out = {}
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in list(project.get("optional-dependencies", {}).values()) + list(
            data.get("dependency-groups", {}).values()):
        specs += [s for s in group if isinstance(s, str)]
    out.update({_req_name(s): s for s in specs})
    poetry = data.get("tool", {}).get("poetry", {})
    for section in [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {})] + [
            g.get("dependencies", {}) for g in poetry.get("group", {}).values()]:
        out.update({k.lower(): str(v) for k, v in section.items() if k.lower() != "python"})
    return out


def _cargo_deps(text):
    data = _toml(text)
    out = {}
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        out.update({k: str(v) for k, v in data.get(key, {}).items()})
    return out


def _requirements_deps(text):
    out = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            out[_req_name(line)] = line
    return out


def _gomod_deps(text):
    return {m.group(1): m.group(2) for m in
            re.finditer(r"^\s*(?:require\s+)?([a-zA-Z0-9.\-_]+\.[a-z]+/\S+)\s+(v\S+)", text, re.M)}


def _gemfile_deps(text):
    return {m.group(1): m.group(0) for m in re.finditer(r"""^\s*gem\s+["']([^"']+)["'].*$""", text, re.M)}


def _csproj_deps(text):
    return {m.group(1): m.group(0) for m in
            re.finditer(r"""<PackageReference\s+Include=["']([^"']+)["'][^>]*>""", text)}


MANIFESTS = [
    (re.compile(r"(^|/)package\.json$"), "npm",
     lambda t: _json_deps(t, ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"))),
    (re.compile(r"(^|/)composer\.json$"), "php", lambda t: _json_deps(t, ("require", "require-dev"))),
    (re.compile(r"(^|/)pyproject\.toml$"), "python", _pyproject_deps),
    (re.compile(r"(^|/)requirements[^/]*\.txt$"), "python", _requirements_deps),
    (re.compile(r"(^|/)Cargo\.toml$"), "cargo", _cargo_deps),
    (re.compile(r"(^|/)go\.mod$"), "go", _gomod_deps),
    (re.compile(r"(^|/)Gemfile$"), "ruby", _gemfile_deps),
    (re.compile(r"\.csproj$"), "dotnet", _csproj_deps),
]


def edit_additions(tool, tool_input):
    path = str(tool_input.get("file_path", "")).replace("\\", "/")
    match = next((m for m in MANIFESTS if m[0].search(path)), None)
    if not match:
        return None
    _, ecosystem, extract = match
    try:
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
    except OSError:
        before = ""
    if tool == "Write":
        after = str(tool_input.get("content", ""))
    else:
        old, new = str(tool_input.get("old_string", "")), str(tool_input.get("new_string", ""))
        if old and old not in before:
            return None                  # the Edit will fail on its own
        after = before.replace(old, new) if tool_input.get("replace_all") else before.replace(old, new, 1)
    try:
        old_deps, new_deps = extract(before), extract(after)
    except (ValueError, TypeError, AttributeError):
        return None                      # mid-edit syntax: nothing reliable to compare
    added = [f"{name} {new_deps[name]}".strip() if new_deps[name] != name else name
             for name in new_deps if name not in old_deps]
    return (ecosystem, added) if added else None


def notebook_additions(tool_input):
    """(ecosystem, [packages]) from a cell's `!pip install x` / `%pip install x` lines, judged as Bash."""
    source = tool_input.get("new_source")
    if tool_input.get("cell_type") == "markdown" or not isinstance(source, str):
        return []
    found = []
    for line in source.splitlines():
        m = NOTEBOOK_SHELL.match(line)
        if m:
            found += [f for f in map(bash_additions, shellwords.segments(m.group(1)) or []) if f]
    return found


def pinned(ecosystem, spec):
    """True when `spec` (a command token or a manifest entry) names one exact version."""
    if ecosystem == "go":
        return "@v" in spec or bool(re.search(r"\sv\d", spec))
    if ecosystem == "python":
        return "==" in spec
    if ecosystem == "dotnet":
        return "Version=" in spec or "--version" in spec
    if ecosystem == "npm":
        version = spec.rsplit("@", 1)[1] if "@" in spec.lstrip("@") else spec.partition(" ")[2]
        return bool(re.fullmatch(r"v?\d+\.\d+\.\d+\S*", version.strip()))
    if ecosystem == "cargo":
        return "@=" in spec or bool(re.search(r"[\s\"']=\s*\d", spec))
    return bool(re.search(r"[\s\"'@:]=?\s*\d+\.\d+\.\d+", spec))


def reason(ecosystem, packages, where):
    unpinned = [p for p in packages if not pinned(ecosystem, p)]
    text = f"New dependency {where}: {', '.join(packages)}. Every dependency is attack surface — confirm it is needed."
    if unpinned:
        text += f" Not pinned to an exact version: {', '.join(unpinned)}."
    text += f" After adding, run `{AUDIT[ecosystem]}`."
    return text


def main():
    payload = hookio.read_payload()
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command")
        if not isinstance(command, str):
            return 0
        if isinstance(payload.get("cwd"), str):
            CWD[0] = payload["cwd"]
        segments = shellwords.segments(command, shellwords.shell_of(payload)) or []
        found = [bash_additions(seg) for seg in segments]
        found = [f for f in found if f]
        if found:
            ecosystem = found[0][0]
            packages = [p for _, pkgs in found for p in pkgs]
            hookio.ask(reason(ecosystem, packages, "command"))
    elif tool in ("Edit", "Write"):
        found = edit_additions(tool, tool_input)
        if found:
            hookio.ask(reason(found[0], found[1], f"in {os.path.basename(str(tool_input.get('file_path')))}"))
    elif tool == "NotebookEdit":
        found = notebook_additions(tool_input)
        if found:
            where = f"in a cell of {os.path.basename(str(tool_input.get('notebook_path')))}"
            hookio.ask(reason(found[0][0], [p for _, pkgs in found for p in pkgs], where))
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
