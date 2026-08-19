# Prosody / delivery watch — Serious History vs Agent Flappy

**Purpose:** characterise the VOICE PERFORMANCE (not the content) of two faceless
narration channels, so the delivery can be rebuilt in a TTS pipeline.

**Method:** Gemini multimodal listening passes via
`mcp__NexLev__watch_youtube_video_and_ask`, sampled in segments.

| Subject | Video | Length | Segments obtained |
|---|---|---|---|
| A | `sNMDXA8Qcts` — "Most Disturbing Revenge Stories in History", Serious History | 22:01 | 0–150s, 600–780s, 1150–1300s (**3/3**) |
| B | `3GKC4kC3iQ0` — "World War 2 Explained in 31 Minutes", Agent Flappy | 31:15 | 0–150s, 900–1080s (**2/3**) |

## Coverage gap — read this before trusting the comparison

The tool quota is **5 calls / 24h** on this plan; the 6th call returned
`RATE LIMIT EXCEEDED`. The missing sample is **B, 1650–1830s (27:30–30:30)** —
Agent Flappy's late/outro delivery. So every claim below about *how B ends*,
whether B decelerates into its outro, and whether B's late-video pause budget
differs from its opening, is **UNMEASURED**. A's late segment was captured, so
the A-vs-B "late video" row of the comparison is one-legged. Do not read the
Differences section as symmetric.

## How reliable is any of this

Gemini answered in the *format* of measurement — durations to 0.1s, WPM to the
unit — but the two passes over video A **contradict each other on breath**
(§A-1 says inhales are deliberately preserved at 30–40% of speech level; §A-2
says sentence starts are "unnaturally clean" and breaths are "likely gated or
manually removed"). It also cited at least one emphasised word that looks
unlikely to be real script text ("fiercesome", A 0:22). Treat the numbers as
**one model's single-pass estimate**, not as instrument readings. Throughout,
claims are tagged:

- **[C]** corroborated — the same behaviour appeared in two or more independent segments
- **[S]** single-source — one segment only, no second look
- **[X]** contested — segments disagree

---

# VIDEO A — Serious History, `sNMDXA8Qcts`

## A / Segment 1 — 0:00–2:30 (hook + intro + sponsor)

### Pauses
| Time | Est. length | Class | Before → after |
|---|---|---|---|
| 0:04–0:07 | ~3.0s | (e) section gap | "history" → "It's" |
| 0:15 | ~0.6s | (c) full stop | — |
| 0:24 | ~0.7s | (c) full stop | — |
| 0:38 | ~0.8s | (c) full stop | — |
| 0:52 | ~0.7s | (c) full stop | — |
| 1:17 | ~0.8s | (c) full stop | — |
| 1:47–1:48 | ~1.2s | (d) dramatic hold | "revenge" → "And" |
| 2:06–2:07 | ~1.5s | (e) section gap, SFX-filled | "issue" → "Huh?" |

The shape: a **3-second cold gap right after the title line** (0:04–0:07) before
the story starts — the single longest silence in the sampled material. Then
sentence gaps sit in a tight **0.6–0.8s** band. Only one 1s+ hold in 150
seconds, and it lands on a reveal into a tone-change. [S]

### Breath
Audible inhales are **left in**, at roughly 30–40% of speech level, and they are
placed as preparation for long phrases: 0:07 (sharp, before the story's first
sentence), 0:15, 0:25 (deep, before a "for over 100 years" span), 0:52, 1:05. [X]
— contradicted by segment 2, see below.

### Tempo
~**155 WPM** overall. Intro hook 0:00–0:04 fast at **~180 WPM**; narrative body
0:07–1:47 settles to **~145 WPM**; the sponsor read from 2:07 jumps back to
**~175 WPM**. Pattern: *hype fast → story slow → ad fast*. [S]

### Emphasis
Mechanism is mixed, not one trick:

| Time | Word class | Mechanism |
|---|---|---|
| 0:02 | adjective | pitch rise + vowel lengthening |
| 0:08 | date | loudness |
| 0:10 | noun | **micro-pause before** |
| 0:22 | adjective | vowel lengthening *(word cited is doubtful — see reliability note)* |
| 0:59 | adjective | loudness + sharp pitch rise |
| 1:11 | sentence-final noun | lengthening + trailing off |

Notable: the **pause-before** mechanism is used on a plain noun, not just on
reveals — i.e. it is a routine emphasis device, not reserved for climaxes. [S]

### Pitch / intonation
Predominantly **falling** sentence-finals (declarative). Contour is a varied
"storyteller" melody, not a flat reading. **Upward pitch resets** at 0:07 (story
start), 1:20 (new plot point), 2:07 (sponsor). Range described as *moderate* —
lower register for dark history, higher for the meta-humour at 1:48. [C — resets
also reported in segments 2 and 3]

### Tone / register
Three distinct registers inside 150 seconds: **theatrical/sombre documentary**
(0:07–1:47) → **wry conversational meta-commentary** (1:48–2:06) → **bright
commercial** (2:07+). Audible relish reported on the grim adjectives at 0:59 and
1:41. [S]

### Imperfections
Mouth click / lip smack just before the emphasised noun at 0:10; sharp sibilance
at 0:52; **volume trailing off** on the last word before the 1:47 hold; natural
un-clipped coarticulation on a casual two-word phrase at 1:51. [S]

### Music / SFX
Voice is **dry**, no noticeable reverb. Music **ducks hard** under speech. He
**pauses for SFX twice**: a whoosh at 0:24 and a clapperboard snap at 1:47 —
note the 1:47 "dramatic hold" is therefore partly an *editorial* hold made for a
sound effect, not purely a performance choice. [C — SFX-holds also in segment 2]

### AI or human
**Human, 95%.** Evidence offered: register-switching between the documentary and
meta personas, emotional colouring/relish on adjectives, natural breath
placement, trailing volume at 1:45.

---

## A / Segment 2 — 10:00–13:00

### Pauses
| Time | Est. length | Class | Before → after |
|---|---|---|---|
| 10:27 | ~2.1s | (e) section gap | "refused" → "With" |
| 10:47 | ~1.2s | (d) dramatic hold | → "waiting" |
| 11:09 | ~2.3s | (e) section gap | "him" → "The" |
| 12:26 | ~0.8s | (c) full stop | "days" → "Trush" |

**Median sentence-to-sentence gap: ~0.7s.** [C — 0.6s in segment 3, 0.6–0.8s in
segment 1; this is the most stable number in the whole study]

Section gaps in mid-body run **2.1–2.3s**, i.e. roughly 3x a sentence gap.

### Breath
**[X] Contested.** This pass reports only two faint intakes (10:32, 11:43) and
says sentence starts are "unnaturally clean", breaths "likely gated or manually
removed in post". That is the opposite of segment 1's finding. Most probable
reconciliation: breaths survive at high-effort/high-emotion moments and in the
hook, and are gated out of routine expository mid-body — but this is my inference,
not something Gemini stated.

### Tempo
~**145 WPM** — slower than the intro segment, consistent with segment 1's claim
that the narrative body runs ~145. [C] Speeds up at 10:24 on list-like camp
detail; slows at 11:55 on gruesome physical description.

### Emphasis
- 11:03 — a large number/scale phrase, **lengthened**
- 11:32 — pitch rise on a mid-phrase noun
- 11:55 — gruesome detail delivered **slower and more deliberately** (rate as emphasis)
- 12:07 — increased **loudness** on a visceral phrase
- 12:45 — **pause-before** on an adjective+noun

Pattern worth stealing: **gore and scale are emphasised by slowing down, not by
getting louder.** [S but consistent with §A-1's slow-narrative claim]

### Pitch / intonation
Consistent downward sentence-finals; conversational-but-controlled melody,
explicitly *not* a newsroom drone. Pitch reset upward at 11:10 for a new chapter.
**Rising list intonation** at 12:12 for an enumeration of items. [S]

### Tone / register
Sombre and matter-of-fact, shifting to **dry/analytical** for the expository
"connective tissue" passages (11:44). Slight vocal smile / relish on the most
visceral phrase at 12:07 — same behaviour as segment 1's 0:59. [C]

### Imperfections
Plosive pop at 10:18; clipped syllable at 11:53. But this pass explicitly says
pacing is "generally very even" and **lacks natural stumbles or mouth clicks** —
tension with segment 1, which reported a mouth click. [X]

### Music / SFX
Dry, centred mono, minimal reverb. Pauses for a tiger roar (10:54) and a scream
(11:06). Music ducks significantly. [C]

### AI or human
**Human, 4/5.** Evidence: micro-variations of emotional weight, non-uniform
rhythm. Note the confidence has dropped from 95% (seg 1) to 80%.

---

## A / Segment 3 — 19:10–21:40 (late body → ending)

### Pauses
| Time | Est. length | Class | Before → after |
|---|---|---|---|
| 19:55 | ~0.8s | (c) sentence gap | — |
| 20:04 | ~1.2s | (d) dramatic hold | "history" → "See" |
| 20:45 | ~0.7s | (c) sentence gap | — |

**Median sentence gap ~0.6s; longest silence in the whole 2.5 minutes is only
1.2s.** Late-video pausing is *tighter* than the intro — no 2s+ section gaps at
all in this stretch. [S]

### Breath
Inhales at 19:12 (moderate, sentence start), 19:39 (soft, mid-paragraph), 20:04
(**loud**, before the transition). And an explicitly **clean start with no
audible intake at 20:33**. So within a single 150-second window: one loud breath
and one absent breath. Breath is **not uniform** — it is loudest before the
biggest structural move. [S, and it partially reconciles the §A-1/§A-2 conflict]

### Tempo
~**165 WPM** — faster than mid-body's 145. Fastest at 19:12–19:20 on date/event
setup; **slowest at 21:33–21:40, the final resolution**. Slight deceleration
into the conclusion. [S]

### Emphasis
| Time | Word class | Mechanism |
|---|---|---|
| 19:12 | date | pitch rise |
| 19:20 | verb | vowel lengthening |
| 19:42 | adverb | staccato loudness |
| 20:13 | noun | pitch rise |
| 21:28 | intensifier ("actual") | loudness |

Dates are given **high pitch + crisp articulation** rather than slowdown. [S]

### Pitch / intonation
Predominantly falling; conversational narrative. Pitch reset at 19:55 for a
commentary transition. **Final sentence of the video: significant slowdown plus a
deep pitch fall at 21:38** — an explicit terminal cadence. [S]

### Tone / register
**Wry and matter-of-fact**, consistent throughout with no separate outro voice.
Audible relish at 19:42 on a gruesome adverb — third instance of the
relish-on-gore behaviour. [C]

### Imperfections
Mouth click at 20:57; swallowed consonant at 21:23. [C with seg 1, contra seg 2]

### Music / SFX
Dry, no reverb; consistent ducking; the 20:04 hold doubles as room for a musical
transition. [C]

### AI or human
**Human, 7/10.** Confidence has now fallen across the three passes: 95% → 80% →
70%. The evidence cited each time is the same class of thing (varied breath,
emotional inflection, pacing micro-variation) — none of it is an artefact-level
observation, which is what would actually settle it.

---

# VIDEO B — Agent Flappy, `3GKC4kC3iQ0`

## B / Segment 1 — 0:00–2:30 (hook + intro)

### Pauses
| Time | Est. length | Class | Before → after |
|---|---|---|---|
| 0:01–0:02 | <0.2s | (a) micro-beat | mid-sentence |
| 0:03–0:04 | ~0.4s | (b) comma breath | — |
| 0:14–0:15 | ~0.8s | (c) full stop | — |
| 0:17–0:18 | ~1.1s | (d) dramatic hold | "explained" → "And by the end" |
| 0:26–0:27 | ~1.2s | (e) section gap | "put it out" → "But our story begins" |
| 0:30–0:31 | ~1.0s | (e) section gap | "ended" → "November, 1918" |
| 0:49–0:50 | ~1.0s | (d) dramatic hold | "Austria" → "And when a chaplain" |
| 0:57–0:58 | ~1.1s | (d) dramatic hold | "weeps" → "His name was" |
| 1:15–1:16 | ~1.2s | (e) section gap | "at home" → "Cause the Treaty…" |
| 1:45–1:46 | ~1.0s | (d) dramatic hold | "about him" → "He was a struggling painter" |
| 2:12–2:13 | ~1.1s | (e) section gap | "stop him" → "But his first bet" |

**This is the headline structural difference.** B uses **7 pauses of 1.0s or
longer in 150 seconds**; A used **one**. And B's holds are all clustered in a
narrow **1.0–1.2s** band — including the section gaps, which for A were 2.1–3.0s.
So B's rhythm is *frequent medium holds*; A's is *rare long holds*.

Every one of B's 1s+ holds is followed by a **sentence-initial connective** —
"And…", "But…", "Cause…", "His name was…". The hold is doing paragraph-break work.

### Breath
Inhales present and audible at ~30–40% of speech level: 0:00, 0:18 (sharp,
before the post-hold line), 0:36 (deep), 0:53, 1:16, 1:46, 2:24. Placement logic
is explicit: **before long narrative beats and before intensity shifts**, and
notably **immediately after the big holds** — the hold and the breath are one
gesture. [S]

### Tempo
~**165 WPM** overall. Intro hook 0:00–0:15 at **~185 WPM**; the hospital
narrative 0:31–1:00 drops to **~140 WPM**; a rapid-fire treaty list at 1:24–1:30
speeds up again. Same fast-hook / slow-story architecture as A, but shifted
~10 WPM faster throughout. [C — 165 also in segment 2]

### Emphasis
| Time | Word class | Mechanism |
|---|---|---|
| 0:00 | subject noun | pitch rise |
| 0:06 | sentence-final noun | vowel lengthening |
| 0:15 | proper name (title) | **pause-before + loudness** |
| 0:31 | date | pitch rise + **pause-before** |
| 0:58 | proper name (the reveal) | loudness + **dramatic hold before** |
| 1:17 | adjective | lengthening + pitch rise |
| 1:35 | sentence-final noun | loudness |
| 1:59 | noun | **pause-before** + pitch rise |

**Pause-before is B's dominant emphasis device** — 4 of 8 examples — and it is
what carries every name reveal. [C — same pattern in segment 2]

### Pitch / intonation
Mostly falling sentence-finals. Contour is **highly varied and theatrical**, a
storyteller arc. Big upward resets at 0:31, 1:16, 1:41. Range described as
**wide** — high head-voice for excitement, low chest voice for sombre passages.
(A's range was called only *moderate*.) [S]

### Tone / register
**Theatrical, high-energy.** Moves from movie-trailer hype (0:00–0:26) to a
hushed sombre narrative (0:31–0:57). Energy spikes at 0:58 and 1:59. An audible
wry smirk at 2:01 on an aside. [C — smirk also at 16:48 in segment 2]

### Imperfections
Clipping on a final consonant at 0:06; volume trailing off on the last word
before the 0:57 hold; mouth click at 1:21; sharp plosive at 1:49; natural
slurring/coarticulation on a hard proper-noun phrase at 2:19. [S]

### Music / SFX
Dry, **close-mic, very little room reverb**. Music ducks ~**-10 dB** under the
voice. Pauses for a title-card music swell (0:15), a gunshot (0:27), a punch
(1:50). Two of the three big "dramatic holds" coincide with SFX — again, the
hold is partly editorial. [C]

### AI or human
**Human, 99%.** Evidence: emotional acting on the "weeps" line, wry chuckle-tone
at 2:01, breath tied to the physical effort of the long intro sentence, and pause
lengths tailored to visual animation timing.

---

## B / Segment 2 — 15:00–18:00

### Pauses
| Time | Est. length | Class | Before → after |
|---|---|---|---|
| 15:15 | ~0.7s | (c) full stop | "tide had turned" → "But Yamamoto's story" |
| 15:19 | ~1.2s | (d) dramatic hold | "one final chapter" → "Cause in April" |
| 15:48 | ~1.8s | (e) section gap | "the Doolittle Raid" → "Meanwhile on the far side" |
| 16:09 | ~0.4s | (b) comma breath | before a short appositive |

**Typical sentence-to-sentence gap ~0.6s** — essentially identical to A's 0.6–0.7s.
[C] The 1s+ holds are still there mid-body but at lower density than the intro.
Section gap here is 1.8s vs A's 2.1–2.3s.

### Breath
Inhales at 15:02, 15:11, 15:20, 16:27 — at sentence starts and major clause
breaks, clearly audible but mixed below peak speech. **But** starts at 16:38 and
17:22 are "unnaturally clean", suggesting gating. **Same mixed picture as A**:
breaths present at structural moments, absent elsewhere. [C — and this is the
strongest evidence that the A breath contradiction is real behaviour, not a
model error]

### Tempo
~**165 WPM** [C]. Speeds up on dates/names (15:21–15:25) and a geographical list
(16:42–16:47); slows on a casualty figure (16:18–16:20) and on a general's name
(17:00–17:01).

### Emphasis
- 15:01 — "single day" — loudness/punch
- 15:06 — a duration — vowel lengthening
- 15:27 — a repeated adjective pair — pitch rise + staccato
- 16:10 — a place name — **pause-before + loudness**
- 17:00 — a proper name — **pause-before + lower pitch**

Stated rule for figures: **casualty numbers get elongated vowels and LOWER pitch
for gravity** — not loudness. [S but consistent with A's "slow down on the gore"]

### Pitch / intonation
Consistent downward finals. High-energy conversational contour with pitch resets
at 15:50 and 16:27. **Explicit list intonation**: rising steps on two list items
at 16:44–16:47, falling on the closing item. [C — A does the same at 12:12]

### Tone / register
General register is **high-energy hype expository**; becomes sombre and
"gravelly" for the Stalingrad stretch (16:10–16:26). Audible smirk at 16:48 on a
dark joke. So B modulates register *within* a segment, same as A, but B's
baseline sits much higher-energy. [C]

### Imperfections
Plosive pop at 15:29; a heavily compressed/fast clipped phrase at 17:19; subtle
mouth click at 17:36 before a conversational aside. [C]

### Music / SFX
Dry, forward-mixed. **Music ducks specifically to expose a casualty figure at
16:18** — ducking used as emphasis, not just intelligibility. Brief holds for an
explosion (15:39) and a slap (17:19). [C]

### AI or human
**Human, 7/10.** Same confidence decay as A between passes (99% → 70%) on the
same class of evidence.

## B / Segment 3 — 27:30–30:30 — **NOT CAPTURED**

Quota exhausted. No data on B's late-video pacing, outro cadence, or terminal
intonation.

---

# Shared recipe — the transferable "V2 human" behaviours

Everything here appeared in **both** videos.

1. **Sentence gaps sit at 0.6–0.8s, and that band is remarkably stable.** A:
   0.6–0.8s across three segments; B: 0.6s. This is the single most reproducible
   number in the study. It is *longer* than default TTS sentence spacing.
2. **Fast hook → slow story.** Both open at 180–185 WPM for the first 10–15
   seconds, then drop to 140–145 WPM for narrative body. A ~40 WPM swing inside
   the first 30 seconds.
3. **Grim material is emphasised by DECELERATION, not volume.** A slows on
   physical/gore detail (11:55); B slows and drops pitch on casualty figures
   (16:18–16:20). Numbers and body counts get *lower and slower*, not louder.
4. **Pause-before is the primary reveal device.** Both use a silence immediately
   preceding a name or key noun as the emphasis mechanism, in preference to
   loudness. B does it on every name reveal; A uses it even on ordinary nouns.
5. **Breath is selective, not uniform — and this is a real behaviour, not a mix
   artefact.** Both videos show audible inhales at structural moments (before
   long sentences, after big holds, before intensity shifts) *and* completely
   clean, breathless sentence starts elsewhere. The pattern is: **breath earns
   its place at the top of a paragraph or before an effortful line; routine
   expository sentences start dry.**
6. **Big holds are co-designed with SFX and music.** A pauses for a clapperboard,
   whoosh, tiger roar, scream; B for a swell, gunshot, punch, explosion, slap.
   Several of the "dramatic holds" exist because the picture needed the room.
   For a TTS rebuild this means **the hold budget must be authored with the edit,
   not baked into the read.**
7. **Upward pitch reset at every new section**, in both, at every sampled
   segment. Falling declarative finals otherwise.
8. **List intonation is genuinely used** — rising on non-final list items,
   falling on the last (A 12:12, B 16:44–16:47).
9. **Register modulates within a segment**, both: sombre for the atrocity, dry or
   wry for the connective tissue, and an audible smirk/relish on the darkest
   line. Both narrators visibly *enjoy* the worst material — that relish is a
   recurring, deliberate colour, not an accident.
10. **Voice is dry and close-mic'd, no reverb, hard ducking on the bed.** B's
    ducking is quantified at ~-10 dB and is at least once used *as an emphasis
    device* rather than for intelligibility.
11. **Consistent human artefacts:** plosive pops, mouth clicks before
    conversational asides, clipped/swallowed consonants, and — in both — **volume
    trailing off on the last word before a big hold.** That trailing decay is
    probably the highest-value single detail to reproduce.

---

# Differences

| Dimension | A — Serious History | B — Agent Flappy |
|---|---|---|
| Baseline energy | Sombre, dry, matter-of-fact | Theatrical, high-energy "hype" |
| Overall WPM | 145 (body) / 155 (intro seg) / 165 (late) | 165 throughout |
| Pitch range | Moderate | **Wide** — head voice to chest voice |
| 1s+ holds per 150s of intro | **1** | **7** |
| Hold length when it happens | 1.2s, but section gaps 2.1–3.0s | Uniform 1.0–1.2s for both holds *and* section gaps |
| Longest silence observed | ~3.0s (0:04–0:07, after the title line) | ~1.8s (15:48) |
| Rhythm character | Rare, long, structural silences | Frequent, medium, paragraph-level silences |
| What follows a hold | Varies | Almost always a connective: "And…", "But…", "Cause…" |
| Registers per video | 3 in the first 150s (documentary / wry meta / sponsor) | 2 (trailer hype / hushed narrative) |
| Ending | Captured: terminal cadence — decelerates and drops pitch hard on the final sentence (21:38) | **Unmeasured** |
| Late-video pacing | Speeds up to 165 WPM and *tightens* pauses (no 2s+ gaps at all after 19:10) | **Unmeasured** |
| Sponsor/ad register | Yes — distinct bright commercial voice at ~175 WPM from 2:07 | None sampled |

**The clearest single contrast:** both average a ~0.6s sentence gap, but they
buy their drama differently. A saves silence up and spends it in one big lump at
a chapter boundary. B spends it constantly in 1-second increments at every
paragraph. If you want A's feel, make long pauses *rare and long*. If you want
B's, make them *frequent and medium*, and always land a connective word on the
other side.

---

# Concrete numbers

| Measure | A — Serious History | B — Agent Flappy | Confidence |
|---|---|---|---|
| Micro-beat (in-sentence) | not itemised | <0.2s (B 0:01) | [S] |
| Comma-length breath | 0.2–0.5s (class present) | ~0.4s (B 16:09) | [S] |
| **Sentence-to-sentence gap (median)** | **0.6–0.8s** (0.7s seg2, 0.6s seg3) | **~0.6s** (seg2) | **[C] — best number here** |
| Dramatic hold (1s+) | 1.2s (both instances measured) | 1.0–1.2s | [C] |
| Section / chapter gap | **2.1–3.0s** | **1.0–1.8s** | [C] |
| Longest single silence sampled | 3.0s (0:04) | 1.8s (15:48) | [S] |
| 1s+ holds per 150s (intro) | 1 | 7 | [S] |
| WPM — hook (first ~15s) | ~180 | ~185 | [C across both] |
| WPM — narrative body | ~140–145 | ~140 (sombre passages) | [C] |
| WPM — overall | 145 (mid) → 155 (intro seg) → 165 (late) | ~165 (both segments) | [C for B, [S] per-segment for A] |
| WPM — ad read | ~175 | n/a | [S] |
| Breath level vs speech | ~30–40% | ~30–40% | [C] |
| Breaths per 150s (intro) | 5 | 7 | [S] |
| Music duck depth | "significant", unquantified | ~-10 dB | [S] |
| Voice treatment | dry, centred mono, no reverb | dry, close-mic, minimal reverb | [C] |
| Verdict: AI or human | Human — 95% / 80% / 70% across 3 passes | Human — 99% / 70% across 2 passes | see below |

## On the AI-vs-human question

Gemini said **human** for both, every time. But its confidence **fell on every
subsequent pass** for both videos (A: 95→80→70; B: 99→70), and the evidence
offered never moved beyond the same soft category — "emotional colouring",
"varied breath", "pacing micro-variation". None of that is decisive against a
2024+ voice clone with breath modelling; all of it is exactly what a good clone
of a human read produces. Gemini also never cited an artefact-level tell
(spectral splice, formant smear, sampled-breath repetition), which is what would
actually settle it, and it self-contradicted on whether breaths were even
preserved.

**My read:** the *performances* are human-derived — the register-switching,
mid-sentence smirks and relish, and the trailing-volume decay before holds are
strong human markers. Whether the delivered audio is that human's raw take or a
clone/TTS render of it is **not resolved by this evidence**, and I would not
claim it either way. For the rebuild, that ambiguity is good news: it means the
target is reachable, and the gap is in the prosody-authoring layer (pause
placement, WPM curve, pause-before-reveal, selective breath, trailing decay)
rather than in raw voice quality.

## What would close the gaps

1. The missing **B 27:30–30:30** call, for outro cadence and late-video pacing.
2. An **overlapping re-sample** of A 600–780s to settle the breath contradiction
   — ask specifically "count sentence starts WITH an audible inhale vs WITHOUT".
3. A **local acoustic measurement** pass (silence detection on the actual audio)
   to replace Gemini's estimated durations with real ones. Every number in the
   table above is a model estimate, and the pause-length figures are the ones
   most worth verifying, since they are what the TTS pipeline will literally
   encode.
