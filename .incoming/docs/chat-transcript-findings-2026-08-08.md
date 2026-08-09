# Findings mined from the full chat transcript (21 Jul to 8 Aug 2026)

*Created 2026-08-08 from a 69-page / 34,669-word export of the Cowork chat log. Everything here was said in chat and never written to a project doc. This file is a RECORD of what was said, not a decision. Where it contradicts a live doc, the conflict is flagged rather than resolved. Resolve the conflicts in the doc that owns them.*

---

## 1. FOUR CONFLICTS WITH LIVE DOCS (resolve these first)

### CONFLICT 1 — house style. The big one.
`claude/editor-brief-2026-07.md` says: *"Our editing reference is **Ficknime**... White canvas throughout. Images sit boxed/centered, not stretched full-screen, EXCEPT for deliberate cinematic moments."*

The owner overrode this on **23 Jul 3:21 PM**, after writing *"I liked the Vu more than Abel which is clean and engaging"*:

> "Abel is editing literal Ficknime (white canvas, floating creature, icon soup) while your taste, and the cleaner-looking channel, is M Simplified (creature composited into scenes, constant title, captions layered on, no corner clutter). That's a house-style decision, and I'd lock it in: **your channel is cinematic-integrated, M Simplified-leaning, not busy-white-canvas Ficknime.**"

Instruction actually sent to Abel: *"Lean into full cinematic scenes over the white-canvas look... let the white-canvas explainer frames be the exception, not half the section."*

It was offered for the doc five times across 23-24 Jul and never confirmed, so the brief still says the opposite and the brief is what new editors receive. **This inverts the default layout: composited full-frame scenes are the default, boxed white canvas is the exception.**

### CONFLICT 2 — image sourcing
Brief: *"Creature images come ONLY from the creature's fandom wiki gallery or the creator's own accounts... Fan art, game models, and AI re-renders are off-limits."*
Owner, **21 Jul 2:19 PM**: *"I recommend dropping the 3rd fix because it's good."* Fan art is tolerated. The only hard rule since then is the one in `editor-evaluation-2026-07.md` item 7: **on-screen anatomy must never contradict the narration line it plays under.**

### CONFLICT 3 — hold duration
Brief says *"never hold one asset longer than 8 seconds."* Every operative decision in the log uses **never more than 4 seconds on one unchanged frame**. The 8s figure is dead.

### CONFLICT 4 — corner mascot
**23 Jul 3:21 PM:** *"Neither M Simplified nor Ficknime uses a corner creature. Ever. Their title lives top-center and the corner stays empty. A little creature pinned in the corner is a small-faceless-channel tell, and on your cinematic scenes it reads as a sticker pasted over the shot. It also fights the eye. Cut it completely."* Banned outright, not "fix the asset."

---

## 2. SPECS PRECISE ENOUGH TO PROGRAM

### Staged reveal (the most repeated correction in the whole log)
The rule, 21 Jul 7:59 PM: *"they stage the same scene as multiple shots: wide 2-3s → creature visibly rises → cut to close-up → back wide with shake."*
Refined to durations, 21 Jul 8:54 PM: *"wide shot 2-3 sec → the skull visibly rises above the trees (fast, I should SEE it move) → cut closer as it turns toward the car → screen shake on the bone-crack line. Never stay on one unchanged frame longer than 4 seconds."*
**One persistent background is correct. One persistent SHOT is the failure mode.** Same pattern on the Mimic (27 Jul): head over the wardrobe, then an arm, then the full body sliding out, 4 discrete element reveals in one plate over ~4s.

### Always-on text layer (new rule, not in the brief)
23 Jul 3:21 PM: *"The title stays top-center on every single frame, even the cinematic scenes, and there's always a keyword caption layered on top synced to the narration. **No frame is ever empty or text-free.**"*
Placement: captions go in the dead space of the frame. *"Add a short keyword caption in the empty space synced to the voiceover, not just the title up top."*

### Icon lists are word-synced, never pre-assembled
23 Jul 3:10 PM: *"Around 0:29 to 0:34 the four icons all sit on screen together for about 5 seconds. Pop them in one at a time synced to each word in the voiceover instead."* For a VO list of N items: N pop-ins anchored to the N spoken nouns.

### Two content bans
- **No blank text-only cards.** 27 Jul: *"three blank white cards with only a red sentence and no image at all... No competitor does that."* Fix: keep the scene on screen and pop the text over it.
- **Pops are keywords, not sentences.** *"'That delay is the weapon' is too long. Use short keyword pops like DELAY, NO WARNING, NO CLEAR TARGET."*

### Multi-image layouts
2-up or 3-up grid, same size, same border. Never ad hoc.

### Section transition cycle (fuller than the doc version)
Roster grid cold open → punch-in to cell 1 → section → back out to roster grid → punch-in to cell 2 → repeat. 21 Jul 11:51 PM: *"show the grid of all the video's creatures at the very start, then zoom into whichever card is next each time a new section starts. That turns every section change into a little reveal instead of a hard cut."*

### Export bitrate, as told to editors
23 Jul 3:32 PM: *"push the bitrate up to around **10 to 15 Mbps at 1080p**, since the dark scenes need more data than the white-canvas frames. If the original images themselves are low resolution, grab higher-res versions too, because a higher export alone won't sharpen a soft source."*

### Measured timing model from the shipped 9:42 video (24 Jul)
Sections cluster at **62-74s**. Mid-roll CTA is **11 seconds, after creature 3** (03:27-03:38). The finale runs long (94s) because it absorbs the outro.

| Section | Start | Length |
|---|---|---|
| Long Horse | 00:00 | 70s |
| The Fetid King | 01:10 | 69s |
| Man With the Upside-Down Face | 02:19 | 68s |
| **Mid-roll CTA** | **03:27** | **11s** |
| Siren Head | 03:38 | 68s |
| The Wandering Faith | 04:46 | 66s |
| The Wandering Doom | 05:52 | 74s |
| Behemoth | 07:06 | 62s |
| Cartoon Cat | 08:08 | 94s incl. outro |

Mid-roll CTA construction: typed text with a red keyword, a screaming-celebration meme, a "MISSION ACCOMPLISHED" banner.

### Whole-video profile of that cut (Vu, never logged to a QC doc)
9:42 total · **zero static stretches over 4s across the whole runtime** · **26% average visual change per second** · **10.2 Mbps** · audio -16 dB mean.

---

## 3. COMPETITOR TEARDOWNS (frame-level, nowhere else in the project)

**Ficknime, "Every Doctor Nowhere Monster Explained in 9 Minutes", Locust opening, first ~60s:**
> "the creature is one PNG cutout reused across ~16 distinct composited scenes: on a wood-panel wall, inside a TV frame, next to stick-figure victims in a cartoon neighborhood, behind cracked glass, then literally breaking 'out' of the TV layer. The story advances by additive layering: same creature, new background, plus stick figures and icons stacking in. Motion is simple but constant."

Their explanation beats use the same cutout, not full artworks: *"The full standalone image barely exists in their language."*

**M Simplified, "Trevor Henderson Biggest Giants Explained in 9 Minutes", Behemoth opening, first ~30s:**
> "6 scenes, and the smarter trick: they reuse the same background while the creature layer changes. Stick figures on a mountain → the creature's head slides up from behind the peaks → boulder PNG slides in as foreground → red-tinted sky for the climax. One location, staged reveal, escalating layers. **They even tint the cutout to match the sky.**"

Asset economy: cutout composites carry story beats; full-screen environmental art or stock footage for atmosphere; white-canvas infographics for numbers. *"Each one has a job, usually 2-4 seconds, then back to the layered language."*

**The two study references sent to editors:** M Simplified Biggest Giants, first 30 seconds. Ficknime Doctor Nowhere, first minute.

---

## 4. PACKAGING SPEC (absent from the project entirely)

Description template used on the 9:42 upload, built to match an M Simplified reference:

```
[Video Title]
Like, subscribe and activate the bell!

— TIMESTAMPS —
00:00 [Creature 1]
...
______________________________

— DISCLAIMER —
This video is made for entertainment and educational purposes only. Some details may be
simplified, dramatized, or not fully accurate for storytelling clarity.
My goal is simply to spark your curiosity and encourage you to explore these topics further
through your own research and trusted sources.
______________________________

[3-4 sentence lore summary paragraph]
```

- Timestamps list **creatures only**; the mid-roll CTA is deliberately not listed.
- The disclaimer is load-bearing: it is what covers the deliberately inflated 800,000 M Behemoth label.
- **Category: People & Blogs** (Fickyep, M Simplified and Prumhy all upload under it, confirmed from live data, not Entertainment).
- Language English; **"No, it's not made for kids"** so comments stay on.
- Tags capped at ~8 at owner's request. Fickyep's pattern: one `[creature name] explained` tag per roster creature plus a few topic tags.
- **Hashtags: the three biggest competitors (1.5M-2.7M views) use ZERO hashtags.** Only the smaller 400-560K TTS channels use them.

---

## 5. RETENTION

**Every retention figure in the log is modeled, never measured against real Analytics.** Stated explicitly twice. Validating them against the real curve was proposed 24 Jul and never done.

Benchmarks: **65-75% at 0:30** for a good video in this niche; **35-45% average view duration** for a 9:42 explainer.

Measured hook failure modes and their modeled cost at 0:30:

| Failure mode | Measured | Cost at 0:30 |
|---|---|---|
| One 14s static wide shot in the hook | 0-3% frame change per 2s | ~45-55% (worst tested) |
| Rotating unrelated stills, no motion | ~4s cadence, 6s frozen at 0:08 | ~62% |
| Correct cadence, wrong palette (sunny clip-art hook) | 2-4s throughout | ~60% |
| Same, night-recolored | luminance L166 → L53 with anchors | ~72% |
| Single asset zoomed three ways for 21s | 0:05-0:26, zero variety | ~55-60% |

Two findings that drove decisions:
1. **Shape beats endpoint.** Two cuts finished within 3 points of each other at 0:70, but one bled steadily throughout because nothing moved, and *"over a full 9-minute video that static texture compounds section after section."* Rank on texture, not on the final number.
2. **A palette recolor was worth ~12 retention points at 0:30 and cost one pass.** *"His flaw is in his assets, the other's flaw is in his hands."*

Three named drop-risk windows to check against the real curve when it exists: 0:03-0:06 (opening still at brightness 27/255, *"a small brightness lift here has more retention value than anything else in the video"*), 3:27-3:38 (mid-roll CTA, a step down here is normal), 4:45-6:00.

---

## 6. EDITORS: COMMERCIAL AND WORKFLOW FACTS

**No rate is quoted by any editor anywhere in 34,669 words.** Rate and turnaround were asked for four separate times and never arrived.

Standing rule agreed 21 Jul 9:26 PM: *"no full-video payment commitments until a complete, fixed section is in hand... Whoever crosses that line first with a sane quote gets video #1."*

**Vu Le** (`duhoangvu3007@gmail.com`) — hired **before** the evaluation concluded, on his 70s sample. Took three rounds to apply the motion note. Works to per-section checkpoints by his own habit, not by instruction. Delivered 70s → 4:45 first half → full 9:42 → publish cut inside 3 days. The honest verdict on the hire: *"you hired early on incomplete evidence. What saved it: he checkpoints, takes hits on the chin, and comes back with the actual fix instead of excuses. Three rounds of increasingly blunt feedback and he never got defensive once."*

**Abel Mulu** — best coachability of the three: applied the night-recolor in one round and restated the principle unprompted (*"colorful clips make the video less scary"*), and flipped a stick figure black to white unasked so it read against a dark street. But twice failed to apply small asset swaps across two rounds, and twice failed to change his export bitrate (1.33 → 1.47 Mbps) after an explicit instruction. Approved-track pending swaps and a quote that never arrived.

**Abdullah** — exited 22 Jul on capacity grounds, at the owner's insistence that the exit not blame his work. Only editor who ever gave a turnaround figure (*"within an hour"* on a rebuild, delivered same night) and the only one to export above 1080p (1440p). Never delivered a full 70s section, never named a price. Admitted he *"lost his own creativity trying to imitate the competitors on the first sample"* — and his self-directed stretch measured as his best material.

**Two-chair model:** *"Abel is your retention-texture editor, Vu is your cinematic-moment editor, and a two-chair setup doubles your upload capacity while the real retention curves from your first two published videos settle who leads long-term."*

---

## 7. OWNER PREFERENCES AND VETOES

| Date | What the owner said | What it settled |
|---|---|---|
| 24 Jul | *"I kept that size intentionally for engagement"* (the 800,000 M Behemoth label) | Deliberate wrong-number comment bait, overriding canon accuracy. Accepted compromise: style it as obvious hyperbole (huge bold label, almost a joke) so it reads as intentional flavour. |
| 24 Jul | *"one guy made an aggressive giant and gone viral so I'm renamed my title 'most aggressive'"* | Titles are set retroactively by copying whichever competitor superlative just spiked. Kept "Most Aggressive" despite two of eight creatures contradicting it. |
| 23 Jul | *"He's adding the creature at the top right corner, which is not good"* | Corner mascot banned. |
| 23 Jul | *"I checked the voiceover, it's good, not glitched"* | Killed a false VO-glitch report. Standing rule since: flag audio as "worth your ear-check", never assert it. |
| 23 Jul | *"so I'm sharing a reference from our channel... which is edited by my other editor in my team"* | Chose full transparency between editors over political cover. |
| 22 Jul | *"I'm writing script on chatgpt"* | Scripts are drafted in ChatGPT, not here. |
| 24 Jul | *"don't give me too much tags, give me important few"* | Tags capped at ~8. |
| 28 Jul | *"those are very minor corrections right?"* | Standing bias toward minimizing correction rounds. The answer that stuck: motion notes are minor, **a baked-in audio limiter is a gate** because it cannot be rescued later. |

---

## 8. OPEN THREADS NEVER CLOSED

1. **Hero-forward A/B thumbnail** (one large creature + bold hook + number badge vs. the 8-box grid). Offered three times on 24 Jul, never built.
2. **The Mimic canon decision.** Bless the 3D render as the house look or supply approved stills. Cost warning attached: *"if you decide in two weeks that you want the canon look, you are recutting every scene the Mimic appears in."*
3. **Full v4 script stress-test of the other six sections.** Only Long Horse was ever tested.
4. **Validating the modeled retention curves against real YouTube Analytics.**
5. **FEH-tid / FET-ted VO pronunciation check.** Requested twice, never confirmed.
6. **Custom ElevenLabs prompt** that protects the deliberate sentence fragments. Offered, never answered. The finding behind it: generic "humanize" prompts *"merge short punchy fragments into smooth flowing sentences, and your fragments ('Then it moves.' 'It is bait.' 'Do not answer.') are deliberate, they're where the dread lives."* Real TTS levers are spelling numbers out, deciding how odd strings read, and using punctuation for pause length.
7. **Two script fixes to Long Horse**, raised 22 Jul, never confirmed made: the hedges *"mean very little"* and *"cannot reliably keep it out"* (*"'reliably' is a lawyer's word"*), and the soft name reveal.

---

## 9. THE FINDING THAT MATTERS MOST FOR AUTOMATION

22 Jul 9:35 AM, on the Long Horse impossible-angles passage:

> *"'The neck can create new joints, twist through impossible angles, and pass through space without connecting in a straight line' — **every single editor struggled at exactly this spot** (Vu's dead zone, Abdullah's zoom-milking, Abel's diagram). When three editors independently stall on the same seven seconds, the words are the cause: it's the only stretch with no image in it."*

Unstageable script lines produce dead zones no matter who is editing. The script QC should flag them before the edit starts, and an automated pipeline should refuse to render a beat it has no shot idea for rather than hold on a zoom.
