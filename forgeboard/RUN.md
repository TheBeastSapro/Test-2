# Running ForgeBoard on your machine

## What you need

**Node 22.5 or newer.** That's the only hard requirement — the database
(`node:sqlite`) ships inside it, so there's nothing else to install and nothing
to pay for.

```bash
node --version      # want v22.5.0 or higher
```

If it's older, get Node 22 LTS from [nodejs.org](https://nodejs.org), or with
nvm: `nvm install 22 && nvm use 22`.

## Start it

```bash
git clone -b claude/kloudie-dashboard-reverse-engineer-ixfyc4 https://github.com/TheBeastSapro/Test-2.git
cd Test-2/forgeboard
npm install
npm start
```

The `-b` matters: ForgeBoard lives on that branch, and the repository's default
branch is a different one. Cloning without it gets you a checkout with no
`forgeboard/` directory.

Then open **http://localhost:8787** and click **Create one** to make your
account. It's local to your machine — no email confirmation, nothing sent
anywhere.

That's the whole setup. Verified from a clean clone.

## Forge on your Claude subscription

If the `claude` CLI is on your PATH and signed in, Forge uses it — no API key,
no per-token bill. Startup tells you which it picked.

Not installed yet:

```bash
npm install -g @anthropic-ai/claude-code
claude                       # sign in with your subscription
```

Everything else works without it; Forge just falls back to canned replies and
says so.

## Switching on Playground audio

Script Writing and Social Posts already work — they run through Forge, so
they're free. Speech and sound effects need ElevenLabs:

```bash
ELEVENLABS_API_KEY=sk_... npm start
```

Nothing to rebuild. Generated audio lands in Drive as a real file you can play.

## Where your data lives

```
forgeboard/data/forgeboard.db     everything except file contents
forgeboard/data/uploads/          the files themselves
```

Both are gitignored. Back up by copying `data/`; reset by deleting it.

## If something goes wrong

| What you see | Fix |
|---|---|
| `Port 8787 is already in use` | `PORT=8080 npm start` |
| `Node ... is too old` | Install Node 22.5+ |
| `node:sqlite ... refused to load` | `node --experimental-sqlite server/index.js` |
| Forge gives canned replies | Install the `claude` CLI and sign in |
| `tts needs a ELEVENLABS_API_KEY` | Expected — set the key, or use Script Writing instead |

## Checking it yourself

```bash
npm run test:server   # 48 API assertions over real HTTP
npm run test:e2e      # 14 browser assertions, full stack
```
