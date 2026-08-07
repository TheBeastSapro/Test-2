#!/usr/bin/env bash
# Install Open Generative AI from source and package the desktop app.
# See README.md for the prebuilt-installer route, which needs no Node.js.
set -euo pipefail

REPO_URL="https://github.com/Anil-matcha/Open-Generative-AI.git"
TARGET_DIR="${OGAI_DIR:-$HOME/Open-Generative-AI}"
BUILD_DESKTOP=1

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) TARGET_DIR="$2"; shift 2 ;;
    --no-desktop) BUILD_DESKTOP=0; shift ;;
    -h|--help)
      sed -n '2,3p' "$0" | sed 's/^# \{0,1\}//'
      echo
      echo "Usage: $0 [--dir PATH] [--no-desktop]"
      echo "  --dir PATH     where to clone (default: \$HOME/Open-Generative-AI)"
      echo "  --no-desktop   skip electron-builder packaging"
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1" >&2; exit 1; }
}
need git
need node
need npm

# The workspace builds use modern syntax; upstream requires Node 18+.
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt 18 ]; then
  echo "Node.js 18+ required, found $(node --version)" >&2
  exit 1
fi

if [ -d "$TARGET_DIR/.git" ]; then
  echo "==> updating existing checkout at $TARGET_DIR"
  git -C "$TARGET_DIR" pull --ff-only
  git -C "$TARGET_DIR" submodule update --init --recursive
else
  echo "==> cloning into $TARGET_DIR"
  # Submodules carry the workflow, agent, and design-agent packages. Without
  # them the workspace builds have nothing to compile.
  git clone --recurse-submodules "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# npm install alone leaves the four workspace packages unbuilt, which breaks
# both entry points. `setup` is install + build:packages.
echo "==> npm run setup"
npm run setup

if [ "$BUILD_DESKTOP" -eq 1 ]; then
  case "$(uname -s)" in
    Linux)  target="electron:build:linux" ;;
    Darwin) target="electron:build" ;;
    *)      target="" ;;
  esac

  if [ -n "$target" ]; then
    echo "==> npm run $target"
    npm run "$target"
    echo "==> desktop artifacts:"
    ls -lh release/ 2>/dev/null || echo "(none found in release/)"
  else
    echo "==> unrecognised platform $(uname -s); run npm run electron:build:win yourself"
  fi
fi

cat <<EOF

Done. From $TARGET_DIR:

  npm run electron:dev   desktop app
  npm run dev            web version at http://localhost:3000

A MuAPI key is optional — skip it at first launch and use Settings ->
Local Models to run models on your own GPU for free.
EOF
