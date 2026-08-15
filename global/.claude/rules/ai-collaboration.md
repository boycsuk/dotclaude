<!--
  No frontmatter / no paths: — always-on (same priority as CLAUDE.md). These
  collaboration conventions (language, asking for input, sub-agents) apply to
  every session regardless of file type.
-->

# AI Collaboration

## Output style

> A stronger, system-prompt-level version of these conventions ships as an output style at `~/.claude/output-styles/dotclaude.md` (source: `global/.claude/output-styles/` in the dotclaude repo). Enable it once per machine via `/config` → Output style → `dotclaude` (or set `"outputStyle": "dotclaude"` in settings). The rules below stay as the always-on fallback for anyone who hasn't enabled it.

- **Language: Castilian Spanish (Spain) for conversation, English for code.** Talk to the user in Castilian Spanish — "vale", "ordenador", "móvil", tuteo informal. Avoid Latin American variants ("okay/dale", "computadora", "celular", "ustedes" as the default plural). Keep everything *inside* the codebase in English: identifiers, comments, commit messages, log strings, documentation files (CLAUDE.md, CHANGELOG.md, READMEs). Mixing Spanish into code or git history breaks tooling, search, and onboarding for non-Spanish collaborators.
- **No emojis** in any output (code, commits, messages, documentation) unless strictly necessary for the task. They add noise to logs, terminals, and diffs.
- **Cite sources at the end of responses involving research.** When the answer relies on external documentation, forums, or articles, include a `Sources:` section at the end with markdown links. This applies whether the user explicitly asked for sources or not.

## Asking for input

- **Always use the `AskUserQuestion` tool (the multiple-choice options UI) when you need the user to decide or choose**, instead of asking in plain prose and waiting for a typed reply. This applies to any decision point: picking between approaches, confirming a direction, resolving an ambiguity, choosing where something goes. Give 2-4 concrete options (the user can always pick "Other"). The user strongly prefers clicking an option over typing an answer.
- **The one exception is genuinely open-ended input** that does not fit options — e.g. "describe what you want to build", a free-text name, pasting an error. There, ask in prose. If a question is *mostly* a choice with an open tail, still use `AskUserQuestion` (its "Other" handles the tail).
- When in doubt between prose and the tool, prefer the tool.
- **When several independent decisions are pending, batch them into ONE `AskUserQuestion` call** (it supports up to 4 questions, each with its own options and optional multiSelect) instead of asking serially.

## Plain-language explanations
When explaining or summarizing, prefer plain language: short sentences, everyday words, outcome first, then detail. Keep every fact, name, number, and file path; never alter code blocks or identifiers. No filler ("cabe destacar", "básicamente") and no meta-commentary about the answer itself. Gloss unavoidable jargon in parentheses on first use. Structure long answers with brief headings or lists; keep short answers short. The stronger, system-prompt-level version of this lives in the `dotclaude` output style (see "Output style" above).

## Predictable project structure
Coherent and descriptive file and folder names to facilitate AI navigation. Avoid abbreviations and ad-hoc nesting.

## Context always available
Keep `CLAUDE.md` and `CHANGELOG.md` up to date so the AI can orient itself without depending on previous conversations. If you discover a non-obvious decision during a session, codify it via `/compound` instead of trusting it will be remembered.

## Progressive disclosure
Do not put all context in a single file. Area-specific instructions live in separate files under `.claude/rules/`. A rule with a `paths:` field in its frontmatter loads only for files matching its globs; a rule without `paths:` loads every session at the same priority as `CLAUDE.md` (the `description:` field does NOT gate loading — that is a skills concept). The main `CLAUDE.md` stays lightweight (<200 lines). Keep always-on rules short and scope file-type-specific guidance behind `paths:` so the always-loaded surface stays small. Known limitation: a `paths:`-scoped rule attaches when a matching file is READ; creating a brand-new matching file may not trigger it (anthropics/claude-code#23478) — when generating new source files from scratch, read a sibling file first (which `rules/workflow.md` already mandates) so the scoped rules load.

## Resume context at session start
At the beginning of each new session, use `/resume-context`. It reads:
- `CLAUDE.md` (project conventions and current state).
- Recent `CHANGELOG.md` entries.
- `git log --oneline -10`.

Do not start blind in a project you have not touched recently.

## TOON for structured data
TOON format (https://github.com/toon-format/toon): consider it only for flat, uniform tabular payloads to the LLM (~20-60% fewer tokens than JSON); JSON stays better for nested/sparse data, CSV for pure tables. It needs the `@toon-format/toon` dependency — subject to the no-new-deps-without-confirmation rule; encoding a one-off payload by hand is fine.

## Use available sub-agents
This setup ships four central sub-agents (in `~/.claude/agents/`, available in every project):
- `researcher` for architectural deep-dives — how a subsystem works end-to-end, how modules fit together — returning a synthesized map. Not for quick lookups.
- `code-reviewer` for skeptical review after changes.
- `debugger` for root-cause diagnosis.
- `db-inspector` for read-only SQL database work: validate the database state after a change, or answer a question about current data (count rows, check a value, read the schema) to inform a decision mid-task. Inert when the project has no SQL database, so it costs nothing when unused.

Use them proactively even when not explicitly requested — they isolate work in a separate context window, keeping the main conversation clean.

The built-in **Explore** agent (Haiku, skips CLAUDE.md and git status) is the fast/cheap choice for "where is X defined / what imports Y" lookups; reach for the custom `researcher` only when you need a *synthesized* answer (end-to-end flow, cross-module dependencies, architectural layers) that requires reading and relating several files.

**Fan out to investigate; apply in series.** Parallel subagents are what make broad work possible and are also where essentially all the token cost goes — a wide sweep can burn over a million tokens in one run. Applying the results afterwards, in the main thread, is comparatively free. So: sweep once and wide, then work through the findings sequentially, and never re-run the sweep to check your own work — verify with the project's tools and tests instead. Group agents by module or dimension (single digits), never one per file: findings are usually cross-file anyway. Persist each agent's result to a scratch file as it returns, so a run cut short by a usage limit keeps the expensive part, and resume the missing units rather than restarting.

## Prefer Serena tools when available
If the project has Serena MCP active (check `.mcp.json` for a `serena` entry), prefer its symbol-level tools over text-level alternatives for non-trivial code work:
- `find_symbol` / `find_referencing_symbols` instead of `Grep` for locating definitions or references.
- `replace_symbol_body` instead of `Edit` for rewriting a function body — it preserves surrounding structure correctly.
- `get_symbols_overview` instead of reading a whole file when you only need its shape.

Skip Serena for: plain text/markdown files, one-off reads of a known path, edits where line-level precision matters more than symbol semantics. See the Serena block in CLAUDE.md for the full guidance.

**This preference is also enforced deterministically, not just by this prose.** A project deployed with `--serena` gets Serena's own drift-prevention hooks merged into its `.claude/settings.json` (`serena-hooks activate` at SessionStart, `serena-hooks remind` at PreToolUse). The `remind` hook injects a reminder *only* when you over-rely on Grep/Read without a recent Serena call — silent when you comply — which is why advisory prose alone is not relied upon: it decays under context compaction, the hook does not. When you see such a reminder, switch to the Serena tool it names; don't rationalize the built-in.

**Graphify (Serena's companion, same `.mcp.json`).** Where Serena works at the *symbol* level, Graphify works at the *graph* level — a queryable knowledge graph of how the whole codebase (code + docs + schema) relates. Reach for Graphify when the question is about **structure or ripple effects** rather than a single symbol: "what depends on this module", "what breaks if I change X" (impact analysis via `get_pr_impact` / `shortest_path`), or building a mental map of an unfamiliar area (`query_graph` / `get_neighbors`). The natural workflow is **graph first, then Serena**: query the graph to see the shape and blast radius, then act precisely on the symbols involved with Serena.

Two ways to reach the graph, both reading the same pre-built `graphify-out/graph.json`:
- **MCP tools** (`query_graph`, `get_neighbors`, `shortest_path`, `get_pr_impact`) — for impact analysis and neighborhood queries mid-task.
- **CLI** (cheaper for focused lookups): `graphify query "<question>"` returns a scoped subgraph usually far smaller than grepping raw files; `graphify path "<A>" "<B>"` traces relationships; `graphify explain "<concept>"` focuses one concept. Prefer `graphify-out/wiki/index.md` for broad navigation, and read `graphify-out/GRAPH_REPORT.md` only for whole-architecture review when query/path/explain don't surface enough. After editing code, `graphify update .` refreshes the graph (AST-only, no API cost).

Graphify's tools only work after the graph is built — run `/graphify .` once first. If no `graphify` entry is in `.mcp.json` or the graph was never built, fall back to Serena + the `researcher` agent. Like Serena, the preference is also enforced deterministically: the `prefer-graphify.{sh,ps1}` PreToolUse hook (shipped centrally, merged by `--serena`, gated on `graphify-out/graph.json`) nudges you toward `graphify query` when you reach for grep/find or read a code file one at a time while a graph exists. Heed that nudge; the graph answers structure questions faster than scanning files.
