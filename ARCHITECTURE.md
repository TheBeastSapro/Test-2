# Forgecast — the constraints, and the design

Two documents in one. Part 1 is what this product has to do and what follows from it
structurally — the conclusions you cannot design around. Part 2 is the architecture of
this repository, which implements that shape.

Everything here is written from first principles and from published vendor pricing. No
third party's code, prompts or internal APIs are involved, and none of their text is
reproduced anywhere in this repository.

---

## Part 1 — What the product has to do, and what that forces

### 1.1 The requirements

| Thing | What it means |
|---|---|
| Pipeline | A production brief, then a full script, then a thumbnail, then the narration and B-roll plan, then a rendered video |
| Transparency | Every generation step is a visible node. You watch the script form, the thumbnail render, the audio sync |
| Gates | Nothing ships without approval. Pause, revise or redirect at any stage |
| Memory | The agent remembers this channel's style, its past decisions and its voice |
| Publish | Compliance checks, a preview before anything is uploaded, then publish |
| Providers | ElevenLabs and MiniMax (voice), HeyGen (avatars), Runway and FAL (video), FAL and Higgsfield (image), OpenAI and Anthropic (language) |
| Keys | Bring your own, including cloned voices |
| Billing | Credits, held before a vendor is called and settled against what was actually spent |

### 1.2 What follows from that, structurally

These are the load-bearing conclusions. Each one is a constraint you cannot design
around, not a feature you can choose.

**A run is a persisted DAG, not a script.** "Visible node" plus "pause at any stage"
means each step is a database row with a status, not a stack frame. A run that pauses
for a human can pause for three days; it must survive deploys. Anything built as a
sequential function call has to be rewritten the first time someone walks away from
their laptop mid-approval.

**The stages are a graph, not a line.** The avatar pass and the B-roll plan are two
independent branches off the script. Voice, thumbnail and B-roll planning all depend
only on the script and nothing on each other. A line would run them serially for no
reason.

**Gates must sit on the cheap stages.** Approving a brief costs nothing; approving
after B-roll generation costs whatever the shots already burned. So the gate belongs
on the stage that *determines* the spend, not the stage that *incurs* it — which is why
the gates cluster early.

**Publishing needs a different gate shape.** Every other stage can run first and ask
after — a rejected script is just credits. An upload cannot be undone. So the
pre-publish approval has to be its own node that spends nothing and blocks the upload
behind it. Preview the finished video, then publish, is exactly that node.

**Rejection is the training signal.** "Remembers your style, past decisions" plus
gates everywhere means the memory is fed by gate outcomes. An operator typing "too
hypey, cut the questions" is a higher-quality preference label than anything you can
infer from telemetry, and it arrives free.

**A revision must cascade.** If a rejected script did not invalidate the narration
recorded from the old one, the video would ship with audio that does not match the
script. Any gate-and-revise product either implements downstream invalidation or is
quietly broken.

**BYO keys forces a provider abstraction and a credentials vault.** Eight vendors
behind one pipeline, some paid by the user and some by the platform, means routing is
a runtime decision and the platform is holding other people's paid secrets.

**Credits are pre-authorisation, not post-billing.** Generation spends real money
before anything is sellable. You must hold credits before the first vendor call, or
users start work they cannot pay for and you eat the vendor bill.

### 1.3 The number that shapes the whole business

Price an 8-minute video against published vendor rates. At ~6 seconds per shot that is
~80 shots. Generated video runs roughly $0.05–0.09/second; stills are ~$0.04 each;
voice is ~$0.15 per 1,000 characters.

| Stage | Units | Provider cost |
|---|---|---|
| B-roll (⅓ animated, ⅔ stills) | 80 shots | ~$14 |
| Voice | ~6,900 chars | ~$1.03 |
| Thumbnails | 2 | ~$0.08 |
| Script + brief + compliance | — | ~$0.10 |

**B-roll is ~90% of the cost of a long-form video.** Everything else is noise. Three
consequences, all of which this repo implements:

1. The B-roll planner must cap animated shots (here: at most ⅓ of the list) or one
   over-eager plan multiplies the bill.
2. Stills animated with a Ken Burns move are ~10× cheaper than generated video and
   are the correct default. Motion is an exception you justify per shot.
3. At any plausible credit price, a month's allowance buys a small number of
   long-form videos. That is not a pricing mistake — it is what generative video
   costs today. Anything promising "unlimited videos" at a consumer price is using
   stock footage, generating far fewer shots, or losing money.

---

## Part 2 — This implementation

### 2.1 Shape

```
forgecast/
  config.py          settings; `mock` vs `live` provider mode
  models.py          schema: users, channels, memory, runs, nodes, artifacts, ledger
  db.py              engine + session scope (SQLite dev / Postgres prod)
  crypto.py          Fernet envelope encryption for BYO provider keys
  auth.py            scrypt passwords, JWT, request dependencies
  credits.py         pricing table + append-only ledger (reserve → settle → release)
  memory.py          the "learning agent": recall/remember, prompt assembly
  graph/
    spec.py          NodeSpec / PipelineSpec, cycle + dangling-dep validation
    pipelines.py     faceless_longform, faceless_shorts
    engine.py        DAG executor, gates, revisions, cascade invalidation, leases
  providers/
    base.py          five capabilities: llm, voice, image, video, avatar
    registry.py      routing + BYO-key resolution
    mock.py          offline deterministic providers that emit real media
    llm.py           OpenAI, Anthropic (raw HTTP)
    media.py         ElevenLabs, FAL image, FAL video, Runway, HeyGen
    youtube.py       resumable upload, OAuth, mock publisher
  nodes/             handlers: brief, script, thumbnail, voice, broll_plan,
                     shots, avatar, render, compliance, final_review, publish
  render/ffmpeg.py   scene assembly, Ken Burns, PiP, captions, mux
  api/               FastAPI: JSON API, SSE, server-rendered UI, in-process runner
  web/               Jinja templates (node graph drawn from live dependency data)
  worker.py          polling worker
  cli.py             initdb / user / channel / run / demo / worker / serve
```

### 2.2 The pipeline graph

`faceless_longform`, gates marked ◆:

```
◆brief → ◆script ─┬→ ◆thumbnail ─────────────┐
                  ├→ voice ──────────┐        │
                  └→ broll_plan → shots       │
                                    ↓         │
                              render → compliance → ◆final_review → publish
```

Four gates: brief, script, thumbnail, final_review. `shots` — the expensive node —
is deliberately *behind* two gates and is not itself one.

### 2.3 Three decisions worth defending

**Node execution is split into three phases, and handlers never touch the database.**
A single B-roll shot can take four minutes. A transaction held open that long wedges
SQLite and bloats Postgres. So: a short transaction claims the node and snapshots
everything it needs into plain dataclasses; the handler runs with no session at all;
a second short transaction persists output, artifacts, credits, and status. The
consequence — handlers receive a `NodeContext` of plain data and cannot issue queries
— is a feature. It makes every node unit-testable and its inputs explicit.

**`mock` mode is product infrastructure, not a test double.** It emits real PNGs via
Pillow and real MP4/M4A via ffmpeg, so the graph engine, gates, renderer, billing
math, and UI can all be built and demoed without an API key or a cent of spend. It is
seeded on the prompt hash, so a run replays identically. It is also what every paying
user should get as a dry-run mode. The full 57-test suite, including a real 60-second
render, runs offline because of it.

**Credits are an append-only ledger with explicit holds.** Never a mutable balance
column. `create_run` reserves the sum of per-node estimates; each node releases its
own estimate and spends its actual cost as it completes; terminal runs release the
remainder. Every movement carries an idempotency key, so a retried settle cannot
double-charge. Verified end to end: a completed run leaves `granted − spent` and
nothing stranded.

### 2.4 Gates and the memory loop

Two gate shapes, because they are not the same problem:

- **Post-execution review** (brief, script, thumbnail): the node runs, then waits.
  Approve accepts the output; approve with `overrides` patches it in place (edit a
  title without a rerun); reject re-runs the node with the feedback in its prompt.
- **Pre-execution gate** (`final_review` → `publish`): a node that spends nothing,
  assembles the publish payload, and blocks the irreversible action behind it.

Rejecting resets every transitively dependent node — reject the script and the
narration, shot list, shots, and render all go back to pending. Without this the
video ships with audio from the previous draft.

Both outcomes are written to `channel_memories`: rejections at weight 2.0, approvals
at 0.5. On the next run, `memory.prompt_block()` injects them, stage-scoped, into the
system prompt. There is no vector database on purpose — with a few hundred lines per
channel, recency and stage-scoping beat semantic similarity, and the ranking is
inspectable. Swap in embeddings when a channel has thousands of memories.

### 2.5 Provider routing

Every vendor collapses into one of five capabilities. Nodes depend only on the
abstract class, never a vendor SDK. Resolution order: explicit per-run override →
the user's own key → the platform key. In `mock` mode nothing else applies, so no
code path can spend money in development.

Written against raw HTTP rather than vendor SDKs: fewer dependencies, and the request
shape stays where you can reason about its cost.

> **Before switching to `live`:** generative-media APIs change shape more often than
> LLM APIs. The endpoints, model slugs, and polling contracts in `providers/media.py`
> reflect documented public shapes at the time of writing and need verifying against
> current vendor docs. Each vendor is isolated behind one interface, so a breaking
> change costs one file. `mock` remains how you develop.

### 2.6 Cost control in the pipeline itself

- `broll_plan` caps animated shots at ⅓ of the list and downgrades the excess.
- Stills default to Ken Burns rather than generated video (~10× cheaper).
- Media stages degrade instead of dying: a failed animation falls back to its still
  plate, a failed still to a captioned card. A vendor timeout must not lose ten
  minutes of paid render.
- Retries only fire on genuinely retryable errors (429, 5xx, timeouts). A 4xx or a
  failed compliance verdict is terminal — re-asking will not fix it.
- The `/api/pipelines/{name}/estimate` endpoint itemises cost before committing.

### 2.7 Known limits — read this before going to production

Honest inventory of what is skeleton and what is finished.

**Finished and verified**
- Graph engine: gates, revisions, cascade invalidation, retries, stale-lease reclaim
- Credit ledger with holds and idempotency; closure verified end to end
- Full pipeline on mock providers → a real 1920×1080 H.264 + AAC MP4 with captions
- Auth, tenant isolation (cross-user reads and gates return 404), key encryption
- JSON API, SSE live updates, node-graph UI
- 57 tests, all offline

**Skeleton — written, never run against the live vendor**
- `providers/media.py` and `providers/youtube.py`. The code is complete; the API
  contracts need verification. Nothing here has made a paid call.
- HeyGen needs the narration reachable by URL. `_public_url` maps local storage to
  `FORGECAST_BASE_URL`, which only works if the vendor can reach your host. Replace
  with presigned object-store URLs before running avatars in production.

**Deliberately absent**
- **Payments.** `POST /api/credits/purchase` is dev-only and refuses to run outside
  mock mode. Credits must only be minted by a verified Stripe webhook
  (`checkout.session.completed`), keyed on the event id for idempotency — never by a
  request a browser can make.
- **Alembic migrations.** `init_db()` creates tables; the dependency is declared but
  no migration chain exists. Generate one before the first schema change in prod.
- **Object storage.** `/files` serves straight off disk with no per-user
  authorisation — anyone with a path can read any artifact. S3 + presigned URLs
  before launch.
- **Teams/orgs.** One user owns everything. No sharing, roles, or seats.
- **YouTube OAuth callback route.** The client methods (`authorize_url`,
  `exchange_code`) exist; the redirect endpoint that stores the refresh token does not.
- **Rate limiting** on auth and run creation.
- **Analytics feedback loop.** `MemoryKind.performance` exists in the schema but
  nothing writes it. Pulling post-publish retention back into channel memory is the
  highest-value next feature — it closes the loop from published result to next script.

**Operational facts you will hit**
- YouTube uploads cost ~1,600 quota units against a default 10,000/day, capping you
  near **6 uploads per day per project** until you request more. Plan channel scale
  around the quota, not render throughput.
- An unverified Google OAuth app can only upload as `private`. The publish node
  defaults to private accordingly.
- The worker polls Postgres/SQLite rather than using a broker. Correct and cheap at
  this scale; swap in Redis when polling *latency* becomes the complaint.

### 2.8 Build order from here

1. Verify one live vendor per capability, cheapest model first, `provider_mode=live`.
2. Stripe checkout + webhook → the only credit-minting path.
3. S3/R2 artifacts with presigned URLs; delete the disk mount.
4. YouTube OAuth callback + refresh-token storage.
5. Alembic baseline.
6. Analytics → `MemoryKind.performance`.
