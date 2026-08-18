# Install VO Studio

**Two steps.** Nothing gets installed on your machine — ffmpeg, Node, espeak-ng
and every Python package land in a `runtime` folder inside this one. No registry,
no Add/Remove Programs, no change to your system PATH. Deleting this folder is
the uninstall.

Setup happens **inside the app**, in a window with a progress bar. There is no
console scrolling pip output at you.

---

## 1. Put the folder somewhere simple

**Any drive.** `C:\VOStudio`, `D:\VOStudio`, `E:\Tools\VOStudio` — nothing
is written outside the folder you unzip to, so put it wherever the space is.
Allow about **10 GB**: ~3 GB of runtime and another ~1 GB of Chatterbox weights
on first render, plus room for your projects.

Three places to avoid, and only these:

- **OneDrive / Dropbox / any synced folder.** It will try to upload several GB
  of model weights, and re-download them on you.
- **A USB stick or network drive.** Not a correctness problem — torch loads
  thousands of small files at startup and it crawls.
- **A drive that is not NTFS.** exFAT USB drives break on the long nested paths
  inside site-packages.

Spaces in the path are fine (`D:\My Tools\VOStudio` works). Move the folder to
another drive later and it keeps working — nothing inside stores an absolute
path.

## 2. Double-click `VO Studio.bat`

A setup window opens. It checks what is already on the machine first and marks
those steps **already installed** — your Python counts, and so does anything a
previous run finished before it stopped. Only what is missing gets downloaded,
and only what is missing moves the bar.

| Step | What | Size |
|---|---|---|
| 1 | Python — an isolated environment built from yours, or a 3.11 download if you have none | 0–11 MB |
| 2 | ffmpeg (static build) | ~80 MB |
| 3 | Node + the Claude Code CLI — only for Claude | ~30 MB |
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

## Signing in for Claude

Only needed for the parts Claude answers — loading a voice, tuning it and
rendering never touch it.

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

**One screen.** Everything happens in the conversation.

**Drop an audio clip into the chat** — that becomes the voice. The best
reference you have is a cut of a voiceover you already delivered: 8–12 seconds
of continuous speech, no music, no long pauses. It tells you the duration and
peak, and warns you if the clip is too short, too long, or clipping.

**Press Render a take** to hear where the voice is starting from, then say what
is wrong in plain English — *"feels bit fast"*, *"too flat"*, *"false pauses"*.
It moves the settings, says which numbers moved, and hands back a new take on
the same words. Repeat until it sounds right, then **Save this voice**.

The dials on the right are draggable if you already know what you want to
change. Nothing saves the profile except the button.

**Paste your script** and it tells you what it will become before spending an
hour on it: the voice and profile it will use, words, sections, chunks, the
chapter headers it found, roughly how long the finished read will be and
roughly how long the render will take. Nothing starts until you press
**Render it**.

A line on its own with three words or fewer and no full stop is a chapter
header. Those get the 0.30 s gap and are exempt from the rate and word-error
checks, which cannot mean anything on one word.

**The render reports chunk 7 of 42** with a real estimate from your own
machine's pace, and the log lands under it. Read the end of it: if it says
`NEEDS AN EAR`, some chunks never passed the read-check and the best take was
kept — listen to those before using the file.

Output lands in `Documents\ExplainTory VO Studio\projects\<title>\`.

> **Do your first render on something short — 30 seconds, not a full video.**
> It tells you in five minutes whether the voice is good enough. A full render
> that turns out unusable costs an hour.

Anything the app does not recognise goes to Claude, along with any screenshot
or clip you attach. Model and *Confirm calls* are in the composer.

---

## ElevenLabs (optional)

Chatterbox is the default and costs nothing — it runs on your GPU and clones
the reference clip. ElevenLabs is there for the two cases where that is not
enough: a script Chatterbox cannot hold, or a job that has to be right first
time and the budget is not the constraint.

Settings → Engine → `elevenlabs`, then set a key and a voice. Or just ask in
the chat — it can list the voices on your account and switch for you.

```
setx ELEVENLABS_API_KEY "your-key"     then reopen the app
```

The environment variable wins over the Settings field. Pasted into Settings
instead, the key sits in plain text in `settings.json` in your Documents
folder — fine on your own machine, wrong for anything shared.

**Two things change when you switch, and nothing else does.** ElevenLabs reads
in one of *its* voices, so your reference clip is not used. And it costs about
**$0.18 per 1000 characters** — a twelve-minute script is roughly $2. The
read-check, the orphan sweep, the comma work and the mastering all run exactly
as before.

The four ElevenLabs dials — Stability, Similarity, Style, Speaker boost — are
in Settings with what each one does. Unlike the Chatterbox numbers, these are
**starting points from the published guidance, not values measured on this
channel.** Tune them the same way: render a take, listen, adjust.

---

## Standard vs Turbo

Settings → Model. **They are not the same model with a speed switch.**

Turbo reads neutrally at exaggeration `0.0` and reference adherence `0.0`;
Standard reads neutrally at `0.5` and `0.5`. Carrying numbers from one to the
other does not mistune the voice slightly — it gives you a different voice.

**Switch models, then re-tune.** Do not copy the settings across.

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
| Claude says it is not signed in | Press **Sign in** in the right-hand panel |

**Copy the line under the progress bar and send it.** The exact error is what is
needed — guessing at it is how time gets burned.
