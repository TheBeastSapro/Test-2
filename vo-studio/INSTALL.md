# Install VO Studio

**Two steps.** Nothing gets installed on your machine — ffmpeg, Node, espeak-ng
and every Python package land in a `runtime` folder inside this one. No registry,
no Add/Remove Programs, no change to your system PATH. Deleting this folder is
the uninstall.

Setup happens **inside the app**, in a window with a progress bar. There is no
console scrolling pip output at you.

---

## 1. Put the folder somewhere simple

`C:\VOStudio` is ideal.

**Not** Desktop and **not** OneDrive — OneDrive will try to sync several GB of
model weights, and paths with spaces cause trouble in the toolchain.

## 2. Double-click `VO Studio.bat`

A setup window opens. It checks what is already on the machine first and marks
those steps **already installed** — your Python counts, and so does anything a
previous run finished before it stopped. Only what is missing gets downloaded,
and only what is missing moves the bar.

| Step | What | Size |
|---|---|---|
| 1 | Python — an isolated environment built from yours, or a 3.11 download if you have none | 0–11 MB |
| 2 | ffmpeg (static build) | ~80 MB |
| 3 | Node + the Claude Code CLI — only for the Assistant | ~30 MB |
| 4 | PyTorch with CUDA 12.4 | ~2.5 GB |
| 5 | Chatterbox and the QC stack | ~500 MB |
| 6 | espeak-ng | ~5 MB |
| 7 | Verify, then build `VOStudio.exe` | — |

**Give it 20–40 minutes on a normal connection.** Step 4 is most of it.

> **You already have Python, so step 1 is nearly free.** It is not installed
> into — a separate environment is built from it inside `runtime`. 2.5 GB of
> CUDA PyTorch dropped into your system Python is exactly what this avoids, and
> it would break the next project that wants a different torch.

Close the window at any point and nothing is lost. The next launch re-checks,
shows what is already there, and picks up the rest.

### What you want to see at the end

```
CUDA True NVIDIA GeForce RTX ____
```

**`CUDA True` and your GPU named = it worked.**

If it says `CPU only`, generation still works but runs at about 10× realtime —
roughly two hours for a twelve-minute script. That almost always means the
NVIDIA driver is older than CUDA 12.4 needs. Update it from nvidia.com and open
the app again; it re-checks and only redoes what it has to.

## 3. Open `VOStudio.exe`

Setup builds it as its last step, so it appears in this folder once and stays
there. From then on that is what you open — a real window, no browser, no
terminal, no localhost address to remember.

`VO Studio.bat` exists only because a Windows `.exe` cannot be built anywhere
except on Windows, so the very first launch has nothing else to start from.
After that first run you can ignore it.

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
| `Python was not found` in a console | No Python on PATH — install 3.11 or 3.12 from python.org, tick *Add to PATH* |
| Setup window says a step failed | Read the line under the bar; closing and reopening resumes from there |
| `CPU only` at the end | NVIDIA driver older than CUDA 12.4 wants — update, reopen |
| `CUDA out of memory` | Settings → Max characters per chunk, drop 300 → 200 |
| `ffmpeg failed` | gyan.dev unreachable; reopen, it retries just that step |
| espeak-ng note during setup | Only the pronunciation check is affected |
| Assistant says the CLI is missing | Run the `claude.cmd login` line above |

**Copy the line under the progress bar and send it.** The exact error is what is
needed — guessing at it is how time gets burned.
