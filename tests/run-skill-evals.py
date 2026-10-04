#!/usr/bin/env python3
"""Run the skill eval suite in tests/skill-evals/ through `claude plugin eval`.

usage: python3 tests/run-skill-evals.py [extra `claude plugin eval` flags]
       e.g. --case 'audit-*' --runs 3 --ablation with-without

Manual only, never in CI: every run is a real model call billed to the
account. The central skills ship through install.sh, not as a plugin, so this
builds a throwaway one in a temp directory (claude/skills/ as skills/, a
generated .claude-plugin/plugin.json, the suite as evals/) and never writes a
manifest into the repo. Skills load namespaced, as `dotclaude:<skill>`.

Two traps when writing a case, both measured: a prompt that types a slash
command loads the skill with no Skill tool call, so grade what the skill did
instead of `tool_used: Skill`; and runs load no output style, so the model may
ask in prose rather than through AskUserQuestion.

Defaults, each dropped when the same flag is passed: one arm and one run per
case, a 5 USD ceiling, the report kept local. The suite's own scaffold scripts
always run (they only create a git repo in the run's workspace) and Bash is
granted for git alone, under the eval run's OS sandbox.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGIN_NAME = "dotclaude"
DEFAULTS = [("--ablation", "none"), ("--runs", "1"), ("--max-cost-usd", "5"), ("--no-publish", None)]
ALWAYS = ["--trust-plugin", "--scaffold"]
GRANTED_TOOLS = ["Bash(git *)"]


def build_plugin(root):
    """Lay out the skills and the suite in `root` as a plugin; return its path."""
    plugin = os.path.join(root, PLUGIN_NAME)
    shutil.copytree(os.path.join(REPO, "claude", "skills"), os.path.join(plugin, "skills"))
    shutil.copytree(os.path.join(HERE, "skill-evals"), os.path.join(plugin, "evals"))
    os.makedirs(os.path.join(plugin, ".claude-plugin"))
    with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as f:
        json.dump({"name": PLUGIN_NAME, "description": "dotclaude central skills under eval"}, f)
    return plugin


def command(plugin, extra):
    cmd = ["claude", "plugin", "eval", plugin]
    for flag, value in DEFAULTS:
        if flag not in extra:
            cmd += [flag] if value is None else [flag, value]
    cmd += [f for f in ALWAYS if f not in extra]
    # --allow-tools takes a list, so it goes last where nothing after it can be read as a tool.
    return cmd + extra + ["--allow-tools", *GRANTED_TOOLS]


def main():
    if shutil.which("claude") is None:
        print("run-skill-evals: `claude` is not on PATH", file=sys.stderr)
        return 1
    root = tempfile.mkdtemp(prefix="dotclaude-skill-evals-")
    plugin = build_plugin(root)
    cmd = command(plugin, sys.argv[1:])
    print("run-skill-evals:", " ".join(cmd), flush=True)
    code = subprocess.run(cmd).returncode
    print(f"run-skill-evals: results under {os.path.join(plugin, 'evals', 'results')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
