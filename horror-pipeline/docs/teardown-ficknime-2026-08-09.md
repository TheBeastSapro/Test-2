# Frame-level teardown — Ficknime, "Every Doctor Nowhere Monster Explained in 9 Minutes"

**Video:** `VZPZi8yb5mg` · 591 s (9:51) · 444,295 views · published 2026-02-22 · channel `UCvyAq4cbdLWlH6j_OKin3iw`
**Teardown date:** 2026-08-09

---

## 0. Coverage statement — read this before trusting any number

The assigned tool (`mcp__NexLev__watch_youtube_video_and_ask`) was **unusable**. Its quota is 5 calls / 24 h and it was already at 5/5 before this session's first call; the one call attempted timed out server-side at 60 s and returned nothing while consuming the last unit. **Zero seconds of this video were analysed by the multimodal tool.**

Direct download of the video was also blocked (YouTube bot-detection / missing GVS PO token on every player client: `tv`, `web_safari`, `ios`, `mweb`, `web_embedded`, `android_vr`).

**What I did instead.** YouTube publishes a storyboard track as ordinary sprite-sheet JPEGs on `i.ytimg.com`, which is neither metered nor blocked. I fetched storyboard level `sb0` — 14 sheets, 3×3 tiles of 320×180 — and split it into **120 real frames covering 100 % of the runtime at a fixed 4.925 s interval** (`fps` field = 0.20304568527918782). Every frame was then measured programmatically with numpy/PIL (background sampling, layout classification, element bounding boxes, per-section palette extraction) and read visually at 3–4× upscale.

| Source | What it covers | Tag |
|---|---|---|
| 120 storyboard frames, 320×180, every 4.925 s, t = 0 → 586.1 s | 100 % of runtime, **coarse time resolution, low spatial resolution** | **[M] MEASURED** |
| Full transcript with cue timings (277 cues) | script, pacing, section boundaries, CTA presence | **[D] DERIVED** |
| `youtube_video_details` (chapters, duration, metadata) | section boundaries cross-check | **[D] DERIVED** |
| — | anything faster than 4.925 s, anything audio, anything sub-pixel at 320×180 | **[U] UNDETERMINED** |

**The honest summary of this coverage:** it is *better* than a single 60 s multimodal window for every question about **proportion, structure, palette, layout and sourcing** — those are settled across the whole video, not extrapolated from one minute. It is *useless* for every question about **cut counts, animation timing, easing, and audio**, because a 4.925 s sampling interval cannot see a 2 s shot or a 0.3 s slide. I have not guessed at any of those. They are listed in §8.

**Timestamp precision:** each storyboard tile represents the frame at `index × 4.925 s`. Treat every timestamp in this document as **±2.5 s**.

**Confidence tags used throughout:** `[M]` measured from frames · `[D]` derived from transcript/metadata · `[U]` undetermined.

---

## 1. Rules you could program

Everything in this section is precise enough to become a config value or a renderer rule. Tag on every line.

### 1.1 Canvas and layout

| Rule | Value | Tag |
|---|---|---|
| Canvas colour is **not** pure white | `#F8F8F8` (measured 248,248,248 on the ring of 104/120 frames) | [M] |
| Runtime on white canvas | **86.7 %** (104/120 frames) | [M] |
| Runtime on a *grey* canvas variant | **3.3 %** (4/120) — `#D0D0D0` at 5:10, `#B8B8B8` at 7:28–7:38 | [M] |
| Runtime on black canvas holding a boxed image | **0.8 %** (1/120, 0:19.7) | [M] |
| Runtime on full-bleed edge-to-edge imagery | **5.0 %** (6/120) — 95 % CI ≈ 1–9 % at n=120 | [M] |
| Runtime on pure-black transition frames | **3.3 %** (4/120) + 1 grey dissolve frame | [M] |
| **Canvas of any colour, combined** | **90.8 %** | [M] |
| Content is **boxed**, never bled, on canvas frames | hard-edged rectangle, no border, no rounded corners, no drop shadow | [M] |
| Box border | **none**. Edge probe on f26/f47/f81/f114 shows canvas → **exactly one** intermediate pixel → image. The intermediate value tracks the image colour (210 / 227 / 88 / 227 against canvas 255), which is antialiasing, not a fixed-colour stroke. Rules out any border thicker than ~6 px at 1080p | [M] |
| Box top edge | y ≈ **0.18–0.22 × frameH** (30–40 px of 180) — sits immediately under the title | [M] |
| Box height | **0.61–0.78 × frameH** (110–141 px of 180) | [M] |
| Box width | follows source aspect; measured **0.27–0.43 × frameW** | [M] |
| Box aspect ratios in use | **1:1 square (most common)**, ~0.68:1 portrait, ~1.5:1 landscape | [M] |
| Solo box horizontal position | **dead centre**, x = 160.0 ± 0.5 of 320 (measured on 11 frames) | [M] |

### 1.2 Composition grammar — the core layout engine

| Rule | Value | Tag |
|---|---|---|
| **Dominant layout is a horizontal N-up row on the canvas** | not a single hero image | [M] |
| 2-up ("creature vs human") | left element centre ≈ **0.27 × W**, right element centre ≈ **0.75 × W** | [M] |
| 3-up (spoken list of three) | element centres ≈ **0.19 / 0.50 / 0.78 × W** — evenly distributed | [M] |
| The right-hand slot is almost always the **human proxy pictogram** | 2-up appears in every section sampled | [M] |
| Elements sit in the band **y ≈ 0.20–0.95 × H** (below the title) | [M] |

### 1.3 Title and badge (persistent chrome)

| Rule | Value | Tag |
|---|---|---|
| Persistent creature title | **top-centre**, centred at x = 158–160 of 320 (**50.0 % ± 0.6**) | [M] |
| Title vertical band | text rows y = **10–21 of 180** → top at **5.6 %**, baseline at **11.7 %** of frame height | [M] |
| Title cap height | **≈ 6.7 % of frame height** (≈ 72 px at 1080p) | [M] |
| Title case | **Title Case**, not ALL CAPS ("Boiled One", "The Terrible Thing in One House") | [M] |
| Title typeface | **high-contrast serif**, sharp fine serifs, Didone/transitional character. Black, no stroke, no shadow | [M] |
| Title present on | white/grey canvas frames only — **absent on all full-bleed and black frames** (f4, f40, f41, f44, f48, f57, f66, f72, f107, f118, f119) | [M] |
| **Persistent per-section badge, top-right** | present in **85/110** sampled in-section frames (the misses are low-saturation badges and full-bleed frames, not true absences) | [M] |
| Badge geometry | **25 × 25 of 320×180** → ≈ **150 × 150 px at 1080p**; bbox x 285–310, y 3–27; right margin ≈ 10/320 (**3.1 % of W**), top margin ≈ 3/180 (**1.7 % of H**) | [M] |
| Badge shape | **regular polygon, ~9–10 sides** (reads as a rounded octagon/decagon) — *not* a circle | [M] |
| Badge content | section accent colour as fill + a high-contrast cutout of that creature | [M] |
| Badge is the same asset as the roster cell | identical shapes and fills at 0:00 and pinned top-right | [M] |

### 1.4 Palette — 12 per-section accents, one per creature

Canvas `#F8F8F8` · ink `#000000` · annotation red (freehand marker) · plus exactly one accent per section, carried by the badge and its roster cell.

| # | Section | Accent (modal badge fill) | Tag |
|---|---|---|---|
| 1 | Locust | `#AC9434` dark gold | [M] |
| 2 | Boiled One | `#DC0404` red | [M] |
| 3 | The Doctor | `#8C2CA4` purple | [M] |
| 4 | The Terrible Thing in One House | `#D4AC34` amber | [M] |
| 5 | Anklager | `#4424C4` indigo | [M] |
| 6 | Watch Tower | `#54A4C4` / near-neutral grey `#5D585E` — **the one desaturated section** | [M] |
| 7 | Longboy Bonsai | `#445CC4` blue | [M] |
| 8 | Disease | `#146C4C` dark green | [M] |
| 9 | Cone Zone | `#84C444` lime | [M] |
| 10 | Fleshbeds | `#E4045C` magenta | [M] |
| 11 | Filbus | `#54C44C` green | [M] |
| 12 | Guilt | `#EC7C04` orange | [M] |

**Accent usage rule:** the accent appears **only** in the roster cell and the pinned badge. It is not used for text, icons, arrows or highlights. Ink is black everywhere else. `[M]`

**Red is a separate, reserved annotation colour** — freehand circle at 0:14.8, red X over a silhouette at 1:43.4, freehand rounded-rect at 9:11.6. Stroke reads as a marker/pen, roughly 3–4 px at 1080p equivalent. It is used **only** for "look here" / "not this". `[M]`

### 1.5 Roster

| Rule | Value | Tag |
|---|---|---|
| Roster grid appears at | **0:00.0 — frame one, no cold open before it** | [M] |
| Cells | **12** (one per creature) | [M] |
| Arrangement | **5 / 4 / 3**, each row horizontally centred (not a rectangular grid) | [M] |
| Cell shape | same ~9–10-sided polygon as the badge | [M] |
| Cell size | 49–50 px of 320 → **≈ 300 px at 1080p** | [M] |
| Column pitch | ≈ 62 px of 320 (**≈ 375 px at 1080p**) | [M] |
| Row pitch | ≈ 62 px of 180 (**≈ 372 px at 1080p**), rows at y = 2 / 61 / 126 of 180 | [M] |
| Cell label | **below** each cell, bold serif, black, Title Case | [M] |
| Labels are **short forms** | "Doctor", "TTTIOH" in the roster vs "The Doctor", "The Terrible Thing in One House" as section titles | [M] |

### 1.6 Typography

| Rule | Value | Tag |
|---|---|---|
| **One typeface for the entire video** | the same high-contrast serif for titles, labels, captions and callouts | [M] |
| Styles in use | regular + **italic** (italic reserved for a humour word — "Creepy" at 8:12.5) | [M] |
| Colour | black on canvas; no stroke, no shadow, no outline anywhere | [M] |
| Case convention | Title Case for the persistent title; **lowercase** for part-labels ("beige head", "jet-black torso", "hands", "legs", "mistake", "regret", "tall", "trumpets", "distant screaming"); sentence case for full-sentence captions | [M] |
| Caption word count | **1 to 13 words** — measured examples: 4 ("On August 13th, 2003"), 5 ("But one thing is clear"), 9 ("bypassing their physical form / to consume their internal organs"), 13 ("Why do I feel like I'm the one who has to start this?") | [M] |
| Caption line breaks | multi-word captions break to **2 lines**, centred on each other | [M] |
| Caption position | **contextual, not fixed** — directly under/beside the icon it labels, or in the empty half of a 2-up layout | [M] |
| Text on *every* frame? | **No.** Full-bleed and black frames carry no text at all | [M] |

### 1.7 Icon language

Two registers, mixed freely in the same frame, both pure black on canvas:

| Register | Examples measured | Tag |
|---|---|---|
| **Solid filled pictograms** | human proxy figure, trumpet, CRT TV, monitor + PC tower, phone, house, bed, fan, city skyline, ruler/height-scale, group-of-three people, bodies lying prone, gavel, bathtub, toys | [M] |
| **Thin-line outline icons** (Noun-Project style, no fill) | baby, gravestone "R.I.P.", lightbulb + gear + warning triangle, sad-face circle, screaming face, brain, head-with-spiral, eye | [M] |

| Rule | Value | Tag |
|---|---|---|
| Human proxy is a **filled pictogram**, not a line stick figure | rounded head as a detached circle, blocky rounded-shoulder torso | [M] |
| At least **two** person-pictogram variants exist | a chunky one (0:34.5, 4:06.2) and a lanky thin-limbed one (7:13.4, 6:58.6) | [M] |
| Crowds are drawn by **repeating the pictogram** | 3-up cluster at 7:08.5; large crowd at 1:33.6 | [M] |
| **Labelled callout diagram** is a named scene type | 8:07.6: boxed image + **4** curved arrows to 4 lowercase labels ("jet-black torso", "beige head", "hands", "legs") | [M] |
| **Flow diagram** is a named scene type | 9:16.5: creature → baby icon → "Little older" → gravestone, connected by curved arrows | [M] |
| **Size comparison** is a named scene type | 8:51.9: human pictogram + vertical ruler + creature, labelled "tall" | [M] |
| Arrows | thin black, **curved with a slight hand-drawn arc**, single arrowhead | [M] |
| Icons illustrating a spoken list | **one icon per list item**, laid out as an evenly spaced horizontal row (devices at 0:24.6; "trumpets / person / distant screaming" at 1:58.2) | [M] |

### 1.8 Structure and pacing

| Rule | Value | Tag |
|---|---|---|
| Creature count | **12** | [M][D] |
| Cold open | **zero-second intro** — first word of the first creature's name lands at **t = 0.08 s**, over the roster grid | [D] |
| Section length | mean **49.3 s**, range **33–65 s** | [D] |
| Section boundaries | 0:00 / 1:05 / 2:06 / 3:02 / 3:42 / 4:37 / 5:16 / 6:00 / 6:33 / 7:22 / 8:09 / 8:55 (description chapter list matches spoken boundaries within ~1 s; the description's "5:00 Disease" is a typo for 6:00) | [D] |
| Section-open formula | **name spoken twice**: "The boiled one. The boiled one, also known as Fen 228…" — 11 of 12 sections | [D] |
| Section transition | **hard cut to a black or near-black frame** — measured at 5:25.1, 5:54.6, 8:47.0, plus a grey dissolve at 1:04.0 | [M] |
| Total narration | **1,881 words** | [D] |
| Global narration rate | **191 wpm** | [D] |
| Per-section rate | 165–220 wpm (slowest: TTTIOH 165, Filbus 171, Guilt 176; fastest: Disease 220, Watch Tower 203, Locust 200) | [D] |
| **Mid-roll CTA** | **NONE.** Zero occurrences of subscribe / comment / notification / channel / "let me know" / "thanks for watching" in 1,881 words. No CTA frame in any of the 120 samples | [D][M] |
| Outro | **none** — narration runs to 9:49.8 and the video ends mid-sentence ("Guilt never forgets and neither will —") over a full-bleed dark shot then black | [D][M] |

### 1.9 Sourcing

| Rule | Value | Tag |
|---|---|---|
| Creature art origin | **(b) PNG cutout composited into editor-controlled layouts**, derived from a single found source artwork per creature | [M] |
| Source artwork character | pre-existing painterly/photographic creature artwork from the source franchise (each has its own studio-ish background: pink wall, tan wood wall, brown interior) — **not** stock photography, **not** custom illustration, **not** 3D | [M] |
| Cutout evidence | at 6:34.0 the enlarged "cutout" of the Cone Zone legs still carries the brown/tan tonal variation of the source photograph — it is a silhouette **cut from the photo**, not a redrawn shape | [M] |
| Background plates | **there usually is no background plate.** The canvas is the background. Where a plate exists it is either the source artwork's own background, or (in the 5 % full-bleed) a found-footage still or an illustrated interior | [M] |
| Full-bleed plate types seen | illustrated cartoon bedroom (3:17.0, 3:21.9), dark photographic stills (3:36.7, 3:56.4, 9:41.1), a blue-sky eyeball composite (4:40.7) | [M] |

### 1.10 The reuse ratio — the headline programmable fact

Per creature there is effectively **one source image**, which is then re-presented in a fixed set of derived treatments:

1. boxed at full size, centred
2. boxed and **cropped/punched in** on the head
3. boxed and **desaturated/washed out** to act as a backdrop for a foreground pictogram
4. **cut out as a near-black silhouette** and placed beside a pictogram
5. cut out, **scaled to 3–5× frame height** and bled off the top/edges
6. cropped into a **device screen** (TV / monitor / phone)
7. shrunk into the **top-right badge and roster cell**

Measured instance — **Cone Zone, 6:33–7:22, 10 sampled frames:** one pink-background source photograph plus its own derived silhouette account for **9 of the 10** compositions (6:29.1 boxed full · 6:34.0 silhouette at extreme scale · 6:38.9 boxed full again · 6:43.8 boxed head-crop, left · 6:48.8 silhouette + pictogram · 6:53.7 boxed desaturated as backdrop · 6:58.6 silhouette + pictogram · 7:03.6 silhouette cropped larger · 7:13.4 boxed full + pictogram). The tenth (7:08.5) is pictograms only.

---

## 2. Verdict on the known prior

> *"In the opening Locust section, ONE creature PNG cutout is reused across roughly 16 distinct composited scenes in ~60 seconds; the story advances by additive layering (same creature, new background, plus stick figures and icons stacking in); the full standalone image barely exists in their language."*

**Claim 1 — one PNG reused across many scenes: SUBSTANTIALLY CONFIRMED, with a correction to "one".** `[M]`

In the Locust section (0:00–1:05, 12 sampled frames) I count **3–5 distinct source assets**, not one:
- **A** — a "Doctor Nowhere" branding artwork (sun-face), used once as a label at 0:04.9.
- **B** — the "main entity" artwork (Locust against a tan wood wall, hand raised). Appears in **6 of 12** sampled frames, in five different treatments: small boxed with caption (0:04.9), larger boxed on black canvas (0:19.7), boxed left paired with a pictogram (0:29.5), desaturated and scaled up to bleed off-frame behind a pictogram (0:39.4), and cropped inside the phone-icon screen (0:24.6) and TV-icon screen (0:34.5).
- **C** — a black full-body Locust cutout, in **5 of 12** frames (0:09.8, 0:14.8 with the red circle, 0:44.3, 0:49.2, 0:54.2), across what looks like 2–3 pose variants.

So the *spirit* of the claim holds hard: **a very small number of creature assets carries an entire section**, and in Cone Zone it is genuinely one photo plus its own silhouette carrying 9/10 compositions. The literal "one PNG" is too strong for Locust.

**Claim 2 — ~16 scenes in 60 s: CANNOT BE CONFIRMED OR REFUTED.** `[U]`
A 4.925 s sampling interval cannot count scenes at a ~3.75 s cadence. What I *can* say is that **all 12 samples inside the Locust section are different compositions** — there is no repeat, which is consistent with a change rate faster than one per 4.9 s, but sets only a lower bound of ~13 scenes/65 s.

**Claim 3 — additive layering: SUPPORTED BUT NOT PROVEN.** `[M]` for the pattern, `[U]` for the per-beat cadence.
Adjacent samples repeatedly show a persisting element gaining a new one: 0:09.8 creature alone → 0:14.8 same creature **+ red annotation circle**; 0:44.3 pictogram + creature+TV → 0:49.2 **+ fallen bodies** → 0:54.2 **+ organ icons + caption**. Cone Zone shows the same: 6:48.8 silhouette + pictogram → 6:53.7 **+ meme caption**. But whether one element is added *per narration beat* at ~1 s intervals is invisible at this sampling rate.

**Claim 4 — "the full standalone image barely exists in their language": REFUTED AS WORDED, CONFIRMED IF IT MEANS FULL-BLEED.** `[M]`
- Truly edge-to-edge full-bleed imagery: **5.0 %** of runtime (6/120 frames). That part is right.
- But a **standalone boxed image with nothing but the title** is extremely common — 0:19.7, 6:29.1, 6:38.9, 2:08.0, 2:52.4, 2:57.3, 3:02.2, 3:51.5, 5:05.3, 8:02.6 and more. The image *is* frequently presented on its own; it is simply always **boxed on the canvas** rather than bled. The distinction the renderer needs is **boxed vs bled**, not **standalone vs composited**.

---

## 3. Confirmations and contradictions vs the stored profile

Compared against `horror-pipeline/spec/style-profiles.json` (`profiles.ficknime`) and `horror-pipeline/docs/competitor-style-profiles.md` (Profile B). **These are about to be used as renderer config, so the contradictions matter most.**

| Field | Stored value | This teardown | Verdict |
|---|---|---|---|
| `palette.bg` | `#FFFFFF` | **`#F8F8F8`** on 104/120 frames | ❌ **CONTRADICTED** — fix to `#F8F8F8` |
| `layout.whiteCanvasPct` | 0.92 | **0.867** white; **0.908** canvas-of-any-colour | ⚠️ **REFINE** — 0.92 conflates white with grey/black canvas |
| `layout.fullFramePct` | 0.08 | **0.050** (95 % CI 1–9 %) | ✅ consistent, but best estimate is lower |
| grey-canvas variant | *absent* | **3.3 %** of runtime (`#D0D0D0`, `#B8B8B8`) | ➕ **MISSING FROM PROFILE** |
| black-canvas-with-boxed-image variant | *absent* | present (0:19.7) | ➕ **MISSING FROM PROFILE** |
| `roster.cells` | **8** | **12** | ❌ **CONTRADICTED** |
| `roster.grid` | `"octagons"` | **5/4/3 centred rows** of ~9–10-sided polygons | ⚠️ shape roughly right, arrangement missing, count wrong |
| `palette.accents` | 5 colours (`#D4AF37, #FF0000, #800080, #0000FF, #008000`) | **12 colours, one per section** (table §1.4). None of the five stored hexes matches a measured value exactly | ❌ **CONTRADICTED** — replace wholesale |
| `palette.accentUse` | `"per-section-octagon"` | ✅ correct — accent appears **only** in badge + roster cell | ✅ **CONFIRMED** |
| red as accent | listed as a per-section accent | red is **also** a reserved annotation colour (circle / X / box), independent of section | ➕ **MISSING DISTINCTION** |
| `title.font` | `serif` | ✅ high-contrast serif | ✅ **CONFIRMED** |
| `title.case` | `title` | ✅ Title Case | ✅ **CONFIRMED** |
| `title.fill` / `stroke` | `#000000` / `null` | ✅ black, no stroke | ✅ **CONFIRMED** |
| title position | top-center | ✅ centred at 50.0 % ± 0.6 of width | ✅ **CONFIRMED** |
| `_universal.titlePersistent: true` | every frame | **false on full-bleed and black frames** (~9 % of runtime) | ❌ **CONTRADICTED** |
| `_universal.textOnScreenPct` | 0.95 | text absent on all full-bleed/black frames; ≈ **0.87–0.91** at best | ⚠️ **REFINE** |
| `_universal.captionMaxWords` | **4** | measured captions of **5, 9 and 13 words** (0:59.1, 0:54.2, 6:53.7) | ❌ **CONTRADICTED for this profile** — do not enforce a 4-word cap on a Ficknime-derived renderer |
| `caption.pos` | "center-bottom-or-beside-icon" | ✅ contextual, beside/under the icon it labels | ✅ **CONFIRMED** |
| box has a border / rounded corners / shadow | not stated | **none of the three** — hard-edged rectangle, single antialias pixel | ➕ **WORTH STATING EXPLICITLY** |
| creature reuse signature | "one PNG cutout reused across ~16 composited scenes" | reuse confirmed and mechanised (7 named treatments, §1.10); "one" is 1–2 per section, not per video; "~16 scenes" unverifiable at my resolution | ⚠️ **PARTLY CONFIRMED** |
| `pacing.scenesPerMin: 27`, `avgShotSec: 2.2`, `maxHoldSec: 4.5` | — | **not testable at 4.925 s sampling** | 🚫 **[U] — still unverified** |
| `motion.iconSlidePx: 200`, `iconSlideMs: 300`, `shakeJitterPx: 5` | — | **not testable** | 🚫 **[U] — still unverified** |
| `audio.sfxPerMin: 22` | — | **no audio access** | 🚫 **[U] — still unverified** |
| `humour.everySec: 90` | — | see §7 — script humour is roughly every **30–50 s**, visual gags rarer | ⚠️ **likely too slow** |
| CTA | profile lists no CTA | ✅ **zero CTA confirmed** in 1,881 words and 120 frames | ✅ **CONFIRMED** |
| cold open | — | ✅ **first word at t = 0.08 s**, zero intro | ✅ **CONFIRMED** (matches the Darkly "0 s intro" finding) |

**Six stored values are wrong and are about to become renderer config: `palette.bg`, `roster.cells`, `palette.accents`, `_universal.titlePersistent`, `_universal.captionMaxWords`, and `layout.whiteCanvasPct`'s conflation of canvas variants.**

---

## 4. Detailed evidence — questions 1 to 10

### Q1 — Sourcing

**Origin: (b), a PNG cutout composited into editor-controlled layouts** — with the important refinement that the cutout is derived from a single pre-existing artwork per creature rather than sourced separately. `[M]`

Ratio estimate across the 120 frames: roughly **75 % of creature appearances are the section's one source artwork** (boxed, cropped, tinted or silhouetted), **~20 %** are derived cutouts of that same artwork placed as a foreground element, and **~5 %** are distinct found stills used full-bleed. No stock photography, no 3D renders, and no evidence of purpose-drawn illustration for the creatures — the creature art has the painterly, uneven, franchise-native look of source material, while the *icons* around it are off-the-shelf pictogram/line-icon sets. `[M]`

**Distinct source images vs distinct scenes, per section:** `[M]` for the numerator, `[U]` for the denominator.
- Locust (0:00–1:05): **3–5** distinct source assets; ≥13 distinct compositions sampled (true count unknown).
- Cone Zone (6:33–7:22): **1 photograph + its own silhouette**; ≥9 distinct compositions sampled.
- Filbus (8:09–8:55): **1 brown-interior photograph + its silhouette**, seen boxed at 8:02.6 / 8:27.3 / 8:42.0 and as a black cutout at 8:07.6 / 8:22.3 / 8:32.2.
- Guilt (8:55–9:51): **1 stairwell photograph** (9:01.8 / 9:21.4 / 9:31.3) **+ 1 white cutout** (8:51.9 / 9:16.5) **+ 1 full-bleed face still** (8:56.8) **+ 1 full-bleed crib still** (9:41.1).

**Background plates:** for ~91 % of runtime there is no plate at all — the canvas *is* the background. The 5 % full-bleed plates split into found-footage-style dark photographic stills and one illustrated cartoon interior (3:17.0–3:21.9, a teal bedroom with black silhouette figures). `[M]`

### Q2 — White canvas

Verified and quantified in §1.1. Headlines: canvas `#F8F8F8` not `#FFFFFF`; **86.7 %** white canvas, **90.8 %** canvas of any colour, **5.0 %** full-bleed. Images are boxed with **no border, no rounded corners and no drop shadow**; box top at ~20 % of frame height, height 61–78 % of frame height, width following source aspect, horizontally dead-centre when solo. `[M]`

**What triggers full-frame:** from the 6 measured instances, full-bleed is used for **the incident/scene-setting beat inside a section**, not for the creature reveal — the cartoon bedroom during the "family found in a closet" story (3:17.0, 3:21.9), the dark stills at 3:36.7 and 3:56.4, the hallway at 3:56.4, the eyeball at 4:40.7, the crib at 9:41.1. Grey canvas (`#B8B8B8`, 7:28–7:38) coincides with the Fleshbeds night-time beat. `[M]`, with the caveat that 6 instances is a thin basis for a causal rule `[U]`.

### Q3 — Scene construction

**Scene A — 6:53.7, Cone Zone (2-up with desaturated backdrop)** `[M]`
Bottom to top: (1) canvas `#F8F8F8`; (2) the pink Cone Zone source photograph, **boxed and desaturated**, placed left of centre; (3) the black human pictogram, standing **in front of** the box, straddling its right edge; (4) title "Cone Zone" top-centre; (5) lime `#84C444` badge top-right. What animates: `[U]`.

**Scene B — 8:07.6, Filbus (callout diagram)** `[M]`
(1) canvas; (2) boxed portrait photograph of Filbus, centred; (3) four thin curved arrows radiating outward; (4) four lowercase serif labels at the arrow tails — "jet-black torso" (left), "beige head" (upper right), "hands" (right), "legs" (lower right); (5) title; (6) badge. No pictogram in this scene.

**Scene C — 0:54.2, Locust (additive stack)** `[M]`
(1) canvas; (2) black Locust cutout, right of centre; (3) prone human pictogram, lower left; (4) heart/lung organ icons, mid-left, overlapping the creature; (5) two-line caption top-left, "bypassing their physical form / to consume their internal organs"; (6) title; (7) gold badge.

**Additive pattern:** the persisting-element-plus-one pattern is visible across adjacent samples (§2, Claim 3). Per-beat timing is `[U]`.

### Q4 — Icon language

Catalogued in §1.7. Two mixed registers (filled pictograms + thin-line outline icons), always pure black.

**Timestamped list example — 1:58.2, Boiled One:** a 3-up row, evenly spaced — trumpet icon (≈0.17 W) labelled "trumpets", human pictogram (≈0.50 W), screaming-face line icon (≈0.80 W) labelled "distant screaming". The narration at 1:56–1:58 is "…they heard trumpets and distant screaming…". All three elements are present in the sample. `[M]`

**Do list icons pop in one at a time or together?** `[U]`. One suggestive data point: at 0:24.6 the three device icons (TV / monitor+PC / phone) are all present, but **only the phone's screen contains the Locust image** while the TV and monitor screens are empty — a mid-build state consistent with a sequential reveal. That is suggestive, not conclusive.

**Animation in — slide distance, duration, scale pop:** `[U]`. Not observable at 4.925 s sampling.

### Q5 — Text layer

Covered in §1.6. The two findings that matter for a renderer: **captions run 1 to 13 words**, so a 4-word cap is wrong for this reference; and **text is not on every frame** — full-bleed and black frames carry none.

Five measured caption examples: `[M]`
| Time | Words | Count | Position |
|---|---|---|---|
| 0:54.2 | "bypassing their physical form / to consume their internal organs" | 9 (2 lines) | upper-left, in the empty half |
| 0:59.1 | "But one thing is clear" | 5 | centred, alone on canvas |
| 1:13.9 | "On August 13th, 2003" | 4 | centred-right |
| 6:53.7 | "Why do I feel like / I'm the one who has to start this?" | 13 (2 lines) | right half, beside the creature |
| 7:33.1 | "Dinner's ready" | 2 | centred, on grey canvas |

On-screen duration and animation of each pop: `[U]`.

### Q6 — Motion

**All `[U]`.** I cannot determine whether every held image has a Ken Burns move, the zoom percentage or direction, the average seconds between visible changes, or whether glitch/VHS/scanline effects exist. A 4.925 s sample cannot see a continuous slow zoom, and none of the 120 frames happened to land on a visible glitch — which is **not** evidence that glitches are absent.

The one motion-adjacent measurement available: consecutive samples of the *same* boxed asset show slightly different framing (6:29.1 vs 6:38.9 for Cone Zone; 3:17.0 vs 3:21.9 for the bedroom), which is consistent with a continuous slow zoom but equally consistent with two separate cuts at different scales. Not decisive. `[U]`

### Q7 — Structure

Covered in §1.8. Roster grid of 12 polygonal cells at 0:00 in a 5/4/3 arrangement; per-section badge pinned top-right for the rest of the section; hard cuts to black between sections (5:25.1, 5:54.6, 8:47.0) plus a grey dissolve at 1:04.0; sections 33–65 s, mean 49.3 s; **no mid-roll CTA anywhere**; no outro.

**Not determined:** whether the roster grid *returns* between sections, and whether there is a punch-in zoom from the roster into the section's cell. Neither the 1:04.0, 5:25.1, 5:54.6 nor 8:47.0 transition samples show a roster, but a 0.5–1 s punch-in would very likely fall between samples. `[U]`

### Q8 — Colour

Covered in §1.4. Canvas `#F8F8F8`, ink `#000000`, **12 per-section accents** used exclusively in the badge and roster cell, plus a reserved freehand red for annotation. Per-section colour change: **confirmed, and it is the single most systematic colour rule in the video.** `[M]`

### Q9 — Audio

**Entirely `[U]`.** No audio was accessible — the storyboard track is images only and the media download was blocked. SFX-per-minute, the music bed, and whether cuts carry sounds are all unverified. The stored `sfxPerMin: 22` remains an unconfirmed number.

### Q10 — Humour

**The gags do NOT stay in the horror register — they deliberately break it.** `[D]` The register is Gen-Z internet slang dropped into an otherwise straight explainer: "Bro really said normal wasn't an option" (2:17), "Man just photobombed without permission" (2:30), "like he just left the game mid-match" (2:52), "like your brain just exposed you in 4K" (4:14), "like you passed a test you didn't study for" (4:26), "Bro got deleted without even a warning" (5:06), "like it's wearing a turtleneck made of its own skin" (6:12), "just like cringe people online" (7:19), "a normal bed that's tired of your existence" (7:29), "Worst surprise ever" (7:45), "Eat a chair, chop it, munch it, season it, whatever" (8:24).

**Frequency — the reputed "every 90 s" is too slow.** `[D]` Script-level gags land roughly **every 30–50 s**, at least one per section, starting from 0:15 ("instantly regret using electronics at night") and 0:36 ("like it's personally interested in your boring life").

**Visual gag form** `[M]` — dedicated humour *graphics* are rarer than the verbal jokes and take four measured forms:
- **speech bubbles** on pictograms — 5:34.9, three figures captioned "You're not just being watched." / "I feel judged."
- **emoji face substitution** — 5:49.7, a pictogram with a yellow shrug-emoji head and "???"
- **meme caption in the empty half** — 6:53.7 "Why do I feel like I'm the one who has to start this?"; 7:33.1 "Dinner's ready"
- **italic type as a punchline** — 8:12.5, "Creepy" set in italic, the only italic in the video

Also observed: coloured emoji used as icons (crossed-swords ⚔ at 5:44.8) — the only place non-black, non-accent colour appears in the icon layer. `[M]`

**Duration of each gag (the claimed 1–2 s):** `[U]`.

---

## 5. Full frame-by-frame layout classification

All 120 samples, `t = index × 4.925 s`, ±2.5 s. `[M]`

| Class | Frames | Count | % of runtime |
|---|---|---|---|
| White canvas `#F8F8F8` | all others | 104 | **86.7 %** |
| Grey canvas | 63 (`#D0D0D0`), 91, 92, 93 (`#B8B8B8`) | 4 | 3.3 % |
| Full-bleed imagery | 40, 41, 44, 48, 57, 118 | 6 | 5.0 % |
| Pure-black frame | 66, 72, 107, 119 | 4 | 3.3 % |
| Black canvas + boxed image | 4 | 1 | 0.8 % |
| Grey dissolve (transition) | 13 | 1 | 0.8 % |

Full-bleed timestamps: **3:17.0, 3:21.9, 3:36.7, 3:56.4, 4:40.7, 9:41.1**.
Black-frame timestamps: **5:25.1, 5:54.6, 8:47.0, 9:46.1** (+ grey dissolve **1:04.0**, black canvas **0:19.7**).

Note how poorly this matches the stored profile's asserted full-frame switch points (0:18, 1:21, 2:06, 3:04, 4:37, 5:17, 6:01, 6:34, 7:23, 8:10, 8:56) — those land almost exactly on the **section boundaries** from the chapter list, which suggests they were transcribed from the chapter markers rather than observed. Only 0:18 ≈ 0:19.7 and 4:37 ≈ 4:40.7 coincide with anything I measured. **Treat that list as unreliable.**

---

## 6. What I could NOT determine — the honest `[U]` list

Do not let anyone fill these in from plausibility. Each needs a real visual pass.

1. **Cut count, average shot length, longest hold.** The stored `avgShotSec: 2.2`, `maxHoldSec: 4.5`, `scenesPerMin: 27` are unverified.
2. **Whether the "~16 scenes in 60 s" figure is right.** Lower bound from my sampling is ~13 scenes / 65 s in Locust.
3. **Ken Burns.** Whether every held image moves, zoom percentage, zoom direction, pan direction. `zoomPerShot [1.05, 1.10]` unverified.
4. **Icon entry animation.** Slide direction, slide distance, duration, scale-pop curve. `iconSlidePx: 200`, `iconSlideMs: 300` unverified.
5. **Whether list icons pop sequentially or together**, and whether they sync to the spoken word.
6. **Caption on-screen duration and in/out animation.** `caption.animMs: 100` unverified.
7. **Glitch / VHS / scanline / chromatic-aberration effects** — existence, frequency, and which beats they land on. No sample caught one; absence of evidence only.
8. **Screen shake / jitter.** `shakeJitterPx: 5` unverified.
9. **All audio.** SFX count and density, music bed character, whether cuts carry whooshes or impacts, ducking depth.
10. **Whether the roster grid returns between sections**, and whether there is a punch-in zoom into the section's cell.
11. **Exact typeface identity.** I can characterise it (high-contrast serif, Didone/transitional, regular + italic) but cannot name the font at 320×180.
12. **Exact stroke weight of the red annotation marker** and of the line-icon set, in px at 1080p.
13. **Whether the boxed image has a border thinner than ~6 px at 1080p.** My probe rules out anything thicker.
14. **Sub-4.9 s humour gag durations** (the claimed 1–2 s).
15. **Whether the desaturation of a backdrop image is a fixed opacity/saturation value.** I can see it happens (6:53.7, 0:39.4) but cannot measure the amount reliably from JPEG-compressed 320×180.

---

## 7. What one visual call each would settle

Priority order, ranked by how much each would change what we build. Each is sized for one call and deliberately scoped so the answer cannot time out.

**1. `0s–60s` — the pacing and animation core.** This is the single highest-value window: it is the one stretch where every unknown in §6 items 1–6 is present at once, and pacing is the thing our renderer must reproduce and currently has zero verified numbers for.
> "List every visual change in this 60 seconds as a table: timestamp in, timestamp out, duration in seconds, and what changed (new element added / whole composition replaced). Give the total count and the average. Separately: for each element that enters, state the direction it enters from, how far it travels as a percentage of frame width, and over how many seconds. Does every held image have a continuous slow zoom — if so, in or out, and by roughly what percentage over the shot? At 0:22–0:26 the narration lists 'TV, computer, or phone': do the three device icons appear all at once or one at a time, and does each land on the spoken word? Answer with timestamps only, no adjectives."

**2. `370s–450s` (Disease → Cone Zone) — verify the reuse mechanic and the additive cadence.** Confirms or kills the §1.10 seven-treatment model, which is the thing the renderer's asset pipeline would be built around.
> "In this 80 seconds, how many DISTINCT source creature images appear? For each, list every timestamp it reappears and describe how it is treated at each appearance (boxed full / cropped / desaturated / silhouetted / scaled off-frame / inside a device screen). Is the same image reused with different elements composited around it, or is each scene a new artwork? Then: is there a pattern where a composition persists and ONE new element is added per narration beat? Give a timestamped run and the average seconds between additions."

**3. `0s–20s` plus `300s–330s` — section-opener structure.** Settles §6 item 10, which decides whether our renderer needs a roster-return-and-punch-in transition at all.
> "At 0:00 a grid of 12 polygonal creature badges appears. How long does it hold, and does the shot zoom or punch in to one cell before the first section? At the section change around 5:16, does the roster grid reappear before the new creature's section starts? Describe every frame of the transition between the two sections: what it cuts to, for how long, and any dissolve, flash or glitch."

**4. Any 60 s window — audio only.** Settles all of §6 item 9. Cheapest possible question, and the only route to it.
> "Ignore the visuals. Count every discrete sound effect in this 60 seconds and give the count and the per-minute rate. Describe the music bed. Does every hard cut carry a sound — whoosh, impact, riser, or nothing? Timestamp ten sound effects and say what each one sounds like and what visual event it lands on."

**5. `530s–591s` — the ending and text behaviour.** Lowest priority: the ending is structurally simple and already partly measured, but it would confirm the no-outro finding and pin caption durations.
> "For every text element in this final stretch: timestamp, exact words, how long it stays on screen, how it animates in and out, and where it sits. Does the video have any outro card, subscribe prompt, or end screen? Describe the last five seconds frame by frame."

---

## 8. Reproducing this teardown

The storyboard method is cheap, unmetered, and works whenever the multimodal budget is gone:

```
yt-dlp --no-playlist -J "https://www.youtube.com/watch?v=<ID>" > meta.json
# pull formats[] where format_id starts with "sb"; sb0 is the largest tile size.
# each entry has rows, columns, width, height, fps (= 1/interval) and a fragments[] list of sheet URLs.
# fetch each sheet from i.ytimg.com, split into rows x columns tiles, timestamp tile i at i * (1/fps).
```

For this video: `sb0` = 14 sheets × 3×3 tiles of 320×180, `fps` 0.20304568527918782 → interval 4.925 s → 120 usable frames over 591 s. Sheets download in a few seconds. The frames are low-resolution but exact colour sampling, bounding-box geometry and layout ratios all survive the downscale — which is why every number in §1.1–§1.5 is measurable and nothing in §6 is.
