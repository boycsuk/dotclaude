---
name: compound
description: Captures a learning from the current session (a mistake, an applied rule, a discovered pattern) and codifies it in the right place of the system. Use when the user invokes /compound, or proactively when the user corrects something systematic that should persist across sessions. Proposes the change for confirmation before editing anything.
---

# Compound

A session has produced a learning. Your job: turn it into infrastructure so it does not get lost.

## 1. Identify the learning

Ask yourself (and the user if needed):
- What happened that should not have happened, or that worked better than expected?
- Is it **general** (applies to future tasks) or **local** (only this case)?

If it is local, **stop** — it does not deserve codification.

## 2. Decide where it goes

| Type of learning | Destination |
|---|---|
| Advisory rule ("prefer X over Y", "module A must not Z") | `CLAUDE.md` section `Don't` or `Conventions` |
| Extensive convention (full topic with multiple rules) | New file in `.claude/rules/<topic>.md` |
| Convention that only applies to certain file types (code style, a language idiom) | A `.claude/rules/<topic>.md` with a `paths:` glob in frontmatter, so it loads only for matching files instead of every session |
| Repeatable procedure (how to deploy, review, generate tests, etc.) | `.claude/skills/<name>/SKILL.md` |
| Tone / language / response-format convention ("answer in Spanish", "no emojis", "always lead with a diagram") | A `.claude/output-styles/<name>.md` (system-prompt level, main conversation only — subagents run their own system prompt and do not inherit it) — enable via `outputStyle`, and set `keep-coding-instructions: true` in the frontmatter for a coding project, since the default strips Claude Code's software-engineering instructions |
| Non-negotiable guarantee (must always pass) | `.claude/hooks/<name>.{sh,ps1}` + entry in `.claude/settings.json` |
| Knowledge that needs isolation to avoid contaminating context | `.claude/agents/<name>.md` |

Mental rule:
- **Information** → CLAUDE.md or rules/ (scope to file types with `paths:` when it only applies to some)
- **Procedure** → Skill
- **Tone / format** → Output style
- **Guarantee** → Hook
- **Isolation** → Subagent

**If the learning lands in a rules file (or a coding convention in CLAUDE.md):** also reflect it in `docs/conventions.md` — the repo-versioned canonical copy that every contributor and non-Claude tool reads. The rules file is the copy Claude Code loads; when the two diverge, reconcile by hand (neither takes precedence). Skipping the sync re-opens the exact gap `conventions.md` exists to close.

## 3. Propose the change

Generate the concrete patch:
- For CLAUDE.md / rules: show the exact lines/section to add, with the **why** included.
- For a skill: show the full file with frontmatter.
- For a hook: show the script content + the entry to add in settings.json.

**Do not edit yet.** Present the patch and confirm via `AskUserQuestion` with options like **Apply** / **Adjust destination** / **Discard**. If step 2 left the destination ambiguous between two rows, offer the candidates the same way instead of picking silently.

## 4. Apply and commit

After confirmation:
- Edit the corresponding file.
- Suggest committing whatever file you edited — `CLAUDE.md`, `docs/conventions.md` and anything under `.claude/` are all part of the project, not transient work. Use `/commit`; it handles the CHANGELOG.

## 5. Verify

Remind the user to test in a new session that the learning applies automatically — without having to repeat it manually. If it does not apply, the rule is not well formulated — iterate.

## 6. Consider promoting to the dotclaude master repo

If the learning applies to **all future projects** (not just this one), suggest promoting it to the dotclaude repo — **not** to `~/.claude/`, which `guard-central-config` blocks and `install.sh` overwrites on every run:

- Reusable artifacts (skills, hooks, rules, agents, output styles) → `global/.claude/`. These are central: they apply to every project automatically.
- Per-project surface (the CLAUDE.md template, `docs/`, scaffolds) → `templates/project/`.

Then: atomic commit, push, and `git pull && ./install.sh` on each machine — that is what propagates the change to every project at once.
