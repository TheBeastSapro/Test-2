# Headroom

Setup for [headroom](https://github.com/headroomlabs-ai/headroom) — a context
optimization layer for LLM applications. It compresses tool outputs, logs,
files, and RAG chunks before they reach the LLM (60-95% fewer tokens for
JSON, ~20% fewer for coding agents) while preserving answer quality.

## Install

Recommended (isolated CLI via [uv](https://docs.astral.sh/uv/)):

```bash
uv tool install --python 3.13 "headroom-ai[all]"
```

Or with pip:

```bash
pip install -r requirements.txt
```

## Verify

```bash
headroom --version
headroom doctor
```

## Quick start

```bash
headroom proxy          # start the optimization proxy
headroom wrap claude     # route Claude Code through the proxy
headroom memory stats    # inspect stored memories
headroom savings         # view durable compression savings over time
```

See `headroom --help` for the full command list (proxy, memory, evals,
init, deploy, mcp, and more).

## ECC

[ECC](https://github.com/affaan-m/ECC) is installed project-scoped into
`.claude/` (280 skills, 67 agents, 94 commands, 22 rule packs, hook runtime).
It is committed to the repo rather than installed into `~/.claude/` because
web sessions run in ephemeral containers — anything outside the working tree
is lost at teardown.

Install state lives in `.claude/ecc/install-state.json`. It was produced by:

```bash
git clone https://github.com/affaan-m/ECC.git
cd ECC && npm install
node scripts/install-apply.js --target claude-project --profile full   # run from this repo's root
```

To upgrade, re-run the same command from a fresh ECC checkout. To inspect or
remove the install, use `node scripts/ecc.js list-installed`,
`node scripts/ecc.js doctor`, or `node scripts/uninstall.js --dry-run` from an
ECC checkout.

Hooks are **installed but not active**. ECC writes them to
`.claude/hooks/hooks.json` and deliberately leaves `settings.json` alone;
Claude Code only loads project hooks declared in `.claude/settings.json`. To
enable them, merge that file's `hooks` entries into `.claude/settings.json`
and set `CLAUDE_PLUGIN_ROOT` to this repo's `.claude` directory so the hook
scripts resolve their ECC root.
