#!/usr/bin/env python3
"""Inject one specific regression into a scratch copy of the repo.

Used by tests/check-selftest.sh to verify that check.py actually fails on the
things it claims to catch. Kept as a file rather than inline heredocs because
guard-destructive blocks inline interpreters.

Usage: python3 tests/inject.py <repo-copy> <regression-name>
"""

import json
import os
import re
import shutil
import sys


def add_deny_rule(repo):
    """A new Bash deny rule with no $verbMap entry would vanish on Windows."""
    path = os.path.join(repo, "claude/settings.json")
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
    path = os.path.join(repo, "claude/rules/security.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace(",sql,vue,svelte", ""))


def _drop_from_inventory_line(repo, anchor, name):
    """Delete `name` from the one inventory line containing `anchor` only.

    The realistic regression: the name still appears in the doc's prose, so a
    whole-document search would pass on it.
    """
    path = os.path.join(repo, "claude/templates/project/README.md")
    with open(path) as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines):
        if anchor in line and name in line:
            lines[i] = re.sub(rf"\b{re.escape(name)}\b(,\s*)?", "", line, count=1)
            break
    else:
        raise SystemExit(f"inject: no inventory line with {anchor!r} lists {name!r}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


def drop_hook_from_readme(repo):
    _drop_from_inventory_line(repo, "- **hooks/** —", "reinject-rules")


def drop_skill_from_readme(repo):
    _drop_from_inventory_line(repo, "- **skills/** —", "resume-context")


def unwire_shell_hook(repo):
    """A safety .sh hook dropped from settings.json still has its file and matrix."""
    path = os.path.join(repo, "claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    for groups in settings["hooks"].values():
        for group in groups:
            group["hooks"] = [h for h in group["hooks"] if "detect-secrets" not in h["command"]]
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def reinject_to_stderr(repo):
    """A Stop notice that delivers as additionalContext resumes every turn."""
    path = os.path.join(repo, "claude/hooks/turn-end-notice.py")
    with open(path) as fh:
        text = fh.read()
    if "hookio.notice(" not in text:
        raise SystemExit("inject: turn-end-notice.py no longer speaks through hookio.notice")
    with open(path, "w") as fh:
        fh.write(text.replace("hookio.notice(", 'hookio.context("Stop", ', 1))


def wire_missing_hook(repo):
    path = os.path.join(repo, "claude/settings.json")
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


def drop_advisory_matrix(repo):
    """reinject-rules and sync-mirror-docs are run by one matrix only; losing it leaves both unrun."""
    os.remove(os.path.join(repo, "tests/advisory-hooks-cases.py"))


def drop_matcher_tool_case(repo):
    """guard-dependencies is wired on NotebookEdit; a matrix that stops sending one must fail check.py."""
    path = os.path.join(repo, "tests/guard-dependencies-cases.py")
    with open(path) as fh:
        text = fh.read()
    if '"NotebookEdit"' not in text:
        raise SystemExit("inject: guard-dependencies-cases.py no longer sends a NotebookEdit payload")
    with open(path, "w") as fh:
        fh.write(text.replace('"NotebookEdit"', '"Notebook"'))


def readd_if_gate(repo):
    """A prefix `if` gate reopens the wrapped-form bypasses."""
    path = os.path.join(repo, "claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["if"] = "Bash(git push *)"
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def revert_advisory_to_stderr(repo):
    """An advisory hook back on stderr+exit 0 is invisible to the model."""
    path = os.path.join(repo, "claude/hooks/sync-mirror-docs.py")
    with open(path) as fh:
        text = fh.read()
    if "hookio.context(" not in text:
        raise SystemExit("inject: sync-mirror-docs.py no longer delivers through hookio.context")
    with open(path, "w") as fh:
        fh.write(text.replace("hookio.context(", "print(file=sys.stderr, *(", 1))


def delete_central_agent(repo):
    """Deleting a central artifact must not pass green (check 5 globs disk)."""
    os.remove(os.path.join(repo, "claude/agents/debugger.md"))


def break_frontmatter(repo):
    """A broken fence makes the artifact silently un-loadable."""
    path = os.path.join(repo, "claude/agents/researcher.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("---\n", "", 1))


def pin_model_on_reviewer(repo):
    """A reasoning agent pinning a model is a reasoning downgrade check.py forbids."""
    path = os.path.join(repo, "claude/agents/code-reviewer.md")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("model: inherit", "model: sonnet", 1))


def wrap_mcp_fragment(repo):
    """A fragment re-wrapped in 'mcpServers' merges the wrong keys into the
    user's .mcp.json — the exact shape of the old monolithic template."""
    path = os.path.join(repo, "claude/templates/project/mcp/xcode.json")
    with open(path) as fh:
        data = json.load(fh)
    with open(path, "w") as fh:
        json.dump({"mcpServers": data}, fh, indent=2)


def break_mcp_fragment_json(repo):
    """playwright.json shipped outside check 11's hardcoded list, so a syntax
    error in it passed green; the list is glob-derived now."""
    path = os.path.join(repo, "claude/templates/project/mcp/playwright.json")
    with open(path, "a") as fh:
        fh.write(",")


def delete_central_skill(repo):
    """Deleting a whole skill dir shrank check 5's glob and passed green;
    the inventory tuple in check 8b must name every skill."""
    shutil.rmtree(os.path.join(repo, "claude/skills/implement-ui"))


def obsolete_hits_shipped_hook(repo):
    """An obsolete.json match that also hits a live hook would strip it from
    every project on the next deploy."""
    path = os.path.join(repo, "claude/templates/project/obsolete.json")
    with open(path) as fh:
        manifest = json.load(fh)
    manifest["hooks"].append({"match": "hooks/guard-destructive.", "reason": "x"})
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)


def lsp_entry_without_binary(repo):
    """A catalog entry with no binary turns the PATH probe into a no-op."""
    path = os.path.join(repo, "claude/templates/project/lsp-plugins.json")
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
    _replace(repo, "claude/hooks/code-intel-context.py", "# hook-kind: advisory\n", "")


def rewrite_hook_without_matrix(repo):
    """A hook that alters tool input must keep its case matrix."""
    os.remove(os.path.join(repo, "tests/explore-graph-prompt-cases.py"))


def wire_py_hook_without_interpreter(repo):
    """install.ps1 only rewrites the `python3 <hook>.py` form; a bare path
    would reach Windows unexecutable."""
    _replace(repo, "claude/settings.json",
             'python3 \\"$HOME\\"/.claude/hooks/code-intel-context.py',
             '\\"$HOME\\"/.claude/hooks/code-intel-context.py')


def py_hook_gains_shell_twin(repo):
    """One hook, one implementation: a .py with a .sh twin is drift waiting."""
    with open(os.path.join(repo, "claude/hooks/code-intel-context.sh"), "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")


def mixed_wildcard_rule(repo):
    """`Bash(mkfs.*:*)` matched nothing on Unix: the `*` before `:*` is literal."""
    _replace(repo, "claude/settings.json", '"Bash(mkfs.*)"', '"Bash(mkfs.*:*)"')


def undocument_opt_out(repo):
    """An opt-out missing from settings.local.json.example is undiscoverable."""
    _replace(repo, "claude/templates/project/.claude/settings.local.json.example",
             '"allowCommitTrailers"', '"someOtherKey"')


def obsolete_broad_match(repo):
    """A match like "python3 " hits no hook file name but every live .py hook command."""
    path = os.path.join(repo, "claude/templates/project/obsolete.json")
    with open(path) as fh:
        manifest = json.load(fh)
    manifest["hooks"].append({"match": "python3 ", "reason": "x"})
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)


def unwire_py_hook(repo):
    """A .py hook that ships but is wired to no event never runs."""
    path = os.path.join(repo, "claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    for groups in settings["hooks"].values():
        for group in groups:
            group["hooks"] = [h for h in group["hooks"] if "guard-dependencies" not in h["command"]]
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def heredoc_back_into_subshell(repo):
    """Fold the python heredoc back inside a $( ), which bash -n on bash 4.2+ cannot see.

    Bash 4.1 and older (macOS /bin/bash is 3.2) mishandle a heredoc opened
    within a command substitution: they lex the quoted body for parens, quotes
    and backticks while hunting the closing paren, so a stray quote in the body
    makes the script unparseable there. bash 4.2+ parses it, so only check.py's
    static rule catches it on a modern host. Looks tidier, which is exactly why
    someone will try it again.
    """
    path = os.path.join(repo, "claude/templates/project/init.sh")
    with open(path) as fh:
        text = fh.read()
    marker = '  spec=$(lsp_spec "$plugin" || true)'
    if marker not in text:
        raise SystemExit("inject: init.sh no longer looks the LSP spec up through lsp_spec")
    text = text.replace(marker, '  spec=$(python3 - "$TEMPLATE_DIR/lsp-plugins.json" "$plugin" <<\'PY\' 2>/dev/null || true\n'
                                'print("x")\nPY\n)', 1)
    with open(path, "w") as fh:
        fh.write(text)


def add_permissions_key(repo):
    """A new scalar key under permissions must reach Windows too.

    install.ps1 builds `permissions` from named keys plus a generic copy of the
    rest. Without that copy a key added to the source applies on Unix only, so
    this drops the copy and adds a key.
    """
    ps1 = os.path.join(repo, "install.ps1")
    with open(ps1) as fh:
        text = fh.read()
    loop = "foreach ($p in $srcSettings.permissions.PSObject.Properties) {"
    if loop not in text:
        raise SystemExit("inject: install.ps1 no longer copies the remaining permissions keys")
    with open(ps1, "w") as fh:
        fh.write(text.replace(loop, "foreach ($p in @()) {", 1))
    path = os.path.join(repo, "claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["permissions"]["blockReadsOutsideWorkingDirectories"] = True
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def diverge_seeded_lists(repo):
    """The SEEDED list is hand-written in both installers; a key added to one
    only is silently never seeded on the other platform."""
    import re
    path = os.path.join(repo, "install.ps1")
    with open(path) as fh:
        text = fh.read()
    # Match the declaration rather than its current contents: pinning the list
    # verbatim made this regression rot the moment a key was added, and a
    # regression that cannot apply reports a false NOT CAUGHT.
    m = re.search(r'\$seeded\s*=\s*@\((.*?)\)', text)
    if not m:
        raise SystemExit("inject: install.ps1 no longer declares $seeded as expected")
    keys = re.findall(r'"([^"]+)"', m.group(1))
    if len(keys) < 2:
        raise SystemExit("inject: $seeded has too few keys to drop one")
    dropped = '$seeded = @(%s)' % ", ".join('"%s"' % k for k in keys[:-1])
    with open(path, "w") as fh:
        fh.write(text[:m.start()] + dropped + text[m.end():])


def own_a_seeded_key(repo):
    """Owning a user-facing preference makes every re-install revert a /config
    choice — the contract violation the three classes exist to prevent."""
    path = os.path.join(repo, "install.sh")
    with open(path) as fh:
        text = fh.read()
    old = 'OWNED = ("permissions", "hooks", "attribution")'
    if old not in text:
        raise SystemExit("inject: install.sh no longer declares OWNED as expected")
    with open(path, "w") as fh:
        fh.write(text.replace(old, 'OWNED = ("permissions", "hooks", "attribution", "outputStyle")'))


def stop_hook_starts_blocking(repo):
    """A Stop hook that emits `decision` resumes the turn on every fire.

    On Stop, decision/exit 2/additionalContext all continue the conversation,
    and the hook cannot tell a finished task from a half-done one. The matrix
    asserts none of those appear; dropping the assertion must not pass green.
    """
    path = os.path.join(repo, "tests/turn-end-notice-cases.py")
    with open(path) as fh:
        text = fh.read()
    if '"decision"' not in text:
        raise SystemExit("inject: turn-end-notice matrix no longer asserts on `decision`")
    # Strip every mention, the way a rewrite that stops caring would.
    with open(path, "w") as fh:
        fh.write(text.replace('"decision"', '"_dropped"'))


def add_unclassified_key(repo):
    """A top-level key in neither class never reaches ~/.claude at all."""
    path = os.path.join(repo, "claude/settings.json")
    with open(path) as fh:
        settings = json.load(fh)
    settings["alwaysThinkingEnabled"] = True
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)


def silence_feedback_hook(repo):
    """A feedback hook that stops calling hookio.feedback reports nothing to Claude."""
    path = os.path.join(repo, "claude/hooks/detect-secrets.py")
    with open(path) as fh:
        text = fh.read()
    if "hookio.feedback(" not in text:
        raise SystemExit("inject: detect-secrets.py no longer reports through hookio.feedback")
    with open(path, "w") as fh:
        fh.write(text.replace("hookio.feedback(", "print(", 1))


def drop_bootstrap(repo):
    """A hook that skips `import bootstrap` recompiles _lib on every run."""
    path = os.path.join(repo, "claude/hooks/guard-push-main.py")
    with open(path) as fh:
        text = fh.read()
    if "import bootstrap" not in text:
        raise SystemExit("inject: guard-push-main.py no longer imports bootstrap")
    with open(path, "w") as fh:
        fh.write(text.replace("import bootstrap  # noqa: E402,F401\n", ""))


def bypass_entrypoint(repo):
    """A guard exiting through sys.exit(main()) lets a crash through as a non-blocking exit 1."""
    path = os.path.join(repo, "claude/hooks/guard-destructive.py")
    with open(path) as fh:
        text = fh.read()
    if "hookio.entrypoint(main)" not in text:
        raise SystemExit("inject: guard-destructive.py no longer exits through hookio.entrypoint")
    with open(path, "w") as fh:
        fh.write(text.replace("hookio.entrypoint(main)", "sys.exit(main())"))


def orphan_shell_hook(repo):
    """A shell hook shipped without its .ps1 twin silently skips Windows."""
    with open(os.path.join(repo, "claude/hooks/new-check.sh"), "w") as fh:
        fh.write("#!/usr/bin/env bash\nexit 0\n")


def drop_ps1_exit_code(repo):
    """Write the .ps1 hook command without re-raising its exit code.

    Under `powershell -Command`, `& "x.ps1"` turns the script's exit 2 into
    exit 1, so every .ps1 guard runs, prints BLOCKED, and blocks nothing. The
    bare form reads as the obvious one, which is how it shipped.
    """
    path = os.path.join(repo, "install.ps1")
    with open(path) as fh:
        text = fh.read()
    if "; exit `$LASTEXITCODE\"" not in text:
        raise SystemExit("inject: install.ps1 no longer re-raises the hook exit code")
    with open(path, "w") as fh:
        fh.write(text.replace("; exit `$LASTEXITCODE\"", "\""))


def drop_fork_from_verify(repo):
    """A skill that pins haiku without forking hands haiku the caller's turn."""
    path = os.path.join(repo, "claude/skills/verify/SKILL.md")
    with open(path) as fh:
        text = fh.read()
    if "\ncontext: fork\n" not in text:
        raise SystemExit("inject: verify/SKILL.md no longer declares context: fork")
    with open(path, "w") as fh:
        fh.write(text.replace("\ncontext: fork\n", "\n", 1))


def unpin_mcp_fragment(repo):
    """An MCP server fragment back on @latest re-resolves the package on every start."""
    path = os.path.join(repo, "claude/templates/project/mcp/playwright.json")
    with open(path) as fh:
        data = json.load(fh)
    data["playwright"]["args"] = ["-y", "@playwright/mcp@latest"]
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


REGRESSIONS = {
    "orphan-shell-hook": orphan_shell_hook,
    "silence-feedback-hook": silence_feedback_hook,
    "unpin-mcp-fragment": unpin_mcp_fragment,
    "drop-fork-from-verify": drop_fork_from_verify,
    "drop-skill-from-readme": drop_skill_from_readme,
    "unwire-shell-hook": unwire_shell_hook,
    "reinject-to-stderr": reinject_to_stderr,
    "drop-ps1-exit-code": drop_ps1_exit_code,
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
    "stop-hook-starts-blocking": stop_hook_starts_blocking,
    "diverge-seeded-lists": diverge_seeded_lists,
    "own-a-seeded-key": own_a_seeded_key,
    "add-unclassified-key": add_unclassified_key,
    "add-permissions-key": add_permissions_key,
    "heredoc-back-into-subshell": heredoc_back_into_subshell,
    "drop-hook-matrix": drop_hook_matrix,
    "drop-advisory-matrix": drop_advisory_matrix,
    "drop-matcher-tool-case": drop_matcher_tool_case,
    "delete-central-agent": delete_central_agent,
    "break-frontmatter": break_frontmatter,
    "pin-model-on-reviewer": pin_model_on_reviewer,
    "add-deny-rule": add_deny_rule,
    "bypass-entrypoint": bypass_entrypoint,
    "drop-bootstrap": drop_bootstrap,
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
    # Every injection is destructive; pointed at the real checkout it would
    # quietly break the repo it is meant to test.
    here = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.realpath(sys.argv[1]) == here:
        print("inject.py: refusing to inject into the repository itself; pass a scratch copy",
              file=sys.stderr)
        return 2
    REGRESSIONS[sys.argv[2]](sys.argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
