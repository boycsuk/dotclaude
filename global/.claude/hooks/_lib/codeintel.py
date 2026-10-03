"""What code-intelligence tooling a project has, and the guidance text for it.

Shared by code-intel-context.py and explore-graph-prompt.py so the session,
the subagents and every Explore delegation are told the same thing.
"""

import os

import hookio

GRAPH_SERVER = "codebase-memory-mcp"
LSP_SUFFIX = "-lsp@claude-plugins-official"


def _enabled_plugins(project):
    # Later scopes win, mirroring Claude Code's precedence: user < project < local.
    merged = {}
    for path in (os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
                 os.path.join(project, ".claude", "settings.json"),
                 os.path.join(project, ".claude", "settings.local.json")):
        data = hookio.load_json(path)
        plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(plugins, dict):
            merged.update(plugins)
    return merged


def detect(payload):
    """Return (lsp_plugins, has_graph) for the payload's project."""
    project = hookio.project_dir(payload)
    lsp = sorted(name[:-len("@claude-plugins-official")]
                 for name, on in _enabled_plugins(project).items()
                 if on is True and name.endswith(LSP_SUFFIX))
    mcp = hookio.load_json(os.path.join(project, ".mcp.json"))
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    has_graph = isinstance(servers, dict) and GRAPH_SERVER in servers
    return lsp, has_graph


def guidance(lsp, has_graph):
    """The tool-choice guidance for whatever is present; '' when nothing is."""
    if not lsp and not has_graph:
        return ""
    lines = ["Code intelligence in this project — pick the tool by the question:"]
    if lsp:
        lines.append(f"- LSP tool ({', '.join(lsp)}): definition, references, hover type or call "
                     "hierarchy of ONE symbol. Diagnostics arrive after each edit; fix them "
                     "before moving on.")
    if has_graph:
        lines.append("- Code graph (mcp__codebase-memory-mcp__*): structure and ripple effects — who "
                     "calls X (trace_path), what the current diff affects (detect_changes), "
                     "architecture (get_architecture), dead code. Check index_status first; if "
                     "the index is missing or stale, say so and fall back to Grep/Read. Never "
                     "run index_repository unless asked.")
    lines.append("- Grep/Glob/Read: literal text, config and non-code files, or when the above "
                 "have no answer.")
    return "\n".join(lines)
