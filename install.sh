#!/usr/bin/env bash
# vercel-incident-toolkit installer
#
# What this script does — audit it before running:
#   1. Verifies python3 >= 3.10 and that `vercel` CLI is logged in
#   2. (Optional) Symlinks this checkout into ~/.claude/skills/ so Claude Code
#      can auto-discover it
#   3. Runs scripts/preflight.py
#   4. Prints what to do next
#
# This script does NOT:
#   - Install any runtime dependency (toolkit uses Python stdlib only)
#   - Pipe anything from the network
#   - Modify your shell rc, system keychain, or any global config outside
#     the optional ~/.claude/skills/vercel-incident-toolkit symlink
#   - Run any --apply action against your Vercel account
#
# Usage:
#   git clone https://github.com/subinium/vercel-incident-toolkit.git
#   cd vercel-incident-toolkit
#   bash install.sh
#
# Options (env vars):
#   SKILL_MODE=1          force "yes" to the Claude Code skill symlink
#   SKILL_MODE=0          skip the skill symlink
#   CLAUDE_SKILLS_DIR     override ~/.claude/skills (default)
#   SKIP_PREFLIGHT=1      do not run scripts/preflight.py at the end

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SKILL_LINK="$SKILLS_DIR/vercel-incident-toolkit"

say() { printf '%s\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
err() { printf '\033[31m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m%s\033[0m\n' "$*"; }

say "vercel-incident-toolkit — install"
say ""

# 1. Python
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found on PATH. Install Python >= 3.10."
  exit 1
fi
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
if [ "$PY_OK" != "1" ]; then
  err "python3 $(python3 --version) is too old. Need >= 3.10."
  exit 1
fi
ok "✓ python3 $(python3 --version | cut -d' ' -f2)"

# 2. Vercel CLI
if ! command -v vercel >/dev/null 2>&1; then
  warn "! vercel CLI not on PATH. Install with: npm i -g vercel"
  warn "  Skipping CLI login check. Run preflight later once installed."
else
  if ! vercel whoami >/dev/null 2>&1; then
    warn "! vercel CLI is installed but not logged in. Run: vercel login"
  else
    ok "✓ vercel CLI logged in as: $(vercel whoami 2>/dev/null)"
  fi
fi

say ""

# 3. Claude Code skill symlink (optional)
link_mode="${SKILL_MODE:-}"
if [ -z "$link_mode" ]; then
  say "Install as a Claude Code skill? (symlink $ROOT → $SKILL_LINK)"
  say "  Claude Code auto-discovers skills in ~/.claude/skills/ and routes prompts"
  say "  like 'audit my Vercel env vars' or 'Vercel breach response' to SKILL.md."
  printf "  [y/N] "
  read -r ans || ans=""
  case "${ans:-n}" in
    y|Y|yes|YES) link_mode=1 ;;
    *) link_mode=0 ;;
  esac
fi

if [ "$link_mode" = "1" ]; then
  mkdir -p "$SKILLS_DIR"
  if [ -L "$SKILL_LINK" ] || [ -e "$SKILL_LINK" ]; then
    warn "! $SKILL_LINK already exists. Leaving it as-is."
    warn "  If you want to reinstall, remove it manually and re-run."
  else
    ln -s "$ROOT" "$SKILL_LINK"
    ok "✓ symlinked $SKILL_LINK → $ROOT"
  fi
else
  say "Skipped skill symlink. You can still use the toolkit standalone from $ROOT."
fi

say ""

# 4. Preflight
if [ "${SKIP_PREFLIGHT:-0}" = "1" ]; then
  say "Skipped preflight (SKIP_PREFLIGHT=1)."
else
  say "Running preflight..."
  say ""
  if ! python3 "$ROOT/scripts/preflight.py"; then
    warn ""
    warn "! Preflight reported issues. Resolve them before running any --apply."
  fi
fi

say ""
say "Next steps:"
say "  1. Read README.md (or README.ko.md / README.ja.md / README.zh-Hans.md)"
say "  2. Read SKILL.md for the decision tree"
say "  3. Dry-run: python3 $ROOT/scripts/audit.py"
say "  4. Never pass --apply until you've read the script you're about to run"
