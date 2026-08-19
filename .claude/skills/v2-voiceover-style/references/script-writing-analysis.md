# Script-writing style analysis: two faceless narration channels

**A** — `sNMDXA8Qcts` · "Most Disturbing Revenge Stories in History" · **Serious History** · 1321 s
**B** — `3GKC4kC3iQ0` · "World War 2 Explained in 31 Minutes" · **Agent Flappy** · 1875 s

All figures produced by `/home/user/Test-2/.work/analysis/script_stats.py` (raw output in
`report.txt`, `stats.json`, `narration_only.json`). Nothing below is estimated.

### Method and caveats

- Source: YouTube auto-transcripts via NexLev (`get_bulk_video_transcripts`), saved verbatim to
  `.work/ref/transcript-{A,B}.txt` (tab-separated `startMs / endMs / mm:ss / text`).
- **Artifacts stripped before measuring:** `[music]` ×27, `[screaming]` ×1, `[bell]` ×1 and 11
  `>>` speaker markers in A; `[music]` ×21 in B. Left in, `[music]` was the 5th most common
  "sentence opener" in A — every count below excludes them.
- Sentence segmentation: spaCy `en_core_web_sm` over the punctuation supplied by YouTube's ASR.
  **This is the single largest caveat**: ASR punctuation is a machine's guess at where the
  narrator's clauses ended, so absolute sentence counts carry error. It is applied identically to
  both videos, so the A-vs-B *comparison* is sound; treat single-video absolutes as ±10%.
- Fragment = spaCy finds no finite verb (`VerbForm=Fin`) **or** no subject dependency
  (`nsubj/nsubjpass/csubj/csubjpass/expl`) anywhere in the sentence.
- Contractions counted from spaCy tokens (`n't`, `'re`, `'ve`, `'ll`, `'d`, `'m`, and `'s` only
  when tagged AUX/VERB). A surface regex that included possessive `'s` roughly doubled the count.
- Register: a word is "uncommon" if neither its surface form nor its lemma appears in
  `wordfreq.top_n_list("en", 2000)`. Proper nouns are excluded from this pool — names are subject
  matter, not register.
- "Narration-only" columns exclude the sponsor read and the outro CTA (A: 107.6–228.9 s and
  1312.1 s→end; B: 761.7–811.9 s and 1845.3 s→end).

---

## 1. Volume and pace

| Metric | A (Serious History) | B (Agent Flappy) |
|---|---|---|
| Duration | 1321 s (22:01) | 1875 s (31:15) |
| Total words (artifacts stripped) | 4,144 | 4,236 |
| Overall WPM | **188.2** | **135.6** |
| Narration-only WPM (no sponsor/outro) | 186.6 | 135.1 |
| Sentences | 223 | 344 |
| Sentences per minute | 10.1 | 11.0 |
| Words per sentence (mean) | 18.6 | 12.3 |

B is 39% slower per word but delivers *more* sentences per minute. Same word budget
(~4,200 words), spread over 9 extra minutes, cut into 121 more sentences.

### WPM over time (30 s buckets)

| Metric | A | B |
|---|---|---|
| Mean of buckets | 188.4 | 135.9 |
| Std dev / coefficient of variation | 19.3 / **10.2%** | 14.6 / **10.8%** |
| Min | **132** @ bucket 34 (17:00–17:30) | **108** @ bucket 30 (15:00–15:30) |
| Max | **230** @ bucket 20 (10:00–10:30) | **176** @ bucket 62 (31:00–31:15, final 15 s CTA); 162 is the highest full bucket, @ 12:30–13:00 (sponsor read) and 26:30–27:00 |
| First 30 s | 154.0 (77 words) | 158.0 (79 words) |
| First 60 s | 180.0 | 143.0 |
| Mean of first / middle / last third | 190.1 / 190.6 / 184.9 | 134.5 / 136.0 / 137.1 |
| Linear trend across whole video | −8.4 WPM total drift | +6.2 WPM total drift |

**Shape:** both curves are *flat with local spikes*, not arcs. Neither ramps up or slows down
across the video (drift under 9 WPM either way, ~5% of the mean). The variation is local — a
30 s window sits within ±10% of the channel's own baseline almost throughout. Both channels are
running a near-constant delivery rate and doing their pacing work elsewhere (sentence length,
section length, silence), not by speeding up and slowing down.

The extremes are diagnostic, and they are *content*, not drift:

- A's slowest bucket is a comedy beat — a sound-effect gag and a two-word Christmas joke.
- A's fastest is the middle of the tiger story's action sequence.
- B's slowest is the Midway payoff, the moment where a prediction planted 5 minutes earlier
  lands; B *slows down for the emotional beat*.
- B's fastest full buckets are the sponsor read and a transitional recap — B *speeds up through
  the non-story material*.

---

## 2. Sentence architecture — the headline difference

| Metric | A | B |
|---|---|---|
| Mean sentence length (words) | 18.6 | **12.3** |
| Median | 17 | **10** |
| Std dev | 8.7 | 7.8 |
| Coefficient of variation | 46.7% | **63.2%** |
| Min / Max | 1 / 50 | 1 / 50 |
| 10th / 90th percentile | 9 / 30 | **4** / 22 |
| Mean absolute difference between adjacent sentences | 8.5 words | 8.3 words |
| …as a fraction of mean length | 0.46 | **0.68** |

### Length distribution

| Bucket (words) | A count | A % | B count | B % |
|---|---|---|---|---|
| 1–3 | 6 | 2.7% | 21 | 6.1% |
| 4–7 | 9 | 4.0% | 90 | **26.2%** |
| 8–12 | 35 | 15.7% | 89 | 25.9% |
| 13–20 | 95 | **42.6%** | 94 | 27.3% |
| 21–30 | 58 | 26.0% | 38 | 11.0% |
| 31+ | 20 | 9.0% | 12 | 3.5% |

| Derived | A | B |
|---|---|---|
| % of sentences ≤5 words | 4.5% | **17.7%** |
| % of sentences ≥20 words | **37.2%** | 17.2% |
| Sentences per one short (≤5 w) sentence | 22.3 | **5.6** |
| Longest run with no short sentence | **70 sentences** | 29 sentences |

**A's distribution is unimodal and centred on 13–20 words (42.6%); B's is front-loaded, with
52% of all sentences at 12 words or fewer.** These are two different rhythmic engines.

### The critical finding: A has no short sentences in its narration

Of A's 10 sentences ≤5 words, **every single one is outside the narrative prose**: three are
spoken story titles, five are sponsor-skit dialogue, two are the Christmas gag. Restricted to
actual narration, A's ≤5-word count is **5** (3 titles + 2 gag lines) out of 199 sentences
(2.5%) — and **zero** inside the storytelling itself. B's narration-only figure is 62 of 333
(18.6%).

| Narration only (sponsor + outro removed) | A | B |
|---|---|---|
| Words / duration / WPM | 3,704 / 1191 s / 186.6 | 4,043 / 1795 s / 135.1 |
| Sentences | 199 | 333 |
| Mean / median length | 18.6 / 17 | 12.1 / 10 |
| % ≤5 words | **2.5%** | **18.6%** |
| % ≥20 words | 36.2% | 16.5% |
| % fragments | **3.0%** | **15.0%** |

### Fragments

| Metric | A | B |
|---|---|---|
| Fragment sentences | 14 (6.3%) | 51 (14.8%) |
| No finite verb | 14 | 46 |
| No subject | 10 | 42 |
| Narration-only fragment rate | 3.0% | 15.0% |

B fragments deliberately and often: bare noun phrases as beats ("George Patton.", "One
problem.", "Asleep."), verbless appositive lists, and one-word answers. A almost never does —
its 14 fragments are mostly titles and skit lines.

### "Long-then-punch" rhythm (≥20 words followed by ≤5)

| Metric | A | B |
|---|---|---|
| Occurrences | 3 | 10 |
| Per 100 sentences | 1.3 | 2.9 |
| As % of all long sentences | 3.7% | 17.2% |
| Expected if lengths were independent | 3.7 | 10.3 |
| **Observed / expected** | **0.82** | **0.97** |
| Softer form: ≥20 followed by ≤8 | 8 (9.8% of longs) | **27 (46.6% of longs)** |

**Honest read: neither writer engineers the long→punch pairing as a special move.** Both sit at
or slightly below chance. What differs is the *base rate* — because B writes short sentences
four times as often, the pattern occurs three times as often even without being aimed for. The
lesson for a scriptwriter is that the rhythm comes from raising the overall density of short
sentences, not from hunting for a spot to place one after a long one.

---

## 3. Voice, address and connectives

| Metric | A | B |
|---|---|---|
| "you / your / yours / yourself" | 17 (0.41 / 100 w) | 12 (0.28 / 100 w) |
| First person "I / me / my" | 23 | 13 |
| First person "we / us / our" | 6 | 14 |
| First person total | 29 (0.70 / 100 w) | 27 (0.64 / 100 w) |
| Questions (punctuated `?`) | 2 | 4 |
| Genuine rhetorical questions after manual check | **1** in narration | **3** in narration |
| Questions per 1,000 words | 0.7 | 0.9 |
| Contractions | 45 (1.09 / 100 w) | 42 (0.99 / 100 w) |
| Expandable full forms (aux/negation) | 186 | 168 |
| **Contraction rate** (contr ÷ contr+full) | **19.5%** | **20.0%** |
| Exclamation marks | 1 | 1 |

Both are far less "conversational" on these surface markers than the folk wisdom suggests.
Second person is under 0.5 per 100 words in both. Rhetorical questions are almost absent —
**four verified in nearly an hour of combined narration**. Contraction rate is ~20% in both:
these narrators say *"was not"* and *"had not"* four times for every *"wasn't"*. The spoken
quality is **not** coming from contractions, questions or "you".

### Sentence-initial connectives

| Opener | A count | A % of sents | B count | B % of sents |
|---|---|---|---|---|
| And | 15 | 6.7% | 41 | 11.9% |
| But | 15 | 6.7% | 32 | 9.3% |
| So | 1 | 0.4% | 17 | 4.9% |
| Because | 0 | 0.0% | 1 | 0.3% |
| Cuz | 0 | — | 5 | 1.5% |
| **And/But/So/Because combined** | **31** | **13.9%** | **91** | **26.5%** |
| Now | 2 | 0.9% | 5 | 1.5% |
| Then | 0 | — | 3 | 0.9% |

B opens **one sentence in four** with a coordinating conjunction. Related: B uses `cuz` 14 times
against `because` twice — a deliberate orthography of speech. A uses `because` once and `cuz`
never.

### Top 20 sentence openers

**A:** he 35 · the 24 · but 15 · and 15 · his 7 · this 7 · Markov 7 · as 5 · it's 4 · see 4 ·
by 4 · Trush 4 · for 3 · thanks 3 · Charles 3 · Oda 2 · on 2 · well 2 · with 2 · oh 2

**B:** and 41 · but 32 · the 30 · so 17 · he 17 · they 7 · his 6 · on 6 · it 6 · now 5 · if 5 ·
cuz 5 · in 5 · that's 5 · by 4 · Hitler 4 · oh 4 · at 4 · one 4 · from 3

A's opener list is dominated by **pronouns and character names** (he/his/Markov/Trush/Charles/
Oda = 58 openers) — it is a story being told about people. B's is dominated by **connectives**
(and/but/so/cuz = 95) — it is an argument being walked through.

### Top 20 opening bigrams

**A:** and so 4 · as he 4 · he was 3 · he knows 3 · but the 3 · Charles II 3 · the head 3 ·
but not 2 · he goes 2 · after years 2 · Sugitani is 2 · this was 2 · the tiger 2 · he looks 2 ·
the poacher 2 · Trush and 2 · by this 2 · Cromwell's head 2 · today we're 1 · Oda Nobunaga 1

**B:** oh and 4 · and the 4 · but the 4 · and that 3 · he was 3 · and on 3 · so the 3 ·
they knew 3 · and it 3 · this is 2 · and when 2 · his name 2 · and here's 2 · so when 2 ·
the first 2 · bet number 2 · and this 2 · so on 2 · and as 2 · in the 2

Note A's `as he / he knows / he looks / he goes` — **present-tense observation verbs**, the
camera-following-a-character move. And B's `oh and` (4×) — the signature aside opener.

### Discourse-marker inventory (all non-zero hits, case-insensitive)

| Marker | A | B |
|---|---|---|
| and so | 8 | 3 |
| so, | 5 | 4 |
| see, | 4 | 1 |
| now, | 3 | 1 |
| turns out / it turns out | 3 | 0 |
| here's… | 2 | 4 |
| instead | 2 | 6 |
| and then | 1 | 2 |
| you see | 1 | 1 |
| except | 1 | 0 |
| however | 1 | 0 |
| remember | 1 | 3 |
| suddenly | 1 | 2 |
| by the way | 1 | 0 |
| to be clear | 1 | 0 |
| this is where | 1 | 0 |
| here's the thing | 0 | 1 |
| meanwhile | 0 | 2 |
| but then | 0 | 2 |
| let's / let me | 0 | 3 |
| imagine / think about / and yet | 0 | 3 |
| within weeks | 0 | 1 |

Marker density is low in both (A: 36 hits ≈ 0.87 / 100 w; B: 42 ≈ 0.99 / 100 w). A's are
*explanatory* (`see,`, `turns out`, `to be clear`, `this is where`); B's are *directive*
(`here's the thing`, `remember`, `let me`, `just think about that`, `and get this`).

---

## 4. Specificity and register

| Metric | A | B |
|---|---|---|
| Proper nouns | 293 (**7.07** / 100 w) | 429 (**10.13** / 100 w) |
| Numerals | 81 (1.95 / 100 w) | 145 (**3.42** / 100 w) |
| Digit-containing tokens | 37 | 69 |
| Four-digit years (15xx–19xx) | 10 | 26 |
| DATE/TIME entities | 64 (1.54 / 100 w) | 80 (1.89 / 100 w) |
| **Combined name+number density** | **9.02 / 100 w** | **13.55 / 100 w** |
| Top entity types | PERSON 99, DATE 55, ORG 54, GPE 29 | GPE 128, DATE 69, CARDINAL 69, PERSON 67, NORP 65 |
| Mean word length | 4.40 | 4.63 |
| % words ≤4 characters | **60.7%** | 55.6% |
| % words ≥8 characters | 10.2% | 12.4% |
| % outside 2,000 most common English words | **16.1%** | **17.4%** |
| Type-token ratio | 0.302 | 0.327 |
| Triads ("x, y, and z") | 3 | 13 |
| "the most …" superlatives | 5 | 6 |

Register is **near-identical and very plain in both**: mean word length 4.4–4.6 characters,
~84% of non-name words drawn from the 2,000 most frequent English words. The uncommon 16–17% is
almost entirely *subject-matter* vocabulary, not elevated diction — A's list runs
tiger/cabin/clan/boar/warlord/poacher, B's runs troops/invasion/aircraft/bombers/carriers, and
B's single most frequent "uncommon" word is `cuz`.

Every one in eleven words in B is a proper noun. Density of concrete named detail — not vocabulary
sophistication — is the register these scripts are written in.

---

## 5. Structure

Two independent measures, because they answer different questions.

**(a) Pause-derived beats.** Boundaries where the gap between consecutive caption starts exceeds
`median + 3×MAD`. This is a weak instrument here — YouTube pads caption cues, which compresses
real silences — so treat it as relative, not absolute.

| Metric | A | B |
|---|---|---|
| Median inter-cue gap | 2,080 ms | 2,721 ms |
| MAD | 280 ms | 400 ms |
| Threshold used | 2,920 ms | 3,919 ms |
| Largest gap | 7,199 ms | 8,479 ms |
| Beats detected | 31 | 34 |
| Mean / median beat length | 39.3 s / 28.4 s | 50.8 s / 40.9 s |

**(b) Narrative sections.** Hand-identified from verbatim anchor phrases; the script resolves each
anchor to its timestamp and computes lengths (all 41 anchors matched, zero misses).

| Metric | A | B |
|---|---|---|
| Sections | **8** | **33** |
| Sections per 10 min | 3.6 | **10.6** |
| Mean section length | 165.1 s | **56.8 s** |
| Median | 118.0 s | 49.3 s |
| Std dev | 139.4 s | 31.2 s |
| Min / Max | 4.4 s / 395.8 s | 20.1 s / 145.0 s |
| Words per section | 518 | **128** |

**A: 8 sections, ~2:45 each, wildly uneven (σ = 139 s).** Cold open → Story 1 (interrupted at
1:47 by a 121 s in-character sponsor skit, resuming at 3:49) → Story 2 → Story 3 → coda → outro.
Three long-form stories of 305 s, 371 s and 396 s. It is an anthology.

**B: 33 sections, ~57 s each, metronomic (σ = 31 s; min 20 s, max 145 s).** The single longest —
145 s — is the Ted Roosevelt Jr. human-interest sequence, i.e. B spends its longest block on the
one segment with no strategic content at all. It is a chaptered timeline.

---

## 6. The hook, beat by beat (first 30 s)

**A — 0:00–0:34, 5 beats, 98 words, 168 WPM — 11% *below* its 188 average.**

1. **Title-as-promise, 10 words** — "we're going over the most" + superlative + category. No
   preamble; the video's title is spoken back to the viewer as sentence one.
2. **Chapter title as a fragment, 5 words** — two proper nouns joined by "and". The card
   announces exactly two people, which pre-frames the whole story as a duel.
3. **Hard cut to a scene in present tense with a date**, ~26 words — "It's June 22nd, 1570, and
   a ninja is lying…". Date + present progressive + a person mid-action. No context, no thesis.
4. **Withhold-then-name, 2 sentences** — "His name is…" *after* the action, then the stakes as
   the mission ("a mission that few would ever dare").
5. **Zoom out to world state**, 27 words — "For over 100 years, Japan had been engulfed…". Only
   now does the background arrive, and only after the reader is inside a scene.

The formula: **promise → title card → scene in present tense → name → world**. Backstory is
always paid for by a scene first.

**B — 0:00–0:30, 4 beats, 79 words, 158 WPM — 16% *above* its 136 average.**

1. **A rule-of-three montage of images, one 36-word sentence** — three "from X to Y to Z"
   clauses, each a concrete strange picture (burning oil; a president's son with a cane; a
   general with a note in his wallet). Zero abstractions. All three are cashed later in the video
   (Pearl Harbor 9:47, Ted Roosevelt Jr 19:37, Eisenhower 18:32) — the hook is a **trailer of
   receipts**, not a teaser.
2. **Naming the video, 5 words** — "This is World War II explained."
3. **The explicit contract, second person** — a "by the end of this video" promise that the
   viewer will understand how it happened. One of only 12 uses of "you" in the script, spent here.
4. **The pivot into the timeline, one sentence** — "But our story begins where the last war
   ended", straight into a dated, located, present-tense scene: month, year, place, then a
   nameless man in a bed.

The formula: **three images → name the video → promise the takeaway → pivot to a scene**. Then
the withheld-name payoff: the man in the hospital bed is described for 40 words before "His name
was Adolf Hitler" lands as a 5-word sentence. **Both channels use the identical device — describe
a person fully, name them last, in a short sentence.**

---

## 7. Section opens, closes and transitions

**A — opens.** Every story opens the same three ways in sequence: (i) a bare **name-and-name
title fragment**; (ii) an **"It's [date]"** present-tense scene-setter with a person doing
something physical (three of three stories do this: 1570 mountain pass, 1997 Siberian evening,
1651 oak tree); (iii) an escalating tour of the antagonist's power *before* any conflict.
Story 2 varies it with a **direct meta-address** — a one-line superlative claim
("might be one of the most unbelievable cases"), then the scene.

**A — closes.** Every story closes on a **grotesque physical object that outlives the people**:
skulls made into drinking cups; a face eaten clean off; a head on a pole. Story 3 then extends
this into a 115 s coda that follows the *object* for 300 years after the story's actual end.
The pattern is: resolve the revenge, then **hand the viewer one image to keep**.

**A — transitions.** Almost none. Sections butt-join: the last sentence of a story is followed
immediately by the next story's title fragment. The only bridging device is the **"Oh, and…"
addendum** — a post-climax extra atrocity ("Oh, and just for funsies, 9 years later…") that
extends a story past its apparent end.

**B — opens.** Two dominant forms. (i) **Datestamp cold-open**: "December 16th, 1944, the Arden
Forest in Belgium" — date, place, then one striking fact. 8 sentences in B open with a bare datestamp ("On December 11th, 1941, …",
"November 1918, a military hospital in Pazavval, Germany."), against 3 in A. (ii) **Connective + spatial jump**: "Meanwhile, on the far side of the
world…", "But first…", "But let's rewind to that June morning…". B openly narrates its own
navigation.

**B — closes.** Sections close on a **short verdict sentence**, typically ≤8 words, that scores
the beat: "But France did nothing." / "It was the first time Hitler ever lost." / "The Axis was
no longer unstoppable." / "The Furer had finally been outplayed." / "And now the tide had
turned." The unit of B's structure is scene → verdict.

**B — transitions.** Explicit and signposted, in four recurring forms:

- **Numbered running motif** — "Bet number one… Bet number two… And bet number three", then
  cashed with "You see the pattern?" The gambling metaphor is set up at 1:38 and paid off at
  30:35 ("not to bet against America").
- **Planted callback** — "Oh, and remember his prediction", then the bare figure "6 months"
  and a warning that it will "come back to haunt them" (9:40), cashed at 15:02 ("almost exactly 6 months after Pearl Harbor"). Also
  the 1918 hospital scene → a closing line naming that same "hospital bed" 26 minutes later.
- **Explicit rewind/jump** — "But let's rewind to that June morning, cuz…"
- **Causal chain** — sections joined with "So…", "Cuz…", "But then…" so the timeline reads as
  consequence rather than chronology.

---

## 8. How tension is built and released

**A — physical dread, deferred.** The device is **information the character does not have**.
Markov's story runs on an explicit statement of the rule (a tiger "will see you a hundred
times" first) followed by 3 minutes of sensory escalation — sounds outside, beehives
falling, pots dropping, then one image ("a giant yellow eye") — and the release is always an
*object described in forensic detail*. A also **states the horror is coming before delivering
it**: a flagged "one of the most insane execution methods" precedes the description by
15 seconds. Sentences stay 13–20 words throughout; A does **not**
shorten sentences for tension. It substitutes concrete sensory nouns instead.

**A's release valve is comedy.** The two lowest-WPM windows in the whole video are gag beats.
After each atrocity, a deflating aside arrives inside the sentence — "just for funsies", "some
pretty impressive skull to cups trick", "who by the way had also died", "still chilling up
there". The horror is never allowed to sit.

**B — stakes stated as arithmetic, released as verdict.** B builds by **counting**: "6 million
Germans lost their jobs", "338,000 soldiers trapped", "1,177 men in 9 seconds", "over 600,000
American troops". The tension peak is almost always a **rhetorical arithmetic question** — having priced
the defence of "tiny islands", B asks what invading Japan itself would cost. Release comes as a **fragment or a one-word answer**: "Nuts." / "Asleep." /
"Not once." / "One problem."

**B's release valve is the persona.** Roughly 19 aside lines across 31 minutes (about one every
98 s) break the fourth wall in a distinct register: "Absolute legends.", "Big mistake, buddy.",
"Cool name, sir.", "Rest easy, sir.", "God, I love this country.", "Tell your wife we said happy
birthday." They are almost all ≤6 words and they are a large part of why B's ≤5-word bucket is
four times A's. **The short-sentence count and the personality are the same phenomenon.**

Both then use the same **hold-then-drop** at emotional peaks: B's slowest 30 s window is the
Midway payoff, and its most affecting passage (Ted Roosevelt Jr.) is also its longest section at
145 s — B buys time for feeling by *lengthening the section*, not by slowing the read.

---

## 9. What makes it sound spoken rather than written

Ranked by how strongly the measurements support each device.

1. **Sentence-length variance, not sentence brevity.** Adjacent sentences differ by 8.4 words on
   average in both — 46% of A's mean length, 68% of B's. Neither writer is uniformly short; both
   are uniformly *uneven*.
2. **Coordinating conjunctions at sentence start** — 13.9% of A's sentences, 26.5% of B's. This
   is the strongest single written-vs-spoken marker in the data. Speech chains clauses; prose
   subordinates them.
3. **Present tense for scenes, past tense for history.** A switches into present progressive
   whenever the camera is on a person ("a ninja is lying", "Markov is walking home", "Charles II
   is hiding") and back to past for exposition. Its opener bigrams show the tic directly:
   `as he`, `he knows`, `he looks`, `he goes`.
4. **The mid-sentence aside.** A's asides are *embedded* ("who by the way had also died"); B's are *standalone* ("Big mistake, buddy."). Same function,
   opposite implementation — and it is exactly what produces the sentence-length gap between the
   two channels.
5. **Spoken orthography.** B writes `cuz` 14 times to `because` twice, and uses "ain't", "folks",
   "buddy", "freaking". A uses "pissed off", "super disrespectful", "BS", "funsies", "chilling".
   Register is deliberately below written-standard in both.
6. **Fragments as beats** — 15% of B's narration sentences. Bare noun phrases ("George Patton.",
   "One problem."), verbless lists ("Trenches, barbed wire, sitting still."), one-word replies.
7. **Withheld-name reveal.** Both open a story by describing a person in full and naming them
   last, in a short sentence. Structurally identical across two unrelated channels.
8. **Concrete nouns instead of adjectives.** 60.7% / 55.6% of words are ≤4 characters; 84% come
   from the 2,000 commonest English words. The uncommon words are things (boar, cabin, carriers,
   bombers), not qualities.
9. **What is NOT doing the work** — the measurements refute three common assumptions:
   contractions (~20% rate in *both*; full forms outnumber contractions 4:1), rhetorical
   questions (4 verified in ~53 minutes of narration combined), and second-person address (under
   0.5 per 100 words). None of these carry the spoken quality here.

---

## 10. Rewrite rules

Numbered, checkable. **A-rules** reproduce Serious History's long-form anthology voice;
**B-rules** reproduce Agent Flappy's chaptered-explainer voice; **U-rules** are shared by both
and are the safe default.

### Universal

1. **Vary adjacent sentence lengths by ~8 words on average.** Measure `mean(|len[i+1] − len[i]|)`
   across the draft; target 8–9 words. This is the single strongest measured signal, and it holds
   for both channels despite their opposite means.
2. **Never write two consecutive sentences within 2 words of each other's length** more than
   twice in a row.
3. **Keep 84% of non-name words inside the 2,000 most common English words.** Mean word length
   4.4–4.6 characters; ≥55% of words at 4 characters or fewer. Any word outside that set must be
   a *thing in the story*, not a quality of it.
4. **Put a name, number or date in every 8–11 words.** A: 9.0 per 100 words; B: 13.6. Below ~8
   per 100 the writing goes abstract.
5. **Open a scene in present tense with a date and a person doing something physical**, before
   any background. "It's [date], and [person] is [-ing]." Every one of A's three stories and most
   of B's chapters do this.
6. **Describe a person fully, then name them last, in a sentence of ≤6 words.** Used by both.
7. **Do not rely on contractions to sound spoken.** Hold the contraction rate near 20% (roughly
   one contraction per four expandable auxiliaries). Over-contracting is a written writer's
   imitation of speech.
8. **Budget at most 1 rhetorical question per 1,000 words**, and place it at a stakes peak, never
   as a section opener.
9. **Spend second person deliberately: under 0.5 uses per 100 words**, concentrated in the hook
   contract and the CTA.
10. **Cash every image planted in the hook.** B's three cold-open images all return as full
    sequences later. If an image in the first 30 s never reappears, cut it or cash it.
11. **Plant one callback and pay it off 5+ minutes later**, flagged when planted ("remember his
    prediction — 6 months") and named when paid ("almost exactly 6 months after Pearl Harbor").
12. **End each section on the concrete object or the verdict, not on a summary sentence.**
13. **Keep read speed flat.** Target a 30 s-window coefficient of variation of ~10% and total
    drift under 10 WPM across the video. Do pacing with sentence length and section length.
14. **Slow down only for the payoff beat**, and only by ~20% for ~30 seconds.

### A-mode (long-form anthology, ~188 WPM, cinematic)

15. **Median sentence 17 words; mean 18–19.** Keep 42% of sentences in the 13–20 band and 37% at
    ≥20 words.
16. **Fragments under 4% of narration sentences.** Fragments here read as sloppy, not stylish.
17. **Short sentences (≤5 words) essentially zero inside narration.** Reserve them for spoken
    chapter titles and comedy beats only.
18. **Give each story 300–400 s and open it with a bare two-name fragment as a title.**
19. **Use present-tense observation verbs to move the camera**: "as he…", "he knows…",
    "he looks…", "he goes…". Aim for ~25% of sentence openers to be a pronoun or a character name.
20. **Put every aside inside the sentence, as a subordinate clause** — "who by the way had also
    died", "just for funsies", "still chilling up there". Never let
    an aside become its own sentence.
21. **Announce the horror ~15 s before delivering it** ("one of the most insane execution methods"), then deliver it in forensic physical detail.
22. **Close every story on a physical object that outlasts the people**, and consider a 100–120 s
    coda following that object forward in time.
23. **Butt-join sections.** No transition sentence — last line of one story, then the next title.
24. **After each atrocity, deflate with one comic word inside the next sentence.**

### B-mode (chaptered explainer, ~136 WPM, personality-forward)

25. **Median sentence 10 words; mean 12.** Keep 52% of sentences at ≤12 words and only 17% at
    ≥20.
26. **One sentence in six must be ≤5 words** (target 17–19%). Never let more than ~29 sentences
    pass without one; ~5–6 sentences is the working average.
27. **15% of sentences should be fragments** — bare noun phrases, verbless lists, one-word
    answers.
28. **Open one sentence in four with And / But / So / Cuz** (target 26%). "And" ~12%, "But" ~9%,
    "So" ~5%.
29. **Write `cuz`, not `because`** — roughly 7:1. Same principle for other spoken spellings.
30. **New section every 45–60 s; hold the standard deviation near 30 s.** Only the one
    human-interest sequence per video may run to ~145 s.
31. **Give every section a verdict close of ≤8 words**: "But France did nothing.",
    "The Axis was no longer unstoppable."
32. **Insert a narrator aside roughly every 100 s** — ≤6 words, evaluative, addressed to the
    viewer ("Absolute legends.", "Big mistake, buddy."). ~19 per 31 minutes. This *is* the
    short-sentence quota; write them together.
33. **Signpost every jump out loud**: "Meanwhile, on the far side of the world…", "But let's
    rewind to…", "But first…", "One problem." Never cut silently.
34. **Run one numbered motif across the video** ("Bet number one/two/three") and close the video
    by naming it.
35. **State stakes as arithmetic**, then answer with a fragment. Ask the cost, answer in one word.
36. **Open ~1 section in 4 with a bare datestamp** — "On [Month] [day], [year], …" or the
    verbless form "[Month] [year], [place], [fact]" — 8 times in 31 minutes.
37. **Use "Oh, and…" to add the extra detail after a beat has closed** (4 sentence-initial uses in
    B; A uses the same device once).

### Self-check before delivery

| Check | A-mode target | B-mode target |
|---|---|---|
| Median sentence length | 17 | 10 |
| Mean adjacent-length difference | ~8.5 w | ~8.3 w |
| % sentences ≤5 words | ~2% (titles/gags only) | 17–19% |
| % sentences ≥20 words | ~36% | ~17% |
| % fragments | <4% | ~15% |
| Longest run with no short sentence | n/a | ≤29 sentences |
| And/But/So/Cuz sentence openers | ~14% | ~26% |
| Contraction rate | ~20% | ~20% |
| Rhetorical questions per 1,000 w | ≤0.7 | ≤0.9 |
| "you/your" per 100 w | ~0.4 | ~0.3 |
| Names+numbers per 100 w | ~9 | ~13.5 |
| % words outside top-2000 | ~16% | ~17% |
| Section length | 300–400 s (stories) | 45–60 s, σ≈30 s |
| Words per section | ~518 | ~128 |
| Target WPM | ~188 | ~136 |
| 30 s-window WPM CV | ~10% | ~11% |

---

### Files

| File | Contents |
|---|---|
| `/home/user/Test-2/.work/ref/transcript-A.txt` | Raw timestamped transcript, video A |
| `/home/user/Test-2/.work/ref/transcript-B.txt` | Raw timestamped transcript, video B |
| `/home/user/Test-2/.work/analysis/script_stats.py` | All measurements |
| `/home/user/Test-2/.work/analysis/report.txt` | Side-by-side script output |
| `/home/user/Test-2/.work/analysis/stats.json` | Full machine-readable results |
| `/home/user/Test-2/.work/analysis/narration_only.json` | Sponsor/outro-excluded stats |
| `/home/user/Test-2/.work/analysis/qual-dump-{A,B}.txt` | Evidence excerpts (hooks, boundaries, short sentences, questions) |
| `/home/user/Test-2/.work/analysis/read-{A,B}.txt` | 30 s-paragraphed reading copies |
| `/home/user/Test-2/.work/analysis/extract.py` | Transcript extraction from the MCP payload |
