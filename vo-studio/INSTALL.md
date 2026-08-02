# Install VO Studio

**Two steps.** Nothing gets installed on your machine — Python, ffmpeg, Node and
espeak-ng all download into a `runtime` folder inside this one. No registry, no
Add/Remove Programs, no change to your system PATH. Deleting this folder is the
uninstall.

---

## 1. Put the folder somewhere simple

`C:\VOStudio` is ideal.

**Not** Desktop and **not** OneDrive — OneDrive will try to sync several GB of
model weights, and paths with spaces cause trouble in the toolchain.

## 2. Double-click `setup.bat`

That is the whole install. It downloads, in order:

| Step | What | Size |
|---|---|---|
| 1 | Python 3.11 (embeddable — no installer, no registry) | ~11 MB |
| 2 | ffmpeg (static build) | ~80 MB |
| 3 | Node + the Claude Code CLI — only for the Assistant | ~30 MB |
| 4 | PyTorch with CUDA 12.4 | ~2.5 GB |
| 5 | Chatterbox, the QC stack, espeak-ng | ~500 MB |
| 6 | Verify, then build `VOStudio.exe` | — |

**Give it 20–40 minutes on a normal connection.** Step 4 is most of it.

### What you want to see at the end

```
   torch 2.6.0+cu124 | CUDA True
   GPU: NVIDIA GeForce RTX ____
```

**`CUDA True` and your GPU named = it worked.**

If it says `CUDA False` / `GPU: NONE`, generation still works but runs on CPU at
about 10× realtime — roughly two hours for a twelve-minute script. That almost
always means the NVIDIA driver is older than CUDA 12.4 needs. Update it from
nvidia.com and run `setup.bat` again; it skips whatever already downloaded.

## 3. Open `VOStudio.exe`

A window opens. No browser, no terminal, no localhost address to remember.

If the exe did not build, `run.bat` does the same thing with a console attached
so you can see errors.

---

## Signing in for the Assistant

Only needed for the Assistant screen — rendering does not use it.

```
runtime\node\claude.cmd login
```

That opens a browser and signs you in with your **normal Claude subscription**.
There is no API key and you should not create one.

> If `ANTHROPIC_API_KEY` is already set on this machine, the app ignores it for
> its own process. That variable silently outranks a subscription login, so
> leaving it active would quietly bill an API account instead of using your plan.

---

## Using it

The app walks you through four steps.

**1 · Voice** — drop in a reference clip. The best one you have is a cut of a
voiceover you already delivered: 8–12 seconds of continuous speech, no music, no
long pauses. It warns you if the clip is too short, too long, or clipping.

**2 · Tune** — press *Render sample*, listen, then type what is wrong in plain
English: *"feels bit fast"*, *"too flat"*, *"false pauses"*. The settings move
and it re-renders. Repeat until it sounds right, then *Save this voice*.

**3 · Script** — paste it. A line on its own with three words or fewer and no
full stop becomes a chapter header.

**4 · Result** — the player plus the full log. Read the end of it: if it says
`NEEDS AN EAR`, some chunks never passed the read-check and the best take was
kept. Listen to those before using the file.

Output lands in `Documents\ExplainTory VO Studio\projects\<title>\`.

> **Do your first render on something short — 30 seconds, not a full video.**
> It tells you in five minutes whether the voice is good enough. A full render
> that turns out unusable costs an hour.

---

## Standard vs Turbo

Settings → Model. **They are not the same model with a speed switch.**

Turbo reads neutrally at exaggeration `0.0` and reference adherence `0.0`;
Standard reads neutrally at `0.5` and `0.5`. Carrying numbers from one to the
other does not mistune the voice slightly — it gives you a different voice.

**Switch models, then re-tune in step 2.** Do not copy the settings across.

---

## When something breaks

It probably will on the first run. Nothing here has been run end-to-end on a
real GPU yet.

| What you see | What it means |
|---|---|
| `Python download failed` | No connection, or a proxy is blocking python.org |
| `CUDA False` | NVIDIA driver older than CUDA 12.4 wants — update, rerun |
| `CUDA out of memory` | Settings → Max characters per chunk, drop 300 → 200 |
| `ffmpeg download failed` | gyan.dev unreachable; rerun, it resumes |
| espeak-ng note during setup | Only the pronunciation check is affected |
| Assistant says the CLI is missing | Run the `claude.cmd login` line above |

**Copy the whole log box and send it.** The exact error is what is needed —
guessing at it is how time gets burned.
