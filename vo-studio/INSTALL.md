# Installing VO Studio on your PC

Windows 11. Takes about 30–40 minutes, most of it downloads.

You do **not** need to know Python or Git. Every command below is copy-paste.

---

## Step 1 — Install the four prerequisites

Open **PowerShell as Administrator** (press Start, type `powershell`, right-click
→ *Run as administrator*) and paste these one at a time:

```powershell
winget install Python.Python.3.11
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS
winget install eSpeak-NG.eSpeak-NG
```

If any of those say "no package found", install it from the website instead:

| What | Where | Note |
|---|---|---|
| Python 3.11 | python.org/downloads | **Tick "Add python.exe to PATH"** on the first screen. Easy to miss, and nothing works without it. |
| ffmpeg | gyan.dev/ffmpeg/builds → "release essentials" | Unzip, then add its `bin` folder to PATH |
| Node.js | nodejs.org → LTS | |
| eSpeak NG | github.com/espeak-ng/espeak-ng/releases | Only used by the pronunciation check |

**Now close PowerShell and open a new one.** Installers change PATH and the old
window won't see it.

Check it worked:

```powershell
python --version
ffmpeg -version
node --version
```

Three version numbers = good. Any "not recognized" = that one didn't install or
PATH wasn't updated — reinstall it, tick the PATH box, reopen the window.

---

## Step 2 — Get the app onto your PC

In your browser:

1. Go to **github.com/TheBeastSapro/Test-2**
2. Click the branch dropdown (it says `main`) and pick
   **`claude/voiceover-qc-automation-xh0an3`**
3. Green **Code** button → **Download ZIP**
4. Unzip it somewhere simple — `C:\VOStudio` is ideal. Avoid Desktop and
   OneDrive: OneDrive syncs the whole model cache and paths with spaces cause
   trouble.

You want to end up with `C:\VOStudio\vo-studio\setup.bat` existing.

---

## Step 3 — Run the installer

Open the `vo-studio` folder, **double-click `setup.bat`**.

It will take 15–30 minutes — PyTorch with CUDA is a ~2.5 GB download. Leave it.

It prints `[1/6]` through `[6/6]`. The last step tells you what it found:

```
   torch 2.6.0+cu124 | CUDA True
   GPU: NVIDIA GeForce RTX ____
```

**`CUDA True` and your GPU named = you're set.**

If it says `CUDA False` or `GPU: NONE`, generation will run on CPU at about 10×
slower than realtime — roughly 2 hours for a 12-minute script. Usually means the
NVIDIA driver is old: update it from nvidia.com and run `setup.bat` again.

---

## Step 4 — Sign in with your Claude subscription

Only needed for the Assistant tab. Skip if you just want to render voiceovers.

In PowerShell:

```powershell
claude login
```

A browser opens — sign in with your normal Claude account. That's it. **No API
key, and don't create one.**

> **If setup.bat warned you about `ANTHROPIC_API_KEY`:** you have one set from
> something earlier, and it silently overrides your subscription — meaning the
> assistant would bill an API account instead. Remove it:
> ```powershell
> setx ANTHROPIC_API_KEY ""
> ```
> then close and reopen PowerShell. Setting it to empty isn't enough on its own;
> the launcher also ignores it per-session so you're covered either way.

---

## Step 5 — Start it

**Double-click `run.bat`.** A browser tab opens at `127.0.0.1`.

It's local only — nothing is exposed to the internet.

---

## Step 6 — Your first render

**Voice tab** — upload a reference clip. The best one you have is your own
finished voiceover: cut 8–12 seconds of clean speech out of
`Every Drug Used in War Explained FINAL v11.mp3`, no music, no silence at the
edges. That's what the clone copies.

**Render tab** —

- **Video title** — becomes the output filename
- **Script** — paste it. A line on its own with three words or fewer and no full
  stop is treated as a chapter header (so `Hashish` on its own line works the way
  you already write them).
- **Exaggeration** — leave at 0.5. Above ~0.7 it starts acting.
- Click **Render**

Progress streams into the box. Expect a few minutes for a full script on GPU.

When it finishes you get a player and a file at:

```
C:\Users\<you>\ExplainTory VO Studio\projects\<Title>\<Title> (final).mp3
```

**Read the summary at the bottom of the log.** If it says
`NEEDS AN EAR — N chunk(s) never passed the read-check`, those chunks failed
three takes and the best one was kept. Listen to them before using the file.

---

## Step 7 — The Assistant tab

Type what you want changed, in plain English:

> *"The pauses after commas feel too long, make them shorter"*

It will show you what it plans to change and ask before touching anything. That's
deliberate — it can edit the code that renders your audio, so it asks every time.

The **Permission mode** control:

- **default** — asks before every edit. Leave it here.
- **acceptEdits** — stops asking. Only for a change you've already agreed to.
- **plan** — describes what it would do and changes nothing. Good for "what's
  wrong with this?"

It can't reach the internet and can't touch anything outside the app folder.
Your renders and voice reference are off-limits to it — they aren't in Git and
can't be recovered.

---

## When something breaks

It probably will on the first run — nothing here has been run end-to-end on a
real GPU yet.

| What you see | What it means |
|---|---|
| `'python' is not recognized` | PATH box wasn't ticked. Reinstall Python, tick it, new window. |
| `CUDA False` | Driver too old. Update from nvidia.com, rerun `setup.bat`. |
| `CUDA out of memory` | Chunk too big for your VRAM. Lower `max_chars_per_chunk` from 300 to 200 in `vostudio\config.py`. |
| `ffmpeg not found` | Installed but not on PATH. Reopen the window; if still missing, add its `bin` folder manually. |
| Assistant says the CLI is missing | `npm install -g @anthropic-ai/claude-code` then `claude login` |
| Render finishes but sounds wrong | Send me the log box contents and a 6-second clip of the bad part. |

**Copy the whole log box when you report a problem.** The exact error matters —
guessing at it is how the last session lost hours.
