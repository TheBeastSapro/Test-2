# AgentSwitch — Milestone 1

A continuity layer for coding-agent CLIs. This milestone is the smallest
executable vertical slice that proves **intelligent failover**: a task starts
on one agent, that agent hits a usage limit, the work is checkpointed, a
*comparable* replacement is chosen, it verifies the existing work read-only,
and it continues — all in one unbroken timeline.

Everything here runs against **simulated agents**. No real provider, no
credential, no network call to any provider is involved. Real adapters are
Milestone 2.

## Layout

| Path | What it is |
|---|---|
| `packages/contracts` | Zod-validated shared contracts: `AgentAdapter`, `AgentEvent`, `Task`, `CapabilityProfile`, `RoutingDecision`, `FailoverState`, `TransitionEvent` |
| `packages/worker-core` | OS-independent orchestration: router, quality floor, failover state machine, checkpoints, continuity package, simulated adapters |
| `apps/control-plane` | Minimal HTTP server that streams the same timeline as NDJSON. Holds no credentials |
| `apps/web` | Browser demo and the Credentials page shell |

`worker-core` has no Node-specific imports, no wall-clock reads and no
randomness. It runs unchanged in the browser and on a server, and the same
configuration always produces a byte-identical timeline.

## Run it

```bash
npm install
npm run build      # typechecks every package and produces the web bundle
npm test           # 15 tests
npm run dev        # browser demo at http://localhost:5173
```

In the demo:

- **Start demo task** — Sim Alpha works, hits a simulated limit, Sim Beta
  verifies and finishes. One timeline, one task id, no reset.
- **Why this agent?** — the real routing explanation, including why Sim Gamma
  was rejected.
- Switch to **Strict** and leave only **Sim Gamma** available — AgentSwitch
  pauses instead of downgrading.

Optional: the same run over HTTP.

```bash
npm run build
npm run serve:control-plane
curl "localhost:8787/api/demo/stream?mode=balanced"
curl "localhost:8787/api/demo/stream?mode=strict&pool=sim-gamma"
```

## Deliberately not implemented yet

Real provider CLIs, authentication, token transmission or storage, Git
worktrees, multi-user access, packaging, and dynamic capability registries.
The Credentials page is a shell: **Test and Save** is disabled because the
encrypted worker delivery it depends on does not exist yet, and a button that
looked functional would be worse than no button.
