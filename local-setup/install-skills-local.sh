#!/usr/bin/env bash
# Install what the repo's skills need on a LOCAL machine.
#
# .claude/hooks/session-start.sh deliberately exits on local machines, so
# nothing it installs in the cloud container exists here. This does that work
# once, without the container's assumptions: a project venv instead of
# --break-system-packages, CPU torch instead of CUDA, and no apt-get without
# asking.
#
#   ./install-skills-local.sh          # everything
#   ./install-skills-local.sh audio    # voiceover + sound-design stack only
#   ./install-skills-local.sh cli      # defuddle, yt-dlp, tweet shim only
#
# Idempotent: re-running skips what is already present.

set -euo pipefail

GROUP="${1:-all}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/.venv"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[X]\033[0m %s\n' "$*" >&2; exit 1; }

case "$GROUP" in
  all|audio|cli) ;;
  *) die "Unknown group '$GROUP'. Use: all | audio | cli" ;;
esac

# Track what could not be done so the summary is honest.
SKIPPED=""

# --- OS package helper ----------------------------------------------------

pkg_install() {
  # pkg_install <binary> <brew-name> <apt-name> <required|optional>
  local bin="$1" brew_name="$2" apt_name="$3" need="$4"

  if command -v "$bin" >/dev/null 2>&1; then
    ok "$bin already installed"
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    say "installing $bin via brew"
    brew install "$brew_name" && return 0
  elif command -v apt-get >/dev/null 2>&1; then
    say "installing $bin via apt (needs sudo)"
    sudo apt-get install -y "$apt_name" && return 0
  fi

  if [ "$need" = "required" ]; then
    die "$bin is required and could not be installed automatically.
     macOS:  brew install $brew_name
     Debian: sudo apt install $apt_name"
  fi
  warn "$bin not installed — install it with 'brew install $brew_name' or 'sudo apt install $apt_name'"
  SKIPPED="$SKIPPED $bin"
  return 0
}

# --- CLI tools ------------------------------------------------------------

install_cli() {
  say "CLI tools (defuddle, yt-dlp, tweet)"

  if command -v npm >/dev/null 2>&1; then
    if command -v defuddle >/dev/null 2>&1; then
      ok "defuddle already installed"
    else
      npm install -g defuddle && ok "defuddle installed"
    fi
  else
    warn "npm not found — skipping defuddle. Install Node, then: npm install -g defuddle"
    SKIPPED="$SKIPPED defuddle"
  fi

  # yt-dlp: sound-designer and the analyse skill both shell out to it.
  if command -v yt-dlp >/dev/null 2>&1; then
    ok "yt-dlp already installed"
  elif command -v brew >/dev/null 2>&1; then
    brew install yt-dlp && ok "yt-dlp installed"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install yt-dlp && ok "yt-dlp installed"
  else
    warn "yt-dlp not installed — 'brew install yt-dlp' or 'pipx install yt-dlp'"
    SKIPPED="$SKIPPED yt-dlp"
  fi

  # The `tweet` shim the session-start hook symlinks in the container.
  local bin_dir="$HOME/.local/bin"
  local src="$REPO_DIR/.claude/tools/tweet-read.py"
  if [ -f "$src" ]; then
    mkdir -p "$bin_dir"
    chmod +x "$src"
    ln -sf "$src" "$bin_dir/tweet"
    ok "tweet -> $bin_dir/tweet"
    case ":$PATH:" in
      *":$bin_dir:"*) ;;
      *) warn "$bin_dir is not on your PATH. Add to your shell profile:"
         warn '  export PATH="$HOME/.local/bin:$PATH"' ;;
    esac
  else
    warn "tweet-read.py not found — skipping tweet shim"
    SKIPPED="$SKIPPED tweet"
  fi
}

# --- Audio / voiceover / sound-design stack -------------------------------

install_audio() {
  say "Audio toolchain (explaintory-voiceover, explaintory-vo-master, sound-designer)"

  # ffmpeg is hard-required: install-audio-tools.sh aborts without it and every
  # measurement in the mastering and sound-design pipeline is an ffmpeg call.
  pkg_install ffmpeg  ffmpeg    ffmpeg    required
  # espeak-ng is soft: without it only the pronunciation check goes dark.
  pkg_install espeak-ng espeak-ng espeak-ng optional

  command -v python3 >/dev/null || die "python3 not found. Install Python 3.11+."

  if [ ! -d "$VENV" ]; then
    say "creating venv at $VENV"
    python3 -m venv "$VENV"
  else
    ok "venv already exists"
  fi

  local PY="$VENV/bin/python"
  [ -x "$PY" ] || die "venv looks broken — remove $VENV and re-run."

  "$PY" -m pip install --upgrade pip -q

  say "generation + read-check"
  "$PY" -m pip install -q elevenlabs faster-whisper jiwer whisper-normalizer spacy
  "$PY" -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null \
    || "$PY" -m spacy download en_core_web_sm

  say "mastering"
  "$PY" -m pip install -q numpy scipy soundfile
  # CPU wheels: ~200 MB instead of the ~2.5 GB CUDA build. VO Studio is the
  # place for GPU torch, in its own isolated runtime.
  "$PY" -m pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu

  say "pronunciation check"
  "$PY" -m pip install -q phonemizer panphon allosaurus

  say "sound design"
  "$PY" -m pip install -q scenedetect librosa silero-vad opencv-python-headless

  say "verifying imports"
  "$PY" - <<'PY'
import importlib, sys
mods = ["elevenlabs", "faster_whisper", "jiwer", "whisper_normalizer", "spacy",
        "phonemizer", "panphon", "allosaurus",
        "numpy", "scipy", "soundfile", "torch", "torchaudio",
        "scenedetect", "librosa", "silero_vad", "cv2"]
missing = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append(f"{m}: {e}")
import spacy
try:
    spacy.load("en_core_web_sm")
except Exception as e:
    missing.append(f"en_core_web_sm: {e}")
if missing:
    print("MISSING:\n  " + "\n  ".join(missing)); sys.exit(1)
print(f"all {len(mods)} packages present")
PY
  ok "audio toolchain complete"

  [ -n "${ELEVENLABS_API_KEY:-}" ] \
    || warn "ELEVENLABS_API_KEY is unset — voiceover generation will not run.
     Add to your shell profile:  export ELEVENLABS_API_KEY=\"...\""
}

# --- run ------------------------------------------------------------------

# Explicit ifs, not `[ a ] || [ b ] && fn`: that parses as `(a || b) && fn`, and
# when the group doesn't match, the list returns 1 and `set -e` kills the script
# before the summary prints.
if [ "$GROUP" = "all" ] || [ "$GROUP" = "cli" ]; then
  install_cli
fi
if [ "$GROUP" = "all" ] || [ "$GROUP" = "audio" ]; then
  install_audio
fi

# --- summary --------------------------------------------------------------

echo
if [ -n "$SKIPPED" ]; then
  warn "Not installed:$SKIPPED"
  warn "Those skills run with reduced capability until you install them."
fi

say "Done. Before launching Claude Code in this repo:"
echo "     source $VENV/bin/activate && claude"
echo
say "MCP servers are account-level and are NOT installed by this script."
echo "     See local-setup/SKILLS.md, section 'Group C'."
