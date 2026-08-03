# Installing Forgecast

Forgecast runs entirely on your own machine. Your scripts, voice takes, renders and API
keys stay on your disk; nothing is uploaded anywhere you did not configure.

---

## The short version

| Your machine | Do this |
|---|---|
| **Windows** | Double-click **`Forgecast.bat`** |
| **macOS** | Double-click **`Forgecast.command`** |
| **Linux** | `./Forgecast.command`, or `python3 launcher.py` |

**That is the only thing you install by hand.** Python has to be there first — it is
what draws the window — and everything else the app fetches itself.

The first launch builds its Python environment (a minute or two), then opens a window
on a setup page listing what is missing and offering to install it: Node.js, the Claude
Code CLI that runs the chat, and ffmpeg on Windows. It all lands in `runtime` inside the
app folder, never on your machine, and shows real progress rather than a scrolling log.

Every launch after that takes a couple of seconds and goes straight to the studio.

One step is left for you, because it cannot be automated: signing in to Claude. Press
**Sign in to Claude** when setup finishes — a terminal opens, you type `/login`, and you
finish in the browser. It is your normal Claude subscription; there is no API key.

To stop it: close the window, or press **Quit** in the app.

---

## What the first launch does

You do not need to do any of this yourself — it is listed so you know what changed on
your machine.

1. **Checks your Python.** 3.11 or newer. If it is older, it stops and says so.
2. **Creates `.venv/`** beside these files and installs the dependencies into it.
   Nothing is installed system-wide; deleting the folder removes everything.
3. **Writes `.env`** with secrets generated on your machine — a session key, an
   encryption key for stored API credentials, and a random password for your local
   account. This file is never uploaded and must not be copied to another install.
4. **Creates `forgecast.db`** (SQLite) and `storage/` for renders.
5. **Opens the setup page** and, if you press Install, downloads Node, the Claude Code
   CLI and (on Windows) ffmpeg into `runtime/`. Skipping is allowed — everything except
   rendering and the chat works without them, and you can come back to `/setup` later.
6. **Removes `ANTHROPIC_API_KEY` from its own environment** if you have one set, because
   it outranks your Claude subscription and would silently bill an API account. Your
   shell keeps it; only the app ignores it.

---

## Requirements

### Python 3.11 or newer — required

- **Windows** — [python.org/downloads](https://python.org/downloads). Tick
  **"Add python.exe to PATH"** during setup. That checkbox is the single most common
  reason the launcher cannot find Python afterwards.
- **macOS** — `brew install python@3.12`
- **Linux** — `sudo apt install python3 python3-venv` (the `venv` package is separate
  on Debian and Ubuntu, and the launcher cannot create its environment without it)

### ffmpeg — for rendering

Research, scripting, voice, the chat and the preview studio all work without it. The
render stage does not.

- **Windows** — the setup page downloads it into `runtime/ffmpeg`. Nothing to do.
- **macOS** — `brew install ffmpeg`
- **Linux** — `sudo apt install ffmpeg`

On macOS and Linux this one is left to you deliberately, rather than unpacked into the
app folder. `brew` and `apt` are how software arrives on those platforms and they put
ffmpeg somewhere the whole machine can use; second-guessing them produces two ffmpegs of
different versions and a bug that only appears in renders.

### The Claude Code CLI — installed for you

The chat is the way into this app, and it runs on **your Claude subscription** — the
same `/login` you already use. There is no API key and you should not create one.

It needs Node.js, which is a second runtime alongside Python. **You do not have to
install either.** The setup page downloads Node into `runtime/node` and uses that Node's
own npm to put the CLI beside it, so the app has its own copy that nothing else on the
machine can change under it. If you would rather do it yourself:

```bash
npm install -g @anthropic-ai/claude-code
claude          # then type /login and finish in the browser
```

Everything else — channels, runs, research, the preview studio — works without it. The
app says plainly whether Claude is connected rather than looking identical either way;
the status is in the sidebar on every page and in full under **Settings → Claude**.

> **One trap, and it costs money quietly.** If `ANTHROPIC_API_KEY` is set anywhere in
> your environment it takes priority over your subscription, and requests bill an API
> account instead of the plan you already pay for. An empty value still counts as set.
> The launcher checks for this before anything starts.

### yt-dlp — reading a channel from a link

**Nothing to do. The launcher installs it.** It is a base dependency, so pasting a channel
link into **Research** works on a first launch: the uploads are read off the public page
with no API key, no quota and no account.

It used to be an optional extra you installed by hand, and the result was that the app
told you to run a pip command to finish an install that had already said it was finished.
An installer that asks you to install something has not installed anything.

yt-dlp does go stale — it tracks a site that changes — so **Settings** lists it with its
installed version and can upgrade it in place, the same as it does the Claude CLI. If
research starts failing on links that used to work, that is the first thing to try.

The public listing has no real publish dates on it, only labels like "2 months ago", so a
date read this way is reconstructed and can be half a month out. Because an outlier is
views per day, that matters for a recent video and barely at all for an old one: each
video is checked on its own, and one whose multiple could fall under the threshold is
reported as a range and marked unreliable instead of as a number that looks measured.
Numbers that came from an API key are measured, and are never marked.

### Node.js for Remotion — optional

Only for the Remotion render backend. The default ffmpeg backend needs nothing extra.

---

## Running it

Everything is in the window that opens.

**The Studio is the chat**, and it is where the work starts. You say what you want and
the agent does it, because it holds the app's operations as tools:

- paste a YouTube channel and it reads what that channel actually publishes — median
  upload length, recent titles, which uploads beat their own cohort — then sets up a
  channel from the measurements
- ask what is waiting on you, and it tells you which runs are paused and on what
- ask for a preview and it builds the timeline before anything renders

The rest of the rail is where you go to *look* at what happened:

- **Long-form / Shorts** — the two workspaces, each with its own channels and runs
- **Research** — score a channel link, or a table you pasted, into ranked outliers; a
  link needs no API key
- **Styles** — editing styles learned from real videos, applied or blended
- **Settings** — Claude, connectors, provider keys, and what will actually be used

Runs pause at decision gates. Approving a brief costs nothing; approving a finished
render costs whatever the shots already burned — so the expensive stages sit behind
gates on the cheap stages that determine them. **The agent never approves a gate on its
own judgement.** It shows you what the gate is holding, says what it thinks, and stops.

### Connectors

A connector hands the agent another service's tools, so it can do the work itself
instead of asking you to paste numbers into a box. **Settings → Connectors** ships with
NexLev, Google Drive and Epidemic Sound; each needs a server URL and token from that
service, and there is a Test button that makes a real request rather than checking the
shape of the string.

This is not the same thing as a provider key. A provider key lets the *pipeline* call a
vendor; a connector lets the *agent* call one.

### It starts in mock mode

No provider is called and nothing is charged. Runs complete end to end with placeholder
script, voice and visuals, so you can see the whole pipeline before spending anything.

Switch to live and add keys in **Settings** — they are encrypted at rest with the key in
`.env` and take effect immediately, no restart. If you would rather edit the file:

```ini
FORGECAST_PROVIDER_MODE=live
FORGECAST_ELEVENLABS_API_KEY=...
FORGECAST_YOUTUBE_API_KEY=...        # measured dates and engagement in research
```

Research reads a channel from a link without that key — `pip install yt-dlp` is enough,
and the publish dates it recovers are approximate. The key replaces them with measured
timestamps and adds like and comment counts.

---

## The command-line tools

Some things belong outside the window — learning a style means measuring video, which
takes minutes and is better watched in a terminal than behind a spinner.

The launcher installs the project into `.venv` rather than onto your PATH, so run
these **from the Forgecast folder** with the venv's own copy. A bare
`forgecast-vision` only works if you have activated the environment yourself.

```bash
# macOS / Linux
./.venv/bin/forgecast-vision  --help
./.venv/bin/forgecast         --help

# Windows
.venv\Scripts\forgecast-vision --help
.venv\Scripts\forgecast        --help
```

**Learn an editing style** from a creator's videos. Several, not one — a single video
is an anecdote, and a style is what survives across their work:

```bash
./.venv/bin/forgecast-vision learn-style ep1.mp4 ep2.mp4 ep3.mp4 --name "Their Look"
```

It prints what it measured, then every departure the upgrade pass made and why. Add
`--raw` to keep exactly what was measured. The result shows up on the Styles tab,
where you can apply it to a channel or mix it with another.

**Render a world map** without a run — free, so iterating on one costs nothing:

```bash
./.venv/bin/forgecast map "Rotterdam" "Suez Canal" "Singapore" --style blueprint
./.venv/bin/forgecast map --list-styles
./.venv/bin/forgecast map --list-places
```

---

## Launcher flags

```
python launcher.py [options]

  --port N            preferred port (default 8765; another is used if taken)
  --window MODE       auto | webview | chrome | browser | none
  --no-window         serve without opening anything; prints the sign-in URL
  --reinstall         reinstall dependencies even if nothing changed
  -v, --verbose       full logs
```

`--window none` is the one to use over SSH or on a headless box.

---

## When something goes wrong

**"Python was not found"** — install it, and on Windows make sure "Add python.exe to
PATH" was ticked. Reopening the terminal after install is sometimes enough.

**"could not create a virtual environment"** — on Debian/Ubuntu, `sudo apt install
python3-venv`.

**"dependency installation failed"** — usually no network access. Run
`python launcher.py --verbose` to see pip's own reason.

**The window opens but shows a login page** — the one-time sign-in link expired, which
happens if the app took unusually long to start. Sign in with the email and password
printed in the console (they are also in `.env`).

**A run is stuck at a gate** — that is the design. Open the run and approve or revise.

**Rendering fails** — check the ffmpeg banner at the top of the app.

**Port already in use** — the launcher picks another automatically. If you want a
specific one, `--port 9000`.

---

## Where you can put it

Anywhere you can write to. There is no install location — the folder *is* the
application, and everything it creates stays inside it.

- **Any drive letter.** `D:\`, `E:\`, a second SSD, an external drive. Nothing is
  hard-coded to `C:`.
- **Paths with spaces.** `D:\My Videos\Forgecast\` is fine.
- **A USB stick or portable drive.** Works, including when it remounts under a
  different letter — the app notices it moved and repairs its own environment on the
  next launch (that launch takes a minute; the ones after are normal).
- **A network share.** The launcher handles a UNC path (`\\server\share\Forgecast`),
  but see the warning below before choosing one.

### Moving an existing install

Move or rename the folder freely, then launch it as usual. The first launch after a
move reinstalls the Python environment — it has to, because the environment records
where the project lives — and then carries on with your database and renders intact.

If you **copy** the folder rather than moving it, launch the copy once before using
it, so it can claim its own environment. Both copies then work independently, each
with its own database.

Do not copy `.env` between installs. Let each one generate its own secrets, then
re-enter provider keys. That file holds the key your stored API credentials are
encrypted with.

### One place to avoid: a network drive

Forgecast keeps its database in SQLite, and SQLite's file locking is unreliable over
SMB and NFS — this is a documented limitation of network filesystems, not of the
app. A run that writes while the share hiccups can corrupt the database.

Keep `forgecast.db` on a local disk. If you want renders on network storage, point
just that at the share:

```ini
FORGECAST_DATABASE_URL=sqlite:///C:/Forgecast/forgecast.db
FORGECAST_STORAGE_DIR=//server/share/forgecast-renders
```

Renders are written once and read back whole, so they are safe on a share in a way
the database is not.

---

## Where your data lives

```
forgecast.db          runs, channels, chats, credit ledger, encrypted provider keys
storage/runs/<id>/    scripts, voice takes, stills, renders for each run
storage/motion_presets/  motion presets learned from reference videos
storage/connectors.json  connector URLs and their encrypted tokens
.env                  machine-specific secrets — never commit or copy this
.venv/                the Python environment; safe to delete and let it rebuild
runtime/              Node, the Claude CLI, and ffmpeg on Windows; safe to delete
```

`runtime/` and `.venv/` are both disposable: delete either and the next launch rebuilds
it. Nothing in them is yours.

To move an install to another machine, copy `forgecast.db` and `storage/` — **not**
`.env`. Let the new machine generate its own secrets, then re-enter provider keys.

To reset completely, delete `forgecast.db` and `storage/`.

---

## Uninstalling

Delete the folder. Nothing is installed outside it and nothing is left in your system
Python, your registry, or your home directory.
