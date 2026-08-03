# Forgecast

An agent that builds and runs faceless video channels. You talk to it; it does the
work, because the app's operations are its tools.

Paste a YouTube channel and it reads what that channel actually publishes — median
upload length, recent titles, which uploads beat their own cohort — and sets a channel
up from the measurements. Ask what is waiting on you and it says which runs are paused
and on what. Ask for a preview and it builds the timeline before a frame is rendered.

Underneath, every video is still a persisted graph you can watch, pause, revise and
resume: brief → script → thumbnail → narration → B-roll → render → compliance →
publish, with a human approval gate at every decision that matters. **The agent never
approves a gate itself** — approving is what lets the next stage spend, so it presents
what the gate is holding, says what it thinks, and stops.

The chat runs on your own Claude subscription through the Claude Code CLI. There is no
API key in this app.

This is a clean-room build of the AI-YouTube-automation product category, designed
from public product behaviour. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
teardown, the unit economics, and an honest list of what is finished versus skeleton.

## Run it in two minutes

Requires Python 3.11+ and `ffmpeg` on PATH.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env            # defaults are fine: mock mode, SQLite

# one video, end to end, no API keys, no spend
.venv/bin/python -m forgecast.cli demo --topic "Why deep-sea cables keep breaking" --seconds 60
```

That produces a real 60-second 1280×720 H.264 file with narration and burned
captions at `storage/runs/1/render/final.mp4`, and prints the credit accounting.

**Mock mode is the default and it is not a stub.** It emits genuine PNGs and MP4s via
Pillow and ffmpeg, seeded deterministically, so you can develop the entire product —
graph, gates, renderer, billing, UI — without an API key or a cent of spend.

### The web app

```bash
.venv/bin/python -m forgecast.cli serve      # http://127.0.0.1:8000
.venv/bin/python -m forgecast.cli worker     # optional: durable background runs
```

It opens on the chat. Paste a channel link and let the agent set one up, or use the
Long-form / Shorts workspaces to do it by hand. The run page shows the live node graph,
streams the log over SSE, and stops at each gate for you to approve or send back with
notes. API docs at `/docs`.

For the chat you also need the Claude Code CLI, signed in with your subscription:

```bash
npm install -g @anthropic-ai/claude-code
claude          # type /login, finish in the browser
```

Everything else works without it, and **Settings → Claude** says exactly what is
missing when it is. Watch out for a stray `ANTHROPIC_API_KEY` in your environment: it
overrides the subscription and silently bills an API account instead. An empty value
still counts as set. The launcher checks before anything starts.

**Connectors** (Settings → Connectors) hand the agent another service's tools —
NexLev's niche finder and outlier search, Drive, Epidemic Sound. Each takes a server
URL and token from that service and can be reached with a real request before you
trust it.

## Hosting it privately

```bash
./docker/first-run.sh you@example.com     # writes .env, prints your password
docker compose up -d                      # http://localhost:8000
```

Registration is closed by default, media is served through signed expiring URLs, and
the port binds to loopback. [DEPLOY.md](DEPLOY.md) covers that plus a Cloudflare tunnel
for phone access, a VPS with automatic TLS, Postgres, backups, and exactly which parts
of the deploy are verified and which are not.

## Going live

Set real keys and flip the mode. Costs real money from the first call.

```bash
FORGECAST_PROVIDER_MODE=live
FORGECAST_ANTHROPIC_API_KEY=...     # or FORGECAST_OPENAI_API_KEY
FORGECAST_ELEVENLABS_API_KEY=...    # voice
FORGECAST_FAL_KEY=...               # stills + video
FORGECAST_RUNWAY_API_KEY=...        # optional, image-to-video
FORGECAST_HEYGEN_API_KEY=...        # optional, talking-head pass
FORGECAST_ENCRYPTION_KEY=...        # required: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Users can bring their own keys per provider (`PUT /api/provider-keys`); those take
precedence over the platform's and are encrypted at rest.

Check the cost before committing to a run:

```bash
curl "localhost:8000/api/pipelines/faceless_longform/estimate?target_seconds=480"
```

Read [ARCHITECTURE.md §2.7](ARCHITECTURE.md) first — payments, object storage and the
YouTube OAuth callback are deliberately not implemented, and the media adapters have
never made a paid call. Migrations now exist: `alembic upgrade head`, applied
automatically at container start.

## CLI

```bash
forgecast initdb
forgecast user create you@example.com --password secret --grant 5000
forgecast channel create --user 1 --name "Deep Field" --niche space --seconds 480
forgecast run start --channel 1 --topic "Why Betelgeuse keeps dimming"
forgecast run show 1
forgecast run gate 1 script --feedback "Blunter hook, cut the third scene"
forgecast run advance 1 --auto-approve      # skip every gate (testing only)
```

## How it works, briefly

- **A run is a persisted DAG.** Nodes are database rows, so a run paused at a gate
  survives restarts and can wait days for you.
- **Gates sit on the cheap stages.** Approving a brief costs nothing; approving after
  B-roll generation costs whatever the shots burned. Publishing gets its own
  zero-cost gate node, because you cannot un-upload a video.
- **Rejections teach the channel.** Gate feedback is stored per channel and injected
  into later prompts, weighted so a rejection counts for more than an approval.
  Rejecting a stage also resets everything downstream of it.
- **Providers are five capabilities**, not eight vendors: llm, voice, image, video,
  avatar. Nodes never import a vendor SDK, so routing is a runtime decision.
- **Credits are an append-only ledger** with explicit holds: reserve before the first
  vendor call, release each estimate and spend the actual as nodes finish.

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q     # 57 tests, fully offline, ~95s
```

Covers ledger closure, DAG validation, gate pause/approve/revise with cascade
invalidation, tenant isolation, and a full pipeline run that renders a real MP4 and
probes it.

## Licence

Yours. Nothing here is derived from another product's source.
