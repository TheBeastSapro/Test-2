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
