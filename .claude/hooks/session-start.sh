#!/bin/bash
# Reinstall Agent Reach in each fresh Claude Code on the web container.
# Containers are ephemeral, so the CLI and its upstream tools have to be
# rebuilt every session. Safe to run repeatedly: every step is a no-op once
# the tool is already present.
set -euo pipefail

# Local machines keep their own install; only rebuild in the remote container.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

AR_HOME="$HOME/.agent-reach"
AR_SRC="$AR_HOME/src/agent-reach"
BIN_DIR="$HOME/.local/bin"
export PATH="$BIN_DIR:$PATH"

# Agent Reach's own rule: nothing goes in the repo working directory.
mkdir -p "$AR_SRC" "$BIN_DIR"

if ! command -v agent-reach >/dev/null 2>&1; then
  if [ -d "$AR_SRC/.git" ]; then
    git -C "$AR_SRC" fetch --depth 1 origin main && git -C "$AR_SRC" reset --hard FETCH_HEAD
  else
    git clone --depth 1 https://github.com/Panniantong/agent-reach.git "$AR_SRC"
  fi

  if command -v uv >/dev/null 2>&1; then
    uv tool install "$AR_SRC"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install "$AR_SRC"
  else
    pip3 install --user "$AR_SRC"
  fi
fi

# Base channels (web, YouTube, GitHub, RSS, Exa search, V2EX, Bilibili) plus
# the two that need cookies. Installing them is unconditional; they only go
# live once credentials are configured below.
agent-reach install --env=auto --channels=twitter,reddit

# Agent Reach ships yt-dlp with the EJS plugin, which the preinstalled
# /usr/local/bin/yt-dlp lacks. Without it YouTube signature solving fails and
# formats go missing, so put the bundled one first on PATH.
AR_YTDLP="$HOME/.local/share/uv/tools/agent-reach/bin/yt-dlp"
if [ -x "$AR_YTDLP" ]; then
  ln -sf "$AR_YTDLP" "$BIN_DIR/yt-dlp"
fi

# yt-dlp resolves the JS runtime before PATH is fully set up, so pin the
# absolute node path rather than relying on a bare `node`.
NODE_BIN="$(command -v node || true)"
if [ -n "$NODE_BIN" ]; then
  mkdir -p "$HOME/.config/yt-dlp"
  printf -- '--js-runtimes node:%s\n' "$NODE_BIN" > "$HOME/.config/yt-dlp/config"
fi

# Zero-login tweet reader. twitter-cli needs cookies for everything; reading a
# single tweet or thread by URL does not, so expose that path as `tweet`.
REPO_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
if [ -f "$REPO_DIR/.claude/tools/tweet-read.py" ]; then
  chmod +x "$REPO_DIR/.claude/tools/tweet-read.py"
  ln -sf "$REPO_DIR/.claude/tools/tweet-read.py" "$BIN_DIR/tweet"
fi

# Optional: set these as environment secrets on the Claude Code environment to
# have Twitter and Reddit come up authenticated instead of needing a paste each
# session. Unset means those channels stay in "needs login" state.
if [ -n "${TWITTER_COOKIE_HEADER:-}" ]; then
  agent-reach configure twitter-cookies "$TWITTER_COOKIE_HEADER" >/dev/null
fi
if [ -n "${REDDIT_COOKIE_HEADER:-}" ]; then
  agent-reach configure reddit-cookies "$REDDIT_COOKIE_HEADER" >/dev/null 2>&1 || true
fi

# twitter-cli reads credentials from the process environment, not from the
# Agent Reach config, so export them for the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export PATH=\"$BIN_DIR:\$PATH\""
    if [ -n "${TWITTER_AUTH_TOKEN:-}" ]; then
      echo "export TWITTER_AUTH_TOKEN=\"$TWITTER_AUTH_TOKEN\""
    fi
    if [ -n "${TWITTER_CT0:-}" ]; then
      echo "export TWITTER_CT0=\"$TWITTER_CT0\""
    fi
  } >> "$CLAUDE_ENV_FILE"
fi

agent-reach doctor || true
