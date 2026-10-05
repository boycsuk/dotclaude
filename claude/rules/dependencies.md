---
paths:
  - "**/package.json"
  - "**/package-lock.json"
  - "**/pnpm-lock.yaml"
  - "**/yarn.lock"
  - "**/bun.lockb"
  - "**/bun.lock"
  - "**/Cargo.toml"
  - "**/Cargo.lock"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
  - "**/uv.lock"
  - "**/poetry.lock"
  - "**/go.mod"
  - "**/go.sum"
  - "**/Gemfile"
  - "**/Gemfile.lock"
  - "**/composer.json"
  - "**/composer.lock"
  - "**/*.csproj"
  - "**/pom.xml"
  - "**/build.gradle*"
---
<!--
  Loaded when Claude reads a dependency manifest or lockfile matching paths:
  above. There is no description: key — it is inert for rules (only Skills act
  on it). Split out of security.md so the source-file glob does not carry it
  into every code read; its glob is its own, so check.py's comparison of the
  code-quality/security extension lists does not apply here. The
  guard-dependencies hook asks before any command or manifest edit that adds a
  dependency, whether or not this rule is loaded — this rule is the why, the
  hook the guarantee. Caveat: path-scoped rules fire on Read, not on file
  *creation* — see anthropics/claude-code#23478.
-->

# Dependencies

## Minimize dependencies
Every dependency is attack surface. Do not add packages for trivial things that can be solved with a few lines of code. The `guard-dependencies` hook asks the user before any command or manifest edit that adds one.

## Pin versions
Use lockfiles and exact versions to avoid unexpected updates that introduce vulnerabilities or break the build.

## Audit regularly
Use ecosystem tools to detect known vulnerabilities:
- `cargo audit` (Rust)
- `npm audit` (Node)
- `pip-audit` (Python)
- `govulncheck` (Go)
