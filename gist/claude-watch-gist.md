# 👁️ Give Claude Eyes — watch any video frame-by-frame

Claude has no native video model. So every "analyze this video" tool just pulls the **transcript** — and
misses everything that's only on screen: the cuts, the text overlays, the visual hook, the b-roll. Half the
meaning of a good video lives in the pixels, not the words.

This skill fixes that. It splits any video into the two things Claude *does* understand — **images + text** —
and hands both over with the timestamps lined up. Claude flips through the frames like a flip-book while it
reads the script, so it knows exactly what's on screen the moment something is said. All local. Zero API cost.

## What you'll install (one-time, ~5 min)

Three free command-line tools:

- **yt-dlp** — pulls the video from almost anywhere (YouTube, Instagram, Loom, TikTok, a direct URL).
- **FFmpeg** — rips frames + a clean audio track out of the video.
- **whisper.cpp** — transcribes the audio locally (free), if the source has no captions.

```bash
# macOS (Homebrew)
brew install yt-dlp ffmpeg whisper-cpp

# grab a small, fast local transcription model (~150 MB, one time)
mkdir -p ~/.claude/models
curl -L -o ~/.claude/models/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```

(Windows/Linux: install `yt-dlp`, `ffmpeg`, and `whisper.cpp` from their repos — same three tools.)

## Step 1 — Install the skill (1 min)

Save the file below as `~/.claude/skills/claude-watch/SKILL.md`, then restart Claude Code. That's it —
Claude now has a `claude-watch` skill it will use whenever you hand it a video URL.

## Step 2 — Use it

In Claude Code, just say:

```
/claude-watch https://www.instagram.com/reel/XXXXXXXXX/
```

or *"watch this video and break down why it works: <url>"*. Claude downloads it, samples the frames,
transcribes the audio, and gives you a scene-by-scene breakdown — hook, cuts, on-screen text, the payoff.

> **The trick that makes it accurate:** sample the **first ~15 seconds at 15 fps** (the hook carries the most
> motion and decides retention), and the rest at 1 frame / 3–4s. One frame every few seconds only catches
> end-states and misses the word-by-word reveals, the fast cuts, and the count-up animations. Dense on the
> hook, sparse on the body.

---

## The skill — copy this into `~/.claude/skills/claude-watch/SKILL.md`

````markdown
---
name: claude-watch
description: Use when the user gives a video URL (YouTube, Instagram, Loom, TikTok, direct link) and wants Claude to actually SEE the video — a scene-by-scene / frame-by-frame breakdown, not just the transcript. Triggers on "/claude-watch <url>", "watch this video", "break this reel down".
---

# claude-watch — see the video, not just the transcript

Claude has no native video model, so this skill splits a video into images + text and reads both with
timestamps aligned. Run every step; never skip the dense-hook sampling.

## Step 1 — Download the video
```bash
mkdir -p /tmp/claude-watch && cd /tmp/claude-watch
yt-dlp -o video.mp4 -f "mp4" "<URL>"
ffprobe -v error -show_entries format=duration -of csv=p=0 video.mp4   # duration (seconds)
```

## Step 2 — Two-stage frame sampling (the important part)
The hook holds the most motion and decides retention — sample it densely; sample the body sparsely.
```bash
# HOOK: first 15s at 15 fps → tiled contact sheets (5 cols x 9 rows = 45 frames = 3s per sheet)
mkdir -p hook && ffmpeg -y -t 15 -i video.mp4 \
  -vf "fps=15,scale=200:-1,tile=5x9:margin=6:padding=4:color=white" -an hook/sheet_%02d.jpg
# BODY: 1 frame / 3.5s across the whole video
mkdir -p body && ffmpeg -y -i video.mp4 -vf "fps=1/3.5,scale=360:-1" body/f_%02d.jpg
```
Read the sheets in order; frame N in the hook is at t = N / 15 seconds (sheet k, cell i → frame (k-1)*45 + i).

## Step 3 — Transcribe the audio (free, local)
```bash
ffmpeg -y -i video.mp4 -ar 16000 -ac 1 audio.wav
whisper-cli -m ~/.claude/models/ggml-base.en.bin -f audio.wav -otxt -of transcript
```
If YouTube has captions, use those (free, exact). Always sanity-check the transcript against the frames —
local models mishear names (they'll hear "Claude" as "plot").

## Step 4 — Read frames + transcript together, then output
Look at the hook sheets and body frames, line them up with the transcript timestamps, and produce:
1. **Transcript** (corrected against what's on screen).
2. **Scene-by-scene breakdown** — for each chapter: time, what's on screen, the on-screen text, the cut.
3. **Why it works** — 2–3 concrete mechanisms (hook structure, cut cadence, the one visual payoff, the CTA).
4. **Steal-the-structure notes** — what to lift into your own video (change the content, keep the structure).

Clean up `/tmp/claude-watch` when done.
````

---

**Want Claude to run workflows like this across your *whole* business** — remembering your projects, your
brand, and your taste every session instead of starting cold? That's what my **get. kits** set up (the
CLAUDE.md + skills + memory system). But this skill alone will already change how you study every video you
save. 🚀

*— Conrad · @buildwith.conrad*
