---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs,cjs,py,pyi,rs,go,java,kt,kts,rb,php,c,h,cc,cpp,cxx,hpp,hh,cs,swift,scala,clj,ex,exs,erl,hs,ml,sql,vue,svelte,sh,bash,ps1,html}"
---
<!--
  Loaded when Claude reads a source file matching paths: above. There is no
  description: key — it is inert for rules (only Skills act on it). Security is
  transversal, so the glob covers all code rather than just backend/auth:
  narrowing it would silently skip files that touch I/O. Caveat: path-scoped
  rules fire on Read, not on file *creation* — see anthropics/claude-code#23478.
-->

# Security

> Review with the same or more rigor than human-written code. Run `/audit` (Security category, Uncommitted-changes scope) before merging anything that touches I/O, auth, or dependencies.

## Secure code

### Validate at system boundaries
All external input (user, APIs, files, environment variables) is validated and sanitized before use. Do not trust data from outside the system.

### Prevent injections
Never concatenate strings to build SQL queries, shell commands, or HTML. Use parameterized queries, escape APIs, or safe templates.

### Authorize every access, deny by default
Every server-side operation verifies that the authenticated user may act on the *specific* resource requested (record ownership) — never trust IDs coming from the client (IDOR). Unless a resource is explicitly public, deny by default. If the server fetches URLs derived from user input, validate them against an allowlist of hosts/schemes (SSRF).

### Principle of least privilege
Each component only has access to what it needs. Do not grant broad permissions "for convenience".

### Do not expose internal information in errors
User-facing error messages must not reveal stack traces, system paths, dependency versions, or internal structure. Log the detail server-side, return a generic message client-side.

### Constant-time comparisons for sensitive values
Compare tokens, hashes, or secrets with secure functions (`hmac.compare_digest`, `crypto.timingSafeEqual`). A normal `==` comparison allows timing attacks.

### Do not implement custom cryptography
Always use established libraries (libsodium, ring, OpenSSL, the language standard library). Homegrown algorithms are almost always vulnerable.

### Validate before deserializing untrusted data
Prefer data-only formats (JSON) over formats that instantiate objects from arbitrary classes. Validate the schema before any deserialization step.

### Prevent race conditions (TOCTOU)
If a check and its action must be inseparable, use atomic operations or locks. State can change between the check and the action.

## Dependencies

### Audit regularly
Use ecosystem tools to detect known vulnerabilities:
- `cargo audit` (Rust)
- `npm audit` (Node)
- `pip-audit` (Python)
- `govulncheck` (Go)

### Minimize dependencies
Every dependency is attack surface. Do not add packages for trivial things that can be solved with a few lines of code.

### Pin versions
Use lockfiles and exact versions to avoid unexpected updates that introduce vulnerabilities or break the build.

### Clean up before release
Remove dead code, test features, and test credentials before any release.

## Runtime

### Do not trust the client
All security validation happens on the server/backend. Frontend validations are UX only, not security.

### Limit resources
Timeouts on external calls, size limits on inputs, rate limiting where applicable. Do not let malicious input consume resources indefinitely.

### Secrets only in memory or secure managers
Never hardcode credentials, API keys, or tokens in source or committed config — load them from environment variables or a secret manager. Never log secrets, never serialize credentials, never pass them via URL query parameters.

### Uploaded files
Validate by header (magic bytes), not by extension. Disable execution permissions on upload directories.

### Secure logs
Do not log sensitive data. Sanitize inputs before writing them to logs to prevent log injection (CRLF, escape sequences).
