#!/usr/bin/env bash
# Re-install The Agency roster (msitarzewski/agency-agents) into .claude/agents/
# and refresh agents-lock.json.
#
#   bash .claude/scripts/update-agency-agents.sh              # latest upstream
#   bash .claude/scripts/update-agency-agents.sh <commit|tag> # pin to a ref
#
# Idempotent. Only files that exist upstream are written, so locally authored
# agents in .claude/agents/ (e.g. claim-auditor.md) are left untouched. Agents
# deleted upstream are NOT removed here — compare agents-lock.json if you want
# to prune.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$REPO_ROOT/.claude/agents"
REF="${1:-}"
UPSTREAM="https://github.com/msitarzewski/agency-agents.git"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[agency-agents] cloning $UPSTREAM"
if [[ -n "$REF" ]]; then
  git clone -q "$UPSTREAM" "$WORK/agency-agents"
  git -C "$WORK/agency-agents" checkout -q "$REF"
else
  git clone -q --depth 1 "$UPSTREAM" "$WORK/agency-agents"
fi

echo "[agency-agents] installing into $DEST"
bash "$WORK/agency-agents/scripts/install.sh" \
  --tool claude-code --path "$DEST" --no-interactive

echo "[agency-agents] writing agents-lock.json"
SRC="$WORK/agency-agents" DEST="$DEST" OUT="$REPO_ROOT/agents-lock.json" python3 - <<'PY'
import hashlib, json, os, re, subprocess

SRC, DEST, OUT = os.environ["SRC"], os.environ["DEST"], os.environ["OUT"]
commit = subprocess.check_output(["git", "-C", SRC, "rev-parse", "HEAD"], text=True).strip()

# Every agent markdown file upstream, keyed by basename -> path within that repo.
src_index = {}
for root, dirs, files in os.walk(SRC):
    dirs[:] = [d for d in dirs if d not in (".git", ".github", "integrations", "scripts")]
    for fn in files:
        if fn.endswith(".md"):
            src_index.setdefault(fn, os.path.relpath(os.path.join(root, fn), SRC))

def field(path, key):
    with open(path, encoding="utf-8") as fh:
        head = re.match(r"---\n(.*?)\n---\n", fh.read(), re.S)
    if not head:
        return ""
    m = re.search(rf"^{key}:\s*(.*)$", head.group(1), re.M)
    return m.group(1).strip().strip('"') if m else ""

agents = {}
for fn in sorted(os.listdir(DEST)):
    if not fn.endswith(".md") or fn not in src_index:
        continue  # locally authored agent — not ours to lock
    with open(os.path.join(DEST, fn), "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    agents[fn[:-3]] = {
        "name": field(os.path.join(DEST, fn), "name"),
        "sourcePath": src_index[fn],
        "computedHash": digest,
    }

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({
        "version": 1,
        "source": "msitarzewski/agency-agents",
        "sourceType": "github",
        "sourceRef": commit,
        "installPath": ".claude/agents",
        "agentCount": len(agents),
        "agents": agents,
    }, fh, indent=2, ensure_ascii=False)
    fh.write("\n")

print(f"[agency-agents] locked {len(agents)} agents at {commit[:12]}")
PY
