# Move everything from the cloud to your machine

You've been working in Claude Code on the web. This directory gets your
**repos** and your **chats** onto your own computer so you can keep going
locally.

Two different things, two different mechanisms:

| What | How | Bulk? |
|---|---|---|
| Repos | `git clone` — `clone-all.sh` does both of yours | yes |
| Claude Code **cloud sessions** (your chats) | `claude --teleport` — `teleport.sh` wraps it | no, one at a time |
| claude.ai **chat conversations** (separate product) | Settings → Privacy → Export data | yes, by email |

---

## 1. Prerequisites

```bash
# Claude Code CLI — required for teleport
npm install -g @anthropic-ai/claude-code
claude          # then /login with the SAME claude.ai account as the web sessions

# GitHub CLI — needed for the private repo
brew install gh          # or: apt install gh   |   https://cli.github.com
gh auth login
```

Teleport needs **claude.ai subscription auth**. If you're signed in with an
API key it fails with `Unable to get organization UUID` — run `/login` and
pick the claude.ai account.

On Windows, run all of this inside WSL.

## 2. Clone the repos

```bash
chmod +x clone-all.sh teleport.sh
./clone-all.sh ~/claude-repos
```

Clones the two repos on this account:

- `TheBeastSapro/Test-2` — public. Skills, VO studio, the observation log.
- `TheBeastSapro/Test` — **private**, so `gh auth login` must be done first.

Re-running is safe: existing clones are fetched and fast-forwarded only. A
dirty working tree is fetched but never touched.

Pass `--all` to enumerate every repo your GitHub account can see instead of
the two pinned ones:

```bash
./clone-all.sh ~/claude-repos --all
```

## 3. Pull your cloud chats down

```bash
./teleport.sh ~/claude-repos/Test-2
```

This opens the session picker. Choose a session and Claude Code fetches its
branch, checks it out, and **loads the full conversation history into your
terminal**. From then on that chat lives on your machine.

Straight CLI equivalents, if you'd rather not use the wrapper:

```bash
claude --teleport                 # interactive picker
claude --teleport <session-id>    # one specific session
```

Or from inside a running session: `/teleport` (alias `/tp`), or `/tasks`
then press `t`. Or in the browser: session menu → **Open in › Terminal**,
which copies a ready-made command.

### Four things teleport checks

1. **Clean git state** — commit or stash first. `teleport.sh` offers to stash.
2. **Correct repository** — a checkout of the same repo, not a fork.
3. **Branch pushed** — the session's branch must exist on the remote.
4. **Same account** — the claude.ai account that owns the session.

### Know this before you rely on it

- **There is no bulk download.** Teleport is one session at a time, by
  design. To get all of them locally, teleport each one. Do the sessions
  you actually want to continue.
- **It's one-way.** Work you do in the teleported local session stays local;
  it does not flow back to the session on claude.ai. Run
  `claude /remote-control` in the local session if you still want to steer
  it from your phone.
- **Cloud sessions aren't deleted** by teleporting. They stay at
  claude.ai/code until you archive or delete them.
- **Don't delete a cloud session you haven't teleported.** Deletion is
  permanent and the transcript is not recoverable.

## 4. claude.ai chats (the non-Claude-Code ones)

Those are a different product and teleport doesn't touch them. Export from
**Settings → Privacy → "Export data"** on the web app or the desktop app.
You get a download link by email; the link expires after 24 hours and you
must be signed in to use it. The export contains your conversation data and
your account data.

## 5. Make the local checkout behave like the cloud one

The cloud environment installs things the repo expects. After cloning:

```bash
cd ~/claude-repos/Test-2

# Python dep (headroom)
pip install -r requirements.txt        # or: uv tool install --python 3.13 "headroom-ai[all]"

# The session-start hook must stay executable
chmod +x .claude/hooks/session-start.sh

claude    # plugins in .claude/settings.json install on first run
```

`.claude/settings.json` pulls three plugin marketplaces — `claude-mem`,
`superpowers`, `ui-ux-pro-max` — and the skills under `.claude/skills/` load
straight from the checkout. Nothing else to wire up.

Two notes on what you'll find there:

- `.claude/settings.json` has the `"hooks"` key twice. Both blocks are
  identical so behaviour is unaffected — the second wins — but it's worth
  collapsing to one next time that file is edited.
- `.agents/skills/` and `agent/skills/` hold near-duplicate copies of the
  same skill set that's in `.claude/skills/`. Only `.claude/skills/` is
  what Claude Code actually loads.

## 6. Once you're local

Nothing in a cloud container survives it. `HANDOFF.md` in this repo records
a session where the entire audio toolchain and every generated file were
gone at the next session's start. Locally that stops being a problem — but
the habit is still right: commit what matters.

The observation log at `skill-observations/log.md` was pinned to this repo
root for exactly that reason (see `CLAUDE.md`). Running locally, that
override is no longer load-bearing, but leaving it in place keeps the log in
one place across both surfaces.

## Going the other way

You can start cloud sessions from your terminal too:

```bash
claude --cloud "Fix the flaky test in auth.spec.ts"
```

It clones your current directory's GitHub remote at your current branch, so
push local commits first — the VM clones from GitHub, not from your disk.
