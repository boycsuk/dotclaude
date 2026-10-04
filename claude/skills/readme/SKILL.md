---
name: readme
description: Writes or refreshes the project's root README.md to a professional, public-repo standard — reads like a maintainer wrote it, not a model. Covers structure (quickstart first), what to omit (internal tooling, secrets, AI attribution), and an explicit ban list of AI-writing tells. Use when the user asks for a README, wants to publish a repo, or after changes that make the existing README stale (new commands, renamed flags, changed install steps).
effort: high
allowed-tools: Bash(git log:*) Bash(git remote:*) Bash(ls *) Glob Grep Read Edit Write
---

# README

Write the root `README.md` the way a careful human maintainer would: for the stranger who lands on the repo and decides in thirty seconds whether it solves their problem. This file is the project's front door — for many readers, the only page they will ever see.

This is NOT `docs/README.md` (the internal index of the contract docs) — do not confuse the two, and never merge them.

## 1. Establish the facts first — a README states, it does not guess

Before writing a word:

- Read the manifest (`package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod`) for the real name, version, commands and entry points.
- Read the existing README if there is one — a refresh preserves the maintainer's voice and structure where they still hold.
- **Every command you write must be copy-pasteable and true.** Take install/run/test commands from the manifest's scripts, not from memory of how such projects usually work. If you cannot verify a command exists, do not print it.
- Check what the project actually requires (runtime version, system deps, env vars) from lockfiles, engines fields, and `.env.example` — never from `.env`.

## 2. Structure — inverted pyramid, quickstart early

Readers scan top to bottom and bail the moment they lose the thread. Most-needed information first; each later section serves a smaller, more committed audience. Target 800–1500 words; scannability beats completeness.

1. **`# Project name`** — one H1, then one or two sentences saying **what it does** for whom (not "what it is": "converts X to Y without Z" beats "a modern framework for...").
2. **Why** — the problem it solves and, when honest and useful, how it differs from the obvious alternative. Two or three sentences, no more.
3. **Quickstart** — within the first 200 words: the shortest real path from clone to seeing it work. One code block, copy-pasteable.
4. **Installation** — requirements (runtime version, system deps) and the package-manager command.
5. **Usage** — two or three concrete examples of the most common real cases, with expected output where it fits. Not an API reference; link out for that.
6. **Configuration** — if it applies: a table of env vars / flags with name, purpose and default. Names only, never values.
7. **Contributing** — how to run tests and what a good PR looks like, or a link to CONTRIBUTING.md. Only if contributions are actually wanted.
8. **License** — always, one line.

Optional, each only when it earns its place: up to 4 *functional* badges (build, version, license — not decoration); a screenshot or GIF for anything with a UI; a small Mermaid diagram when architecture genuinely aids understanding. A table of contents only past ~1500 words.

## 3. What a public README must NOT contain

Review against this list before showing the draft — these are the leaks that make a repo look unprofessional or expose things that are nobody's business:

- **Internal tooling and process**: no mention of CLAUDE.md, `.claude/`, dotclaude, hooks, skills, agents, internal conventions docs, or how the maintainer's AI setup works. The reader cares what the project does, not how it was developed.
- **AI attribution**: no "built with Claude/ChatGPT", no "AI-generated", no model names in prose. Same rule as commit trailers.
- **Secrets and near-secrets**: no env var *values*, tokens, internal hostnames, private URLs, ports of internal services, or real emails beyond the license/contact the user chooses.
- **Personal information**: no full names, no machine paths (`/home/...`), no local usernames leaking through example output.
- **The development story**: no changelog-in-prose ("recently refactored to..."), no TODO lists or roadmap-of-shame, no apologies about code quality. CHANGELOG.md exists for history.
- **Aspirational claims**: no features that do not exist yet, no "coming soon". A README describes the present.

## 4. Write like a person — the anti-slop contract

AI-written READMEs have recognisable tells, and readers discount the whole project when they spot them. Hard bans:

- **No emoji** in headings or as bullet decorations. No 🚀, no ✨, no emoji feature-lists. (Repo rule anyway; doubly so here.)
- **No hype adjectives**: blazingly / lightning fast, powerful, seamless, robust, cutting-edge, comprehensive, elegant, effortless, supercharge, revolutionize. If performance matters, give a number; if there is no number, drop the claim.
- **No AI-vocabulary**: delve, leverage, showcase, foster, bolster, underscore, pivotal, crucial, meticulous, "serves as", "is designed to", "aims to". Say what it *does*.
- **No formulaic constructions**: "not just X, but Y"; "whether you're A or B"; adjective-adjective-adjective triplets; a "Challenges"/"Limitations" section written as filler.
- **Restraint in formatting**: sentence-case headings (not Title Case), bold only for genuine emphasis (rarely), straight quotes, em dashes sparingly, paragraphs of *varied* length — uniform blocky paragraphs read as generated.
- **No filler sections**: if there is nothing real to say under a heading, the heading goes. An eight-line README that is all true beats a forty-line one that is half padding.
- **Concrete over abstract**: every sentence should survive the question "could this sentence describe any project?" If yes, rewrite or delete it.

## 5. Propose, then write

Show the draft (or the diff, on a refresh) and confirm via `AskUserQuestion` — **Write it** / **Adjust** / **Discard** — before touching the file. On a refresh, list what you changed and why in one line per change ("quickstart updated: `npm start` no longer exists, script is `npm run dev`").

Public repos are in English (the repo convention: everything inside the codebase in English). If the project is deliberately local-audience, ask.

## 6. Keeping it true

A README is undone the moment it drifts from reality — an outdated one actively misleads. On any invocation over an existing README, diff its claims against the repo before editing: do the commands still exist, are the flags still real, do the examples still run, is the structure section still the actual structure? Fix silently-stale facts even when the user only asked for a cosmetic change, and say you did.

## 7. Where these rules come from

Checked against the public prior art in 2026-08. Two of the rules above were arrived at independently by others, which is the main reason to trust them:

- **"State, don't guess" (§1) and "keep it true" (§6)** match the *API Drift Protocol* in [adewale/good-readme](https://github.com/adewale/good-readme) — "treat README examples, previous docs, and model memory as suspect until checked against current source and manifests". That skill is the most rigorous of the public ones: a 22-criterion rubric, 15 catalogued anti-patterns, and an `evals/` suite with ablations. Worth reading before extending this file.
- **The anti-slop contract (§4)** matches [yetone/kill-ai-slop](https://github.com/yetone/kill-ai-slop) (~1k stars), which catalogues 33 markers of machine-made output. Its argument is the one to keep in mind: these patterns are "so common you've stopped seeing it". Emoji-led headings (`📦 Installation`, `🚀 Usage`) now read as template and low effort, not as friendliness. Maintainers say so directly — see [Ask HN: Do you feel reading AI generated readme tiring?](https://news.ycombinator.com/item?id=48003871), where the recurring complaint is repetitive *structure*, not bad prose.

**The leak list (§3) has no public counterpart.** None of the surveyed skills — [good-readme](https://github.com/adewale/good-readme), [yamz8/readme-skill](https://github.com/yamz8/readme-skill), [dmccreary/claude-skills](https://github.com/dmccreary/claude-skills/tree/main/skills/readme-generator) — mentions internal tooling, AI attribution, machine paths or aspirational claims. It is specific to publishing from a setup like this one, so do not expect prior art to validate it.

**Known gap:** every rule here is written by judgement, with nothing measuring whether it earns its place. `good-readme` ablates its rules against fixtures; this file does not. If the skill starts producing READMEs that miss, build the fixture before rewriting the rule.
