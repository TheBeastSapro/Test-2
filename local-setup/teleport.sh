#!/usr/bin/env bash
# Pull a Claude Code *cloud* session — its full conversation history and its
# branch — down into your terminal.
#
#   ./teleport.sh                    # use the current directory
#   ./teleport.sh ~/claude-repos/Test-2
#   ./teleport.sh ~/claude-repos/Test-2 <session-id>
#
# This is the only supported way to get a cloud chat onto your machine.
# It checks the four requirements first so you get a readable error instead
# of a mid-teleport failure.

set -euo pipefail

REPO_DIR="${1:-$PWD}"
SESSION_ID="${2:-}"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[X]\033[0m %s\n' "$*" >&2; exit 1; }

command -v claude >/dev/null \
  || die "Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code"

[[ -d "$REPO_DIR/.git" ]] || die "$REPO_DIR is not a git repository."
cd "$REPO_DIR"

# 1. Correct repository — teleport refuses a fork or an unrelated checkout.
remote="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$remote" ]] || die "No 'origin' remote here. Teleport needs the repo the session ran in."
say "Repository: $remote"

# 2. Clean git state — teleport will otherwise prompt you to stash.
if [[ -n "$(git status --porcelain)" ]]; then
  warn "Uncommitted changes present. Teleport requires a clean tree."
  warn "Commit them, or stash with: git stash -u"
  # `|| reply=""` so a non-interactive shell (no TTY) aborts with the message
  # below instead of dying silently on read's EOF under `set -e`.
  read -r -p "Stash them now and continue? [y/N] " reply || reply=""
  [[ "$reply" =~ ^[Yy]$ ]] || die "Aborted — nothing was changed."
  git stash push -u -m "pre-teleport $(git rev-parse --short HEAD)"
  say "Stashed. Restore later with: git stash pop"
fi

# 3. Branch available — teleport fetches the session's branch from the remote.
say "Fetching remote branches…"
git fetch --all --prune

# 4. Same account — teleport needs claude.ai subscription auth, not an API key.
say "Launching the session picker. Pick the cloud session you want locally."
say "(If it errors with 'Unable to get organization UUID', run /login first.)"
echo

if [[ -n "$SESSION_ID" ]]; then
  exec claude --teleport "$SESSION_ID"
else
  exec claude --teleport
fi
