#!/usr/bin/env python3
"""Inject one specific regression into a scratch copy of the repo.

Used by tests/check-selftest.sh to verify that check.py actually fails on the
things it claims to catch. Kept as a file rather than inline heredocs because
guard-destructive blocks inline interpreters (DESIGN.md §5).

Usage: python3 tests/inject.py <repo-copy> <regression-name>
"""

import json
import os
import shutil
import sys


def add_deny_rule(repo):
    """A new Bash deny rule with no $verbMap entry would vanish on Windows."""
    path = os.path.join(repo, "global/.claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["permissions"]["deny"].append("Bash(curl:*)")
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def drop_design_heading(repo):
    path = os.path.join(repo, "DESIGN.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("## Things deliberately not included", ""))


def diverge_extensions(repo):
    path = os.path.join(repo, "global/.claude/rules/security.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace(",sql,vue,svelte", ""))


def drop_hook_from_readme(repo):
    path = os.path.join(repo, "templates/project/README.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("reinject-rules", "xxx"))


def wire_missing_hook(repo):
    path = os.path.join(repo, "global/.claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = \
        '"$HOME"/.claude/hooks/nonexistent.sh'
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def drop_push_case(repo):
    """Removing a known-bypass case from the matrix must not pass silently."""
    path = os.path.join(repo, "tests/guard-push-main-cases.py")
    with open(path) as fh:
        lines = fh.readlines()
    with open(path, "w") as fh:
        for line in lines:
            if "+main:main" in line:
                continue
            fh.write(line)


def drop_hook_matrix(repo):
    """A safety hook losing its case matrix must not pass silently."""
    os.remove(os.path.join(repo, "tests/guard-destructive-cases.py"))


def readd_if_gate(repo):
    """A prefix `if` gate reopens the wrapped-form bypasses (DESIGN.md §27b)."""
    path = os.path.join(repo, "global/.claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["if"] = "Bash(git push *)"
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def revert_advisory_to_stderr(repo):
    """An advisory hook back on stderr+exit 0 is invisible to the model."""
    path = os.path.join(repo, "global/.claude/hooks/prefer-graphify.sh")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("additionalContext", "someOtherField"))


def delete_central_agent(repo):
    """Deleting a central artifact must not pass green (check 5 globs disk)."""
    os.remove(os.path.join(repo, "global/.claude/agents/debugger.md"))


def break_frontmatter(repo):
    """A broken fence makes the artifact silently un-loadable."""
    path = os.path.join(repo, "global/.claude/agents/researcher.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("---\n", "", 1))


def pin_model_on_reviewer(repo):
    """A reasoning agent pinning a model is the §7 drift the audit found."""
    path = os.path.join(repo, "global/.claude/agents/code-reviewer.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("model: inherit", "model: sonnet", 1))


def wrap_mcp_fragment(repo):
    """A fragment re-wrapped in 'mcpServers' merges the wrong keys into the
    user's .mcp.json — the exact shape of the old monolithic template."""
    path = os.path.join(repo, "templates/project/mcp/xcode.json")
    with open(path) as fh:
        data = json.load(fh)
    with open(path, "w") as fh:
        json.dump({"mcpServers": data}, fh, indent=2)


def break_mcp_fragment_json(repo):
    """playwright.json shipped outside check 11's hardcoded list, so a syntax
    error in it passed green; the list is glob-derived now."""
    path = os.path.join(repo, "templates/project/mcp/playwright.json")
    with open(path, "a") as fh:
        fh.write(",")


def delete_central_skill(repo):
    """Deleting a whole skill dir shrank check 5's glob and passed green;
    the inventory tuple in check 8b must name every skill."""
    shutil.rmtree(os.path.join(repo, "global/.claude/skills/implement-ui"))


REGRESSIONS = {
    "drop-hook-matrix": drop_hook_matrix,
    "delete-central-agent": delete_central_agent,
    "break-frontmatter": break_frontmatter,
    "pin-model-on-reviewer": pin_model_on_reviewer,
    "add-deny-rule": add_deny_rule,
    "drop-design-heading": drop_design_heading,
    "diverge-extensions": diverge_extensions,
    "drop-hook-from-readme": drop_hook_from_readme,
    "wire-missing-hook": wire_missing_hook,
    "drop-push-case": drop_push_case,
    "readd-if-gate": readd_if_gate,
    "revert-advisory-to-stderr": revert_advisory_to_stderr,
    "wrap-mcp-fragment": wrap_mcp_fragment,
    "break-mcp-fragment-json": break_mcp_fragment_json,
    "delete-central-skill": delete_central_skill,
}


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in REGRESSIONS:
        print(f"usage: inject.py <repo-copy> <{'|'.join(REGRESSIONS)}>", file=sys.stderr)
        return 2
    REGRESSIONS[sys.argv[2]](sys.argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
