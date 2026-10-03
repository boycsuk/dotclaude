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
    path = os.path.join(repo, "global/.claude/hooks/sync-mirror-docs.sh")
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


def obsolete_hits_shipped_hook(repo):
    """An obsolete.json match that also hits a live hook would strip it from
    every project on the next deploy."""
    path = os.path.join(repo, "templates/project/obsolete.json")
    with open(path) as fh:
        manifest = json.load(fh)
    manifest["hooks"].append({"match": "hooks/guard-destructive.", "reason": "x"})
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)


def lsp_entry_without_binary(repo):
    """A catalog entry with no binary turns the PATH probe into a no-op."""
    path = os.path.join(repo, "templates/project/lsp-plugins.json")
    with open(path) as fh:
        catalog = json.load(fh)
    del catalog["plugins"]["pyright-lsp"]["binary"]
    with open(path, "w") as fh:
        json.dump(catalog, fh, indent=2)


def _replace(repo, rel, old, new):
    path = os.path.join(repo, rel)
    with open(path) as fh:
        text = fh.read()
    assert old in text, f"{old!r} not in {rel}"
    with open(path, "w") as fh:
        fh.write(text.replace(old, new))


def drop_py_hook_kind(repo):
    """A .py hook without its kind marker escapes the advisory/guard checks."""
    _replace(repo, "global/.claude/hooks/code-intel-context.py", "# hook-kind: advisory\n", "")


def rewrite_hook_without_matrix(repo):
    """A hook that alters tool input must keep its case matrix."""
    os.remove(os.path.join(repo, "tests/explore-graph-prompt-cases.py"))


def wire_py_hook_without_interpreter(repo):
    """install.ps1 only rewrites the `python3 <hook>.py` form; a bare path
    would reach Windows unexecutable."""
    _replace(repo, "global/.claude/settings.json",
             'python3 \\"$HOME\\"/.claude/hooks/code-intel-context.py',
             '\\"$HOME\\"/.claude/hooks/code-intel-context.py')


def py_hook_gains_shell_twin(repo):
    """One hook, one implementation: a .py with a .sh twin is drift waiting."""
    with open(os.path.join(repo, "global/.claude/hooks/code-intel-context.sh"), "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")


def mixed_wildcard_rule(repo):
    """`Bash(mkfs.*:*)` matched nothing on Unix: the `*` before `:*` is literal."""
    _replace(repo, "global/.claude/settings.json", '"Bash(mkfs.*)"', '"Bash(mkfs.*:*)"')


def undocument_opt_out(repo):
    """An opt-out missing from settings.local.json.example is undiscoverable."""
    _replace(repo, "templates/project/.claude/settings.local.json.example",
             '"allowCommitTrailers"', '"someOtherKey"')


def obsolete_broad_match(repo):
    """A match like "python3 " hits no hook file name but every live .py hook command."""
    path = os.path.join(repo, "templates/project/obsolete.json")
    with open(path) as fh:
        manifest = json.load(fh)
    manifest["hooks"].append({"match": "python3 ", "reason": "x"})
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)


def unwire_py_hook(repo):
    """A .py hook that ships but is wired to no event never runs."""
    path = os.path.join(repo, "global/.claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    for groups in settings["hooks"].values():
        for group in groups:
            group["hooks"] = [h for h in group["hooks"] if "guard-dependencies" not in h["command"]]
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


REGRESSIONS = {
    "obsolete-broad-match": obsolete_broad_match,
    "unwire-py-hook": unwire_py_hook,
    "undocument-opt-out": undocument_opt_out,
    "mixed-wildcard-rule": mixed_wildcard_rule,
    "drop-py-hook-kind": drop_py_hook_kind,
    "rewrite-hook-without-matrix": rewrite_hook_without_matrix,
    "wire-py-hook-without-interpreter": wire_py_hook_without_interpreter,
    "py-hook-gains-shell-twin": py_hook_gains_shell_twin,
    "obsolete-hits-shipped-hook": obsolete_hits_shipped_hook,
    "lsp-entry-without-binary": lsp_entry_without_binary,
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
