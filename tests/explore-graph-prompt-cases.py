#!/usr/bin/env python3
"""Behavioural contract for explore-graph-prompt.py and code-intel-context.py.

Run:  python3 tests/explore-graph-prompt-cases.py
      python3 tests/explore-graph-prompt-cases.py --pwsh PATH  # PowerShell command form too

Both hooks tell the model which code-intelligence tools a project has. They
must stay SILENT where there is nothing to say (a hook that injects text into
every session of every project is noise), and the Explore rewrite must change
nothing but the prompt — a dropped key would silently change what the
subagent runs.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

MARKER = "[dotclaude code-intel]"


def project(tmp, graph=False, lsp=None, local_lsp_off=False):
    os.makedirs(os.path.join(tmp, ".claude"), exist_ok=True)
    if graph:
        with open(os.path.join(tmp, ".mcp.json"), "w") as fh:
            json.dump({"mcpServers": {"codebase-memory-mcp": {"command": "codebase-memory-mcp"}}}, fh)
    if lsp:
        with open(os.path.join(tmp, ".claude", "settings.json"), "w") as fh:
            json.dump({"enabledPlugins": {f"{lsp}@claude-plugins-official": True}}, fh)
    if local_lsp_off:
        with open(os.path.join(tmp, ".claude", "settings.local.json"), "w") as fh:
            json.dump({"enabledPlugins": {f"{lsp}@claude-plugins-official": False}}, fh)
    return tmp


def agent_payload(subagent="Explore", prompt="find callers of foo"):
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": subagent, "prompt": prompt,
                           "description": "find callers", "run_in_background": False}}


def rewritten(out):
    return (out or {}).get("hookSpecificOutput", {}).get("updatedInput")


def context(out):
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def check_rewrite_with_graph(tmp, pwsh):
    payload = agent_payload()
    code, out, _ = pyhook.run("explore-graph-prompt", payload, cwd=project(tmp, graph=True), pwsh=pwsh)
    new = rewritten(out)
    if code != 0 or not new:
        return f"no rewrite (exit {code}, out {out})"
    if not new["prompt"].startswith(payload["tool_input"]["prompt"]) or "trace_path" not in new["prompt"]:
        return f"prompt not extended with graph guidance: {new['prompt']!r}"
    for key in ("subagent_type", "description", "run_in_background"):
        if new.get(key) != payload["tool_input"][key]:
            return f"key {key!r} changed or dropped"
    if "permissionDecision" in out["hookSpecificOutput"]:
        return "rewrite must not carry a permission decision (it would bypass the user's rules)"
    return None


def check_rewrite_lsp_only(tmp, pwsh):
    code, out, _ = pyhook.run("explore-graph-prompt", agent_payload(),
                              cwd=project(tmp, lsp="pyright-lsp"), pwsh=pwsh)
    prompt = (rewritten(out) or {}).get("prompt", "")
    if "pyright-lsp" not in prompt or "trace_path" in prompt:
        return f"LSP-only project got the wrong guidance: {prompt!r}"
    return None


def check_silent_without_tools(tmp, pwsh):
    code, out, _ = pyhook.run("explore-graph-prompt", agent_payload(), cwd=project(tmp), pwsh=pwsh)
    return None if code == 0 and out is None else f"spoke in a project with no tools: {out}"


def check_other_agents_untouched(tmp, pwsh):
    code, out, _ = pyhook.run("explore-graph-prompt", agent_payload("general-purpose"),
                              cwd=project(tmp, graph=True), pwsh=pwsh)
    return None if out is None else f"rewrote a non-Explore agent: {out}"


def check_idempotent(tmp, pwsh):
    payload = agent_payload(prompt=f"x\n\n{MARKER}\nalready there")
    code, out, _ = pyhook.run("explore-graph-prompt", payload, cwd=project(tmp, graph=True), pwsh=pwsh)
    return None if out is None else "appended the guidance twice"


def check_malformed_input(tmp, pwsh):
    for payload in ({}, {"tool_name": "Agent", "tool_input": "not a dict"},
                    {"tool_name": "Agent", "tool_input": {"subagent_type": "Explore"}}):
        code, out, _ = pyhook.run("explore-graph-prompt", payload, cwd=project(tmp, graph=True), pwsh=pwsh)
        if code != 0 or out is not None:
            return f"malformed input {payload} -> exit {code}, out {out}"
    return None


def check_context_session_and_subagent(tmp, pwsh):
    proj = project(tmp, graph=True, lsp="gopls-lsp")
    for event in ("SessionStart", "SubagentStart"):
        code, out, _ = pyhook.run("code-intel-context", {"hook_event_name": event}, cwd=proj, pwsh=pwsh)
        text = context(out)
        if out.get("hookSpecificOutput", {}).get("hookEventName") != event:
            return f"{event}: wrong hookEventName in {out}"
        if "gopls-lsp" not in text or "trace_path" not in text:
            return f"{event}: guidance incomplete: {text!r}"
    return None


def check_context_silent_without_tools(tmp, pwsh):
    code, out, _ = pyhook.run("code-intel-context", {"hook_event_name": "SessionStart"},
                              cwd=project(tmp), pwsh=pwsh)
    return None if code == 0 and out is None else f"spoke in a project with no tools: {out}"


def check_context_local_disable_wins(tmp, pwsh):
    proj = project(tmp, lsp="pyright-lsp", local_lsp_off=True)
    code, out, _ = pyhook.run("code-intel-context", {"hook_event_name": "SessionStart"}, cwd=proj, pwsh=pwsh)
    return None if out is None else f"a plugin disabled in settings.local.json was still announced: {out}"


def check_graph_added_with_claude_mcp_add(tmp, pwsh):
    """A server added with `claude mcp add` (local scope) lives in ~/.claude.json, not .mcp.json."""
    proj = project(tmp)
    state = os.path.join(os.environ["HOME"], ".claude.json")
    with open(state, "w") as fh:
        json.dump({"projects": {proj: {"mcpServers": {"codebase-memory-mcp": {"command": "x"}}}}}, fh)
    try:
        code, out, _ = pyhook.run("code-intel-context", {"hook_event_name": "SessionStart"}, cwd=proj, pwsh=pwsh)
    finally:
        os.remove(state)
    return None if "trace_path" in context(out) else f"local-scope server not detected: {out}"


CASES = [
    ("graph server added with claude mcp add is detected", check_graph_added_with_claude_mcp_add),
    ("Explore prompt gains graph guidance, other keys intact", check_rewrite_with_graph),
    ("LSP-only project: LSP guidance, no graph tools", check_rewrite_lsp_only),
    ("no tools: silent", check_silent_without_tools),
    ("non-Explore agents untouched", check_other_agents_untouched),
    ("already-marked prompt is not extended twice", check_idempotent),
    ("malformed input exits 0 silently", check_malformed_input),
    ("context at SessionStart and SubagentStart", check_context_session_and_subagent),
    ("context silent without tools", check_context_silent_without_tools),
    ("settings.local.json disabling the plugin wins", check_context_local_disable_wins),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()
    total = bad = 0
    # A HOME without settings, so the user's own enabledPlugins cannot leak in.
    home = tempfile.mkdtemp(prefix="codeintel-home-")
    os.environ["HOME"] = home
    try:
        for label, pwsh in pyhook.runners(args.pwsh):
            for name, fn in CASES:
                tmp = tempfile.mkdtemp(prefix="codeintel-case-")
                try:
                    problem = fn(tmp, pwsh)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                total += 1
                bad += bool(problem)
                print(f"  {'ok  ' if not problem else 'BAD '}[{label}] {name}"
                      + (f" — {problem}" if problem else ""))
    finally:
        shutil.rmtree(home, ignore_errors=True)
    print(f"\ncode-intel hooks: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
