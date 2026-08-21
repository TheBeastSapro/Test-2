# AgentSwitch — Milestones 1 & 2A

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
| `packages/contracts` | Zod-validated shared contracts: `AgentAdapter`, `AgentEvent`, `Task`, `CapabilityProfile`, `RoutingDecision`, `FailoverState`, `TransitionEvent`, `SealedEnvelope`, `DeliveryReceipt` |
| `packages/worker-core` | OS-independent orchestration: router, quality floor, failover state machine, checkpoints, continuity package, simulated adapters |
| `packages/crypto` | Sealed-envelope protocol (libsodium): worker identity, fingerprints, seal/open, replay guard, key pinning |
| `packages/relay-core` | In-memory single-use envelope relay. **No private key, no decrypt function, no crypto dependency** |
| `apps/control-plane` | HTTP server: failover demo stream plus the envelope relay. Holds no credentials and cannot decrypt |
| `apps/worker` | Worker process: generates an in-memory key pair, prints its fingerprint, receives and decrypts envelopes |
| `apps/web` | Browser demo and the encrypted credential delivery page |

`worker-core` has no Node-specific imports, no wall-clock reads and no
randomness. It runs unchanged in the browser and on a server, and the same
configuration always produces a byte-identical timeline.

## Run it

```bash
npm install
npm run build      # typechecks every package and produces the web bundle
npm test           # 57 tests
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

## Milestone 2A — encrypted credential transport

Proves one flow end to end: **browser plaintext → browser encryption → control
plane sees ciphertext only → confirmed worker decrypts → acknowledgement →
ciphertext deleted.**

Run all three processes:

```bash
npm run build
npm run serve:control-plane                      # terminal 1
npm run serve:worker                             # terminal 2 - prints its fingerprint
npm run dev                                      # terminal 3
```

Open **Credentials**, compare the fingerprint the page shows against the one
the worker printed in its own terminal, confirm it, then send a test value.
Delivery stays disabled until you confirm, and a page refresh clears the
confirmation.

To see the canary check, start the worker with an expected value:

```bash
AGENTSWITCH_TEST_CANARY="my-test-value" npm run serve:worker
```

### How the security properties are enforced

- **The relay cannot decrypt.** `packages/relay-core` and
  `apps/control-plane` import no crypto library and hold no private key. This
  is enforced by a test, not by convention.
- **Metadata is authenticated without custom cryptography.** The routing
  header is duplicated *inside* the libsodium sealed box. Editing an outer
  field produces a mismatch; editing the ciphertext fails the box's own
  authentication.
- **The plaintext is never React state.** It is read from an uncontrolled
  input at the moment the button is pressed, encrypted, and the box cleared
  before any network call.
- **Envelopes are single-use and short-lived.** Five-minute ceiling, unique
  replay nonce, deleted on acknowledgement, swept when expired.

### Honest limitations (Milestone 2A)

- The worker's X25519 private key is an **ordinary `Uint8Array` in process
  memory**. It is not OS-protected and not "non-exportable" — anything that
  can read the process can read it. Persistent DPAPI / Windows Credential
  Manager protection is Milestone 2B.
- A worker restart produces a **new identity**, so the browser must confirm a
  new fingerprint. That is intended for this milestone.
- Byte arrays are wiped best-effort with `sodium.memzero`. **JavaScript
  strings cannot be wiped** — they are immutable and garbage-collected. Where
  a string is unavoidable (a DOM input value) the mitigation is a short
  lifetime, not erasure.
- Nothing is persisted. No provider is contacted. No credential is validated.

## Deliberately not implemented yet

Real provider CLIs, provider authentication or validation, credential
persistence, DPAPI / Windows Credential Manager, Electron, Git worktrees,
multi-user access, and dynamic capability registries.
