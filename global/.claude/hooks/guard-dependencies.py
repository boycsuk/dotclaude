# hook-kind: guard
"""PreToolUse hook on Bash and Edit|Write: ask before any new dependency.

Every dependency is attack surface (rules/security.md), and the old safety
net — prefix `ask` rules such as `Bash(npm install:*)` — missed `npm i`,
`pnpm add`, `pip3 install`, `python -m pip install`, `uv add` and anything
behind a wrapper. This hook asks the user whenever:
  - a package-manager command would add or install a NAMED package
    (bare lockfile installs such as `npm ci`, `npm install`, `uv sync`,
    `pip install -r requirements.txt` pass: they add nothing new);
  - an Edit/Write adds a dependency entry to a manifest (package.json,
    pyproject.toml, requirements*.txt, Cargo.toml, go.mod, Gemfile,
    composer.json, *.csproj).
The reason names the packages, flags unpinned version specs, and gives the
ecosystem's audit command. It never denies: adding a dependency is often
right; it is the user's call (DESIGN.md §35).
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
NODE_TOOLS = {"npm": ("i", "install", "add"), "pnpm": ("i", "install", "add"),
              "yarn": ("add",), "bun": ("i", "install", "add")}
# Option flags of these commands that consume the next token as their value.
VALUED = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "--index-url",
          "-i", "--extra-index-url", "--target", "-t", "--prefix", "--python",
          "--group", "-G", "--optional", "--package", "-p", "--filter", "--workspace",
          "-w", "--registry", "--source", "-s", "--version", "-v", "--project", "--framework",
          "-f", "--features", "--rename", "--path", "--git", "--branch", "--tag", "--rev"}


def positionals(args):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            i += 2 if a in VALUED and "=" not in a else 1
            continue
        out.append(a)
        i += 1
    return out


def bash_additions(seg):
    """Return (ecosystem, [packages]) when the segment adds named packages."""
    seg = shellwords.unwrap(seg)
    if not seg:
        return None
    prog, args = shellwords.basename(seg[0]), seg[1:]
    if re.fullmatch(r"python[0-9.]*|py", prog) and args[:2] == ["-m", "pip"]:
        prog, args = "pip", args[2:]
    if prog == "uv" and args[:1] == ["pip"]:
        prog, args = "pip", args[1:]
    if prog in NODE_TOOLS and args and args[0] in NODE_TOOLS[prog]:
        pkgs = positionals(args[1:])
        return ("npm", pkgs) if pkgs else None
    if re.fullmatch(r"pip[0-9.]*", prog) and args[:1] == ["install"]:
        rest = args[1:]
        pkgs = [p for p in positionals(rest) if p not in (".",) and not p.startswith(("./", "/"))]
        return ("python", pkgs) if pkgs else None
    simple = {("uv", "add"): "python", ("poetry", "add"): "python", ("pdm", "add"): "python",
              ("cargo", "add"): "cargo", ("go", "get"): "go", ("gem", "install"): "ruby",
              ("bundle", "add"): "ruby", ("composer", "require"): "php"}
    if args and (prog, args[0]) in simple:
        pkgs = positionals(args[1:])
        return (simple[(prog, args[0])], pkgs) if pkgs else None
    if prog == "dotnet" and args[:1] == ["add"] and "package" in args:
        pkgs = positionals(args[args.index("package") + 1:])
        return ("dotnet", pkgs[:1]) if pkgs else None
    return None


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
    try:
        import tomllib
    except ImportError:          # Python < 3.11: no stdlib TOML parser
        return None
    return tomllib.loads(text) if text.strip() else {}


def _req_name(spec):
    return re.split(r"[\s<>=!~;\[@]", spec.strip(), maxsplit=1)[0].lower()


def _pyproject_deps(text):
    data = _toml(text)
    if data is None:
        return _line_deps(text)
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
    if data is None:
        return _line_deps(text)
    out = {}
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        out.update({k: str(v) for k, v in data.get(key, {}).items()})
    return out


def _line_deps(text):
    return {line.strip(): line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith(("#", "//", "["))}


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
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return 0
        found = [bash_additions(seg) for seg in (shellwords.segments(command) or [])]
        found = [f for f in found if f]
        if found:
            ecosystem = found[0][0]
            packages = [p for _, pkgs in found for p in pkgs]
            hookio.ask(reason(ecosystem, packages, "command"))
    elif tool in ("Edit", "Write"):
        found = edit_additions(tool, tool_input)
        if found:
            hookio.ask(reason(found[0], found[1], f"in {os.path.basename(str(tool_input.get('file_path')))}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
