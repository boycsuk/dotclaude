---
name: verify
description: Runs the project's full verification chain — tests, typecheck, and linter — over the whole project to confirm a code task is actually complete. Runs the commands the project's CLAUDE.md declares, auto-detecting the stack for the rest. Use before closing any code task, and whenever the user asks to verify, validate, or check that changes pass. Complements the per-edit verify-on-edit hook, which only lints/typechecks single files; this also runs the test suite.
allowed-tools: Bash(npm *) Bash(pnpm *) Bash(yarn *) Bash(bun *) Bash(python *) Bash(python3 *) Bash(pytest *) Bash(ruff *) Bash(mypy *) Bash(uv *) Bash(poetry *) Bash(cargo *) Bash(go *) Bash(make *) Bash(mvn *) Bash(./mvnw *) Bash(gradle *) Bash(./gradlew *) Bash(dotnet *) Bash(bundle *) Bash(swift *) Glob Read
model: haiku
context: fork
background: false
---

# Verify

Before marking a task as done, run the project's verification chain.

> `context: fork` runs this in a subagent, so `model: haiku` applies to the mechanical run (find the commands → run them → report) instead of downgrading the rest of the caller's turn, and the test output stays out of the main context. You REPORT the outcome; the caller's session fixes what failed with its own model.

## 1. Read the declared commands

Read `CLAUDE.md` at the project root with the **Read tool**. In template-derived projects its `## WHAT — Commands` section has lines like ``- Test: `pytest` ``, ``- Lint: `…` `` and ``- Typecheck: `…` `` (filled by `/init-project`). A line counts only if its command is neither `<not configured>` nor a `{{PLACEHOLDER}}`.

For each of typecheck, lint and test that has a declared command, run exactly that command — it overrides both the Makefile and the stack defaults below. Use stack detection (steps 2-3) only for the steps with no declared command, or for all of them when there is no `CLAUDE.md` or no such section.

## 2. Detect the stack

Use the **Glob tool** (portable across Unix and Windows; `ls ... 2>/dev/null` is not) to see which manifests and lockfiles are present at the project root:

```
Glob: {package.json,pnpm-lock.yaml,yarn.lock,bun.lock,bun.lockb,pyproject.toml,requirements.txt,uv.lock,poetry.lock,Cargo.toml,go.mod,pom.xml,mvnw,build.gradle,build.gradle.kts,gradlew,*.sln,*.csproj,*.fsproj,Gemfile,.rspec,Rakefile,Package.swift,Makefile}
```

## 3. Run the appropriate commands

Run **in this order** if they exist for the detected stack. Use the runner the lockfile names — a project on pnpm/bun often has no working `npm`:

**Node / TypeScript** (`package.json`): `pnpm-lock.yaml` → `pnpm`, `yarn.lock` → `yarn`, `bun.lock`/`bun.lockb` → `bun`, otherwise `npm`.
- `<pm> run typecheck` (or `npx --no-install tsc --noEmit` / `bunx --no-install tsc --noEmit` if there is no script — without `--no-install`, npx in a non-interactive shell downloads and runs whatever registry package answers to `tsc`)
- `<pm> run lint`
- `<pm> test`

**Python** (`pyproject.toml` / `requirements.txt`): if `uv.lock` exists prefix every command with `uv run`; if `poetry.lock` exists, `poetry run`.
- `ruff check .` (only if ruff is available and a `pyproject.toml` / `ruff.toml` / `.ruff.toml` configures it)
- `mypy .` (only if `[tool.mypy]` is configured)
- `pytest`

**Rust** (`Cargo.toml`):
- `cargo clippy -- -D warnings`
- `cargo test`

**Go** (`go.mod`):
- `go vet ./...`
- `go test ./...`

**Java / Kotlin, Maven** (`pom.xml`): `./mvnw -q test` if `mvnw` exists, otherwise `mvn -q test`.

**Java / Kotlin, Gradle** (`build.gradle` / `build.gradle.kts`): `./gradlew test` if `gradlew` exists, otherwise `gradle test`.

**.NET** (`*.sln` / `*.csproj` / `*.fsproj`):
- `dotnet build`
- `dotnet test`

**Ruby** (`Gemfile`):
- `bundle exec rspec` if `.rspec` exists or Glob `spec/**/*_spec.rb` matches; otherwise `bundle exec rake test` if a `Rakefile` exists.

**Swift** (`Package.swift`):
- `swift build`
- `swift test`

**Makefile present**: for each step the Makefile covers, run the make target INSTEAD of the raw stack command; run the stack command only for steps with no target. Check a target exists with `make -n <target>` (exit 0 = it exists) before running it — a `No rule to make target` is not a verification failure.

## 4. Report

- **All pass**: confirm explicitly: "Verification passed: typecheck + lint + tests."
- **Something fails**: report exactly what failed, with the tool's own error output. Do NOT mark the task as done — and do not fix it here; the caller's session applies fixes with its own model.
- **Tool not installed or not configured**: that is neither a pass nor a failure. Say which step could not run and why ("ruff not on PATH", "no lint script"), then report on the steps that did run.
- **Nothing detectable**: say so explicitly: "No tests/lint configured — cannot verify mechanically."

## Reminder

Tests passing does not mean the feature works. If you touched UI or any observable behaviour, confirm it against the real app (the bundled `/run` skill launches it) before closing. If you touched I/O, test the failure paths.
