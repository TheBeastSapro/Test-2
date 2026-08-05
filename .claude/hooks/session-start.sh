#!/bin/bash
# Install the audio toolchain so a web session can generate, QC and master a
# voiceover without a setup round-trip first. Remote only — local machines keep
# their own environments.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

bash "${CLAUDE_PROJECT_DIR:-.}/.claude/scripts/install-audio-tools.sh"
