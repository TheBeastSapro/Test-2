# Frame-level teardown — M Simplified, "Trevor Henderson Biggest Giants Explained in 9 Minutes"

**Video:** `lrY0ErBfytQ` · M Simplified (`UCqXlPGw_s8Mr7YOSVZYjWOg`)
**Runtime:** 545 s (9:05) · **Views:** 1,537,191 · **Likes:** 15,493 · **Published:** 2026-03-06
**Teardown date:** 2026-08-09
**Purpose:** reverse-engineer the editing grammar precisely enough to rebuild it in a renderer.

---

## 0. COVERAGE AND CONFIDENCE — READ THIS FIRST

This teardown did **not** get the visual coverage that was planned. The multimodal watch tool
(`watch_youtube_video_and_ask`) is rate-limited to **5 calls per 24 hours on the current LITE plan**, and
**4 of those 5 had already been consumed before this session started**. Exactly **one** call landed
(0:00–1:00). Every subsequent window (60–150 s, 200–265 s, 400–480 s, 455–545 s) returned
`RATE LIMIT EXCEEDED`.

So: **visual coverage is 60 s of 545 s = 11.0 % of runtime.** Everything in this document is
labelled with one of four confidence tiers. Do not promote a tier-3 or tier-4 line into
`spec/style-profiles.json` without re-measuring.

| Tier | Meaning | How it was obtained |
|---|---|---|
| **[M]** MEASURED | Directly observed this session | Frame-level watch of 0:00–1:00 |
| **[D]** DERIVED | Computed, not guessed | Full timestamped transcript + official chapter list + video metadata; arithmetic shown |
| **[P]** PRIOR | From an earlier session's watch already in this repo | `spec/style-profiles.json`, `docs/editor-brief-2026-07.md`, `docs/editor-evaluation-2026-07.md` — **not re-verified today**, and in four places **contradicted** by [M] (see §11) |
| **[U]** UNDETERMINED | Could not be established | Ran out of tool budget — §12 lists the exact calls needed |

**The single most valuable new finding in this document is in §3: M Simplified does not have one
non-scene canvas, it has three (white, black void, red). The existing profile only models white,
and the numbers/measurements — the thing we assumed triggers white — actually land on BLACK.**

---

## 1. RULES YOU COULD PROGRAM

Everything below is precise enough to become a config value or a renderer rule. Tier tag on each.

### 1.1 Timeline / structure

| Rule | Value | Tier |
|---|---|---|
| Total runtime | 545 s | [D] |
| Creature count | 8 | [D] |
| Section boundaries (s) | 0, 66, 136, 209, 274, 329, 390, 457 — last section ends 533 | [D] |
| Section length range | 55–76 s (mean 66.6 s, median 66.5 s) | [D] |
| Intro / branding / "welcome to" preamble | **0 s. None.** First narrated word is the first creature's name. | [M] |
| First creature named at | 0:00 (word 1) | [M][D] |
| Every section opens with the creature's NAME as the first word(s) | 8/8 sections | [D] |
| Sections that then run a narrative incident vignette before the spec block | **5 of 8** (Behemoth, Remain Indoors, Wandering Faith, Bird Watcher, Tree Head) | [D] |
| Sections that go straight to spec, no incident | **3 of 8** (Sky Mantas, Wandering Doom, Breaking News) | [D] |
| Incident vignette length | 21–30 s (mean 25 s) | [D] |
| Spec block length | 36–61 s | [D] |
| Mid-roll CTA | starts 200 s, ends 209 s → **9 s**, placed at the END of creature 3 of 8 (36.7 % through runtime) | [D] |
| Outro CTA | starts 533 s, ends 545 s → **12 s**, hard end, no end-card dwell after speech stops | [D] |
| Sections stating an explicit size figure | 6 of 8 (all but Wandering Doom and Breaking News) | [D] |

### 1.2 Narration pace — the number most worth copying

| Rule | Value | Tier |
|---|---|---|
| Total narrated words | 1,661 | [D] |
| Global narration rate | **182.9 wpm** | [D] |
| Per-section rate | 164.6 – 194.8 wpm; every section ≥ 164 wpm | [D] |
| Dead air | Effectively none — transcript segments are contiguous end-to-end for all 545 s | [D] |

> This corrects a working assumption in `docs/competitor-style-profiles.md`, which frames 160–180 wpm as
> Darkly's differentiator against a "competitor field of 120–140". **M Simplified narrates at 183 wpm.**
> Narration speed is not what separates the 2.7 M video from this 1.5 M video.

### 1.3 Frame families — three canvases, not one

| Family | Renders as | What it carries | Share of the 0:00–1:00 sample | Tier |
|---|---|---|---|---|
| **A — full-frame scene** | Composited environment, creature integrated | Story action, atmosphere | 38 s = **63.3 %** | [M] |
| **B — white canvas** | Pure `#FFFFFF` | Short text card + icon pairs at narration pivots | 7 s = **11.7 %** | [M] |
| **C1 — black void canvas** | Pure/near black | **Measurements, scale comparisons, anatomy call-outs, full-body reveal** | 12 s = **20.0 %** | [M] |
| **C2 — red field** | Saturated red full-bleed | Impact / death beat close-up only | 3 s = **5.0 %** | [M] |

Config sketch:

```json
"canvasFamilies": {
  "fullFrameScene":  { "id": "A"  },
  "whiteCard":       { "id": "B",  "bg": "#FFFFFF", "durSec": [1, 3] },
  "blackSpecVoid":   { "id": "C1", "bg": "#000000", "durSec": [2, 4] },
  "redImpactField":  { "id": "C2", "bg": "red",     "durSec": [1, 2], "maxPerIncident": 2 }
}
```

### 1.4 THE CANVAS TRIGGER RULE (the central question)

**One-sentence rule, as measured:**

> A **numeric, scale-comparison or anatomy** statement cuts to the **BLACK void** canvas; a **beat-boundary
> line** — the definition line, the sourcing line, or the pivot conjunction that opens a new sub-topic —
> cuts to a **1–3 s WHITE text/icon card**; a **kill or impact word** cuts to a **1–2 s RED field**;
> everything else stays on a full-frame composited scene.

Evidence, every non-scene span in 0:00–1:00:

| Span | Dur | Canvas | Narration during it | On-canvas graphics | Trigger class |
|---|---|---|---|---|---|
| 0:00–0:01 | 1 s | WHITE | "Behemoth" | roster row of creature cards | section entry |
| 0:27–0:28 | 1 s | RED | "…a massive boulder came crashing down" | boulder close-up | impact |
| 0:29–0:31 | 2 s | RED | "…crushed beneath it, dying instantly" | boulder close-up | kill beat |
| 0:31–0:33 | 2 s | WHITE | "Behemoth is described as a…" | red/black text | definition line |
| 0:33–0:35 | 2 s | BLACK | "…colossal reptilian, lizard-like titan" | full-body creature | full-body reveal |
| 0:35–0:38 | 3 s | WHITE | "Based on satellite imagery and seismic data" | satellite + seismic **icons** | sourcing line |
| 0:38–0:40 | 2 s | BLACK | "…its height is estimated at around" | measurement line | **number** |
| 0:44–0:48 | 4 s | BLACK | "…believed to be larger than Mount Everest" | Everest comparison | **size comparison** |
| 0:48–0:52 | 4 s | BLACK | "…teeth may span several miles… ridges along its skull" | anatomical arrows | **anatomy call-out** |
| 0:55–0:56 | 1 s | WHITE | "Unlike ordinary monsters…" | yellow/black text | pivot conjunction |

Note 0:40–0:48 sits an **Earth-atmosphere diagram with the creature in it** on a full-frame plate rather
than a void — so a scale statement that has a real-world referent (the exosphere) can be staged as a
diagram-over-scene instead of a void card. Only one instance observed; treat as a variant, not a rule. [M]

**Programmable trigger table:**

```json
"canvasTrigger": {
  "number":            "blackSpecVoid",
  "sizeComparison":    "blackSpecVoid",
  "anatomyCallout":    "blackSpecVoid",
  "fullBodyReveal":    "blackSpecVoid",
  "definitionLine":    "whiteCard",
  "sourcingLine":      "whiteCard",
  "pivotConjunction":  "whiteCard",
  "sectionEntry":      "whiteCard",
  "impactOrKillWord":  "redImpactField",
  "_default":          "fullFrameScene"
}
```

Detectable in a script by regex/NLP:
- `number` → `\b\d[\d,\.]*\s*(km|m|tons|amps|miles|years)\b`
- `sizeComparison` → `larger than|taller than|the size of|compared to|Mount \w+`
- `pivotConjunction` → sentence-initial `Unlike|Despite|Instead|Although|However`
- `definitionLine` → `^<Name> is (described as|a)\b`
- `sourcingLine` → `Based on|Witnesses|Reports suggest|It is estimated`

### 1.5 Block-level canvas density — the strongest structural rule

Within the sampled minute, canvas usage is not spread evenly; it is gated by block type. [M]

| Block | Window | Full-frame | Canvas (B+C) |
|---|---|---|---|
| **Incident vignette** | 0:01–0:31 (30 s) | 27 s = **90 %** | 3 s = 10 % (both RED impact) |
| **Spec block** | 0:31–1:00 (29 s) | 11 s = **38 %** | 18 s = **62 %** (6 s white, 12 s black) |

> **Rule: the incident vignette is ~90 % full-frame composited scene; the spec block is ~60 % canvas.
> The canvas is not a style, it is the visual signature of the spec block.**

Runtime-level extrapolation (**[D], modelled — not measured**):
incident total 125 s × 0.90 + spec total 399 s × 0.38 ≈ 264 s full-frame → **≈ 48 % full-frame,
≈ 52 % canvas across the whole video**. This is arithmetic on a single 60 s sample and disagrees with
the prior-session figure of 75 % / 25 % ([P]). Do not encode either number until §12's calls are run.

### 1.6 Sourcing / asset economy

| Rule | Value | Tier |
|---|---|---|
| Creature imagery origin | **(b) PNG cutout composited onto an editor-controlled background.** Not whole pre-made artworks, not stock, not 3D renders. Evidence: hard cutout edges and lighting that does not match the plate. | [M] |
| Distinct creature source images in the Behemoth section | **1** | [M] |
| Distinct scenes built from it in 0:00–1:00 | **5** | [M] |
| **Cutout-reuse ratio** | **1 source image : 5 built scenes** | [M] |
| Background plates | Digital paintings + solid-colour voids. **No photographs, no game/film stills observed.** | [M] |
| Creature tinted to match plate | Reported in a prior session's Behemoth note; not independently confirmed in this pass | [P] |

```json
"sourcing": { "creatureAsset": "png-cutout", "cutoutsPerSection": 1, "scenesPerCutout": 5,
              "backgroundPlate": "digital-painting", "banStockPhoto": true, "ban3dRender": true }
```

### 1.7 Text layer

| Rule | Value | Tier |
|---|---|---|
| Persistent creature-name title | **Yes** | [M] |
| Position | top-centre | [M] |
| Case | Title Case | [M] |
| Font character | chunky bold comic | [M] |
| Fill / stroke | **white fill, black outline** (over the dark mountain scene — see §11, this is inverted vs the stored profile) | [M] |
| Frames carrying some text | **≈ 95 %** | [M] |
| Caption animation in | **instant pop**, no scale or slide ramp observed | [M] |
| Caption forms | speech bubbles attached to stick figures; free narrative text on canvas cards | [M] |
| Caption colour on canvas | red/black (0:31), yellow/black (0:55) — colour changes between cards | [M] |
| Words per caption | [U] — not resolved at this granularity | [U] |
| Caption hold duration | [U] — not resolved separately from shot duration | [U] |

### 1.8 Motion

| Rule | Value | Tier |
|---|---|---|
| Every held image moves | **Yes** — continuous slow zoom on most shots | [M] |
| Zoom amount | ≈ **1.1×** per shot | [M] |
| Pan direction | [U] | [U] |
| Screen shake | 2 instances in 60 s: **0:03** (rhythmic, low amplitude) and **0:15** (high amplitude) | [M] |
| Shake trigger | Seismic/impact narration — 0:03 "satellites detected unusual seismic activity"; 0:15 "the gigantic eye slowly opened" | [M] |
| Glitch / chromatic aberration | **None observed in 0:00–1:00** | [M] |
| Screen-content change rate | 20 changes in 60 s → **mean 3.0 s**, **median 2.0 s**, **min 1 s**, **max 10 s** | [M] |

The 10 s maximum (0:15–0:25, eye opens then head rises) is a single continuously-animated beat, not a
static hold. It nonetheless **violates the `maxHoldSec: 4.0` invariant** currently in
`spec/style-profiles.json`. Caveat: the shot log may have merged sub-changes inside a continuous
animation, so the true change rate is a lower bound of ~20 changes/min.

### 1.9 Roster / section entry

| Rule | Value | Tier |
|---|---|---|
| Roster appears | at **0:00**, before anything else | [M] |
| Cells visible | **3, in a single 1×3 row** — **not** the 9-cell 3×3 grid in the stored profile | [M] |
| Roster background | white | [M] |
| Entry move | **punch-in zoom into the first cell, ≈ 0.5 s** | [M] |
| Roster returns between sections | [U] — no visual coverage of any section boundary | [U] |

**Low confidence on cell contents:** the tool named the cells "Behemoth, Sky Man, The Bloop". "The Bloop"
is **not** in this video's roster, so at least one label is a misread. The cell *count* of 3 is also
suspect given the video has 8 creatures — it may be a partial view, a scrolling lineup, or a misread.
**Do not encode roster geometry from this pass.**

### 1.10 Colour

| Role | Value | Used for | Tier |
|---|---|---|---|
| Canvas white | `#FFFFFF` (pure) | white text/icon cards, roster | [M] |
| Canvas black | black void | spec sheet: measurements, scale, anatomy, full-body reveal | [M] |
| Impact red | saturated red full-bleed | kill/impact beats only (2 in 60 s) | [M] |
| Title ink | white fill + black outline | persistent creature name | [M] |
| Accent green | measurement lines and call-out arrows | [M] |
| Accent yellow | narrative caption text (0:55 card) | [M] |
| Accent red (text) | narrative caption text (0:31 card) | [M] |
| Accent blue / orange | diagram layers (atmosphere diagram, 0:40) | [M] |

House palette is white/black/red (`#D62020`). **M Simplified's accent set is green + yellow with red
reserved for impact**, plus blue/orange inside diagrams. The house red accent remains a deliberate
divergence, as already documented — nothing here changes that decision, but note M Simplified spends red
on *impact framing*, not on titles.

### 1.11 Audio

| Rule | Value | Tier |
|---|---|---|
| Distinct SFX in 0:00–1:00 | **6** → **6 SFX/min measured** | [M] |
| SFX timestamps | rumble 0:03 · squelch 0:16 · roar 0:17 · whoosh 0:25 · impact 0:28 · beep 0:36 | [M] |
| Music bed | **constant, continuous low-frequency suspense drone**, present throughout the sample | [M] |
| Do cuts carry a sound? | **Mostly silent.** Only cuts that coincide with a physical event carry an impact/whoosh. | [M] |

The measured 6 SFX/min contradicts the stored `sfxPerMin: 20` ([P]). Both may be right under different
counting rules (salient discrete hits vs. every layered element). §12 has the disambiguating call.

### 1.12 Humour

| Rule | Value | Tier |
|---|---|---|
| Gag form observed | **stick figures with speech bubbles**, 0:10–0:15 (5 s) — scientists reacting on the mountain | [M] |
| Gag frequency | [U] — one instance in 11 % of runtime is not a rate | [U] |
| Meme text / photo gags | none observed in the sample | [M] |

---

## 2. SHOT LOG — 0:00 to 1:00 (complete) [M]

| # | In | Dur | Family | Content |
|---|---|---|---|---|
| 1 | 0:00 | 1 s | B white | roster row of 3 creature cards |
| 2 | 0:01 | 2 s | A | snowy mountain range, stick figures |
| 3 | 0:03 | 7 s | A | Behemoth head appears behind the mountains |
| 4 | 0:10 | 5 s | A | figures with equipment + speech bubbles |
| 5 | 0:15 | 10 s | A | eye opens within the rock, head rises |
| 6 | 0:25 | 2 s | A | boulder falls toward the figures |
| 7 | 0:27 | 1 s | C2 red | boulder close-up on red field |
| 8 | 0:28 | 1 s | A | boulder impact in the mountain scene |
| 9 | 0:29 | 2 s | C2 red | boulder close-up on red field |
| 10 | 0:31 | 2 s | B white | narrative text card |
| 11 | 0:33 | 2 s | C1 black | full-body Behemoth on black |
| 12 | 0:35 | 3 s | B white | satellite + seismic icons |
| 13 | 0:38 | 2 s | C1 black | measurement line |
| 14 | 0:40 | 4 s | A | Earth-atmosphere diagram with creature |
| 15 | 0:44 | 4 s | C1 black | Mount Everest scale comparison |
| 16 | 0:48 | 4 s | C1 black | anatomical arrows |
| 17 | 0:52 | 3 s | A | Behemoth head in mountain range |
| 18 | 0:55 | 1 s | B white | narrative text card |
| 19 | 0:56 | 2 s | A | green field, creature + figure |
| 20 | 0:58 | 2 s | A | snowy mountain, equipment |

20 changes / 60 s. Mean 3.0 s, median 2.0 s.

---

## 3. SCENE CONSTRUCTION — the staged reveal [M]

Only one section had visual coverage, so this is **one worked example**, not two or three. The requested
second and third examples are [U].

### The Behemoth cold open, 0:00–0:31 — layer stack and beat durations

Layer stack, bottom to top:

1. **Background plate** — snowy mountain range, digital painting.
2. **Mid-ground** — mountain peaks that occlude the creature.
3. **Creature layer** — Behemoth head PNG cutout, positioned *behind* the peaks.
4. **Foreground** — stick-figure scientists + equipment props; later a falling boulder.
5. **Text layer** — persistent "Behemoth" title top-centre; speech bubbles on the figures.

Beat sheet:

| Beat | In–out | Dur | What moves |
|---|---|---|---|
| 1 — wide establishing | 0:01–0:03 | 2 s | slow zoom on the plate; figures static |
| 2 — creature emerges | 0:03–0:10 | 7 s | head **rises from behind the peaks** (upward); screen shake starts at 0:03 |
| 3 — human reaction | 0:10–0:15 | 5 s | figure props + speech bubbles pop in |
| 4 — reveal escalation | 0:15–0:25 | 10 s | eye opens, head rises further; heavy shake at 0:15 |
| 5 — threat descends | 0:25–0:27 | 2 s | boulder falls (downward) |
| 6 — impact cut-in | 0:27–0:31 | 4 s | red field × 2, one full-frame impact frame sandwiched between them |

**The signature move is confirmed: the creature layer sits BEHIND a mid-ground occluder and rises
upward into frame, in the same location, rather than being cut to.** The escalation is achieved by
*adding layers and raising the creature*, not by changing location — one plate carries beats 1–5,
about 26 s of screen time.

The requested "wide → closer → back wide" pattern was **not** observed in this window; the escalation
runs continuously on one plate and then cuts to the red impact field. Whether the wide/close/wide
alternation appears in later sections is [U].

---

## 4. SECTION MAP [D]

Derived from the official chapter list in the video description, cross-checked against the first
utterance of each name in the transcript (chapter marks run 1–2 s behind the spoken name; spoken times
below).

| # | Creature | Spoken start | End | Dur | Words | wpm | Incident? | Incident len | Size figure stated |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Behemoth | 0:00 | 1:06 | 66 s | 198 | 180.0 | yes | 30 s | 800 km; head > Everest |
| 2 | Sky Mantas | 1:06 | 2:16 | 70 s | 192 | 164.6 | **no** | — | 4 km / 350 m / 1 km / 10 km |
| 3 | Remain Indoors | 2:16 | 3:29 | 73 s | 237 | 194.8 | yes | 23 s | 9 km; 910,000 tons |
| — | **MID-ROLL CTA** | **3:20** | **3:29** | **9 s** | 24 | — | — | — | — |
| 4 | The Wandering Faith | 3:29 | 4:34 | 65 s | 197 | 181.8 | yes | 21 s | 1.5 km |
| 5 | The Wandering Doom | 4:34 | 5:29 | 55 s | 174 | 189.8 | **no** | — | **none** |
| 6 | Breaking News | 5:29 | 6:30 | 61 s | 193 | 189.8 | **no** | — | **none** |
| 7 | The Bird Watcher | 6:30 | 7:37 | 67 s | 199 | 178.2 | yes | 22 s | 300 m – 1.5 km |
| 8 | Tree Head / Big Branch | 7:37 | 8:53 | 76 s | 230 | 181.6 | yes | 29 s | 400 m – several km; 100,000 t |
| — | **OUTRO CTA** | **8:53** | **9:05** | **12 s** | 41 | 205.0 | — | — | — |

Observations worth encoding:
- The two sections with **no size figure** (Wandering Doom, Breaking News) are also two of the three with
  **no incident**, and are the **two shortest sections**. Weak-canon creatures get the compressed
  spec-only treatment. [D]
- Two consecutive sections carry a **"day 17" / "day 18"** diegetic date tag (Wandering Faith, Wandering
  Doom) — a mini-continuity device used only for the paired "Wandering" entities. [D]
- Sections 4 and 5 are ordered so the two "Wandering" creatures are adjacent — roster ordering groups
  by name family. [D]

### Number-mention map (canvas-trigger input) [D]

Every numeric/measurement utterance, for scheduling black-void cards:

`0:39` 800 km · `0:46` Everest · `0:48` several miles · `1:22` 4 km · `1:25` 350 m to 1 km ·
`1:28` 10 km · `1:57` 5 years · `2:03` 3 years · `2:14` 50,000 amps · `2:57` 9 km · `3:00` 910,000 tons ·
`4:12` 1.5 km · `7:00` 300 m – 1.5 km · `8:16` 400 m · `8:47` 100,000 tons

**15 measurement utterances across 8 sections = 1.9 per section**, clustered inside spec blocks.
If the black-void card runs 2–4 s per number as measured at 0:38/0:44/0:48, that predicts roughly
**30–60 s of black-void canvas across the video from numbers alone**, before adding full-body reveals
and anatomy call-outs.

---

## 5. MID-ROLL CTA [D] / [U]

- **Timing:** 200–209 s, **9 s**, at 36.7 % of runtime, placed at the **end of creature 3 of 8** — it
  interrupts nothing; it lands after the Remain Indoors spec block closes and before the Wandering
  Faith name is spoken.
- **Script:** *"If you've made it this far, you probably like this kind of content. So don't forget to
  like, subscribe, and drop a comment. It helps the video reach more people and supports the channel."*
- **Ask order:** like → subscribe → comment. Same order as the outro. [D]
- **Visual treatment:** **[U]** — no visual coverage. A prior session recorded it as "stick figure on
  white canvas, LIKE / SUBSCRIBE / COMMENT" ([P], unverified today).

**Outro CTA:** 533–545 s, **12 s**, ask order like → subscribe → comment, and the comment ask is
specific — *"I really want to know what topic you want me to explore next."* The video ends the instant
narration ends; there is no silent end-card tail. [D]

---

## 6. WHAT THIS CHANGES vs. THE STORED PROFILE

`spec/style-profiles.json → profiles["m-simplified"]` was built from a prior full watch. Four of its
values are **contradicted** by today's direct measurement, and one whole concept is **missing**.

| Field | Stored [P] | Measured today [M] | Verdict |
|---|---|---|---|
| *(missing)* black canvas | not modelled at all | **20 % of the sampled minute is a black void canvas carrying all measurements, scale comparisons and anatomy call-outs** | **Add it. Highest-value correction.** |
| `whiteCanvasTrigger` | `["number","size-comparison","spec"]` | numbers and size comparisons trigger **black**, not white; white carries definition / sourcing / pivot lines | **Wrong mapping — revise** |
| `title.fill` / `title.stroke` | `#000000` fill, `#FFFFFF` stroke | **white fill, black stroke** over a dark scene | Likely context-dependent (flips on white canvas). Needs one call to settle. |
| `roster.cells` / `grid` | 9 cells, `3x3` | **3 cells, 1×3 row** at 0:00 | Conflict. Today's read has a known misread in its cell labels — **treat both as unreliable** |
| `audio.sfxPerMin` | 20 | **6** salient discrete hits per minute | Conflict, possibly a counting-rule difference |
| `pacing.avgShotSec` | 2.2 | **3.0 mean / 2.0 median** | Today's is a lower bound (merged sub-changes) |
| `pacing.maxHoldSec` | 4.0 | one **10 s** continuously-animated beat | The invariant as written is violated by the reference itself |
| `layout.fullFramePct` | 0.75 | 0.633 in the sample; ≈0.48 modelled over runtime | Unresolved — do not change without §12 |
| `motion.shakeCount9min` | 9 | **2 in the first 60 s** (≈18/9 min at that rate) | Conflict; the first minute is an impact-heavy cold open, so extrapolation is unsafe |
| `midCta.atSec` / `durSec` | 201 / 9 | **200 / 9** | **Confirmed** |
| `signature` | creature rises from behind a background element | **Confirmed** — head rises from behind mountain peaks, 0:03 and 0:15 | **Confirmed** |
| `palette.accents` | green, yellow | **Confirmed** (+ blue/orange inside diagrams, red for impact) | **Confirmed** |
| `_universal.musicBed` | constant low-freq drone | **Confirmed** | **Confirmed** |
| `_universal.textOnScreenPct` | 0.95 | **Confirmed ≈95 %** | **Confirmed** |
| `_universal.rosterPunchInSec` | 0.5 | **Confirmed ≈0.5 s** | **Confirmed** |

---

## 7. WHAT I COULD NOT DETERMINE

Stated plainly rather than filled with guesses.

1. **White-canvas spans anywhere after 1:00.** The requested "timestamp every white-canvas span in the
   video" is answered for 11 % of runtime only.
2. **True white-vs-full-frame percentage over runtime.** Two incompatible figures exist (75/25 stored,
   ≈48/52 modelled today). Neither is trustworthy.
3. **Section start/end transition mechanics.** No coverage of any of the 7 section boundaries — whether
   the roster returns, whether there is a card, whether the punch-in repeats per section.
4. **A second and third scene layer-stack example.** Only the Behemoth cold open was observed.
5. **The wide → close → back-wide alternation.** Not present in the one section observed; unknown elsewhere.
6. **Words per caption and caption hold duration** as distinct from shot duration.
7. **Caption position rules** beyond "speech bubbles attach to figures; narrative text sits on cards".
8. **Pan direction and whether pan or zoom dominates.**
9. **Glitch / chromatic aberration anywhere in the video.** None in the first minute; the stored profile
   does not claim any for M Simplified either, but this is not the same as confirming absence.
10. **Mid-roll CTA visual treatment.**
11. **Humour rate.** One gag in one minute is not a rate.
12. **Roster geometry.** Today's read is internally inconsistent (named a creature not in the video).
13. **Whether the creature cutout is colour-tinted to match the plate.** Asserted in a prior session,
    not confirmed today.
14. **Finale treatment** — whether section 8 escalates visually relative to sections 1–7.

---

## 8. THE EXACT CALLS NEEDED TO FINISH THIS

Budget is 5 calls / 24 h. This closes every [U] above in five calls, and they are ordered so that
calls 1–2 alone close the highest-value gaps.

| # | Window | Why | Closes |
|---|---|---|---|
| 1 | **196–276 s** | Straddles the mid-roll CTA, the end of section 3 and the start of section 4 — the only window that gets a CTA treatment AND a full section boundary in one call | 3, 10, plus a second layer-stack example |
| 2 | **136–210 s** | Remain Indoors: an incident-led section containing the video's densest number cluster (9 km, 910,000 tons at 2:57–3:02) — the decisive test of the black-void trigger rule | 1, 2, canvas-trigger confirmation |
| 3 | **274–390 s** | The two spec-only, no-number sections back to back — tests what the canvas does when there is nothing to put a number on | 2, 5, 11 |
| 4 | **390–460 s** | Bird Watcher, incident-led, contains a range measurement at 7:00 | 4, 5, 6, 7, 8 |
| 5 | **455–545 s** | Finale + outro | 9, 14, and the outro end-card |

Ask each call for: (a) a complete shot log with a frame-family tag per shot, (b) every non-scene canvas
span with its background colour, duration and the narration during it, (c) title fill/stroke on both
scene and canvas frames, (d) roster cell count if a roster appears, (e) an SFX timestamp list with a
stated counting rule.

---

## 9. SOURCES USED

- `mcp__NexLev__watch_youtube_video_and_ask`, `lrY0ErBfytQ`, `startOffset=0s`, `endOffset=60s` — the
  single successful visual call (§2, §3, and all [M] rows).
- `mcp__NexLev__get_video_transcript`, `lrY0ErBfytQ` — full timestamped transcript, 1,661 words (all [D]).
- `mcp__NexLev__youtube_video_details`, `lrY0ErBfytQ` — runtime 545 s, view/like counts, publish date,
  and the description's official 8-chapter timestamp list used for §4.
- `spec/style-profiles.json` and `docs/competitor-style-profiles.md` — prior-session measurements,
  used only for the [P] rows and the §6 comparison.
