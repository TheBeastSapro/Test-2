# 👁️ Give Claude Eyes — watch any video frame-by-frame

A Claude Code skill that lets Claude *see* a video (every cut, every on-screen detail), not just read its
transcript. All local. Zero API cost.

---

## Why this exists

Claude has no native video model. So every "analyze this video" tool just pulls the **transcript** — and
misses everything that's only on screen: the cuts, the text overlays, the visual hook, the b-roll. Half the
meaning of a good video lives in the pixels, not the words.

This skill fixes that. It splits any video into the two things Claude *does* understand — **images + text** —
and hands both over with the timestamps lined up. Claude flips through the frames like a flip-book while it
reads the script, so it knows exactly what's on screen the moment something is said.

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

Copy [`.claude/skills/claude-watch/SKILL.md`](.claude/skills/claude-watch/SKILL.md) from this repo to
`~/.claude/skills/claude-watch/SKILL.md`, then restart Claude Code:

```bash
mkdir -p ~/.claude/skills/claude-watch
curl -L -o ~/.claude/skills/claude-watch/SKILL.md \
  https://raw.githubusercontent.com/TheBeastSapro/Test-2/main/.claude/skills/claude-watch/SKILL.md
```

That's it — Claude now has a `claude-watch` skill it will use whenever you hand it a video URL.

(If you clone this repo and run Claude Code inside it, the skill is picked up automatically from
`.claude/skills/` — no copying needed.)

## Step 2 — Use it

In Claude Code, just say:

```
/claude-watch https://www.instagram.com/reel/XXXXXXXXX/
```

or *"watch this video and break down why it works: \<url\>"*. Claude downloads it, samples the frames,
transcribes the audio, and gives you a scene-by-scene breakdown — hook, cuts, on-screen text, the payoff.

> **The trick that makes it accurate:** sample the **first ~15 seconds at 15 fps** (the hook carries the most
> motion and decides retention), and the rest at 1 frame / 3–4s. One frame every few seconds only catches
> end-states and misses the word-by-word reveals, the fast cuts, and the count-up animations. Dense on the
> hook, sparse on the body.

## What you get back

For every video, the skill produces:

1. **Transcript** (corrected against what's on screen).
2. **Scene-by-scene breakdown** — for each chapter: time, what's on screen, the on-screen text, the cut.
3. **Why it works** — 2–3 concrete mechanisms (hook structure, cut cadence, the one visual payoff, the CTA).
4. **Steal-the-structure notes** — what to lift into your own video (change the content, keep the structure).

---

*— Conrad · @buildwith.conrad*
