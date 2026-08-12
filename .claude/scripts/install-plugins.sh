#!/usr/bin/env bash
# Re-install the Claude Code plugins this repo depends on.
#
#   bash .claude/scripts/install-plugins.sh
#
# Why this exists: plugins install to ~/.claude/plugins/ (user scope), which is
# ephemeral on Claude Code on the web — every session gets a fresh container, so
# the plugins have to be reinstalled each time, like agent-reach and the audio
# toolchain.
#
# And why declaring them in .claude/settings.json was never enough: a PROJECT
# settings.json cannot register plugin marketplaces. `claude plugin marketplace
# add` writes to ~/.claude/settings.json, and only that user-level copy is read.
# A repo listing extraKnownMarketplaces/enabledPlugins looks configured and
# installs nothing — which is exactly what happened here.
set -euo pipefail

# marketplace-id|github-repo|plugin-name
PLUGINS=(
  "thedotmack|thedotmack/claude-mem|claude-mem"
  "superpowers-dev|obra/superpowers|superpowers"
  "ui-ux-pro-max-skill|nextlevelbuilder/ui-ux-pro-max-skill|ui-ux-pro-max"
)

command -v claude >/dev/null 2>&1 || { echo "[plugins] claude CLI not on PATH, skipping"; exit 0; }

installed="$(claude plugin list 2>/dev/null || true)"

for entry in "${PLUGINS[@]}"; do
  IFS='|' read -r market repo name <<< "$entry"

  # Already present and enabled — nothing to do. Keeps warm containers fast.
  if grep -q "^  > ${name}@${market}$" <<< "$installed"; then
    echo "[plugins] ${name}@${market} already installed"
    continue
  fi

  echo "[plugins] installing ${name}@${market}"
  claude plugin marketplace add "$repo" >/dev/null 2>&1 \
    || echo "[plugins] marketplace add failed for $repo, trying install anyway"
  claude plugin install "${name}@${market}" >/dev/null 2>&1 \
    || echo "[plugins] WARN: install failed for ${name}@${market}"
done

claude plugin list 2>/dev/null | grep -E '^  > |Status:' || true
