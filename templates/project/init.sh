#!/usr/bin/env bash
# Deploy the PER-PROJECT files of the dotclaude template into the current
# project.
#
# The reusable artifacts — hooks, agents, skills, rules, output-styles — are
# NOT deployed here: they live centrally in ~/.claude/ (installed from the
# dotclaude repo via install.sh) and the harness applies them to every project
# automatically. This script only writes what is specific to THIS project:
# CLAUDE.md, CHANGELOG.md, docs/, a minimal settings.json stub, .gitignore,
# optional .mcp.json servers, and optional infra scaffolds. Every run also
# prunes hook entries dotclaude no longer ships (obsolete.json).
#
# Usage (run inside the target project directory):
#   bash ~/.claude/templates/project/init.sh [--xcode] [--ui] [--codebase-memory] [--lsp=<plugin>] [--update] [scaffold flags]
#
# Core flags:
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
#   --codebase-memory  Merge the 'codebase-memory-mcp' server (DeusData's
#              persistent code graph: callers, impact of a change, dead code,
#              architecture) into ./.mcp.json and its READ-ONLY tool names into
#              .claude/settings.json permissions.allow. Exit 8 if the binary is
#              not in PATH. Binary only: never run its own `install`
#              subcommand, which rewrites ~/.claude/settings.json hooks.
#   --lsp=<plugin>  Install an official LSP plugin (lsp-plugins.json, e.g.
#              pyright-lsp) at PROJECT scope via `claude plugin install
#              --scope project`, which also records it in .claude/settings.json
#              so teammates see it. Repeatable for polyglot repos. Never fatal:
#              a missing language-server binary, a missing `claude` CLI or an
#              unknown plugin name each print a WARN with the fix. (Listing the
#              plugin in enabledPlugins alone does NOT load it — verified: an
#              uninstalled plugin stays off until installed.)
#   --update   Informational: marks a re-deploy, but every deploy already
#              behaves this way. Per-project files are user-owned: CLAUDE.md,
#              CHANGELOG.md, docs/* and settings.json are only seeded when
#              absent, never overwritten. settings.local.json.example is
#              refreshed if untouched, drift-reported if edited. (There is no
#              hooks/agents/skills/rules drift here anymore — those are central;
#              update them with `git pull && ./install.sh` in the dotclaude repo.)
#   --update --recursive [dir]  Update EVERY dotclaude project under dir
#              (default: .), each with the flags its .mcp.json implies, after
#              showing the plan and asking (--yes skips the question,
#              --dry-run only shows it). Obsolete MCP servers are removed.
#              Implemented once in scripts/update-projects.py for both OSes.
#   --remove-obsolete-mcp  Also remove the obsolete.json MCP servers (and their
#              mcp__<name> permission rules) instead of only reporting them.
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
#   5  --xcode requested on a non-macOS host
#   6  --xcode requested but `xcrun mcpbridge` is unavailable (needs Xcode 26.3+)
#   7  --ui requested but 'npx' is not in PATH
#   8  --codebase-memory requested but 'codebase-memory-mcp' is not in PATH
#   9  unknown flag, or a directory argument (or --yes / --dry-run / --depth)
#      without --recursive: nothing was deployed. A `--dry-run` that deployed
#      anyway is exactly what this prevents. (Older versions only warned and deployed anyway — which is how
#      an `init.sh --update --recursive .` run by a version without
#      --recursive seeded the template into a folder of projects.)
#  10  --recursive: at least one project failed (each is listed)
#  11  --recursive: cancelled, or no terminal to confirm and no --yes
#  12  --recursive: python3 is missing (the walker runs on it)

set -euo pipefail

INSTALL_XCODE=false
INSTALL_UI=false
INSTALL_CODEBASE_MEMORY=false
LSP_PLUGINS=()
RECURSIVE=false
RECURSIVE_DIR="."
RECURSIVE_ARGS=()
UNKNOWN=()
REMOVE_OBSOLETE_MCP=false
FULLSTACK=false
RUNTIME=""
COMPOSE=false
PROXY=""
DEPLOY_SCRIPT=false
for arg in "$@"; do
  case "$arg" in
    --xcode)          INSTALL_XCODE=true ;;
    --ui)             INSTALL_UI=true ;;
    --lsp=*)          LSP_PLUGINS+=("${arg#--lsp=}") ;;
    --codebase-memory) INSTALL_CODEBASE_MEMORY=true ;;
    --update)         : ;;  # informational: seeding always skips existing files
    --recursive)      RECURSIVE=true ;;
    --yes|--dry-run|--depth=*) RECURSIVE_ARGS+=("$arg") ;;
    --remove-obsolete-mcp) REMOVE_OBSOLETE_MCP=true ;;
    --db)             : ;;  # accepted, no-op (db-inspector is central now)
    --fullstack)      FULLSTACK=true ;;
    --runtime=*)      RUNTIME="${arg#--runtime=}" ;;
    --compose)        COMPOSE=true ;;
    --proxy=*)        PROXY="${arg#--proxy=}" ;;
    --deploy-script)  DEPLOY_SCRIPT=true ;;
    -*)               UNKNOWN+=("$arg") ;;
    *)                POSITIONAL="$arg" ;;
  esac
done
if [ -n "${POSITIONAL:-}" ]; then
  if [ "$RECURSIVE" = "true" ]; then RECURSIVE_DIR="$POSITIONAL"
  else UNKNOWN+=("$POSITIONAL (a directory is only taken with --recursive)"); fi
fi
if [ "$RECURSIVE" != "true" ]; then
  for a in ${RECURSIVE_ARGS[@]+"${RECURSIVE_ARGS[@]}"}; do
    UNKNOWN+=("$a (only meaningful with --recursive)")
  done
fi
if [ ${#UNKNOWN[@]} -gt 0 ]; then
  for u in "${UNKNOWN[@]}"; do echo "ERROR: unknown argument: $u" >&2; done
  echo "       Nothing was deployed. Run 'git pull && ./install.sh' in dotclaude if the flag is new." >&2
  exit 9
fi

# Helper: compose ./.mcp.json from per-server fragments in templates/project/mcp/.
# The file is COMPOSED, never copied: each flag owns its own server keys and must
# leave every other key alone — including servers the template knows nothing
# about (a hand-added playwright, a third-party server). Merging by key is also
# what makes re-runs idempotent and the flags order-independent. See
# tests/mcp-merge-cases.py for the cases that pin this.
#
# Usage: merge_mcp_servers <fragment.json> [...]  — JSON via python3, never jq
# (DESIGN.md §5). Never fatal: a broken .mcp.json warns and the deploy continues.
merge_mcp_servers() {
  is_link ./.mcp.json && return 0
  # One implementation for init.sh and init.ps1 (scripts/merge-mcp.py).
  # Fragments travel as argv: a $HOME with a space broke a whitespace-split list.
  if python3 "$TEMPLATE_DIR/scripts/merge-mcp.py" . "$@"; then
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
  if [ -e "$dst" ] || [ -L "$dst" ]; then
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

# --- Recursive mode: hand over to the shared walker, which calls this script --
# once per project found (with --update and that project's own flags).
if [ "$RECURSIVE" = "true" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: --recursive needs python3 (the walker runs on it)." >&2
    exit 12
  fi
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  exec python3 "$TEMPLATE_DIR/scripts/update-projects.py" "$RECURSIVE_DIR" --init "$self" \
    ${RECURSIVE_ARGS[@]+"${RECURSIVE_ARGS[@]}"}
fi

# A symlink in the project is never written through: it can point anywhere
# (another repo's .gitignore, ~/.claude.json), and --recursive deploys into
# every project under a directory. Each such path is reported and skipped.
is_link() {
  if [ -L "$1" ]; then
    echo "WARN: $1 is a symlink; not writing through it (it could point outside the project)." >&2
    return 0
  fi
  return 1
}

# --- Per-project .claude/ : only the project-specific files ------------------
if ! is_link "$DST_CLAUDE"; then
mkdir -p "$DST_CLAUDE"

# settings.json: a per-project stub (the base config is central). Seed only if
# absent — never overwrite the user's project-specific permissions.
seed_copy "$SRC_CLAUDE/settings.json" "$DST_CLAUDE/settings.json"

# settings.local.json.example: documentary. Refresh if untouched, drift if edited.
if [ -f "$SRC_CLAUDE/settings.local.json.example" ]; then
  ex_dst="$DST_CLAUDE/settings.local.json.example"
  if [ ! -f "$ex_dst" ]; then
    cp "$SRC_CLAUDE/settings.local.json.example" "$ex_dst"
  # Line endings do not count as an edit: a Windows checkout (autocrlf) holds
  # the same text with CRLF.
  elif [ "$(tr -d '\r' < "$SRC_CLAUDE/settings.local.json.example")" != "$(tr -d '\r' < "$ex_dst")" ]; then
    echo "DRIFT: .claude/settings.local.json.example (template updated; your edits kept)" >&2
  fi
fi
fi

# --- Obsolete artifacts: prune dead hook entries, report the rest ------------
# The deploy merges only ever add; a hook dotclaude stopped shipping stays wired
# in the project and errors on every matching tool call once install.sh removes
# its script. One Python implementation serves init.sh and init.ps1 alike. Its
# human report is on stderr; the KEY= lines on stdout are for its tests only
# (detect-drift.py imports the same detection instead of parsing them).
if [ -f "$TEMPLATE_DIR/obsolete.json" ]; then
  prune_args=()
  [ "$REMOVE_OBSOLETE_MCP" = "true" ] && prune_args+=(--remove-mcp)
  python3 "$TEMPLATE_DIR/scripts/prune-obsolete.py" "$TEMPLATE_DIR/obsolete.json" . ${prune_args[@]+"${prune_args[@]}"} >/dev/null \
    || echo "WARN: obsolete-artifact check did not complete; deploy continues." >&2
fi

# --- CLAUDE.md, CHANGELOG.md : user-owned, seed when absent -------------------
[ -e ./CLAUDE.md ]    || is_link ./CLAUDE.md    || cp "$TEMPLATE_DIR/CLAUDE.md.template"    ./CLAUDE.md
[ -e ./CHANGELOG.md ] || is_link ./CHANGELOG.md || cp "$TEMPLATE_DIR/CHANGELOG.md.template" ./CHANGELOG.md

# --- docs/ : portable contract surface, seed each file when absent -----------
if [ -d "$TEMPLATE_DIR/docs" ] && ! is_link ./docs; then
  mkdir -p ./docs
  for f in "$TEMPLATE_DIR"/docs/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    [ -e "./docs/$name" ] || is_link "./docs/$name" || cp "$f" "./docs/$name"
  done
fi

# --- .gitignore : merge template entries in (or seed if absent) --------------
# APPEND, never sort. Order is semantic in .gitignore: a negation (`!x`) only
# re-includes when it comes AFTER the pattern that excluded it. `sort -u`
# reorders by bytes and hoists negations above their parents — verified with
# real git under LC_ALL=C: both the template's own `!.env.example` and a user's
# `!keep.log` ended up ignored. Appending only the missing lines keeps every
# negation behind its parent and preserves the user's comments and grouping.
if is_link ./.gitignore; then
  :
elif [ -f ./.gitignore ]; then
  # Compare without CR (a CRLF file never matched, so every line was appended
  # again) and end the user's last line before appending (a file without a
  # final newline got `build.log.codebase-memory/`, breaking both patterns).
  eol='\n'
  grep -q $'\r' ./.gitignore && eol='\r\n'
  [ -s ./.gitignore ] && [ -n "$(tail -c 1 ./.gitignore)" ] && printf "$eol" >> ./.gitignore
  if ! tr -d '\r' < ./.gitignore | grep -qxF "# --- dotclaude template ---"; then
    printf "${eol}# --- dotclaude template ---${eol}" >> ./.gitignore
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    # `--` so a template line starting with '-' is a pattern, not grep options.
    tr -d '\r' < ./.gitignore | grep -qxF -- "$line" || printf "%s${eol}" "$line" >> ./.gitignore
  done < "$TEMPLATE_DIR/.gitignore.template"
else
  cp "$TEMPLATE_DIR/.gitignore.template" ./.gitignore
fi

# --- Xcode MCP (opt-in, macOS only) ------------------------------------------
# Apple's own MCP server, shipped with Xcode 26.3+ as `xcrun mcpbridge`. It is a
# STDIO bridge that connects over XPC to a RUNNING Xcode process — there is no
# standalone mode, so Xcode must be open with the project before Claude Code
# starts or the server simply shows as unavailable.
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
  python3 "$TEMPLATE_DIR/scripts/merge-permissions.py" "$TEMPLATE_DIR/permissions/playwright.json" . \
    || echo "WARN: playwright permissions not merged; deploy continues." >&2
fi

# --- codebase-memory-mcp (opt-in) ---------------------------------------------
# A persistent code graph for structural questions. Opt-in, not default: its
# authors' own benchmark scores it below plain file exploration on answer
# quality (it wins on tokens) — DESIGN.md §34. Only the binary is a
# prerequisite; dotclaude wires the server and permissions itself.
if [ "$INSTALL_CODEBASE_MEMORY" = "true" ]; then
  if ! command -v codebase-memory-mcp >/dev/null 2>&1; then
    echo "ERROR: 'codebase-memory-mcp' not found in PATH (--codebase-memory needs it)." >&2
    echo "       Install the BINARY only, with one of:" >&2
    echo "         npm install -g codebase-memory-mcp" >&2
    echo "         pip install --user codebase-memory-mcp" >&2
    echo "         release archive + checksums.txt from github.com/DeusData/codebase-memory-mcp/releases" >&2
    echo "         (verify with sha256sum -c, then put the binary in ~/.local/bin)" >&2
    echo "       Do NOT run 'codebase-memory-mcp install' or its curl|bash one-liner: they rewrite" >&2
    echo "       ~/.claude/settings.json hooks, add agents and skills, and edit your shell rc." >&2
    exit 8
  fi
  merge_mcp_servers "$TEMPLATE_DIR/mcp/codebase-memory-mcp.json"
  python3 "$TEMPLATE_DIR/scripts/merge-permissions.py" "$TEMPLATE_DIR/permissions/codebase-memory-mcp.json" . \
    || echo "WARN: codebase-memory-mcp permissions not merged; deploy continues." >&2
fi

# --- LSP plugins (opt-in, one per --lsp=<plugin>) -----------------------------
# Native code intelligence: go-to-definition/references through the `LSP` tool
# and diagnostics after every edit. The plugin is only wiring; the language
# server binary must be on PATH, so its absence is reported, not fatal.
# The heredoc lives in a function at top level: inside $( ) bash 4.1 and older
# (macOS /bin/bash) lex its body and break on a stray quote or backtick.
lsp_spec() {
  python3 - "$TEMPLATE_DIR/lsp-plugins.json" "$1" 2>/dev/null <<'PY'
import json, sys
catalog = json.load(open(sys.argv[1], encoding="utf-8"))
entry = catalog["plugins"].get(sys.argv[2])
if entry:
    print("%s\t%s\t%s" % (catalog["marketplace"], entry["binary"], entry["install"]))
PY
}

# ${arr[@]+...}: an empty array under `set -u` is an error on bash < 4.4.
for plugin in ${LSP_PLUGINS[@]+"${LSP_PLUGINS[@]}"}; do
  spec=$(lsp_spec "$plugin" || true)
  if [ -z "$spec" ]; then
    echo "WARN: --lsp=$plugin is not an official LSP plugin (see $TEMPLATE_DIR/lsp-plugins.json); skipped." >&2
    continue
  fi
  IFS=$'\t' read -r marketplace binary install_hint <<< "$spec"
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "WARN: language server '$binary' is not in PATH — $plugin stays inert until you install it:" >&2
    echo "        $install_hint" >&2
  fi
  if ! command -v claude >/dev/null 2>&1; then
    echo "WARN: 'claude' CLI not in PATH; install the plugin from Claude Code with:" >&2
    echo "        /plugin install $plugin@$marketplace   (choose project scope)" >&2
    continue
  fi
  if claude plugin install "$plugin@$marketplace" --scope project >/dev/null 2>&1; then
    echo "  - installed LSP plugin $plugin (project scope, recorded in .claude/settings.json)" >&2
  else
    echo "WARN: could not install $plugin; run it yourself:" >&2
    echo "        claude plugin install $plugin@$marketplace --scope project" >&2
  fi
done

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
