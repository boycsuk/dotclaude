#!/usr/bin/env python3
"""Coherence validator for the dotclaude repo. Run: python3 check.py

This repo has no build and no test suite, so nothing catches the failure mode
it is most exposed to: a hand-maintained list drifting from its twin. Every
check below encodes a duplication the architecture actually requires (a .sh/.ps1
pair, a doc inventory, a shared extension list) and fails when the copies stop
agreeing. Prose in CLAUDE.md asks maintainers to keep them in lockstep; this
makes the ask verifiable.

Exit 0 = coherent, 1 = at least one divergence. Advisory by design: it reports
everything it finds rather than stopping at the first error.
"""

import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
failures = []
checks_run = 0


def fail(check, detail):
    failures.append((check, detail))


def read(path):
    with open(os.path.join(REPO, path)) as fh:
        return fh.read()


def walk_files(roots, suffix):
    """Every file under `roots` ending in `suffix`.

    Uses os.walk rather than glob because glob skips dot-directories, and the
    central artifacts all live under `global/.claude/` — a glob-based scan
    silently sees none of them and reports a clean pass.
    """
    for root in roots:
        for dirpath, _, filenames in os.walk(os.path.join(REPO, root)):
            for filename in sorted(filenames):
                if filename.endswith(suffix):
                    yield os.path.join(dirpath, filename)


def check(name):
    """Decorator: register and run a check, counting it."""
    def wrap(fn):
        global checks_run
        checks_run += 1
        try:
            fn()
        except FileNotFoundError as exc:
            fail(name, f"missing file: {exc.filename}")
        except Exception as exc:  # a broken check is itself a finding
            fail(name, f"check raised {type(exc).__name__}: {exc}")
        return fn
    return wrap


# --- 1. Every hook ships as a .sh + .ps1 pair --------------------------------
@check("hook .sh/.ps1 pairs")
def _():
    hooks = os.path.join(REPO, "global/.claude/hooks")
    sh = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(hooks, "*.sh"))}
    ps = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(hooks, "*.ps1"))}
    for only in sorted(sh - ps):
        fail("hook .sh/.ps1 pairs", f"{only}.sh has no .ps1 sibling")
    for only in sorted(ps - sh):
        fail("hook .sh/.ps1 pairs", f"{only}.ps1 has no .sh sibling")


# --- 2. Other scripts that must exist in both forms --------------------------
@check("installer/deployer pairs")
def _():
    for base in ("install", "templates/project/init"):
        for ext in (".sh", ".ps1"):
            path = os.path.join(REPO, base + ext)
            if not os.path.exists(path):
                fail("installer/deployer pairs", f"{base}{ext} is missing")


# --- 3. Every hook wired in settings.json actually exists --------------------
@check("settings.json hook wiring")
def _():
    settings = json.loads(read("global/.claude/settings.json"))
    for event, groups in settings["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                name = os.path.basename(hook["command"]).replace(".sh", "")
                for ext in (".sh", ".ps1"):
                    path = os.path.join(REPO, "global/.claude/hooks", name + ext)
                    if not os.path.exists(path):
                        fail("settings.json hook wiring",
                             f"{event} wires '{name}' but {name}{ext} does not exist")


# --- 4. install.ps1 derives its rules instead of re-typing them ---------------
@check("install.ps1 derives from settings.json")
def _():
    ps1 = read("install.ps1")
    if "ConvertFrom-Json" not in ps1 or "global\\.claude\\settings.json" not in ps1:
        fail("install.ps1 derives from settings.json",
             "install.ps1 no longer reads global/.claude/settings.json — it is "
             "re-typing the rules, which is how Unix and Windows drifted before")
    # Every Bash verb in the source needs a $verbMap entry (or an explicit
    # $null drop). Parse the $verbMap block rather than searching the whole
    # file: a bare substring test would false-pass on a verb that merely
    # appears in a comment.
    block = re.search(r"\$verbMap\s*=\s*@\{(.*?)\n\}", ps1, re.S)
    if not block:
        fail("install.ps1 derives from settings.json",
             "could not find the $verbMap block — this check can no longer verify "
             "Windows coverage, so fix the check before trusting a pass")
        return
    mapped = set(re.findall(r'^\s*"([^"]+)"\s*=', block.group(1), re.M))

    settings = json.loads(read("global/.claude/settings.json"))
    rules = (settings["permissions"]["allow"] + settings["permissions"]["ask"]
             + settings["permissions"]["deny"])
    for rule in rules:
        m = re.match(r"^Bash\((.*?):?\*?\)$", rule)
        if not m or rule == "Bash":
            continue
        verb = m.group(1)
        if verb not in mapped:
            fail("install.ps1 derives from settings.json",
                 f"Bash({verb}) has no entry in install.ps1's $verbMap — it would "
                 f"be silently dropped on Windows")


# --- 5. Doc inventories match the artifacts on disk --------------------------
@check("doc inventories")
def _():
    hooks = sorted(os.path.basename(p)[:-3]
                   for p in glob.glob(os.path.join(REPO, "global/.claude/hooks/*.sh")))
    agents = sorted(os.path.basename(p)[:-3]
                    for p in glob.glob(os.path.join(REPO, "global/.claude/agents/*.md")))
    skills = sorted(os.path.basename(os.path.dirname(p))
                    for p in glob.glob(os.path.join(REPO, "global/.claude/skills/*/SKILL.md")))

    # Hooks that are opt-in (merged only by --serena) are not part of the
    # always-on inventory those docs describe.
    optional_hooks = {"prefer-serena-bash", "prefer-graphify"}
    core_hooks = [h for h in hooks if h not in optional_hooks]

    inventories = {
        "CLAUDE.md": read("CLAUDE.md"),
        "templates/project/README.md": read("templates/project/README.md"),
    }
    for doc, text in inventories.items():
        for hook in core_hooks:
            if hook not in text:
                fail("doc inventories", f"{doc} never mentions the '{hook}' hook")
        for agent in agents:
            if agent not in text:
                fail("doc inventories", f"{doc} never mentions the '{agent}' agent")
    readme = inventories["templates/project/README.md"]
    for skill in skills:
        if skill not in readme:
            fail("doc inventories",
                 f"templates/project/README.md never mentions the '{skill}' skill")


# --- 6. The code-extension lists agree across rules and hooks ----------------
@check("code extension lists")
def _():
    def exts_from_rule(path):
        head = read(path).split("---")[1]
        m = re.search(r"paths:\s*(.+)", head)
        return set(re.findall(r"\w+", m.group(1).split("{")[-1])) if m else set()

    def exts_from_hook(path):
        # The hook's list lives inside a grep -qE '\.(ts|tsx|...)' alternation.
        # Anchor on that shape rather than on specific extensions, so reordering
        # the list cannot make this silently return nothing.
        m = re.search(r"\\\.\(([a-z0-9|]+)\)", read(path))
        return set(m.group(1).split("|")) if m else set()

    rule_exts = exts_from_rule("global/.claude/rules/code-quality.md")
    sec_exts = exts_from_rule("global/.claude/rules/security.md")
    if rule_exts != sec_exts:
        diff = rule_exts.symmetric_difference(sec_exts)
        fail("code extension lists",
             f"code-quality.md and security.md disagree on: {sorted(diff)}")

    hook_exts = exts_from_hook("global/.claude/hooks/prefer-serena-bash.sh")
    # A check that silently no-ops is worse than no check: if either list came
    # back empty the extraction broke, and that is itself the finding.
    if not hook_exts:
        fail("code extension lists",
             "could not extract the extension list from prefer-serena-bash.sh — "
             "fix this check rather than trusting its pass")
    if not rule_exts:
        fail("code extension lists",
             "could not extract the paths: glob from code-quality.md — "
             "fix this check rather than trusting its pass")
    if hook_exts and rule_exts:
        missing = hook_exts - rule_exts
        if missing:
            fail("code extension lists",
                 f"prefer-serena-bash.sh treats {sorted(missing)} as code but the "
                 f"rules' paths: glob does not, so no rule loads for those files")


# --- 7. Skills never use inline interpreters (guard-destructive blocks them) --
@check("skills avoid inline interpreters")
def _():
    # Matches `python3 -c "..."`, `node -e '...'` and the bare `-c` form. The
    # quote right after the flag is the common shape, so it must not be required
    # to be preceded by a space.
    pattern = re.compile(r"""(python3?|node|ruby|perl)\s+-(c|e)[\s"']""")
    # os.walk, not glob: glob skips dot-directories, so `global/.claude/skills/`
    # — every central skill — was invisible to this check.
    for path in walk_files(("skills", "global/.claude/skills"), ".md"):
        rel = os.path.relpath(path, REPO)
        for i, line in enumerate(open(path), 1):
            if pattern.search(line) and "guard-destructive" not in line:
                fail("skills avoid inline interpreters",
                     f"{rel}:{i} uses an inline interpreter; guard-destructive "
                     f"blocks it with exit 2 (put the code in a script file)")


# --- 8. Every safety hook that has a case matrix keeps it ---------------------
@check("safety hooks have case matrices")
def _():
    # Each of these hooks shipped a real defect that reading them did not
    # reveal (DESIGN.md §18, §26, §27). Their matrices are the regression net;
    # a hook silently losing its matrix would be invisible in a passing run.
    for hook, matrix in (("guard-push-main", "tests/guard-push-main-cases.py"),
                         ("guard-destructive", "tests/guard-destructive-cases.py"),
                         ("detect-secrets", "tests/detect-secrets-cases.py"),
                         ("guard-central-config", "tests/guard-central-config-cases.py"),
                         ("verify-on-edit", "tests/verify-on-edit-cases.py")):
        if not os.path.exists(os.path.join(REPO, matrix)):
            fail("safety hooks have case matrices",
                 f"{hook} has no case matrix at {matrix}")


# --- 9. The guard-push-main matrix still covers the known bypasses -----------
@check("guard-push-main case coverage")
def _():
    cases = read("tests/guard-push-main-cases.py")
    # Each of these forms was a real bypass or a real false positive at some
    # point (DESIGN.md §18). Dropping one from the matrix would let the same
    # bug ship again, and a dropped case is invisible in a passing run.
    required = [
        "+main:main",                 # force via refspec, no --force flag
        "origin HEAD",                # HEAD resolves to the current branch
        "'main'",                     # quoted branch name
        "feature/main-refactor",      # branch merely containing 'main'
        "fix +main flag",             # '+main' inside a commit message
        "echo push notes",            # the words without an actual push
    ]
    for form in required:
        if form not in cases:
            fail("guard-push-main case coverage",
                 f"tests/guard-push-main-cases.py no longer covers {form!r} — that "
                 f"form was a real bug once; removing it lets it regress silently")


# --- 8b. The central artifacts still exist -----------------------------------
@check("central artifact inventory")
def _():
    # check 5 derives its inventories FROM disk, so deleting an agent or a
    # whole skill directory just shrinks the glob and passes green. The
    # expected set is therefore hardcoded here: this is what every project
    # gets, and losing one silently is exactly the "mechanism that never ran"
    # class DESIGN.md §27a names.
    expected = {
        "agents": ["code-reviewer.md", "db-inspector.md", "debugger.md", "researcher.md"],
        "rules": ["ai-collaboration.md", "code-quality.md", "security.md", "workflow.md"],
        "output-styles": ["dotclaude.md"],
    }
    for subdir, names in expected.items():
        for name in names:
            if not os.path.exists(os.path.join(REPO, "global/.claude", subdir, name)):
                fail("central artifact inventory",
                     f"global/.claude/{subdir}/{name} is missing — every project loses it")
    for skill in ("audit", "changes", "commit", "compound", "implement-ui",
                  "plan-feature", "readme", "resume-context", "update-docs",
                  "verify"):
        if not os.path.exists(os.path.join(REPO, "global/.claude/skills", skill, "SKILL.md")):
            fail("central artifact inventory",
                 f"global/.claude/skills/{skill}/SKILL.md is missing")


# --- 8c. Agent and skill frontmatter parses and declares what it must --------
@check("frontmatter validity")
def _():
    # A broken fence or a missing `description` makes an artifact silently
    # un-loadable or un-invokable — no error anywhere, it just never fires.
    paths = (glob.glob(os.path.join(REPO, "global/.claude/agents/*.md"))
             + glob.glob(os.path.join(REPO, "global/.claude/skills/*/SKILL.md")))
    # model: is scoped to mechanical components (DESIGN.md §7). Anything else
    # pinning a model is a downgrade of reasoning work — the exact drift the
    # §27 audit found on code-reviewer and debugger.
    model_allowed = {"verify", "changes", "resume-context"}
    for path in paths:
        rel = os.path.relpath(path, REPO)
        body = read(rel)
        if not body.startswith("---\n") or "\n---\n" not in body[4:]:
            fail("frontmatter validity", f"{rel} has no closing --- fence")
            continue
        front = body[4:].split("\n---\n", 1)[0]
        keys = dict(re.findall(r"^([A-Za-z-]+):\s*(.*)$", front, re.M))
        expected_name = (os.path.basename(os.path.dirname(path))
                         if path.endswith("SKILL.md") else os.path.basename(path)[:-3])
        for required in ("name", "description"):
            if required not in keys:
                fail("frontmatter validity", f"{rel} frontmatter has no `{required}:`")
        if keys.get("name") not in (None, expected_name):
            fail("frontmatter validity",
                 f"{rel} declares name: {keys['name']!r} but lives at {expected_name!r}")
        model = keys.get("model")
        if model and model != "inherit" and expected_name not in model_allowed:
            fail("frontmatter validity",
                 f"{rel} pins model: {model} — §7 allows an override only for "
                 f"mechanical components ({', '.join(sorted(model_allowed))})")


# --- 9b. Hook wiring: no prefix `if` gates, no dead advisory channel ---------
@check("hook wiring")
def _():
    settings = json.loads(read("global/.claude/settings.json"))
    # An `if` pattern is prefix-anchored, so it reopens exactly the wrapped
    # forms the hooks' parsers exist to catch: "if": "Bash(git push *)" let
    # `git -C /repo push origin main` through unjudged, and the matrix passed
    # because it invokes the hook directly (DESIGN.md §27b). Hooks self-gate.
    for event, groups in settings.get("hooks", {}).items():
        for group in groups:
            for entry in group.get("hooks", []):
                if "if" in entry:
                    fail("hook wiring",
                         f"{event} hook {entry.get('command', '?')} has an `if` gate — "
                         f"prefix-anchored patterns reopen wrapped-form bypasses; "
                         f"let the hook self-gate instead (DESIGN.md §27b)")

    # An advisory hook must deliver via hookSpecificOutput.additionalContext on
    # stdout: with exit 0, stderr reaches the debug log only, so three hooks
    # were inert for months (DESIGN.md §17, 2026-08-15).
    for name in ("prefer-serena-bash", "prefer-graphify", "sync-mirror-docs"):
        for ext in ("sh", "ps1"):
            body = read(f"global/.claude/hooks/{name}.{ext}")
            if "additionalContext" not in body:
                fail("hook wiring",
                     f"{name}.{ext} does not emit additionalContext — an advisory "
                     f"written to stderr with exit 0 never reaches the model")


# --- 10. DESIGN.md structural headings survive edits -------------------------
@check("DESIGN.md structure")
def _():
    design = read("DESIGN.md")
    for heading in ("## Things deliberately not included",
                    "## Open questions for future iteration"):
        if heading not in design:
            fail("DESIGN.md structure",
                 f"the '{heading}' heading is gone — its bullets now read as part "
                 f"of the preceding decision")


# --- 10b. MCP fragments are single-server and flat -----------------------------
# `.mcp.json` is composed from these, one file per server. A fragment holding two
# servers, or wrapping them in an "mcpServers" key (the shape of the old
# monolithic template), would merge the wrong keys into the user's file.
@check("MCP fragments")
def _():
    frag_dir = os.path.join(REPO, "templates/project/mcp")
    if not os.path.isdir(frag_dir):
        fail("MCP fragments", "templates/project/mcp/ is missing")
        return
    names = sorted(n for n in os.listdir(frag_dir) if n.endswith(".json"))
    if not names:
        fail("MCP fragments", "templates/project/mcp/ has no fragments")
    for name in names:
        rel = f"templates/project/mcp/{name}"
        try:
            data = json.loads(read(rel))
        except json.JSONDecodeError:
            continue          # the JSON validity check reports the parse error
        if "mcpServers" in data:
            fail("MCP fragments",
                 f"{rel} wraps its server in 'mcpServers' — fragments hold the "
                 f"bare server entry, the wrapper belongs to ./.mcp.json")
        if len(data) != 1:
            fail("MCP fragments",
                 f"{rel} defines {len(data)} servers; one file per server")
        stem = name[:-len(".json")]
        if stem not in data:
            fail("MCP fragments",
                 f"{rel} defines '{list(data)[0]}' — the key must match the "
                 f"filename so the deploy scripts can name fragments directly")


# --- 11. JSON files parse -----------------------------------------------------
@check("JSON validity")
def _():
    # mcp/ fragments are globbed, not listed: the --ui commit shipped
    # playwright.json without extending this list, so a syntax error in it
    # passed green while check 10 deferred to "the JSON validity check".
    fragments = sorted(
        os.path.relpath(p, REPO)
        for p in glob.glob(os.path.join(REPO, "templates/project/mcp/*.json")))
    for rel in ["global/.claude/settings.json",
                "templates/project/.claude/settings.json",
                "templates/project/.claude/serena-hooks.json",
                "templates/project/.claude/settings.local.json.example",
                ] + fragments:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        try:
            json.loads(read(rel))
        except json.JSONDecodeError as exc:
            fail("JSON validity", f"{rel} does not parse: {exc}")


def main():
    print(f"dotclaude coherence check — {checks_run} checks\n")
    if not failures:
        print("PASS — no divergences found.")
        return 0
    by_check = {}
    for name, detail in failures:
        by_check.setdefault(name, []).append(detail)
    for name, details in by_check.items():
        print(f"FAIL  {name}")
        for d in details:
            print(f"      - {d}")
        print()
    print(f"{len(failures)} divergence(s) across {len(by_check)} check(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
