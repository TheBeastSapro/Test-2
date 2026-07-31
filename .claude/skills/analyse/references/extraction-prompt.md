# Extraction prompt for watch-tool calls

One well-built prompt per video beats five narrow ones: the watch tools run full
multimodal inference per call, so asking for everything at once is both cheaper and
more coherent — the model sees the hook and the CTA in the same pass and can relate
them.

Send this as the `prompt` argument to `watch_instagram_video_and_ask`,
`watch_tiktok_video_and_ask`, or `watch_youtube_video_and_ask`.

## The prompt

```
Analyse this video exhaustively so it can be reverse-engineered. Be literal and
specific. Where you cannot tell something, say "unclear" rather than guessing —
a stated gap is more useful to me than a confident invention.

1. FULL VERBATIM TRANSCRIPT of all speech, in order, with approximate timestamps.
   Do not clean up filler words, false starts, or grammar.

2. HOOK: quote the exact opening words before the video establishes its promise.
   State the timestamp where the hook ends and the body begins. Describe what is
   visually on screen during those opening seconds.

3. ON-SCREEN TEXT: every caption, title card, label, arrow, or overlay. Quote each
   exactly and give its rough timing and screen position. Note whether captions
   are burned in, and if so their style (word-by-word highlight, phrase, full
   sentence), position, colour, and weight.

4. VISUAL LAYOUT: framing and subject (face / hands / screen / product). Shot
   changes and roughly how many cuts. Zoom or camera-move pattern. Transition
   types. Colour and lighting. Any recurring branding element. Aspect ratio.

5. STRUCTURE: break the video into its beats with timestamps, and for each say
   what job it does — establishing credibility, giving context, explaining the
   mechanism, showing proof, handling an objection, calling to action.

6. TOOLS, BRANDS, PRODUCTS: name everything visible or mentioned, including any
   UI, app, or website shown on screen, and what is being done with it.

7. CALL TO ACTION: quote it exactly, say when it appears, and what the viewer is
   asked to do.

8. NUMBERS AND CLAIMS: any figure, metric, statistic, price, or specific claim
   stated, quoted exactly.

9. AUDIO: music presence and mood, sound effects, whether speech is direct-to-
   camera or voiceover.

10. Video duration in seconds.
```

## Adapting it

**YouTube, clipped watch.** When you have already pulled the transcript via
`get_video_transcript`, drop section 1 and add a line telling the tool the clip
boundaries so it does not describe the video as if it ended at 30s:

```
You are seeing only the first 30 seconds of a longer video. Analyse what is
present and do not speculate about what follows.
```

**Music-only or no-speech video.** Add:

```
There may be no speech. If so, treat the on-screen text as the script and
transcribe it in order with timings instead.
```

**A specific user question.** When the user asked something particular ("what's
his editing style", "why does the hook work"), append their question as an extra
numbered section rather than replacing the structure. Keeping the standard sections
means the output still slots into the batch dataset; dropping them to answer one
question makes that video incomparable to the rest.
