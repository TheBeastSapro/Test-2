---
name: analyse
description: >-
  Reverse-engineer social media videos into structured intelligence. Given one or
  many Instagram Reel, TikTok, or YouTube URLs, produces a per-video breakdown —
  full transcript, format, topic and angle, 7-section storytelling structure, hook
  analysis, visual layout, CTA, and pace metrics (duration, word count, WPM) — plus
  cross-video trend, pattern, and insight synthesis when given more than one URL.
  Use this whenever the user pastes social video links and wants to know why the
  content works, or asks to analyse, break down, deconstruct, study, or
  reverse-engineer a video, a creator's style, a hook, a format, or a batch of
  saved/swiped videos. Trigger it even when the user just drops URLs with a terse
  instruction like "analyse these", "what's the pattern here", "break this down",
  or "why did this go viral" — and for research questions about what is working in
  a niche where the evidence is a set of video links.
---

# Analyse

Turn raw social video URLs into structured, comparable, reusable content
intelligence.

The value is not the transcript — anyone can get a transcript. The value is that
every video comes out in the **same shape**, so ten videos can be stacked against
each other and the pattern becomes visible. Hold that in mind throughout: you are
producing rows in a dataset, not essays.

## Two modes

| URLs given | Mode | Produce |
|---|---|---|
| 1 | Single | One video report + its JSON |
| 2+ | Batch | Every video report + JSON, **then** a synthesis pass |

Batch is where the real insight lives. Never skip the synthesis when given more
than one URL, even if the user only said "analyse these" — cross-video patterns
are the whole reason for pasting several links at once.

## Workflow

### 1. Parse and route

Extract every URL from the user's message. They arrive pasted in bulk, often one
per line, sometimes with tracking junk (`?utm_source=...&igsh=...`) — strip query
strings before use.

Route by platform:

| Platform | URL shape | Tool |
|---|---|---|
| Instagram | `/reel/<code>/`, `/reels/<code>/`, `/p/<code>/` | `watch_instagram_video_and_ask` |
| TikTok | `/@user/video/<id>`, `vm.tiktok.com/<code>` | `watch_tiktok_video_and_ask` |
| YouTube | `watch?v=`, `youtu.be/`, `/shorts/` | text tools first — see below |

If a URL is a platform you have no tool for, or is an image post / carousel /
Story, say so plainly in the report and move on. A partial batch with one honest
gap beats a batch with one invented entry.

### 2. Gather — cheapest sufficient source

**Instagram and TikTok** have no transcript API, so one multimodal watch call per
video does everything. Send the extraction prompt from
`references/extraction-prompt.md`.

**YouTube is different and it matters.** `watch_youtube_video_and_ask` runs full
multimodal inference and is expensive; a 40-minute video costs many times what the
text tools cost. So:

1. `get_video_transcript` (videoId) → timestamped transcript
2. `youtube_video_details` (video_id) → duration, views, likes, comments, title,
   description, tags
3. Only then, for the visual half, `watch_youtube_video_and_ask` with
   `startOffset: "0s"` and `endOffset: "30s"`

That clipped watch is the deliberate trade. Hook analysis and visual-style
identification need eyes, but they need eyes on the *opening*, where the hook and
the visual grammar are both established. The transcript covers the other 39
minutes for free. Widen the clip only when the user asks about something specific
later in the video, and say in the report which span you actually watched.

For YouTube Shorts (under ~60s) just watch the whole thing — the clip trick saves
nothing.

### 3. Analyse

Read `references/frameworks.md` before your first analysis of a session. It holds
the taxonomies — hook types, format types, the 7-section structure, visual-layout
vocabulary — that make outputs comparable. Free-form adjectives ("engaging",
"punchy") destroy comparability; a fixed vocabulary creates it.

Compute pace metrics with the bundled script rather than by hand, because manual
word counts drift and WPM is the number people actually act on:

```bash
python3 scripts/metrics.py pace --words <word_count> --duration <seconds>
# or pipe the transcript directly:
python3 scripts/metrics.py pace --duration 47 --transcript-file transcript.txt
```

### 4. Write the per-video output

Two artefacts per video, both required:

- **Markdown report** following `assets/report-template.md` — for the human
- **JSON** following `references/output-contract.md` — for everything downstream

The JSON is not optional bookkeeping. It is the interface: a website, a database,
a batch comparison, or a later skill all consume it, and a field renamed on a whim
breaks them silently. Keep to the contract.

Write files to `analysis/<platform>-<video_id>.md` and
`analysis/<platform>-<video_id>.json` unless the user asks for somewhere else.

Validate before you finish:

```bash
python3 scripts/metrics.py validate analysis/instagram-DZU1D_8OI62.json
```

### 5. Synthesise (2+ URLs)

Read `references/batch-synthesis.md` and follow it. The short version: a pattern
is a claim about frequency, so every pattern carries a count (`7/9 videos`) and
per-video evidence. Anything you can only point to once is an observation about
one video, not a pattern.

Write to `analysis/batch-<slug>.md` and `analysis/batch-<slug>.json`.

Count prevalence with the script instead of eyeballing it:

```bash
python3 scripts/metrics.py batch analysis/*.json
```

## What separates a good analysis from a useless one

**Quote, don't paraphrase.** "Uses a curiosity hook" is worthless. `"Most people
don't know this, but you can just type /analyze into Claude"` — 0.0–3.2s,
contrarian + capability-reveal — is usable. Every judgement in the report should
be traceable to something you can point at.

**Separate what you saw from what you inferred.** "Captions are burned in, centred,
word-by-word highlight in yellow" is observation. "The word-by-word highlight is
doing the retention work in the first three seconds" is inference. Both belong in
the report; conflating them makes the whole thing untrustworthy. The
`confidence` block in the JSON exists for exactly this, and low confidence stated
plainly is more useful than false precision.

**Score hook–payoff alignment honestly.** The hook promises something; the body
either delivers it or does not. This gap is the single most actionable thing in the
analysis — it is where a creator's content quietly loses people — so do not
flatter the video. If the hook promises "every secret in that video" and the body
delivers a product ad, say that.

**Answer "so what".** Close every report with what is actually reusable. The
`replication` block asks for `what_to_steal` (transferable mechanics) versus
`what_not_to_steal` (things that only work because of that creator's face,
audience, or numbers). A breakdown nobody can act on was decoration.

## Handling awkward cases

**Private, removed, or region-locked video.** The watch tool will fail. Record the
URL in the report with `status: "unavailable"` and the reason. Do not substitute a
different video.

**No speech** (music-only, text-on-screen only). Transcript is legitimately empty.
Set `word_count: 0`, `words_per_minute: null` — not 0, which reads as "someone
talked very slowly" — and analyse the on-screen text as the script, noting the
substitution.

**Very long video** (podcast, stream). Do not attempt a full 7-section structure
across two hours; it will be mush. Analyse the opening as its own unit, tell the
user that is what you did, and offer to analyse specific segments with
`startOffset`/`endOffset`.

**A big batch** (10+ URLs). Watch calls are the cost and the latency. Tell the user
the count up front, work through them, and if any fail keep going — report the
failures in the synthesis rather than aborting the batch.

## Optional: persisting to a swipe file

For **YouTube** items the NexLev swipefile can store the video for later research:
`list_swipefile_folders` for a real `folderId`, then `save_to_swipefile`. Forward
the metadata already in hand from `youtube_video_details` so the catalog entry is
populated.

Two honest limits: the swipefile is YouTube-only, so Instagram and TikTok
analyses live only in your output files; and `get_swipefile_folder_insights`
returns just the share count — it does no analysis. Cross-video insight comes from
step 5, not from a tool.

Only save when the user asks. Writing to their saved research uninvited is a
surprise.

## Bundled resources

| File | Read it when |
|---|---|
| `references/frameworks.md` | Before your first analysis — the taxonomies |
| `references/extraction-prompt.md` | Composing a watch-tool call |
| `references/output-contract.md` | Writing JSON, or wiring a consumer to it |
| `references/batch-synthesis.md` | 2+ videos, before synthesising |
| `assets/report-template.md` | Writing the markdown report |
| `scripts/metrics.py` | Pace metrics, JSON validation, batch prevalence |
| `examples/instagram-DZU1D_8OI62.{md,json}` | A complete worked pair, if you want to see the standard before writing your own |
