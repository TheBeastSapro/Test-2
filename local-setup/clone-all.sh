#!/usr/bin/env bash
# Clone every repo this Claude account can reach into one local directory.
#
#   ./clone-all.sh                  # clone into ~/claude-repos
#   ./clone-all.sh ~/code           # clone into ~/code
#   ./clone-all.sh ~/code --all     # discover every repo via `gh` instead of
#                                   # the pinned list below
#
# Already-cloned repos are fetched and fast-forwarded, never clobbered.

set -euo pipefail

TARGET="${1:-$HOME/claude-repos}"
DISCOVER=0
[[ "${2:-}" == "--all" ]] && DISCOVER=1

# The repos attached to this Claude account as of 2026-08-06.
PINNED_REPOS=(
  "TheBeastSapro/Test-2"   # public  — skills, VO studio, observation log
  "TheBeastSapro/Test"     # private — needs GitHub auth
)

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[X]\033[0m %s\n' "$*" >&2; exit 1; }

# --- prerequisites --------------------------------------------------------

command -v git >/dev/null || die "git is not installed."

HAVE_GH=0
command -v gh >/dev/null && HAVE_GH=1

if [[ $HAVE_GH -eq 0 ]]; then
  warn "GitHub CLI (gh) not found. Private repos will fall back to HTTPS and"
  warn "may prompt for credentials. Install it: https://cli.github.com"
  [[ $DISCOVER -eq 1 ]] && die "--all needs gh to enumerate repos."
fi

if [[ $HAVE_GH -eq 1 ]] && ! gh auth status >/dev/null 2>&1; then
  warn "gh is installed but not authenticated. Run: gh auth login"
fi

command -v claude >/dev/null || {
  warn "Claude Code CLI not found. Install it before teleporting sessions:"
  warn "  npm install -g @anthropic-ai/claude-code"
}

# --- pick the repo list ---------------------------------------------------

REPOS=()
if [[ $DISCOVER -eq 1 ]]; then
  say "Discovering repos via gh…"
  # while-read, not mapfile: macOS still ships bash 3.2, which has no mapfile.
  while IFS= read -r line; do
    [[ -n "$line" ]] && REPOS+=("$line")
  done < <(gh repo list --limit 200 --json nameWithOwner --jq '.[].nameWithOwner')
  [[ ${#REPOS[@]} -gt 0 ]] || die "gh returned no repositories."
else
  REPOS=("${PINNED_REPOS[@]}")
fi

say "Cloning ${#REPOS[@]} repo(s) into $TARGET"
mkdir -p "$TARGET"

# --- clone or update ------------------------------------------------------

# Plain string, not an array: an empty array under `set -u` is an unbound
# variable on bash 3.2, which is what macOS ships.
FAILED=""

for repo in "${REPOS[@]}"; do
  name="${repo##*/}"
  dest="$TARGET/$name"

  if [[ -d "$dest/.git" ]]; then
    say "$repo — already cloned, fetching"
    git -C "$dest" fetch --all --prune || { FAILED="$FAILED $repo(fetch)"; continue; }
    # Fast-forward only; never touch a dirty tree or rewrite local work.
    if [[ -z "$(git -C "$dest" status --porcelain)" ]]; then
      git -C "$dest" merge --ff-only '@{u}' >/dev/null 2>&1 \
        || warn "$name: branch diverged or has no upstream — left as-is"
    else
      warn "$name: uncommitted changes — fetched only, working tree untouched"
    fi
    continue
  fi

  say "$repo — cloning"
  if [[ $HAVE_GH -eq 1 ]]; then
    gh repo clone "$repo" "$dest" || { FAILED="$FAILED $repo"; continue; }
  else
    git clone "https://github.com/$repo.git" "$dest" || { FAILED="$FAILED $repo"; continue; }
  fi
done

# --- report ---------------------------------------------------------------

echo
if [[ -n "$FAILED" ]]; then
  warn "Failed:$FAILED"
  warn "Private repos need auth — run 'gh auth login' and re-run this script."
else
  say "All repos present in $TARGET"
fi

echo
say "Next: pull your cloud sessions down with"
echo "     $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/teleport.sh $TARGET/Test-2"

# Exit non-zero if any repo failed, so a caller checking $? isn't told a
# partial clone succeeded. The guidance above still prints either way.
[[ -z "$FAILED" ]] || exit 1
