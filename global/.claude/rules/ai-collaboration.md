<!--
  No frontmatter / no paths: — always-on (same priority as CLAUDE.md). These
  collaboration conventions (language, asking for input, sub-agents) apply to
  every session regardless of file type.
-->

# AI Collaboration

## Output style
The full tone and language conventions live in the `dotclaude` output style (`~/.claude/output-styles/dotclaude.md`), which `install.sh` enables unless you chose another style. Minimal fallback if it is off:
- Castilian Spanish (Spain) with the user, English for everything inside the codebase; no emojis; plain language, outcome first.
- Cite sources (`Sources:` with markdown links) when an answer relies on external research.

## Asking for input

- **Always use the `AskUserQuestion` tool (the multiple-choice options UI) when you need the user to decide or choose**, instead of asking in plain prose and waiting for a typed reply. This applies to any decision point: picking between approaches, confirming a direction, resolving an ambiguity, choosing where something goes. Give 2-4 concrete options (the user can always pick "Other"). The user strongly prefers clicking an option over typing an answer.
- **The one exception is genuinely open-ended input** that does not fit options — e.g. "describe what you want to build", a free-text name, pasting an error. There, ask in prose. If a question is *mostly* a choice with an open tail, still use `AskUserQuestion` (its "Other" handles the tail).
- When in doubt between prose and the tool, prefer the tool.
- **When several independent decisions are pending, batch them into ONE `AskUserQuestion` call** (it supports up to 4 questions, each with its own options and optional multiSelect) instead of asking serially.

## Plain-language explanations
When explaining or summarizing, prefer plain language: short sentences, everyday words, outcome first, then detail. Keep every fact, name, number, and file path; never alter code blocks or identifiers. No filler ("cabe destacar", "básicamente") and no meta-commentary about the answer itself. Gloss unavoidable jargon in parentheses on first use. Structure long answers with brief headings or lists; keep short answers short.

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

The built-in **Explore** agent (skips CLAUDE.md and git status, so it starts with a small context; since Claude Code v2.1.198 it runs on the session model, not Haiku) is the fast/cheap choice for "where is X defined / what imports Y" lookups; reach for the custom `researcher` only when you need a *synthesized* answer (end-to-end flow, cross-module dependencies, architectural layers) that requires reading and relating several files.

**Fan out to investigate; apply in series.** Parallel subagents are what make broad work possible and are also where essentially all the token cost goes — a wide sweep can burn over a million tokens in one run. Applying the results afterwards, in the main thread, is comparatively free. So: sweep once and wide, then work through the findings sequentially, and never re-run the sweep to check your own work — verify with the project's tools and tests instead. Group agents by module or dimension (single digits), never one per file: findings are usually cross-file anyway. Persist each agent's result to a scratch file as it returns, so a run cut short by a usage limit keeps the expensive part, and resume the missing units rather than restarting.

**Agent memory is available but unused here, deliberately.** A subagent can persist knowledge across sessions with `memory: user|project|local` in its frontmatter (stored in `~/.claude/agent-memory/<agent>/`, `.claude/agent-memory/<agent>/`, or `.claude/agent-memory-local/<agent>/` respectively). Two things to know before adding it. First, it rides on auto memory: with `autoMemoryEnabled` false or `CLAUDE_CODE_DISABLE_AUTO_MEMORY` set, the field is ignored **silently** — a configured capability that does nothing, with no error. Second, enabling it auto-enables Read/Write/Edit so the agent can manage its own files, which collides with the read-only guarantee `researcher`, `code-reviewer` and `debugger` get from `disallowedTools: Write, Edit`; the docs do not say which side wins. Resolve that empirically before giving memory to a read-only agent — an agent that silently regains Write is a worse outcome than no memory.

**A subagent's findings are hypotheses, not facts.** A sweep returns a confident synthesis whether or not it is right, and the confidence reads the same either way. Before acting on a claim from a subagent, verify it at the source — the doc page, the file, the command's real output — whenever the claim will become code, configuration, or an answer the user relies on. Cheap heuristics for which claims need checking: anything that contradicts what the code in front of you does; a version number, flag name, or field name you have not seen yourself; an API described but never quoted; a recommendation whose rationale the report does not show. Delegation moves the reading out of your context, not the responsibility for it. This is the same standard "Verify external references" in `code-quality.md` sets for third-party APIs, applied to the layer that now supplies most of the claims.
