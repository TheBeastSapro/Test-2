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

The first launch takes a minute or two while it builds its environment. Every launch
after that takes a couple of seconds. A window opens, already signed in.

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
5. **Looks for ffmpeg** and warns if it is missing.

---

## Requirements

### Python 3.11 or newer — required

- **Windows** — [python.org/downloads](https://python.org/downloads). Tick
  **"Add python.exe to PATH"** during setup. That checkbox is the single most common
  reason the launcher cannot find Python afterwards.
- **macOS** — `brew install python@3.12`
- **Linux** — `sudo apt install python3 python3-venv` (the `venv` package is separate
  on Debian and Ubuntu, and the launcher cannot create its environment without it)

### ffmpeg — required for rendering, optional for everything else

Research, scripting, voice and the preview studio all work without it. The render stage
does not. The app shows a banner rather than refusing to start, so you can install it
later.

- **Windows** — `winget install Gyan.FFmpeg`, then reopen the launcher
- **macOS** — `brew install ffmpeg`
- **Linux** — `sudo apt install ffmpeg`

### Node.js — optional

Only for the Remotion render backend. The default ffmpeg backend needs nothing extra.

---

## Running it

Everything is in the window that opens.

- **Channels & runs** — make a channel, start a run, approve at each gate
- **Research** — paste or fetch video statistics, see what genuinely outperformed, turn
  an outlier into a topic
- **Studio** — watch a run *before* it renders: scrubber, per-scene timeline, live plan

Runs pause at decision gates. Approving a brief costs nothing; approving a finished
render costs whatever the shots already burned — so the expensive stages sit behind
gates on the cheap stages that determine them.

### It starts in mock mode

No provider is called and nothing is charged. Runs complete end to end with placeholder
script, voice and visuals, so you can see the whole pipeline before spending anything.

To use real providers, edit `.env`:

```ini
FORGECAST_PROVIDER_MODE=live
FORGECAST_ANTHROPIC_API_KEY=sk-ant-...
FORGECAST_ELEVENLABS_API_KEY=...
FORGECAST_YOUTUBE_API_KEY=...        # research desk: fetch a channel's statistics
```

Restart the app after editing. Keys can also be entered in the app, where they are
encrypted at rest with the key in `.env`.

---

## Command-line flags

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

## Where your data lives

```
forgecast.db          runs, channels, credit ledger, encrypted provider keys
storage/runs/<id>/    scripts, voice takes, stills, renders for each run
storage/motion_presets/  motion presets learned from reference videos
.env                  machine-specific secrets — never commit or copy this
.venv/                the Python environment; safe to delete and let it rebuild
```

To move an install to another machine, copy `forgecast.db` and `storage/` — **not**
`.env`. Let the new machine generate its own secrets, then re-enter provider keys.

To reset completely, delete `forgecast.db` and `storage/`.

---

## Uninstalling

Delete the folder. Nothing is installed outside it and nothing is left in your system
Python, your registry, or your home directory.
