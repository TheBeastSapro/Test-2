# Automated Edit Pipeline (script + VO + approved images -> finished cut)

*Created 2026-08-07. Companion to `claude/video-qc-workflow.md` (which grades a finished cut) and `claude/editor-brief-2026-07.md` (the style standard being encoded). This doc records what an automated editing pipeline can and cannot do for this channel, and where the human still has to stand.*

## The honest capability split

| Stage | Can be automated | Notes |
|---|---|---|
| Timeline assembly, shot in/out, Ken Burns on every asset | **Yes, fully** | Nothing is ever static; the rule is enforced in code, not remembered |
| Keyword pops synced to the exact spoken word | **Yes, fully** | Force-align the VO with faster-whisper `word_timestamps=True`, then anchor pops to words, not to seconds |
| Icon language (stick figure, red X, arrow, warning) | **Yes** | Drawn as vectors, spring-animated in |
| Section title, creature card punch-in, roster grid | **Yes** | Same layout every section by construction, so title/font/case drift cannot happen |
| SFX placement, ducked bed, master to spec | **Yes** | Every cut and every pop gets a sound automatically |
| Measured QC and self-correction | **Yes, and this is the real advantage** | The renderer runs the QC pass on its own output and re-cuts until it clears the bar |
| **Sourcing canon creature images** | **No** | This is the whole bottleneck. See below |
| Canon design calls (which Mimic? which Horned Serpent?) | **No** | Owner-only |
| Judging whether a gag is in register | **Partly** | Rules can ban licensed IP and real people; taste still needs a human |

## The bottleneck is assets, not editing

Every canon failure in this channel's QC history traces back to an editor choosing images without an approved set. The pipeline makes that worse if unaddressed, because a machine will place a wrong image with perfect timing.

The fix is the process fix already flagged as highest-leverage in `claude/video-qc-workflow.md`: **lock a per-creature approved image shortlist before the edit starts.** In the automated pipeline this becomes a hard gate. The renderer refuses to run without a `materials/<creature>.json` shortlist, and every image in it carries a recorded source URL and a written description that gets diffed against the narration line it plays under.

Sourcing runs on the owner's machine via the Fandom MediaWiki API (`action=parse&prop=images` on a creature's `/Gallery` page returns filenames in page order; `generator=images&prop=imageinfo` returns the real asset URLs). Live-tested against `trevorhenderson.fandom.com`. Note that official galleries are not clean: the Cartoon Cat gallery contains a wallpaper-site scrape. The human tick-off is not optional.

## What was built and proven (2026-08-07)

A 62-second Sewer Spider section (from `claude/script-trevor-cannot-survive-v4.md`) was cut end to end from script + generated VO + Epidemic bed and SFX, with procedural placeholder plates standing in for canon art. Two engines:

- **v1, ffmpeg + Python/PIL.** Renders in ~3 min. Portable, no browser. Lower ceiling on compositing.
- **v2, Remotion (React).** Renders in ~13 min headless. Spring easing, real glitch compositing, full-bleed cinematic push-ins. This is the recommended engine.

### Measured result (v2, against `claude/video-qc-workflow.md` benchmarks)

| Check | Result | Verdict |
|---|---|---|
| Motion, whole frame, avg % change per 0.5s | 12.8% | Below the 22% bar, see note |
| Motion measured **inside the image box** | 22.1% | On benchmark |
| Motion during full-bleed spans | 30.0% | Above Vu's 25.1% best |
| Dead zones >= 4s | 0 | Green |
| Longest hold on one asset | 3.9s | Green |
| Integrated loudness | -15.03 LUFS | Green |
| True peak | -1.44 dBTP | Green |
| LRA | 3.00 LU | Borderline, far better than the 1.9 that failed |
| Cuts carrying an audio transient within 0.6s | 100% | Green (small sample) |
| Video bitrate | 13.9 Mbps | Green |
| Keyword pops, count and spelling | 9/9, 9/9 | Green |
| Duration vs authored sheet | exact | Green |

**Important calibration note.** The whole-frame motion benchmark is not directly comparable across layouts. A boxed white-canvas layout puts ~59% of the frame under static white, so it caps around 40% by construction. Vu's 22-25% comes from full-bleed cinematic composites. Judge a boxed cut on in-box motion, or raise the number the legitimate way (more deliberate cinematic push-ins, which the brief already allows), never by adding jitter or grain.

## Lessons that cost time (keep these)

- **Single-pass dynamic `loudnorm` plus a pre-limiter is what crushes LRA.** Use a two-pass **linear** loudnorm: measure, then apply with the `measured_*` values and `linear=true`. This is the direct fix for the over-limited-mix failure.
- **`-shortest` on the mux silently truncates the picture** to the audio length. Use an explicit `-t <duration>`. It cost 0.63s off the end of a cut and hid a dead audio tail.
- **CRF alone gives a terrible bitrate on flat white-canvas content** (1.6-1.9 Mbps at CRF 16-17). Use explicit ABR. This is the same trap that produced the 0.87 Mbps export.
- **In a browser renderer, animate `transform: translate3d/scale`, never `width`/`left`.** Chrome snaps layout to device pixels and emits duplicate frames on slow moves, which reads as a frozen shot.
- **OCR misses white-on-dark text.** Global binarization drops pops sitting inside a dark image box. Run a second inverted bright-mask pass over the content box, at 2 fps not 1 fps, or the QC will falsely report missing pops.
- **Whisper hallucinates on a dense bed.** It inserted two words that were never spoken in a 61s VO. Always confirm a suspected gap with an RMS-per-0.5s analysis before acting on it.

## Handoff

The full build spec for running this on the owner's machine is the Claude Code packet delivered 2026-08-07 (11.5k words): repo layout, the asset-sourcing stage, edit-sheet schema and validator, render and audio chains, the self-QC loop, the kickoff prompt, a repo `CLAUDE.md`, and six slash commands.
