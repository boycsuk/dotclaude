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


def code_only(text):
    """`text` without full-line `#` comments and triple-quoted docstrings.

    Marker checks run on this, not the raw file: a hook that names
    `additionalContext` only in a comment explaining it still passed a
    whole-file substring test while emitting on stderr.
    """
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    text = re.sub(r"<#(?:.|\n)*?#>", "", text)
    return re.sub(r"^\s*#.*$", "", text, flags=re.M)


def py_hooks():
    """Names of the single-file Python hooks (no .sh/.ps1 twin by design)."""
    return sorted(os.path.basename(p)[:-3]
                  for p in glob.glob(os.path.join(REPO, "global/.claude/hooks/*.py")))


# --- 1. Every shell hook ships as a .sh + .ps1 pair --------------------------
@check("hook .sh/.ps1 pairs")
def _():
    hooks = os.path.join(REPO, "global/.claude/hooks")
    for name in py_hooks():
        for ext in (".sh", ".ps1"):
            if os.path.exists(os.path.join(hooks, name + ext)):
                fail("hook .sh/.ps1 pairs",
                     f"{name}.py also has a {name}{ext} — one hook, one implementation")
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
                command = hook["command"].rstrip('"')
                if command.endswith(".py"):
                    name = os.path.basename(command)
                    if not command.startswith("python3 "):
                        fail("settings.json hook wiring",
                             f"{event} wires {name} without `python3 ` — install.ps1 "
                             f"only rewrites that form to the verified interpreter")
                    if not os.path.exists(os.path.join(REPO, "global/.claude/hooks", name)):
                        fail("settings.json hook wiring",
                             f"{event} wires '{name}' but it does not exist")
                    continue
                name = os.path.basename(command).replace(".sh", "")
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
        # Claude Code reads a `*` placed before the `:*` prefix suffix
        # literally, so `Bash(mkfs.*:*)` matched only commands containing a
        # literal `mkfs.*` — mkfs.ext4 ran unblocked (DESIGN.md §35).
        if re.search(r"\*.*:\*\)$", rule):
            fail("install.ps1 derives from settings.json",
                 f"{rule} mixes a `*` wildcard with the `:*` prefix suffix — Claude Code "
                 f"matches that `*` literally; write it as a pure wildcard rule")
        m = re.match(r"^Bash\((.*?)(?::\*)?\)$", rule)
        if not m or rule == "Bash":
            continue
        verb = m.group(1)
        if verb not in mapped:
            fail("install.ps1 derives from settings.json",
                 f"Bash({verb}) has no entry in install.ps1's $verbMap — it would "
                 f"be silently dropped on Windows")

    # install.ps1 rebuilds `permissions` key by key rather than copying the
    # object, so a NEW scalar key in the source reaches Unix and silently
    # vanishes on Windows. defaultMode was added that way and was caught here.
    generic_copy = re.search(r"foreach \(\$\w+ in \$srcSettings\.permissions\.PSObject\.Properties\)", ps1)
    for key in settings["permissions"]:
        if key in ("allow", "ask", "deny") or generic_copy:
            continue                      # rules: Convert-RuleList; scalars: the generic copy
        if key not in ps1:
            fail("install.ps1 derives from settings.json",
                 f"permissions.{key} is in settings.json but never read by "
                 f"install.ps1 — it would be dropped on Windows")

    # Claude Code runs a "shell": "powershell" hook through `-Command`, which
    # turns exit 2 into exit 1 unless the command re-raises $LASTEXITCODE.
    # Without it every .ps1 guard ran and blocked nothing.
    new_hook = re.search(r"function New-Hook\b.*?\n\}", ps1, re.S)
    if not new_hook:
        fail("install.ps1 derives from settings.json",
             "could not find function New-Hook — fix this check before trusting a pass")
        return
    commands = re.findall(r'^\s*\$command\s*=\s*"(.*)"\s*$', new_hook.group(0), re.M)
    if not commands:
        fail("install.ps1 derives from settings.json",
             "New-Hook assigns no $command — fix this check before trusting a pass")
    for command in commands:
        if not command.endswith("; exit `$LASTEXITCODE"):
            fail("install.ps1 derives from settings.json",
                 f"New-Hook writes `{command}` without `; exit $LASTEXITCODE` — "
                 f"PowerShell -Command turns the hook's exit 2 into a non-blocking 1")


# --- 4b. OWNED/SEEDED key classes agree across all three sites ---------------
# The same two lists are written by hand in install.sh and install.ps1, and a
# top-level key in settings.json that is in neither list never reaches
# ~/.claude at all. Nothing caught that: the `permissions` scalar-key check
# above covers only keys NESTED under permissions.
@check("settings key classes")
def _():
    NAME = "settings key classes"
    sh, ps1 = read("install.sh"), read("install.ps1")

    def lists(text, pat):
        m = re.search(pat, text)
        return set(re.findall(r'"([^"]+)"', m.group(1))) if m else None

    sh_owned = lists(sh, r"OWNED\s*=\s*\((.*?)\)")
    sh_seeded = lists(sh, r"SEEDED\s*=\s*\((.*?)\)")
    ps_owned = lists(ps1, r"\$owned\s*=\s*@\((.*?)\)")
    ps_seeded = lists(ps1, r"\$seeded\s*=\s*@\((.*?)\)")
    for label, got in (("OWNED", sh_owned), ("SEEDED", sh_seeded),
                       ("$owned", ps_owned), ("$seeded", ps_seeded)):
        if got is None:
            fail(NAME, f"could not find the {label} list — fix this check "
                       f"before trusting a pass")
            return

    if sh_owned != ps_owned:
        fail(NAME, f"owned keys differ: install.sh {sorted(sh_owned)} vs "
                   f"install.ps1 {sorted(ps_owned)}")
    if sh_seeded != ps_seeded:
        fail(NAME, f"seeded keys differ: install.sh {sorted(sh_seeded)} vs "
                   f"install.ps1 {sorted(ps_seeded)}")
    if sh_owned & sh_seeded:
        fail(NAME, f"{sorted(sh_owned & sh_seeded)} is both owned and seeded — "
                   f"owned overwrites every install, seeded must not")

    # Every non-comment top-level key in the source must be classified, or the
    # installers simply drop it.
    settings = json.loads(read("global/.claude/settings.json"))
    for key in settings:
        if key.startswith("_"):
            continue
        if key not in sh_owned and key not in sh_seeded:
            fail(NAME, f"top-level key '{key}' in settings.json is neither "
                       f"owned nor seeded — it never reaches ~/.claude")

    # Seeded keys are the ones a re-install must not revert.
    for key in sh_seeded:
        if key not in settings:
            fail(NAME, f"'{key}' is listed as seeded but is absent from "
                       f"settings.json — nothing would be seeded")


# --- 5. Doc inventories match the artifacts on disk --------------------------
@check("doc inventories")
def _():
    hooks = sorted(os.path.basename(p)[:-3]
                   for p in glob.glob(os.path.join(REPO, "global/.claude/hooks/*.sh"))) + py_hooks()
    agents = sorted(os.path.basename(p)[:-3]
                    for p in glob.glob(os.path.join(REPO, "global/.claude/agents/*.md")))
    skills = sorted(os.path.basename(os.path.dirname(p))
                    for p in glob.glob(os.path.join(REPO, "global/.claude/skills/*/SKILL.md")))

    # `statusline` lives in hooks/ for the .sh/.ps1 install machinery but is NOT
    # a hook — it is the statusLine command, wired through its own settings key
    # and firing on a different lifecycle — so the hook inventories do not
    # describe it.
    not_hooks = {"statusline"}
    hooks = [h for h in hooks if h not in not_hooks]

    # Names are matched inside the inventory LINE, as whole words. Searching the
    # whole document passed on a deleted inventory: every name also appears in
    # prose elsewhere ("guard-push-main" seven times in CLAUDE.md alone).
    inventories = [
        ("CLAUDE.md", "The central hooks (", "hook", hooks),
        ("CLAUDE.md", "├── agents/", "agent", agents),
        ("templates/project/README.md", "- **hooks/** —", "hook", hooks),
        ("templates/project/README.md", "- **agents/** —", "agent", agents),
        ("templates/project/README.md", "- **skills/** —", "skill", skills),
    ]
    for doc, anchor, kind, names in inventories:
        line = next((ln for ln in read(doc).splitlines() if anchor in ln), None)
        if line is None:
            fail("doc inventories", f"{doc} has no inventory line containing {anchor!r} — "
                                    f"fix this check before trusting a pass")
            continue
        for name in names:
            if not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", line):
                fail("doc inventories",
                     f"{doc}: the {kind} inventory ({anchor.strip()}) never lists '{name}'")


# --- 6. The code-extension lists agree across the path-scoped rules ----------
@check("code extension lists")
def _():
    def exts_from_rule(path):
        head = read(path).split("---")[1]
        m = re.search(r"paths:\s*(.+)", head)
        return set(re.findall(r"\w+", m.group(1).split("{")[-1])) if m else set()

    rule_exts = exts_from_rule("global/.claude/rules/code-quality.md")
    sec_exts = exts_from_rule("global/.claude/rules/security.md")
    # A check that silently no-ops is worse than no check: an empty list means
    # the extraction broke, and that is itself the finding.
    if not rule_exts:
        fail("code extension lists",
             "could not extract the paths: glob from code-quality.md — "
             "fix this check rather than trusting its pass")
    if rule_exts != sec_exts:
        diff = rule_exts.symmetric_difference(sec_exts)
        fail("code extension lists",
             f"code-quality.md and security.md disagree on: {sorted(diff)}")


# --- 7. Skills never use inline interpreters (guard-destructive blocks them) --
@check("skills avoid inline interpreters")
def _():
    # The same forms guard-destructive.py blocks, so a skill that passes here
    # cannot die with exit 2 at runtime. A narrower list let `bash -c`,
    # `sh -c`, `node --eval` and `python3 -Ic` through. A quote right after
    # the flag is the common shape, so the terminator also accepts quotes.
    pattern = re.compile(
        r"""(^|[\s`(])(python[0-9.]*\s+(-[A-Za-z]*)?-c|node\s+--eval|node\s+-e|deno\s+eval"""
        r"""|(ruby|perl)\s+(-[A-Za-z]*)?-e|php\s+-r|(ba|z|da|k)?sh\s+-c)([\s"']|$)""")
    # os.walk, not glob: glob skips dot-directories, so `global/.claude/skills/`
    # — every central skill — was invisible to this check.
    for path in walk_files(("skills", "global/.claude/skills"), ".md"):
        rel = os.path.relpath(path, REPO)
        for i, line in enumerate(open(path), 1):
            if pattern.search(line):
                fail("skills avoid inline interpreters",
                     f"{rel}:{i} uses an inline interpreter; guard-destructive "
                     f"blocks it with exit 2 (put the code in a script file)")


# --- 8. Every safety hook that has a case matrix keeps it ---------------------
@check("hooks have case matrices")
def _():
    # Each of these hooks shipped a real defect that reading them did not
    # reveal (DESIGN.md §18, §26, §27). Their matrices are the regression net;
    # a hook silently losing its matrix would be invisible in a passing run.
    #
    # The shell advisory hooks share ONE matrix: their failure mode is silence,
    # not a wrong verdict, so nothing else would notice them breaking — which
    # is how three advisory hooks sat on a dead delivery channel for months (§17).
    advisory = "tests/advisory-hooks-cases.py"
    for hook, matrix in (("guard-push-main", "tests/guard-push-main-cases.py"),
                         ("guard-destructive", "tests/guard-destructive-cases.py"),
                         ("detect-secrets", "tests/detect-secrets-cases.py"),
                         ("guard-central-config", "tests/guard-central-config-cases.py"),
                         ("verify-on-edit", "tests/verify-on-edit-cases.py"),
                         ("guard-commit", "tests/guard-commit-cases.py"),
                         ("guard-dependencies", "tests/guard-dependencies-cases.py"),
                         ("reinject-rules", advisory),
                         ("sync-mirror-docs", advisory),
                         ("changelog-reminder", "tests/changelog-reminder-cases.py"),
                         # Not a hook, but the same lockstep .sh/.ps1 pair, and
                         # its failure mode is worse than silence: whatever it
                         # emits lands in the status bar, so a traceback becomes
                         # permanent UI noise.
                         ("statusline", "tests/statusline-cases.py")):
        if not os.path.exists(os.path.join(REPO, matrix)):
            fail("hooks have case matrices",
                 f"{hook} has no case matrix at {matrix}")

    # changelog-reminder fires on Stop, where `decision: "block"`, exit 2 AND
    # hookSpecificOutput.additionalContext all CONTINUE the turn. Its matrix is
    # only a net if it asserts the hook emits none of them — "it printed
    # something" would pass on a version that silently resumes every turn.
    stop_matrix = "tests/changelog-reminder-cases.py"
    if os.path.exists(os.path.join(REPO, stop_matrix)):
        # Strip docstrings and comments first: the field names appear in this
        # matrix's own prose explaining why they must not be emitted, so a
        # whole-file substring test passes on a matrix that stopped asserting
        # anything — the false pass the $verbMap block-parse already avoids.
        body = read(stop_matrix)
        body = re.sub(r'""".*?"""', "", body, flags=re.S)
        body = re.sub(r"^\s*#.*$", "", body, flags=re.M)
        for needle in ("systemMessage", "decision", "hookSpecificOutput"):
            if f'"{needle}"' not in body:
                fail("hooks have case matrices",
                     f'{stop_matrix} has no executable assertion on "{needle}" — '
                     f"it cannot tell an advisory Stop hook from one that "
                     f"resumes the turn")

    # The advisory matrix is only a net if it asserts the DELIVERY channel.
    # Asserting "something was printed" would pass on the stderr form that was
    # inert, so pin the two strings that make the assertion real.
    if os.path.exists(os.path.join(REPO, advisory)):
        body = read(advisory)
        for needle in ("additionalContext", "hookEventName"):
            if needle not in body:
                fail("hooks have case matrices",
                     f"{advisory} does not assert {needle} — it would pass on "
                     f"the dead stderr channel (DESIGN.md §17)")


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
    # The per-project surface init.sh copies: a missing one makes the deploy
    # exit 1, which the skill reports as "template missing" on every machine.
    for rel in ("templates/project/CLAUDE.md.template",
                "templates/project/CHANGELOG.md.template",
                "templates/project/.gitignore.template",
                "templates/project/.claude/settings.json",
                "templates/project/.claude/settings.local.json.example",
                "templates/project/obsolete.json",
                "templates/project/lsp-plugins.json",
                "templates/project/scripts/prune-obsolete.py",
                "templates/project/scripts/merge-permissions.py",
                "templates/project/scripts/update-projects.py",
                "templates/project/scripts/merge-mcp.py",
                "templates/project/docs/README.md",
                "templates/project/docs/backend.md",
                "templates/project/docs/ui.md",
                "templates/project/docs/user-stories.md",
                "templates/project/docs/conventions.md",
                "skills/init-project/SKILL.md",
                "skills/init-project/scripts/detect-drift.py"):
        if not os.path.exists(os.path.join(REPO, rel)):
            fail("central artifact inventory", f"{rel} is missing — every deploy needs it")


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
        # A skill's model applies to the rest of the caller's turn unless the
        # skill forks (DESIGN.md §27): resume-context ran without the fork, so
        # every session's first turn dropped to haiku after it.
        if (path.endswith("SKILL.md") and model and model != "inherit"
                and keys.get("context") != "fork"):
            fail("frontmatter validity",
                 f"{rel} pins model: {model} without `context: fork` — the model "
                 f"would run the rest of the caller's turn")


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
    for name in ("sync-mirror-docs",):
        for ext in ("sh", "ps1"):
            body = code_only(read(f"global/.claude/hooks/{name}.{ext}"))
            if "additionalContext" not in body:
                fail("hook wiring",
                     f"{name}.{ext} does not emit additionalContext — an advisory "
                     f"written to stderr with exit 0 never reaches the model")
    # reinject-rules runs on SessionStart, where plain stdout is the context
    # channel; the same stderr regression would silence it.
    for ext, stderr_marks in (("sh", (">&2",)), ("ps1", ("[Console]::Error", "Write-Error"))):
        body = code_only(read(f"global/.claude/hooks/reinject-rules.{ext}"))
        if any(mark in body for mark in stderr_marks):
            fail("hook wiring",
                 f"reinject-rules.{ext} writes to stderr — on SessionStart only "
                 f"stdout reaches the model")

    hook_entries = [h for groups in settings.get("hooks", {}).values()
                    for g in groups for h in g.get("hooks", [])]
    wired = {os.path.basename(h["command"].rstrip('"')) for h in hook_entries}
    for name in py_hooks():
        if f"{name}.py" not in wired:
            fail("hook wiring", f"{name}.py ships but no event in settings.json runs it")
    # Shell hooks too: a safety hook dropped from settings.json still has its
    # file and its matrix, so nothing else notices it stopped running.
    status_command = settings.get("statusLine", {}).get("command", "")
    for path in sorted(glob.glob(os.path.join(REPO, "global/.claude/hooks/*.sh"))):
        name = os.path.basename(path)
        if name == "statusline.sh":
            if name not in status_command:
                fail("hook wiring", "statusline.sh ships but statusLine.command does not run it")
        elif name not in wired:
            fail("hook wiring", f"{name} ships but no event in settings.json runs it")

    # Python hooks declare their kind instead of being listed here by hand, so
    # a new hook cannot dodge this check by never being added to a tuple.
    for name in py_hooks():
        raw = read(f"global/.claude/hooks/{name}.py")
        m = re.search(r"^# hook-kind: (guard|advisory|rewrite)\s*$", raw, re.M)
        if not m:
            fail("hook wiring",
                 f"{name}.py has no `# hook-kind: guard|advisory|rewrite` header line")
            continue
        kind = m.group(1)
        body = code_only(raw)
        if kind == "advisory" and "hookio.context(" not in body:
            fail("hook wiring",
                 f"{name}.py is advisory but never calls hookio.context() — its "
                 f"text would not reach the model")
        if kind == "guard" and "hookio.deny(" not in body and "hookio.ask(" not in body:
            fail("hook wiring",
                 f"{name}.py is a guard but never calls hookio.deny() or hookio.ask()")
        if kind == "rewrite" and "hookio.update_input(" not in body:
            fail("hook wiring",
                 f"{name}.py is a rewrite hook but never calls hookio.update_input()")
        # A guard decides, a rewrite alters what a tool receives: both are
        # pinned by a matrix, since neither failure shows up in normal use.
        if kind in ("guard", "rewrite") and not os.path.exists(
                os.path.join(REPO, "tests", f"{name}-cases.py")):
            fail("hook wiring",
                 f"{name}.py is a {kind} hook with no tests/{name}-cases.py matrix — "
                 f"every guard hook shipped defects reading did not reveal")


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
        # `@latest` re-resolves on every server start: one compromised publish
        # runs as the user on every machine deployed with the flag.
        for server in data.values():
            for arg in server.get("args", []) if isinstance(server, dict) else []:
                if isinstance(arg, str) and arg.endswith("@latest"):
                    fail("MCP fragments", f"{rel} runs {arg!r} — pin an exact version")
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
        for p in glob.glob(os.path.join(REPO, "templates/project/mcp/*.json"))
        + glob.glob(os.path.join(REPO, "templates/project/permissions/*.json")))
    for rel in ["global/.claude/settings.json",
                "templates/project/.claude/settings.json",
                "templates/project/obsolete.json",
                "templates/project/lsp-plugins.json",
                "templates/project/.claude/settings.local.json.example",
                ] + fragments:
        try:
            json.loads(read(rel))
        except json.JSONDecodeError as exc:
            fail("JSON validity", f"{rel} does not parse: {exc}")


# --- 12. obsolete.json names only what dotclaude really stopped shipping -----
@check("obsolete manifest")
def _():
    # prune-obsolete.py deletes every project hook entry whose command contains
    # a listed match. A match that also hits a hook still shipped would strip
    # a live hook from every project on its next deploy.
    manifest = json.loads(read("templates/project/obsolete.json"))
    shipped_hooks = [f"hooks/{n}" for n in os.listdir(os.path.join(REPO, "global/.claude/hooks"))]
    # Every command the central settings wire, in the POSIX form and in the
    # PowerShell forms install.ps1 writes — a match hitting any of them (say
    # "claude", "python3 " or "$HOME") would prune live hooks everywhere.
    settings = json.loads(read("global/.claude/settings.json"))
    live = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    live += [c.replace("/", "\\") for c in live]
    # The exact forms install.ps1's New-Hook writes, not just a slash swap.
    win_hooks = "C:\\Users\\u\\.claude\\hooks"
    for c in list(live):
        name = os.path.basename(c.replace("\\", "/").rstrip('"'))
        if name.endswith(".py"):
            live.append(f'& "C:\\Python\\python.exe" "{win_hooks}\\{name}"; exit $LASTEXITCODE')
        elif name.endswith(".sh"):
            live.append(f'& "{win_hooks}\\{name[:-3]}.ps1"; exit $LASTEXITCODE')
    for entry in manifest.get("hooks", []):
        match = entry.get("match", "")
        if not match or not entry.get("reason"):
            fail("obsolete manifest", f"hook entry {entry} needs a non-empty match and reason")
            continue
        for hook in shipped_hooks:
            if match in hook or match.replace("\\", "/") in hook:
                fail("obsolete manifest",
                     f"match {match!r} hits {hook}, which dotclaude still ships — "
                     f"every project would lose it on the next deploy")
        for command in live:
            if match in command:
                fail("obsolete manifest",
                     f"match {match!r} also matches the live central hook command {command!r}")
    granted = set()
    for frag in glob.glob(os.path.join(REPO, "templates/project/permissions/*.json")):
        with open(frag) as fh:
            granted |= set(json.load(fh).get("allow", []))
    for entry in manifest.get("permissions", []):
        if not entry.get("rule") or not entry.get("reason"):
            fail("obsolete manifest", f"permission entry {entry} needs a non-empty rule and reason")
        elif entry["rule"] in granted:
            fail("obsolete manifest",
                 f"permission {entry['rule']!r} is listed as obsolete but a permissions/ fragment still grants it")
    for entry in manifest.get("mcpServers", []):
        name = entry.get("name", "")
        if os.path.exists(os.path.join(REPO, "templates/project/mcp", f"{name}.json")):
            fail("obsolete manifest",
                 f"MCP server {name!r} is listed as obsolete but mcp/{name}.json still ships")


# --- 12b. Every opt-out a hook honours is documented ---------------------------
@check("opt-outs documented")
def _():
    # An opt-out nobody can discover is a guard nobody can relax on purpose,
    # so users disable the whole hook instead.
    example = read("templates/project/.claude/settings.local.json.example")
    keys = set()
    for name in py_hooks():
        body = read(f"global/.claude/hooks/{name}.py")
        found = re.findall(r'local_opt_out\(\w+, "(\w+)"[,)]', body)
        # A call this pattern cannot read (single quotes, a constant) would
        # otherwise drop out of the check silently.
        if body.count("local_opt_out(") != len(found):
            fail("opt-outs documented",
                 f"{name}.py calls local_opt_out() in a form this check cannot read — "
                 f"pass the key as a double-quoted literal")
        keys |= set(found)
    for key in sorted(keys):
        if f'"{key}"' not in example:
            fail("opt-outs documented",
                 f"a hook honours {key!r} but settings.local.json.example never explains it")


# --- 13. The LSP plugin catalog is complete and well-formed -------------------
@check("LSP plugin catalog")
def _():
    # init.sh/init.ps1 read the binary and install hint from here, and the
    # skill maps languages through it: a missing field degrades into a WARN
    # with an empty command, which looks like a hint and helps nobody.
    catalog = json.loads(read("templates/project/lsp-plugins.json"))
    if catalog.get("marketplace") != "claude-plugins-official":
        fail("LSP plugin catalog", "marketplace must be claude-plugins-official (official plugins only)")
    plugins = catalog.get("plugins", {})
    if not plugins:
        fail("LSP plugin catalog", "no plugins listed")
    for name, entry in plugins.items():
        if not name.endswith("-lsp"):
            fail("LSP plugin catalog", f"{name!r} is not an official *-lsp plugin name")
        for field in ("languages", "binary", "install"):
            if not entry.get(field):
                fail("LSP plugin catalog", f"{name} has no {field!r}")


def heredoc_in_substitution(line):
    """True when `line` opens a heredoc inside a `$(` it has not closed yet.

    Bash 4.1 and older (macOS ships 3.2) lex such a heredoc body for parens,
    quotes and backticks while hunting the closing paren, so a body that
    parses on a modern bash breaks there. `$((`, here-strings (`<<<`) and
    comment lines are not this shape.
    """
    if line.lstrip().startswith("#"):
        return False
    depth = 0
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"':
                i += 1
        elif ch in "'\"":
            quote = ch
        elif line.startswith("$((", i):
            i += 2
        elif line.startswith("$(", i):
            depth += 1
            i += 1
        elif ch == ")" and depth:
            depth -= 1
        elif depth and line.startswith("<<", i) and not line.startswith("<<<", i):
            return True
        i += 1
    return False


# --- 14. Every shipped script actually parses ---------------------------------
@check("script syntax")
def _():
    # Every other check reads these files as TEXT: it globs names, greps for
    # markers, compares inventories. None of them would notice a script that
    # cannot be parsed at all. That is not hypothetical: a literal backtick
    # inside a Python heredoc opened inside $( ) made guard-destructive.sh and
    # guard-push-main.sh unparseable on bash 4.1 and older (bash scanned the
    # heredoc body for backtick substitutions while hunting the closing paren,
    # and quoting the delimiter did not stop it). Both are PreToolUse hooks on
    # Bash, so EVERY Bash call in EVERY project failed — while this validator
    # reported a clean pass.
    #
    # `bash -n` alone cannot catch that shape on a bash fixed in 4.2, so the
    # shape itself is rejected statically below, on every host.
    #
    # pwsh is optional (absent on most Unix dev machines); skip rather than
    # fail, since CLAUDE.md is explicit that a .ps1 parse pass proves nothing
    # about whether it RUNS — the matrices remain the behavioural net.
    import shutil
    import subprocess

    roots = ["global/.claude/hooks", "templates/project", "tests"]
    scripts = sorted(walk_files(roots, ".sh")) + [
        os.path.join(REPO, n) for n in ("install.sh",)
        if os.path.exists(os.path.join(REPO, n))]
    for path in scripts:
        rel = os.path.relpath(path, REPO)
        for i, line in enumerate(read(rel).splitlines(), 1):
            if heredoc_in_substitution(line):
                fail("script syntax",
                     f"{rel}:{i} opens a heredoc inside $( ) — bash 4.1 and older "
                     f"(macOS /bin/bash) cannot parse that; write the heredoc in a "
                     f"function at top level and substitute the function")
        try:
            proc = subprocess.run(["bash", "-n", path], capture_output=True,
                                  text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            fail("script syntax", f"could not parse-check {rel}: {exc}")
            continue
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().splitlines()
            fail("script syntax",
                 f"{rel} does not parse: {detail[0] if detail else 'bash -n failed'}")

    # Python is now the standard hook form, and a .py hook that fails to
    # compile exits 1 — a non-blocking error, so the guard is silently off.
    # A broken _lib/hookio.py takes every .py hook down with it.
    py_roots = ["global/.claude/hooks", "templates/project/scripts", "skills", "tests"]
    for path in sorted(walk_files(py_roots, ".py")) + [os.path.join(REPO, "check.py")]:
        rel = os.path.relpath(path, REPO)
        try:
            compile(read(rel), rel, "exec")
        except SyntaxError as exc:
            fail("script syntax", f"{rel}:{exc.lineno} does not compile: {exc.msg}")

    if not shutil.which("pwsh"):
        return
    ps_scripts = sorted(walk_files(roots, ".ps1")) + [
        os.path.join(REPO, n) for n in ("install.ps1",)
        if os.path.exists(os.path.join(REPO, n))]
    for path in ps_scripts:
        rel = os.path.relpath(path, REPO)
        # Parse without executing: the AST parser reports syntax errors only.
        quoted = path.replace("'", "''")
        probe = ("$ErrorActionPreference='Stop';"
                 "$t=$null;$e=$null;"
                 "[System.Management.Automation.Language.Parser]::ParseFile("
                 f"'{quoted}',[ref]$t,[ref]$e)|Out-Null;"
                 "if($e.Count){$e[0].Message;exit 1};exit 0")
        try:
            proc = subprocess.run(["pwsh", "-NoProfile", "-Command", probe],
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            fail("script syntax", f"could not parse-check {rel}: {exc}")
            continue
        if proc.returncode != 0:
            detail = (proc.stdout or proc.stderr or "").strip().splitlines()
            fail("script syntax",
                 f"{rel} does not parse: {detail[0] if detail else 'parse failed'}")


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
