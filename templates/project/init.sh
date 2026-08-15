#!/usr/bin/env bash
# Deploy the PER-PROJECT files of the dotclaude template into the current
# project.
#
# The reusable artifacts — hooks, agents, skills, rules, output-styles — are
# NOT deployed here: they live centrally in ~/.claude/ (installed from the
# dotclaude repo via install.sh) and the harness applies them to every project
# automatically. This script only writes what is specific to THIS project:
# CLAUDE.md, CHANGELOG.md, docs/, a minimal settings.json stub, .gitignore,
# the optional Serena + Graphify .mcp.json bundle, and optional infra scaffolds.
#
# Usage (run inside the target project directory):
#   bash ~/.claude/templates/project/init.sh [--serena] [--xcode] [--ui] [--update] [scaffold flags]
#
# Core flags:
#   --serena   Merge the serena + graphify servers into ./.mcp.json AND merge
#              Serena's drift-prevention hooks (serena-hooks.json) into the
#              project's .claude/settings.json — these make the model
#              deterministically prefer Serena's tools instead of drifting back
#              to Grep/Edit over a long session (oraios/serena #1201). The two
#              are companions: serena (symbol-level) + graphify (graph-level).
#              Exit 4 if the 'serena' binary is not in PATH; warns (non-fatal)
#              if 'graphify' is not in PATH. Both merges are idempotent and
#              non-destructive.
#   --xcode    Merge the 'xcode' server (Apple's own `xcrun mcpbridge`, shipped
#              with Xcode 26.3+) into ./.mcp.json. macOS-only: aborts with exit 5
#              on a non-Darwin host and exit 6 if `xcrun mcpbridge` is missing.
#              Note the server bridges into a RUNNING Xcode via XPC: Xcode must
#              be open with the project before Claude Code starts, or the server
#              shows as unavailable.
#   --ui       Merge the 'playwright' browser server (@playwright/mcp via npx)
#              into ./.mcp.json — gives the model eyes on the running app
#              (navigate, resize, screenshot) for the visual verification loop
#              the central /implement-ui skill drives. Exit 7 if 'npx' is not
#              in PATH (the server is fetched and launched through it).
#
#   Both MCP flags COMPOSE ./.mcp.json rather than copying it: each owns its own
#   server keys, so they combine in either order, re-run idempotently, and never
#   drop a server the user added by hand. See tests/mcp-merge-cases.py.
#   --update   Re-deploy mode. Per-project files are user-owned: CLAUDE.md,
#              CHANGELOG.md, docs/* and settings.json are only seeded when
#              absent, never overwritten. settings.local.json.example is
#              refreshed if untouched, drift-reported if edited. (There is no
#              hooks/agents/skills/rules drift here anymore — those are central;
#              update them with `git pull && ./install.sh` in the dotclaude repo.)
#   --db       Accepted for compatibility. The db-inspector agent is now central
#              (always available), so this no longer adds/removes an agent; the
#              skill may add psql/sqlite3 permissions to the project settings stub.
#
# Scaffold flags (generate infra files alongside — only on first deploy; never
# overwrite existing files):
#   --fullstack          mkdir backend, clients/web, scripts; write .env.example.
#   --runtime=<name>     Write Dockerfile (+ .dockerignore) for: node | python.
#   --compose            Write docker-compose.yml (app + Postgres db service).
#   --proxy=<name>       Write reverse-proxy config: caddy (nginx reserved).
#   --deploy-script      Write ./deploy.sh (mode driven by APP_MODE in .env).
#
# Exit codes:
#   0  success
#   1  template missing
#   3  RETIRED (was: --serena and ./.mcp.json conflict). .mcp.json is composed
#      per-server now, so there is no whole-file conflict to abort on. Do not
#      reuse this number: a project on an older init.sh still emits it.
#   4  --serena requested but the 'serena' binary is not in PATH
#   5  --xcode requested on a non-macOS host
#   6  --xcode requested but `xcrun mcpbridge` is unavailable (needs Xcode 26.3+)
#   7  --ui requested but 'npx' is not in PATH

set -euo pipefail

INSTALL_SERENA=false
INSTALL_XCODE=false
INSTALL_UI=false
FULLSTACK=false
RUNTIME=""
COMPOSE=false
PROXY=""
DEPLOY_SCRIPT=false
for arg in "$@"; do
  case "$arg" in
    --serena)         INSTALL_SERENA=true ;;
    --xcode)          INSTALL_XCODE=true ;;
    --ui)             INSTALL_UI=true ;;
    --update)         : ;;  # informational: seeding always skips existing files
    --db)             : ;;  # accepted, no-op (db-inspector is central now)
    --fullstack)      FULLSTACK=true ;;
    --runtime=*)      RUNTIME="${arg#--runtime=}" ;;
    --compose)        COMPOSE=true ;;
    --proxy=*)        PROXY="${arg#--proxy=}" ;;
    --deploy-script)  DEPLOY_SCRIPT=true ;;
    *)                echo "WARN: ignoring unknown flag $arg" >&2 ;;
  esac
done

# Helper: compose ./.mcp.json from per-server fragments in templates/project/mcp/.
# The file is COMPOSED, never copied: each flag owns its own server keys and must
# leave every other key alone — including servers the template knows nothing
# about (a hand-added playwright, a third-party server). Merging by key is also
# what makes re-runs idempotent and the flags order-independent.
#
# It replaced a `cp` + whole-file `cmp` for --serena, which aborted (exit 3) as
# soon as ./.mcp.json differed from the template by even one key — so --xcode and
# --serena could not coexist, and a user's own server was silently dropped. See
# tests/mcp-merge-cases.py for the cases that pin this.
#
# Usage: merge_mcp_servers <fragment.json> [...]  — JSON via python3, never jq
# (DESIGN.md §5). Never fatal: a broken .mcp.json warns and the deploy continues.
merge_mcp_servers() {
  # Fragments travel as argv, not a whitespace-split env var: a $HOME with a
  # space broke every fragment path and degraded silently to the WARN path.
  if python3 - "$@" <<'PY'
import json, os, sys

dst = "./.mcp.json"
fragments = sys.argv[1:]

if os.path.exists(dst):
    try:
        with open(dst) as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        print("  ! ./.mcp.json exists but is not readable JSON (%s) — merge the" % e, file=sys.stderr)
        print("    server fragments manually from the template's mcp/ directory", file=sys.stderr)
        sys.exit(1)
else:
    cfg = {}

servers = cfg.setdefault("mcpServers", {})
added, updated, skipped = [], [], []

for frag_path in fragments:
    with open(frag_path) as fh:
        for name, spec in json.load(fh).items():
            if servers.get(name) == spec:
                skipped.append(name)
            elif name in servers:
                servers[name] = spec
                updated.append(name)
            else:
                servers[name] = spec
                added.append(name)

if added or updated:
    try:
        with open(dst, "w") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
    except OSError as e:
        print("  ! could not write %s (%s)" % (dst, e), file=sys.stderr)
        sys.exit(1)

for label, names in (("merged", added), ("updated", updated), ("skip", skipped)):
    if names:
        print("  - %s: %s in %s" % (label, ", ".join(sorted(names)), dst), file=sys.stderr)
PY
  then
    return 0
  fi
  echo "WARN: could not compose ./.mcp.json; deploy continues. Merge the server" >&2
  echo "      fragments manually from $TEMPLATE_DIR/mcp/" >&2
  return 0
}

# Helper: copy a file into the project only if the destination does not already
# exist. Re-runs and existing files are always preserved.
seed_copy() {
  local src="$1" dst="$2"
  if [ -e "$dst" ]; then
    echo "  - skip: $dst (already exists)" >&2
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  echo "  - wrote: $dst" >&2
}

TEMPLATE_DIR="${TEMPLATE_DIR:-$HOME/.claude/templates/project}"
SRC_CLAUDE="$TEMPLATE_DIR/.claude"
DST_CLAUDE="./.claude"

if [ ! -d "$TEMPLATE_DIR" ]; then
  echo "ERROR: template not found at $TEMPLATE_DIR (run install.sh from the dotclaude repo)" >&2
  exit 1
fi

# --- Per-project .claude/ : only the project-specific files ------------------
mkdir -p "$DST_CLAUDE"

# settings.json: a per-project stub (the base config is central). Seed only if
# absent — never overwrite the user's project-specific permissions.
seed_copy "$SRC_CLAUDE/settings.json" "$DST_CLAUDE/settings.json"

# settings.local.json.example: documentary. Refresh if untouched, drift if edited.
if [ -f "$SRC_CLAUDE/settings.local.json.example" ]; then
  ex_dst="$DST_CLAUDE/settings.local.json.example"
  if [ ! -f "$ex_dst" ]; then
    cp "$SRC_CLAUDE/settings.local.json.example" "$ex_dst"
  elif ! cmp -s "$SRC_CLAUDE/settings.local.json.example" "$ex_dst"; then
    echo "DRIFT: .claude/settings.local.json.example (template updated; your edits kept)" >&2
  fi
fi

# --- CLAUDE.md, CHANGELOG.md : user-owned, seed when absent -------------------
[ -f ./CLAUDE.md    ] || cp "$TEMPLATE_DIR/CLAUDE.md.template"    ./CLAUDE.md
[ -f ./CHANGELOG.md ] || cp "$TEMPLATE_DIR/CHANGELOG.md.template" ./CHANGELOG.md

# --- docs/ : portable contract surface, seed each file when absent -----------
if [ -d "$TEMPLATE_DIR/docs" ]; then
  mkdir -p ./docs
  for f in "$TEMPLATE_DIR"/docs/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    [ -f "./docs/$name" ] || cp "$f" "./docs/$name"
  done
fi

# --- .gitignore : merge template entries in (or seed if absent) --------------
# APPEND, never sort. Order is semantic in .gitignore: a negation (`!x`) only
# re-includes when it comes AFTER the pattern that excluded it. `sort -u`
# reorders by bytes and hoists negations above their parents — verified with
# real git under LC_ALL=C: both the template's own `!.env.example` and a user's
# `!keep.log` ended up ignored. Appending only the missing lines keeps every
# negation behind its parent and preserves the user's comments and grouping.
if [ -f ./.gitignore ]; then
  if ! grep -qxF "# --- dotclaude template ---" ./.gitignore; then
    printf '\n# --- dotclaude template ---\n' >> ./.gitignore
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    # `--` so a template line starting with '-' is a pattern, not grep options.
    grep -qxF -- "$line" ./.gitignore || printf '%s\n' "$line" >> ./.gitignore
  done < "$TEMPLATE_DIR/.gitignore.template"
else
  cp "$TEMPLATE_DIR/.gitignore.template" ./.gitignore
fi

# --- Serena + Graphify MCP (opt-in) ------------------------------------------
# Both servers deploy together (they are companions: Serena = symbol-level,
# Graphify = graph-level). Serena is required (abort if missing);
# Graphify is a soft prerequisite (warn only) because its MCP server is
# secondary — it starts only after a graph is built (/graphify .) and fails
# inertly otherwise, without affecting Serena.
if [ "$INSTALL_SERENA" = "true" ]; then
  if ! command -v serena >/dev/null 2>&1; then
    echo "ERROR: 'serena' binary not found in PATH." >&2
    echo "       Install once per machine with:" >&2
    echo "         uv tool install -p 3.13 serena-agent@latest --prerelease=allow" >&2
    echo "       (Requires uv: curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
    exit 4
  fi
  if ! command -v graphify >/dev/null 2>&1; then
    echo "WARN: 'graphify' not found in PATH — the bundled graphify MCP server" >&2
    echo "      will be unavailable until you install it and build a graph:" >&2
    echo "        uv tool install graphifyy" >&2
    echo "        then run '/graphify .' once to build graphify-out/graph.json." >&2
    echo "      Serena still works; this is non-fatal." >&2
  else
    # Graphify present: install its git post-commit/post-checkout hooks so the
    # graph auto-rebuilds (AST-only, no API cost) and never goes stale — a stale
    # graph is the main reason the graph-first workflow gets abandoned. We do NOT
    # run 'graphify install'/'graphify claude install': those append a raw block
    # to CLAUDE.md and a per-project skill that duplicate what the template + the
    # central prefer-graphify hook already provide. The graph itself is still
    # built by '/graphify .' (run it once); the hooks only keep it fresh after.
    if graphify hook install >/dev/null 2>&1; then
      echo "  - graphify git hooks installed (graph auto-rebuilds on commit/checkout)"
    else
      echo "  ! graphify hook install failed (non-fatal); run 'graphify hook install' manually" >&2
    fi
  fi
  # Serena and Graphify are companions and always deploy together.
  merge_mcp_servers "$TEMPLATE_DIR/mcp/serena.json" "$TEMPLATE_DIR/mcp/graphify.json"

  # Merge Serena's drift-prevention hooks into the project's settings.json.
  # These are what make the model deterministically prefer Serena's tools over
  # Grep/Edit instead of drifting back over a long session (oraios/serena #1201).
  # We MERGE rather than overwrite so any project-specific hooks/permissions in
  # the stub survive, and we de-duplicate by command so re-running --serena is
  # idempotent. We parse JSON with python3, never jq (DESIGN.md §5). 'serena'
  # is already confirmed in PATH above (exit 4 otherwise), so 'serena-hooks'
  # ships alongside it — the hooks will resolve at runtime.
  if [ -f "$SRC_CLAUDE/serena-hooks.json" ]; then
    # A merge failure must not abort the deploy (.mcp.json is already written),
    # so run the heredoc under `if` (which neutralizes `set -e` for this command)
    # and turn a non-zero exit into a non-fatal WARN.
    if SERENA_HOOKS_SRC="$SRC_CLAUDE/serena-hooks.json" \
       SETTINGS_DST="$DST_CLAUDE/settings.json" \
       python3 - <<'PY'
import json, os, sys

src = os.environ["SERENA_HOOKS_SRC"]
dst = os.environ["SETTINGS_DST"]

with open(src) as f:
    # {{HOOK_EXT}} resolves to the OS hook form: 'sh' here, 'ps1' in init.ps1.
    # serena-hooks.json stays OS-agnostic; only the merge picks the concrete script.
    raw = f.read().replace("{{HOOK_EXT}}", "sh")
hook_block = json.loads(raw)["hooks"]

try:
    with open(dst) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

hooks = settings.setdefault("hooks", {})

def cmds(group_list):
    out = set()
    for g in group_list:
        for h in g.get("hooks", []):
            if "command" in h:
                out.add(h["command"])
    return out

changed = False
for event, groups in hook_block.items():
    existing = hooks.setdefault(event, [])
    have = cmds(existing)
    for group in groups:
        new_cmds = cmds([group])
        if new_cmds and new_cmds.issubset(have):
            continue  # already present — keep idempotent
        existing.append(group)
        have |= new_cmds
        changed = True

if changed:
    try:
        with open(dst, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
    except OSError as e:
        # Don't abort the whole deploy: .mcp.json is already written. Surface a
        # warning so the user can add the hooks manually, and exit non-zero so
        # the caller's `|| ...` guard turns this into a WARN rather than a fatal.
        print("  ! could not write Serena hooks into %s (%s) — add them manually from serena-hooks.json" % (dst, e), file=sys.stderr)
        sys.exit(1)
    print("  - merged: Serena drift-prevention hooks into %s" % dst, file=sys.stderr)
else:
    print("  - skip: Serena hooks already present in %s" % dst, file=sys.stderr)
PY
    then
      :  # merge succeeded (the heredoc already printed merged/skip)
    else
      echo "WARN: Serena hook merge did not complete; deploy continues. Add the hooks manually from serena-hooks.json." >&2
    fi
  fi
fi

# --- Xcode MCP (opt-in, macOS only) ------------------------------------------
# Apple's own MCP server, shipped with Xcode 26.3+ as `xcrun mcpbridge`. It is a
# STDIO bridge that connects over XPC to a RUNNING Xcode process — there is no
# standalone mode, so Xcode must be open with the project before Claude Code
# starts or the server simply shows as unavailable (same shape as the graphify
# server being inert until a graph exists).
if [ "$INSTALL_XCODE" = "true" ]; then
  if [ "$(uname -s)" != "Darwin" ]; then
    echo "ERROR: --xcode is macOS-only (Apple's mcpbridge ships with Xcode)." >&2
    echo "       Host reports: $(uname -s)" >&2
    exit 5
  fi
  # `xcrun mcpbridge` is the real capability probe: xcrun exists on every Mac
  # with the Command Line Tools, but mcpbridge only from Xcode 26.3.
  if ! xcrun --find mcpbridge >/dev/null 2>&1; then
    echo "ERROR: 'xcrun mcpbridge' not available — needs Xcode 26.3 or later." >&2
    echo "       Check the selected toolchain with: xcode-select -p" >&2
    echo "       Then enable MCP in Xcode > Settings > Intelligence." >&2
    exit 6
  fi
  merge_mcp_servers "$TEMPLATE_DIR/mcp/xcode.json"
fi

# --- Playwright MCP (opt-in) --------------------------------------------------
# Browser eyes for UI work: navigate, resize and screenshot the running app so
# the model can compare its output against a design reference and iterate (the
# loop the central /implement-ui skill drives). npx fetches @playwright/mcp on
# demand, so the only host prerequisite is npx itself.
if [ "$INSTALL_UI" = "true" ]; then
  if ! command -v npx >/dev/null 2>&1; then
    echo "ERROR: 'npx' not found in PATH — the playwright MCP server launches via npx." >&2
    echo "       Install Node.js (which ships npx) and re-run." >&2
    exit 7
  fi
  merge_mcp_servers "$TEMPLATE_DIR/mcp/playwright.json"
fi

# --- Optional scaffolding ----------------------------------------------------
SCAFFOLDS="$TEMPLATE_DIR/scaffolds"

if [ "$FULLSTACK" = "true" ]; then
  mkdir -p backend clients/web scripts
  seed_copy "$SCAFFOLDS/env.example.template" ./.env.example
fi

if [ -n "$RUNTIME" ]; then
  case "$RUNTIME" in
    node)   seed_copy "$SCAFFOLDS/Dockerfile.node"   ./Dockerfile ;;
    python) seed_copy "$SCAFFOLDS/Dockerfile.python" ./Dockerfile ;;
    *)      echo "WARN: unknown --runtime=$RUNTIME, skipping Dockerfile." >&2 ;;
  esac
  # A Dockerfile without a .dockerignore leaks .env/.git/node_modules into the
  # image via COPY . . — write one alongside it (only if absent).
  case "$RUNTIME" in
    node|python) seed_copy "$SCAFFOLDS/dockerignore.template" ./.dockerignore ;;
  esac
fi

if [ "$COMPOSE" = "true" ]; then
  seed_copy "$SCAFFOLDS/docker-compose.yml.template" ./docker-compose.yml
fi

if [ -n "$PROXY" ]; then
  case "$PROXY" in
    caddy) seed_copy "$SCAFFOLDS/Caddyfile.template" ./Caddyfile ;;
    nginx) echo "WARN: --proxy=nginx scaffold not yet implemented; Caddyfile only on day 1." >&2 ;;
    *)     echo "WARN: unknown --proxy=$PROXY, skipping reverse-proxy config." >&2 ;;
  esac
fi

if [ "$DEPLOY_SCRIPT" = "true" ]; then
  seed_copy "$SCAFFOLDS/deploy.sh.template" ./deploy.sh
  chmod +x ./deploy.sh 2>/dev/null || true
fi

echo "init.sh: deploy OK"
