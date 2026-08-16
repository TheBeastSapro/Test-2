# Frame-level teardown — M Simplified, "Trevor Henderson Biggest Giants Explained in 9 Minutes"

**Video:** `lrY0ErBfytQ` · M Simplified (`UCqXlPGw_s8Mr7YOSVZYjWOg`)
**Runtime:** 545 s (9:05) · **Views:** 1,537,191 · **Likes:** 15,493 · **Published:** 2026-03-06
**Teardown date:** 2026-08-09 (revised same day — full-runtime pass)
**Purpose:** reverse-engineer the editing grammar precisely enough to rebuild it in a renderer.

---

## 0. COVERAGE AND CONFIDENCE — READ THIS FIRST

This document merges **two** passes over the same video.

| Pass | Method | Covers | Tag used below |
|---|---|---|---|
| **Pass 1** (earlier session) | `watch_youtube_video_and_ask`, one successful call, `0–60 s` | **11.0 %** of runtime, high time resolution, full colour/motion/audio | `[M60]` |
| **Pass 2** (this session) | **Storyboard sprite-sheet track**, 13 sheets from `i.ytimg.com`, split into **110 frames at 320×180 on a fixed 4.9545 s interval, t = 0 → 540.05 s** | **99.1 %** of runtime bracketed by samples, low time resolution, low spatial resolution, **no audio** | `[M]` |
| Transcript + metadata | 274 cues, 1,661 words, official chapter list | structure, pacing, CTA copy | `[D]` |
| — | anything faster than 4.95 s, anything audio, anything sub-pixel at 320×180 | — | `[U]` |

**Coverage statement in the terms asked for.**
- **Seconds directly seen at full fidelity: 60 of 545 = 11.0 %** (pass 1).
- **Seconds bracketed by a measured still: 540.0 of 545 = 99.1 %** (pass 2, at ±2.5 s timestamp precision). The final 4.95 s (540.0–545.0) contains no sample.
- **Seconds derived, not seen: 100 %** of the structural/pacing layer comes from the transcript, cross-checked against frames.
- **Undetermined:** every sub-4.95 s phenomenon and all audio — enumerated exhaustively in §12.

Pass 2 was necessary because the multimodal tool's quota was exhausted (5/5) and direct media download is blocked by bot detection. **Method note that matters for reuse:** the storyboard track's maximum resolution is *client-dependent*. `yt-dlp` with `player_client=android_vr`, `tv_embedded` and `web_embedded` each exposed a top storyboard level of only **160×90**; `player_client=mweb` exposed **320×180** (`storyboard3_L3`, 13 sheets, 3×3 tiles of 320×180, `fps` 0.2018348623853211 → 4.9545 s). Four times the pixel area, and the difference between being able to read on-screen labels and not. Always sweep every client before accepting the first inventory.

**The two most valuable results of this pass, stated up front:**

1. **The canvas rule in pass 1 was wrong, and the correction is mechanical, not semantic.** Pass 1 concluded that *content class* selects the canvas — numbers/scale/anatomy → black void, beat boundaries → white card. Across the full runtime that mapping fails: numbers, scale comparisons and anatomy call-outs land on **white**, on **black** and on **full-frame scene**. The one predictor that holds is **subject luminance**: a pale creature cutout goes on a **black** canvas, a dark creature cutout goes on a **white** canvas. It is a contrast rule, not a content rule. Measured separation in §3.

2. **The stored profile's layout split is inverted.** Stored `fullFramePct: 0.75 / whiteCanvasPct: 0.25`. Measured: **full-frame scene 47.3 %, non-scene canvas 52.7 %.** Pass 1's modelled extrapolation (≈48 / 52) was right and the stored value is wrong.

**Timestamp precision:** every pass-2 timestamp is `index × 4.9545 s`, treat as **±2.5 s**.

---

## 1. CANVAS FAMILIES — settled

### 1.1 The measured split, whole runtime

n = 110 samples over 545 s. Classification is programmatic: 3-px border ring + whole-frame masks for near-white (`min ≥ 238`, `sat ≤ 14`) and near-black (`max ≤ 28`), plus a red-dominance test (`R−G ≥ 40 and R−B ≥ 40`). Roster frames were tagged by hand and are a white-canvas sub-type.

| Family | Frames | % of runtime | Exact background hex (modal pixel) | Tag |
|---|---|---|---|---|
| **A — full-frame scene** (composited environment, creature integrated, edge to edge) | 51 | **46.4 %** | n/a — photographic or painted plate | [M] |
| **B — white canvas** | 46 | **41.8 %** | **`#FFFFFF`** — pure white, exactly 255,255,255 as the modal pixel and the corner-patch modal | [M] |
| **C — black void canvas** | 9 | **8.2 %** | **`#000000`** — pure black, exactly 0,0,0 as modal and corner-patch modal | [M] |
| **D — roster grid** (on white) | 3 | **2.7 %** | `#FFFFFF` | [M] |
| **E — red field / red-tinted scene** | 1 | **0.9 %** | frame-mean `RGB(187, 95, 118)`, modal `#D86878` — this is the **scene plate recoloured red**, not a solid fill | [M] |

**Roll-ups:**
- **Full-frame imagery (A + E) = 47.3 %** of runtime. `[M]`
- **Non-scene canvas of any colour (B + C + D) = 52.7 %.** `[M]`
- **White-family canvas (B + D) = 44.5 %.** `[M]`

95 % binomial CI at n=110: white 32–52 %, black 4–15 %, scene 37–56 %, red field 0.02–5 %.

Two important negatives. `[M]`
- The canvas is **pure `#FFFFFF`**, not the off-white `#F8F8F8` that Ficknime uses. Sampled on 46 frames; the modal pixel of every white-canvas corner patch is 255,255,255. The `#FEFFFA` second mode is JPEG chroma noise, not a design value.
- The black canvas is **pure `#000000`**, not a near-black.

### 1.2 Black-canvas timestamps (all 9) `[M]`

`0:34.7 · 0:39.6 · 0:44.6 · 0:49.5` (Behemoth) and `6:51.2 · 6:56.2 · 7:01.1 · 7:06.1 · 7:11.0` (The Bird Watcher).

**They occur in exactly two of eight sections.** No black canvas anywhere in Sky Mantas, Remain Indoors, Wandering Faith, Wandering Doom, Breaking News or Tree Head.

### 1.3 Red field `[M]`

**One** sample, `0:29.7`, inside the Behemoth incident vignette on the kill beat ("crushed beneath it, dying instantly"). It is the mountain plate pushed to a pink-red duotone with the boulder in silhouette over it, **not** a flat red card. Pass 1 counted 3 s of red in the first 60 s; across the full runtime red field is **≈1 % of runtime, and confined to the one impact beat sampled.** Red *as an overlay graphic* (arrows, dashed measurement lines, drawn tendrils) is common and is a separate thing — see §6.

### 1.4 Block-level canvas density — the strongest structural rule, now confirmed across all 8 sections

Pass 1 derived this from one minute. Pass 2 confirms it across the whole runtime with almost the same numbers.

| Block type | Total duration | Samples | Full-frame scene | Non-scene canvas |
|---|---|---|---|---|
| **Incident vignette** (narrative cold-open story) | 125.5 s | 27 | **81.5 %** | 18.5 % |
| **Spec block** (the "X is described as…" descriptive passage) | 386.6 s | 78 | 37.2 % | **62.8 %** |
| **CTA** (mid-roll + outro) | 20.3 s | 4 | 0 % | **100 %** |

> **Rule, confirmed: the canvas is the visual signature of the SPEC BLOCK, not a global style.** Incident vignettes run ~80 % full-frame composited scene; spec blocks run ~63 % canvas; CTAs are 100 % canvas. `[M]`
>
> Pass 1's numbers from a single minute were 90 % / 62 %. The spec-block figure was accurate to within 1 point.

### 1.5 Per-section canvas mix `[M]`

| # | Section | Dur | n | Scene | White | Black | Roster | Red |
|---|---|---|---|---|---|---|---|---|
| 1 | Behemoth | 66.1 s | 14 | 57 % | 0 % | **29 %** | 7 % | 7 % |
| 2 | Sky Mantas | 70.1 s | 14 | 71 % | 29 % | 0 % | — | — |
| 3 | Remain Indoors | 64.3 s | 13 | 46 % | 54 % | 0 % | — | — |
| — | **MID-ROLL CTA** | 9.1 s | 2 | 0 % | **100 %** | — | — | — |
| 4 | The Wandering Faith | 65.2 s | 13 | 46 % | 54 % | 0 % | — | — |
| 5 | The Wandering Doom | 54.8 s | 11 | 45 % | 55 % | 0 % | — | — |
| 6 | Breaking News | 60.6 s | 12 | 25 % | **75 %** | 0 % | — | — |
| 7 | The Bird Watcher | 67.7 s | 14 | 36 % | 21 % | **36 %** | 7 % | — |
| 8 | Tree Head / Big Branch | 76.0 s | 15 | 53 % | 40 % | 0 % | 7 % | — |
| — | **OUTRO CTA** | 11.2 s | 2 | 0 % | **100 %** | — | — | — |

---

## 2. THE CANVAS TRIGGER — the question this teardown existed to settle

### 2.1 The rule, in one sentence

> **The video cuts to a non-scene canvas for the SPEC BLOCK and for CTAs; the canvas is BLACK when a pale creature cutout is on it and WHITE in every other case (dark cutout, black pictograms, boxed photograph, or text alone).** `[M]`

### 2.2 The evidence that kills the content-class rule

Pass 1's proposed mapping was `number → black`, `sizeComparison → black`, `anatomyCallout → black`, `definitionLine/sourcingLine/pivot → white`. Full-runtime cross-reference of every canvas frame against the transcript destroys it. Each content class appears on **both** canvases:

| Content class | On BLACK | On WHITE |
|---|---|---|
| **Explicit size figure** | `0:39.6` "800 km" · `7:01.1` "between 300 m and 1.5 km tall" | `2:58.4` "around 9 km tall" · `4:12.7` "about 1.5 km tall" · `8:15.5` "between 400 m and several kilometers" |
| **Anatomy call-out** | `0:49.5` skull ridges (green arrow) · `7:06.1` "rusted iron beams / shattered glass" · `7:11.0` "elephant-like feet" | `1:34.1` "venomous barbs" (red arrow) · `2:48.5`/`2:53.4` tendril crops (red arrows) · `5:41.9` ribcage icon |
| **Definition line** | `0:34.7` "colossal reptilian, lizard-like titan" | `1:09.4` "enormous airborne creatures" · `2:43.5` "gigantic tripodal entity" |
| **Pivot conjunction** | — | `6:01.7` "Unlike some giants that constantly move" |
| **Full-body reveal** | `0:34.7`, `6:56.2` | `4:37.5`, `5:36.9`, `8:05.5` |

There is no content class that predicts the canvas colour.

### 2.3 The predictor that does work: subject luminance

For every white/black canvas frame I masked out the canvas, masked out saturated graphic ink (so green/yellow/red text and arrows don't pollute), dropped the title band, and took the **median luminance of the remaining subject pixels**.

| Canvas | n (frames with a subject) | Subject median luminance, range | Mean of medians |
|---|---|---|---|
| **BLACK** | 6 | **110.0 – 159.0** | **129.8** |
| **WHITE** | 32 | **0.0 – 122.0** | **48.3** |

Every unboxed cutout on white measures **≤ 84**. The single white-canvas frame above 100 is `1:09.4`, which is a **boxed** photograph (a hard rectangle supplies its own edge, so it doesn't need canvas contrast). Clean separation at roughly luminance 100 for bled cutouts. `[M]`

The two creatures that get a black canvas are exactly the two pale ones: **Behemoth** (bone-white 3D reptile) and **The Bird Watcher** (bone-white bird figure). Every other creature in the video is dark grey, black or dark brown, and gets a white canvas.

### 2.4 The confirming detail — the Bird Watcher section switches canvas mid-section

Inside section 7 the canvas flips **five times to black and three times to white**, and the split is not by content:

| Frame | Canvas | What is on it |
|---|---|---|
| `6:51.2 – 7:11.0` (5 frames) | **BLACK** | the pale Bird Watcher cutout, at five different crops |
| `7:16.0` | WHITE | **text only** — "the Bird Watcher is" |
| `7:25.9` | WHITE | **text only** — "Those who believe" |
| `7:30.9` | WHITE | **two black stick pictograms**, no creature |

The canvas goes white the instant the pale creature leaves the frame, and comes back to black when it returns. That is a legibility rule, executed per shot. `[M]`

### 2.5 Programmable form

```json
"canvas": {
  "specBlockCanvasPct": 0.63,
  "incidentBlockCanvasPct": 0.19,
  "ctaCanvasPct": 1.00,
  "selectBy": "subjectLuminance",
  "rule": "subject median luma > ~100  -> #000000 ; otherwise -> #FFFFFF ; no subject (text-only / pictograms) -> #FFFFFF",
  "white": "#FFFFFF",
  "black": "#000000",
  "redField": { "kind": "scene-duotone-not-flat-fill", "runtimePct": 0.009 }
}
```

**What pass 1 got right and I am keeping:** the *existence* of three non-scene canvases, the fact that the profile models only one, and the block-level density rule. **What pass 1 got wrong:** the content-to-canvas mapping. `[M]` supersedes `[M60]` here because the 60 s window contained only one creature and that creature happened to be pale.

---

## 3. BOX GEOMETRY — and the finding that boxing is almost absent

### 3.1 Boxing is rare

The dominant presentation is a **bled cutout with a transparent background sitting directly on the canvas** — no frame, no container. A hard-edged rectangular photo box appears in **2 of 110 samples = 1.8 % of runtime.** `[M]`

| Time | What is boxed |
|---|---|
| `1:09.4` | one square-ish photograph of a Sky Manta in a real sky, left of centre, with the green label "airborne creatures" under it |
| `5:32.0` | **two** boxes side by side — a night photograph of Breaking News (left) and a portrait photograph of the creator, labelled "Trevor Henderson" (right), joined by a red arrow |

### 3.2 Edge probe — is there a border, a radius, or a shadow?

**Result: none of the three.** `[M]`

Horizontal scan through the right edge of the left box at `5:32.0`, y=60:

```
x=113 (8,8,8)   x=114 (3,3,3)   x=115 (7,7,7)   <- photo interior
x=116 (50,50,50)                                <- ONE intermediate pixel
x=117 (235,235,235)  x=118 (255,255,255) ...    <- canvas
```

Vertical scan through the top edge of the box at `1:09.4`, x=110:

```
y=31 (252,255,255)  y=32 (252,255,255)          <- canvas
y=33 (237,241,244)                              <- ONE intermediate pixel
y=34 (189,192,197)  y=35 (188,191,198) ...      <- photo interior
```

Canvas → **exactly one** intermediate pixel → image, and the intermediate value tracks the image colour (50 against a dark photo, 237 against a light one). That is antialiasing, not a stroke of fixed colour. It rules out any border thicker than ~6 px at 1080p.

Corner probe of the top-left of the left box at `5:32.0` (min-channel, canvas = 250+):

```
250 255 253 254 248 248 239 252 249 249
236 254 254 253 254 247 245 253 254 255
255 255 254 175 181 170 186 175 184 184
253 255 197  31  14   0  25   0   3   3
253 255 215   3  11   5   9   8   7   7
253 255 215   3  11   5   9   8   6   6
```

The dark content begins at the **same x on the first content row as on every row below it.** No inset, no arc, no radius. Below and to the right of the box the canvas returns to 255 immediately — **no drop shadow.**

### 3.3 Box metrics, as fractions of frame dimensions `[M]`

| Metric | `1:09.4` solo box | `5:32.0` left box | `5:32.0` right box |
|---|---|---|---|
| Top edge | 0.189 H | 0.150 H | 0.144 H |
| Height | 0.672 H | 0.717 H | 0.722 H |
| Width | 0.381 W | 0.288 W | 0.312 W |
| Centre x | **0.255 W** | 0.223 W | 0.730 W |
| Aspect | ≈1.00 : 1 (square) | ≈0.71 : 1 (portrait) | ≈0.77 : 1 (portrait) |

**Note the solo box is NOT centred** — it sits at 0.255 W with the label under it and empty canvas to the right. Contrast Ficknime, whose solo box is dead centre at 0.500 W ± 0.002.

### 3.4 The one thing that IS bordered and rounded: the roster cell

The roster is the exception and it is stylistically inconsistent with the body of the video. Measured on the magnified roster at `8:50.1` (cell width 123 px, i.e. 1.73× the base roster scale):

- **Border:** black, 2 px at the magnified scale → **≈1.2 px at 320 px frame width → ≈7 px at 1080p.** Scan `x=171 (189) → x=172 (9,6,1) → x=173 (63) → x=174 (245)`.
- **Corner radius:** the top-left arc spans 2–3 px over a 123 px cell → **≈2 % of cell width ≈ 8–10 px at 1080p.** Left edge x=53 at y=22, x=54 at y=21, x=55 at y=20.
- **Drop shadow:** **none.** Below the bottom border the canvas returns to 255 within one pixel (`y=132 (0,0,19) → y=133 (31,28,47) → y=134 (223) → y=135 (252)`).

> **Direct answer to the house-style question:** M Simplified applies **no border and no corner radius to content images** (which are almost never boxed anyway), and applies a **~7 px black border with a ~8–10 px radius, no shadow, only to roster cells.** Our house 6 px border + 20 px radius is close to their *roster* treatment and wrong for their *content* treatment — but the deeper point is that they barely box content at all. `[M]`

---

## 4. LAYOUT

### 4.1 Dominant unit

**Single hero, overwhelmingly.** Automatic cluster counting on canvas frames plus hand verification of every montage:

| Layout | Instances (of 45 imagery-carrying canvas frames) | Share |
|---|---|---|
| **Single hero** — one subject, optionally with a caption/arrow/measurement line | 37 | **82 %** |
| **2-up** — two distinct image subjects | 8 | **18 %** |
| 3-up or more | 0 confirmed | 0 % |

Full-frame scene frames (46.4 % of runtime) are always a single composited environment with one creature in it — a hero composition by construction. `[M]`

### 4.2 The 2-up instances and their x-positions `[M]`

| Time | Left subject (centre x) | Right subject (centre x) | What it is doing |
|---|---|---|---|
| `0:34.7` | reference lizard photo (0.20 W) | Behemoth cutout (0.69 W) | real-animal comparison |
| `4:27.5` | rifle + tank pictograms (≈0.25 W) | creature cutout (≈0.62 W) | "human weapons would be ineffective" |
| `5:32.0` | boxed creature photo (0.22 W) | boxed creator portrait (0.73 W) | attribution |
| `5:41.9` | creature silhouette (0.37 W) | stacked line icons: light-reflection diagram + ribcage (0.81 W) | anatomy |
| `6:21.5` / `6:26.5` | black creature (≈0.42 W) | red-dotted variant creature (≈0.60 W) | "connected to the giant with red dots" |
| `7:30.9` | pictogram (0.17 W) | pictogram (0.47 W) | reaction figures |
| `8:20.4` | creature cutout (0.32 W) | human pictogram (0.65 W) | **size comparison** |

There is **no fixed grid.** Left slot lands anywhere in **0.17–0.42 W**, right slot in **0.47–0.81 W**. Compare Ficknime, whose 2-up is a repeatable 0.27 / 0.75 and whose 3-up is a repeatable 0.19 / 0.50 / 0.78. M Simplified positions by eye. `[M]`

### 4.3 Text-only cards

**7 of 110 frames (6.4 %) are a canvas carrying nothing but a line of text** — no image, no icon, no creature. `[M]`

`1:49.0` "Their bodies produce" · `4:32.5` "meaning their numbers" · `6:01.7` "Unlike some giants that constantly move" · `7:16.0` "the Bird Watcher is" · `7:25.9` "Those who believe" · `8:10.5` "believed to be a member of The Giants" · `9:00.0` "COMMENT"

**This directly violates house rule 10 ("No blank text-only cards").** The 1.5 M-view reference uses them at roughly one per section. Worth an owner decision; I am not making it.

---

## 5. TITLE AND CHROME

### 5.1 Persistent title `[M]`

| Property | Measured value |
|---|---|
| Present on **full-frame scene** frames | **52 / 52 = 100 %** (white-fill + dark-outline detector in the band y 7–22, x 55–265) |
| Present on **canvas** frames | 46 / 46, **except the 4 CTA frames** (`3:23.1`, `3:28.1`, `8:55.1`, `9:00.0`) |
| Overall | **106 / 110 = 96.4 %** of runtime. The title is suppressed for the duration of both CTAs and nowhere else |
| Horizontal centre | **x = 160.0 of 320 = 50.00 % W**, on every single measurable frame, zero variance |
| Glyph band top | **y = 8 of 180 → 0.044 H** |
| Glyph band bottom | **y = 20 of 180 → 0.111 H** |
| Glyph band height (ascender to baseline, incl. outline) | **13 px of 180 → 0.072 H ≈ 78 px at 1080p** |
| Cap height (derived from ascender-only titles, e.g. "Behemoth") | **≈ 11 px of 180 → ≈ 0.061 H ≈ 66 px at 1080p** `[D]` |
| Title width | scales with the name: 70 px ("Behemoth") to 158 px ("The Wandering Faith") of 320 |
| Case | **Title Case** on all 8 section titles |
| Fill / stroke | **white fill, black stroke** — verified by pixel slice on white canvas, black canvas and grey scene alike |
| Stroke width | 1 px at 320 → **4–8 px at 1080p**; the stored `6` is consistent but not exactly confirmable at this resolution |
| Typeface | **bold, rounded, oblique CASUAL/COMIC face** — single-storey `a`, open-tailed `g`, rounded `W`. Reads as Comic Sans MS Bold Italic or a close relative. **Not** a neutral bold sans |

Pixel slice through the title glyphs at `2:58.4`, y=14 (white canvas), mean of RGB:
`79 226 232 127 197 240 243 171 78 211 103 188 235 90 112 253 …` — alternating dark outline / light fill. On black canvas at `6:56.2`: `3 4 4 178 250 92 7 0 0 0 215 214 127 254 …` — same structure. **Fill is light in both cases; the profile has fill and stroke inverted.**

### 5.2 Chrome — badge, corner element, watermark

**There is none.** `[M]`

Tested by stacking the four corner patches (34 × 60 px) across all 51 scene frames and taking the per-pixel standard deviation. A persistent overlay would produce a low-variance patch. Results: TL 65.0, TR 71.0, BL 63.3, BR 65.0 — i.e. every corner is as variable as ordinary scene content. **No per-section badge, no channel bug, no watermark, no corner logo anywhere in the video.**

This is a real structural difference from Ficknime, which pins a per-section accent-coloured polygon badge top-right on 85/110 in-section frames.

---

## 6. PALETTE

### 6.1 Structural colours — exact `[M]`

| Role | Hex | Evidence |
|---|---|---|
| **White canvas** | **`#FFFFFF`** | modal pixel of 46 white-canvas frames and of their corner patches, exactly 255,255,255 |
| **Black canvas** | **`#000000`** | modal pixel of 9 black-canvas frames and of their corner patches, exactly 0,0,0 |
| **Ink** (pictograms, icons, arrows-as-shapes, title stroke, roster border) | **`#000000`** | pictogram interiors and title outline both floor at 0–8 |

### 6.2 Accent inks

Measured as the brightest saturated pixels inside each labelled element. At 320×180 a 1–2 px glyph stroke is heavily JPEG-blended toward its dark outline, so these are **peak-fill estimates, not exact source hexes** — tag `[M~]`.

| Accent | Peak fill measured | Best estimate | Where it is used |
|---|---|---|---|
| **Green** | `#7CF769` `#5CF157` `#6EEE63` (white canvas) · `#86D55E` `#8CDD5D` (black canvas) | **≈ `#5AF050`** with a dark-green outline ≈ `#006400` | keyword labels, CTA words (LIKE / SUBSCRIBE / COMMENT), some verbatim caption cards |
| **Yellow-chartreuse** | `#DCE767` `#D3DF5F` `#C4D352` | **≈ `#DCE767`** with an olive outline ≈ `#5A6300` | keyword labels, size figures, adjective lists |
| **Red** | `#FF595C` `#DC1826` `#D32F3A` | **≈ `#D5192A`** | arrows, dashed measurement lines, drawn "grab" tendrils, occasional caption cards |

**The accent does NOT change per section.** `[M]` All three colours appear in multiple sections and the choice within a frame looks driven by contrast against what is behind the text, not by section identity. Green and yellow are used interchangeably for the same job (compare `2:43.5` green "tripodal entity" with `7:06.1` yellow "rusted iron beams"). This is the opposite of Ficknime, whose 12 accents map one-to-one onto 12 creatures.

Caption ink colour is not fixed either: `8:10.5` is red, `6:01.7` is green, `4:32.5` is yellow — three text-only cards in three colours.

**Blue/orange** appear only inside a diagram at `0:40` `[M60]`, and inside photographic plates. They are not part of the graphic palette.

### 6.3 Programmable form

```json
"palette": {
  "bg":       "#FFFFFF",
  "bgAlt":    "#000000",
  "ink":      "#000000",
  "accents":  ["#5AF050", "#DCE767", "#D5192A"],
  "accentUse": "per-shot-contrast, NOT per-section",
  "accentRoles": {
    "#5AF050": ["keyword-label", "cta-word", "caption"],
    "#DCE767": ["keyword-label", "size-figure", "adjective-list"],
    "#D5192A": ["arrow", "dashed-measurement-line", "drawn-overlay", "caption"]
  }
}
```

---

## 7. ROSTER

### 7.1 Geometry, measured at `0:00.0` `[M]`

| Property | Measured |
|---|---|
| **Cell count** | **8** — one per creature |
| **Arrangement** | **4 × 2**, a true rectangular grid, both rows full |
| Background | `#FFFFFF` |
| Cell x-runs (of 320) | (8–78) (86–156) (163–233) (241–311) |
| Cell size | **71 × 67 px of 320 × 180 → 0.222 W × 0.372 H ≈ 426 × 402 px at 1080p** — effectively square |
| Column pitch | **77.7 px of 320 → 0.243 W ≈ 466 px at 1080p** |
| Row pitch | **86 px of 180 → 0.478 H ≈ 516 px at 1080p** (row 1 image y 10–76, row 2 image y 96–161) |
| Left / right margin | 8 px and 8 px of 320 → **2.5 % W each side** |
| Top margin | 10 px of 180 → **5.6 % H** |
| Bottom margin | 3 px of 180 → **1.7 % H** |
| Cell border | **black, ≈7 px at 1080p** (§3.4) |
| Cell corner radius | **≈2 % of cell width ≈ 8–10 px at 1080p** (§3.4) |
| Cell shadow | **none** |
| Label placement | **below** each cell, y 82–91 (row 1) and 167–176 (row 2) — band height 10 px = **5.6 % H** |
| Label style | **ALL CAPS**, bold, same comic face as the title, **white fill + black outline** |

### 7.2 Cell contents `[M]`

Row 1: **BEHEMOTH · SKY MANTAS · REMAIN INDOORS · DAY 17**
Row 2: **DAY 18 · BREAKING NEWS · BIRD WATCHER · TREE HEAD**

Each cell holds a **different image from the one used in the section body** — the Behemoth cell is a blue-sky head shot, while the section opens on a snowy mountain plate.

**Roster labels are not the section titles.** `[M]` Three of eight differ:

| Roster label | Section title used on screen |
|---|---|
| DAY 17 | The Wandering Faith |
| DAY 18 | The Wandering Doom |
| TREE HEAD | Big Branch |
| BIRD WATCHER | The Bird Watcher (article added) |

### 7.3 When it appears

Caught in **3 of 110 samples**: `0:00.0` (opening), `7:35.8` (the section 7 → 8 boundary, mid punch-in, "…WATCHER" and "TREE HEAD" enlarged), and `8:50.1` (end of section 8, immediately before the outro CTA). `[M]`

**The roster therefore DOES return between sections** — pass 1 listed this as undetermined; it is now confirmed at one mid-video boundary and one pre-outro position, and confirmed to carry a **punch-in zoom toward the incoming creature's cell** (the `7:35.8` sample is caught mid-zoom with the Tree Head cell enlarging).

**Duration `[D]`, estimate only:** we caught it at 2 of 7 mid-video boundaries. If it returns at every boundary with duration *d*, the expected catch rate is *d* / 4.9545, giving **d ≈ 1.4 s**. Wide confidence interval; do not encode. Pass 1's `rosterPunchInSec: 0.5` remains untestable at this sampling.

---

## 8. STRUCTURE

### 8.1 Section map `[D]` (spoken boundaries, cross-checked against the description chapter list)

| # | Creature | Start | End | Dur | Words | wpm | Incident? | Size figure stated |
|---|---|---|---|---|---|---|---|---|
| 1 | Behemoth | 0:00.0 | 1:06.1 | 66.1 s | 198 | **179.7** | yes, 30 s | 800 km; head > Everest |
| 2 | Sky Mantas | 1:06.1 | 2:16.2 | 70.1 s | 192 | **164.4** | no | 4 km / 350 m–1 km / 10 km |
| 3 | Remain Indoors | 2:16.2 | 3:20.5 | 64.3 s | 203 | **189.5** | yes, 23 s | 9 km; 910,000 tons |
| — | **MID-ROLL CTA** | **3:20.5** | **3:29.6** | **9.1 s** | 34 | 224.7 | — | — |
| 4 | The Wandering Faith | 3:29.6 | 4:34.8 | 65.2 s | 197 | **181.2** | yes, 21 s | 1.5 km |
| 5 | The Wandering Doom | 4:34.8 | 5:29.6 | 54.8 s | 174 | **190.7** | no | **none** |
| 6 | Breaking News | 5:29.6 | 6:30.2 | 60.6 s | 193 | **191.1** | no | **none** |
| 7 | The Bird Watcher | 6:30.2 | 7:37.8 | 67.7 s | 199 | **176.4** | yes, 22 s | 300 m – 1.5 km |
| 8 | Tree Head / Big Branch | 7:37.8 | 8:53.8 | 76.0 s | 230 | **181.7** | yes, 30 s | 400 m – several km; 100,000 t |
| — | **OUTRO CTA** | **8:53.8** | **9:05.0** | **11.2 s** | 41 | 219.6 | — | — |
| | **TOTAL** | | | **545 s** | **1,661** | **182.9** | 5 of 8 | 6 of 8 |

**Cold open:** confirmed. **Zero intro.** The first narrated word is the first creature's name, at t = 0.00 s, over the roster grid. `[M][D]`

**Section-open formula:** every section opens with the creature's name as the first word(s); 3 of 8 repeat it immediately ("Sky Mantas, Sky Mantas are…", "Breaking News, Breaking News is…"). `[D]`

**Narration rate:** global **182.9 wpm**, per-section **164.4–191.1**, every section above 164. CTA copy is read faster (220–225 wpm). Dead air: effectively none, cues are contiguous end to end. `[D]`

> This still corrects the working assumption in `docs/competitor-style-profiles.md` that 160–180 wpm is Darkly's differentiator against a 120–140 field. **M Simplified narrates at 183 wpm and has 1.5 M views.** Narration speed is not the lever.

### 8.2 What separates sections `[M]`

| Boundary | Last sample before | First sample after | Mechanism observed |
|---|---|---|---|
| 1 → 2 (66.1 s) | `1:04.4` Behemoth scene | `1:09.4` Sky Mantas white card | hard cut |
| 2 → 3 (136.2 s) | `2:13.8` Sky Mantas sky | `2:18.7` yellow-wall TV room | hard cut |
| 3 → 4 (209.6 s) | `3:28.1` CTA card | `3:33.0` fog road scene | hard cut, CTA sits in the seam |
| 4 → 5 (274.8 s) | `4:32.5` white text card | `4:37.5` cutout on white | hard cut |
| 5 → 6 (329.6 s) | `5:27.0` cutout on white | `5:32.0` two boxed photos | hard cut |
| 6 → 7 (390.2 s) | `6:26.5` cutout on white | `6:31.4` misty city scene | hard cut |
| **7 → 8 (457.8 s)** | `7:35.8` **ROSTER, mid punch-in** | `7:40.8` sunset forest scene | **roster return + punch-in** |

No fade, no dissolve, no black frame was sampled at any boundary. Because the roster was caught at one boundary and at the pre-outro position, the safe reading is: **the roster-return-and-punch-in is the section transition, it lasts about 1–1.5 s, and the other six boundary samples simply fell outside it.** `[M]` for the two catches, `[D]` for the generalisation.

### 8.3 Mid-roll CTA `[D]` + `[M]`

- **Timing:** 200.5 – 209.6 s, **9.1 s**, at **36.8 % of runtime**, at the end of creature 3 of 8. It interrupts nothing — it lands after the Remain Indoors spec block closes and before the Wandering Faith name is spoken.
- **Copy:** *"If you've made it this far, you probably like this kind of content. So don't forget to like, subscribe, and drop a comment. It helps the video reach more people and supports the channel."* Ask order **like → subscribe → comment**.
- **Visual treatment `[M]` — pass 1 listed this as undetermined; now measured.** Pure `#FFFFFF` canvas. A **hand-drawn line stick figure** (thin black outline, circle head with a smiley face and a tuft of hair — a completely different drawing register from the solid black pictograms used everywhere else in the video), standing centre-frame. One green ALL-CAPS word above it (`3:23.1` = "LIKE"). **The persistent creature title is removed for the whole CTA.** At `3:28.1` the figure is joined by two lines of green verbatim caption, "helps the video reach more peopole / and support the channel" (typo in original).

### 8.4 Outro `[D]` + `[M]`

- 533.8 – 545.0 s, **11.2 s**, ask order like → subscribe → comment, with a specific comment ask ("I really want to know what topic you want me to explore next").
- **Visual `[M]`:** identical language to the mid-roll — `#FFFFFF` canvas, the same hand-drawn stick figure at `8:55.1`, then a green ALL-CAPS "COMMENT" alone on white at `9:00.0`. No title, no end card, no subscribe animation, no video thumbnails.
- The video ends the instant narration ends; there is no silent end-card tail.

---

## 9. SOURCING

### 9.1 Origin `[M]`

**(b) — PNG cutout composited into editor-controlled backgrounds.** Not whole pre-made artworks dropped in, and not the Ficknime pattern of re-presenting one found artwork with its own background intact.

The decisive evidence is section 5 (The Wandering Doom, 4:34.8 – 5:29.6). **One** skeletal-quadruped cutout appears in **seven different background plates** in 55 seconds:

| Time | Plate |
|---|---|
| `4:37.5` `4:42.4` `4:47.4` `4:52.3` `4:57.3` | white void, at five increasing scales |
| `5:02.2` | Swiss hillside stock photograph (farmhouses, green pasture) |
| `5:07.2` | illustrated night sky with a second moon |
| `5:12.1` | tropical island aerial stock photograph |
| `5:17.1` | aerial village stock photograph |
| `5:22.0` | grey fog plate |
| `5:27.0` | white void + a cartoon flame graphic |

The creature is pixel-identical across all seven. **The editor owns the background; the creature is a fixed asset.** `[M]`

### 9.2 Distinct source artworks per creature `[M]`

| Section | Distinct creature artworks | Distinct compositions in 11–15 samples |
|---|---|---|
| 1 Behemoth | **1** (+ 1 stock lizard photo used for comparison) | 13 of 14 samples are different compositions |
| 2 Sky Mantas | **2–3** (a standard manta render; an open-mouthed shark-manta at `2:08.8`; a boxed sky photograph at `1:09.4`) | 14 of 14 |
| 3 Remain Indoors | **3** (tendril entity; a four-legged variant at `3:13.2`; a distant misty version at `3:18.2`) | 13 of 13 |
| 4 The Wandering Faith | **1** | 13 of 13 |
| 5 The Wandering Doom | **1** | 11 of 11 |
| 6 Breaking News | **2** (black humanoid; red-dotted variant at `6:21.5`) + 1 real portrait photograph | 12 of 12 |
| 7 The Bird Watcher | **1** | 14 of 14 |
| 8 Tree Head / Big Branch | **1** | 15 of 15 |

**Median 1 distinct creature artwork per creature; range 1–3.** No two sampled frames inside a section repeat a composition, so the composition count is a lower bound in every case. `[M]` for the artwork count, `[U]` for the true composition count.

### 9.3 The treatment set — M Simplified's answer to Ficknime's seven

Each artwork is re-presented through a fixed repertoire. Measured instances of each:

1. **Cutout bled on white void, full body, centred** — `4:37.5`, `5:36.9`, `8:05.5`
2. **Cutout bled on white void, punched-in crop** (head, neck, limb) — `2:48.5`, `2:53.4`, `4:02.8`, `4:07.7`, `8:25.4`
3. **Cutout bled on black void** (pale creatures only) — `0:34.7`, `6:56.2`
4. **Cutout composited into a photographic or painted plate, small, establishing** — `5:02.2`, `6:31.4`, `7:45.7`
5. **Same plate, creature scaled up** (escalation without changing location) — `6:36.4` → `6:46.3`, `7:50.7` → `8:00.6`
6. **Cutout + red dashed vertical measurement line + size label** — `2:58.4`, `4:12.7`, `6:56.2`, `8:15.5`
7. **Cutout + red or green arrow + keyword anatomy label** — `0:49.5`, `1:34.1`, `2:48.5`, `2:53.4`
8. **Cutout + human/vehicle pictogram for scale (2-up)** — `4:27.5`, `8:20.4`
9. **Cutout inside the roster cell thumbnail** — `0:00.0` (a *different* image from the section body)
10. **Boxed source photograph on white** — rare, `1:09.4`, `5:32.0`

**Ten treatments vs Ficknime's seven.** The structural difference: Ficknime keeps the source artwork's own background and boxes it; **M Simplified strips the background and composites the cutout into plates the editor chose.** `[M]`

### 9.4 Background plate types `[M]`

Mixed and unashamedly stock:
- **Stock photography** — Swiss hillside, tropical island aerial, aerial village, misty highway, grey city skyline, retro TV on a yellow wall (`2:18.7`), a hand holding a phone (`2:23.7`), rainforest.
- **Digital painting / illustration** — snowy mountain range (`0:05.0`–`0:24.8`), cartoon brick town (`2:28.6`), sunset wheat-field forest (`7:40.8`–`8:00.6`), night sky with a second moon (`5:07.2`).
- **Recognisable third-party imagery** — the Windows XP "Bliss" wallpaper at `1:44.0`, and a **real, identifiable photograph of a named living person** (the franchise creator) at `5:32.0`.

> Two of these would be rejected under this repo's rule 6 ("no licensed characters, no real identifiable people, no meme photographs, ever"). The 1.5 M-view reference does both. Flagging, not recommending.

### 9.5 Icon and pictogram language `[M]`

Three registers, all pure black, mixed freely:
- **Solid filled pictograms** — human figures (at least three poses: standing, running, hands-to-head panic), lab equipment, rifle, tank, buildings.
- **Thin-line outline icons** — ribcage, light-reflection diagram (`5:41.9`).
- **Hand-drawn line stick figure with a smiley face** — reserved exclusively for the two CTAs, never used in a creature section.

**Speech bubbles** are a named scene type: rounded-rectangle white bubble with a tail, black handwritten text, frequently carrying an emoji. Measured: `0:05.0` "Hey friends, I'm hiding here 😄", `0:14.9` "Bro, what is happening here?" and "If I die, my friend will marry my girl", `1:29.2` "I'm so big that I can't fit on the screen", `1:58.9` "I want that sweet spot". Roughly one per section in the incident vignettes.

---

## 10. WHAT PASS 1 MEASURED THAT PASS 2 CANNOT SEE — preserved

These are real measurements from the 60 s multimodal window. Nothing in pass 2 contradicts them, and pass 2 cannot test most of them. They stay tagged `[M60]` — **measured, but over 11 % of runtime only.**

### 10.1 Shot log, 0:00–1:00 `[M60]`

| # | In | Dur | Family | Content |
|---|---|---|---|---|
| 1 | 0:00 | 1 s | roster | roster grid |
| 2 | 0:01 | 2 s | scene | snowy mountain range, stick figures |
| 3 | 0:03 | 7 s | scene | Behemoth head appears behind the mountains |
| 4 | 0:10 | 5 s | scene | figures with equipment + speech bubbles |
| 5 | 0:15 | 10 s | scene | eye opens within the rock, head rises |
| 6 | 0:25 | 2 s | scene | boulder falls toward the figures |
| 7 | 0:27 | 1 s | red | boulder close-up on red field |
| 8 | 0:28 | 1 s | scene | boulder impact in the mountain scene |
| 9 | 0:29 | 2 s | red | boulder close-up on red field |
| 10 | 0:31 | 2 s | white | narrative text card |
| 11 | 0:33 | 2 s | black | full-body Behemoth on black |
| 12 | 0:35 | 3 s | white | satellite + seismic icons |
| 13 | 0:38 | 2 s | black | measurement line |
| 14 | 0:40 | 4 s | scene | Earth-atmosphere diagram with creature |
| 15 | 0:44 | 4 s | black | Mount Everest scale comparison |
| 16 | 0:48 | 4 s | black | anatomical arrows |
| 17 | 0:52 | 3 s | scene | Behemoth head in mountain range |
| 18 | 0:55 | 1 s | white | narrative text card |
| 19 | 0:56 | 2 s | scene | green field, creature + figure |
| 20 | 0:58 | 2 s | scene | snowy mountain, equipment |

20 changes / 60 s → mean 3.0 s, median 2.0 s, min 1 s, max 10 s. **Caveat carried forward:** the log may have merged sub-changes inside continuous animation, so 20 is a lower bound.

**Pass 2 cross-check.** Pass 2's independent lower bound on change rate: **101 of 109 adjacent 4.95 s sample pairs differ substantially** (mean |ΔL| > 6 over the frame), so there is at least one visible change per 4.95 s → **≥ 12.1 changes/min**. That is consistent with pass 1's 20/min but does not confirm it. The true rate stays `[U]`.

### 10.2 Scene construction — the Behemoth cold open `[M60]`

Layer stack, bottom to top: background plate (snowy mountains) → mid-ground occluding peaks → Behemoth head cutout positioned **behind** the peaks → foreground stick-figure scientists and props → text layer (title + speech bubbles).

| Beat | In–out | Dur | What moves |
|---|---|---|---|
| 1 wide establishing | 0:01–0:03 | 2 s | slow zoom on the plate |
| 2 creature emerges | 0:03–0:10 | 7 s | head rises from behind the peaks; screen shake starts |
| 3 human reaction | 0:10–0:15 | 5 s | props + speech bubbles pop in |
| 4 reveal escalation | 0:15–0:25 | 10 s | eye opens, head rises further; heavy shake |
| 5 threat descends | 0:25–0:27 | 2 s | boulder falls |
| 6 impact | 0:27–0:31 | 4 s | red field × 2 with one full-frame impact frame between |

**Pass 2 confirms the underlying grammar in a different form.** The escalation-by-scaling-up-on-one-plate pattern recurs across the whole video: `6:36.4 → 6:46.3` (Bird Watcher grows in the city plate) and `7:45.7 → 8:00.6` (Tree Head grows in the forest plate) are the same move. So the signature generalises as **"one plate, creature scales up over the beat"**, of which "rises from behind an occluder" is the section-1 instance. `[M]`

**Pass 2 contradicts "cutout tinted to match the sky".** In section 5 the same cutout appears untinted over seven wildly different plates (bright green pasture, night sky, tropical blue, grey fog). If tinting happens it is not systematic. `[M]`

### 10.3 Motion, humour and audio from pass 1 `[M60]`

| Finding | Value | Status after pass 2 |
|---|---|---|
| Continuous slow zoom on most held shots, ≈1.1× | `[M60]` | **Partly contradicted** — see §11 and §12; at least one 4.95 s span has *zero* movement |
| Screen shake ×2 in 60 s (0:03 rhythmic, 0:15 high-amplitude), triggered by seismic/impact lines | `[M60]` | untestable in pass 2, preserved |
| No glitch / chromatic aberration in 0:00–1:00 | `[M60]` | no counter-evidence in 110 frames, but absence of evidence only |
| 6 discrete SFX in 60 s (rumble 0:03, squelch 0:16, roar 0:17, whoosh 0:25, impact 0:28, beep 0:36) | `[M60]` | untestable — storyboard track carries no audio |
| Constant low-frequency suspense drone throughout | `[M60]` | untestable |
| Cuts mostly silent; only physical-event cuts carry a hit | `[M60]` | untestable |
| Stick figures with speech bubbles as the humour form | `[M60]` | **Confirmed and extended** — §9.5 lists five more instances across the runtime, roughly one per incident vignette, with emoji |

---

## 11. CONFIRMED / CONTRADICTED vs `spec/style-profiles.json`

Every stored value under `profiles["m-simplified"]`, plus the `_universal` entries this evidence touches. **This is the most valuable output of the document.**

### 11.1 `profiles["m-simplified"]`

| Field | Stored | Measured this pass | Verdict |
|---|---|---|---|
| `layout.fullFramePct` | **0.75** | **0.473** (scene 46.4 % + red-tint 0.9 %), n=110 | ❌ **CONTRADICTED** |
| `layout.whiteCanvasPct` | **0.25** | **0.418** white; **0.445** white-family; **0.527** canvas of any colour | ❌ **CONTRADICTED** |
| `layout.whiteCanvasTrigger` | `["number","size-comparison","spec"]` | `"spec"` ✅ (spec blocks are 62.8 % canvas). `"number"` and `"size-comparison"` ❌ — both appear on white, black **and** full-frame scene. Canvas *colour* is selected by subject luminance, not content class | ⚠️ **1 of 3 correct — replace with §2.5** |
| `title.font` | `bold-sans` | bold **rounded oblique COMIC/casual** face (Comic-Sans-class), not a neutral sans | ⚠️ **REFINE** |
| `title.case` | `title` | ✅ Title Case, all 8 sections | ✅ **CONFIRMED** |
| `title.fill` | **`#000000`** | **white fill** (~`#FFFFFF`) on white canvas, black canvas and scene alike | ❌ **CONTRADICTED — inverted** |
| `title.stroke` | **`#FFFFFF`** | **black stroke** (~`#000000`) | ❌ **CONTRADICTED — inverted** |
| `title.strokeWidth` | 6 | 1 px at 320 → 4–8 px at 1080p | ✅ **CONSISTENT** (not exactly confirmable) |
| *(missing)* title position | — | x = **50.00 % W**, zero variance across 46 frames; glyph band **0.044–0.111 H**; cap height ≈ **0.061 H** | ➕ **ADD** |
| `palette.bg` | `#FFFFFF` | ✅ **exactly `#FFFFFF`** (modal pixel, 46 frames) | ✅ **CONFIRMED** |
| *(missing)* second canvas | — | **`#000000`, 8.2 % of runtime** | ➕ **MISSING — add** |
| `palette.ink` | `#000000` | ✅ pictograms, icons, roster border, title stroke all floor at 0–8 | ✅ **CONFIRMED** |
| `palette.accents` | `["#00FF00","#FFFF00"]` | green and yellow confirmed as the two label colours, but measured peaks are **≈`#5AF050`** and **≈`#DCE767`** (a chartreuse, not pure yellow), and there is a **third accent, red ≈`#D5192A`**, carrying arrows and measurement lines | ⚠️ **INCOMPLETE + off-hue** |
| *(missing)* accent selection | — | **NOT per-section.** All three accents recur across sections; choice is per-shot contrast | ➕ **ADD — and note it is the opposite of Ficknime** |
| `caption.pos` | `bottom-center` | ❌ Measured positions: beside the subject left (`2:43.5`), beside right (`7:06.1`), under the subject (`1:09.4`), mid-frame centred on text-only cards (`4:32.5`), upper-left (`8:10.5`). **No bottom-centre caption was sampled in 110 frames** | ❌ **CONTRADICTED** |
| `caption.anim` / `animMs` | `instant-pop` / 0 | not testable at 4.95 s | 🚫 **[U]** |
| `roster.cells` | **9** | **8** | ❌ **CONTRADICTED** |
| `roster.grid` | **`3x3`** | **`4x2`** | ❌ **CONTRADICTED** |
| *(missing)* roster metrics | — | cell 0.222 W × 0.372 H; pitch 0.243 W / 0.478 H; label below, ALL CAPS, white-on-black-outline; black border ≈7 px @1080p; radius ≈8–10 px @1080p; no shadow; margins 2.5 % W / 5.6 % H | ➕ **ADD** |
| *(missing)* roster labels ≠ titles | — | DAY 17 / DAY 18 / TREE HEAD in the roster vs The Wandering Faith / The Wandering Doom / Big Branch on screen | ➕ **ADD** |
| `pacing.avgShotSec` | 2.2 | not testable; lower bound **≥12.1 changes/min** from 101/109 differing adjacent samples | 🚫 **[U]** |
| `pacing.maxHoldSec` | **4.0** | ❌ `6:41.3 → 6:46.3` is a **4.95 s span with mean per-pixel ΔL = 0.095 and only 0.09 % of pixels changed by more than 8** — functionally a frozen frame | ❌ **CONTRADICTED** |
| `audio.sfxPerMin` | 20 | no audio in the storyboard track; pass 1 measured 6 salient hits/min | 🚫 **[U]** — conflict unresolved |
| `motion.shakeOnImpact` | true | pass 1 `[M60]` only | 🚫 **[U]** for the full runtime |
| `motion.shakeCount9min` | 9 | pass 1 saw 2 in the first 60 s (an impact-heavy cold open); extrapolation unsafe | 🚫 **[U]** |
| `signature` | "creature layer rises from behind a background element; **cutout tinted to match the sky**" | rise-from-behind ✅ in section 1; generalises to **"one plate, creature scales up over the beat"** (`6:36→6:46`, `7:45→8:00`). **Tinting ❌** — the same untinted cutout sits on seven different plates in section 5 | ⚠️ **first clause CONFIRMED and generalised; second clause CONTRADICTED** |
| `midCta.atSec` / `durSec` | 201 / 9 | **200.5 / 9.1** | ✅ **CONFIRMED** |
| `midCta.treatment` | "stick figure on white canvas, LIKE / SUBSCRIBE / COMMENT" | ✅ exactly that — plus: the figure is a **hand-drawn line** figure (not the solid pictogram used elsewhere), the words are **green ALL CAPS**, and **the persistent title is removed for the whole CTA** | ✅ **CONFIRMED + extended** |
| *(missing)* outro | — | 533.8–545.0 s, **11.2 s**, identical visual language to the mid-roll, no end card, no tail | ➕ **ADD** |
| *(missing)* no chrome | — | **no badge, no watermark, no corner element anywhere** (corner-patch SD 63–71 across 51 scene frames) | ➕ **ADD** |
| *(missing)* content boxes | — | boxing is **1.8 % of runtime**; boxes have **no border, no radius, no shadow**; solo box is **not centred** (0.255 W) | ➕ **ADD** |
| *(missing)* text-only cards | — | **6.4 % of runtime** is a canvas with text and nothing else | ➕ **ADD** (and note it contradicts house rule 10) |

### 11.2 `_universal`

| Field | Stored | Measured | Verdict |
|---|---|---|---|
| `titlePersistent` | true | **106/110 = 96.4 %**; present on 100 % of scene frames and 100 % of canvas frames **except the 4 CTA frames** | ✅ **CONFIRMED with a CTA exception** |
| `titlePos` | `top-center` | ✅ x = **50.00 % W**, zero variance | ✅ **CONFIRMED** |
| `textOnScreenPct` | 0.95 | **≈99 %** (109/110 — the single text-free sample is `8:55.1`, the CTA stick figure alone) | ✅ **CONFIRMED / exceeded** |
| `captionMaxWords` | **4** | ❌ measured cards of **6 words** (`6:01.7`), **8 words** (`8:10.5`) and **10 words** (`3:28.1`). Keyword labels are 1–3 words, but verbatim caption cards are not capped | ❌ **CONTRADICTED for this profile** |
| `maxHoldSec` | **4.0** | ❌ 4.95 s frozen span at `6:41.3–6:46.3` | ❌ **CONTRADICTED** |
| `staticRuntimePct` | **0.0** | ❌ same span. At 320×180 even a 1.01× zoom over 5 s would displace edge pixels by ~1.5 px and register; 0.09 % of pixels changed | ❌ **CONTRADICTED** |
| `zoomPerShot` | [1.05, 1.10] | not measurable in general, but the frozen span proves **at least one shot has no zoom at all** | 🚫 **[U] + one counter-example** |
| `rosterPunchInSec` | 0.5 | roster return and punch-in **confirmed**; duration estimated ≈1.4 s from catch rate, wide CI | 🚫 **[U]** |
| `iconPopMs` / `iconPopScale` / `captionSyncTo` | 200 / [0,1.1,1] / first-syllable | not testable at 4.95 s | 🚫 **[U]** |
| `musicBed` / `duckDb` | drone / −12 | no audio | 🚫 **[U]** |
| `avgShotSec` | 2.2 | lower bound ≥12.1 changes/min | 🚫 **[U]** |

### 11.3 The short list

**Twelve stored values are wrong and are about to become renderer config:**
`layout.fullFramePct` · `layout.whiteCanvasPct` · `layout.whiteCanvasTrigger` · `title.fill` · `title.stroke` · `caption.pos` · `roster.cells` · `roster.grid` · `pacing.maxHoldSec` · `signature` (second clause) · `_universal.captionMaxWords` · `_universal.staticRuntimePct`.

**Three whole concepts are missing:** the black `#000000` canvas (8.2 % of runtime), the red accent (a third accent used for all arrows and measurement lines), and the fact that **there is no chrome at all** — no badge, no watermark.

---

## 12. WHAT I COULD NOT DETERMINE — the honest `[U]` list

A 4.95 s sampling interval cannot measure anything faster than 4.95 s. None of the following is guessed at, and none of it should be filled in from plausibility.

1. **Ken Burns amount, direction, and whether every held image moves.** `zoomPerShot [1.05,1.10]` unverified. The only hard datum is a counter-example: one 4.95 s span with zero movement.
2. **Cuts per minute / average shot length / longest hold.** `avgShotSec: 2.2` unverified. Lower bound ≥12.1 changes/min.
3. **Icon and pictogram entry animation** — slide direction, distance, duration, scale-pop curve. `iconPopMs: 200`, `iconPopScale` unverified.
4. **Whether list items pop sequentially or together**, and whether they land on the spoken word. `captionSyncTo: first-syllable` unverified.
5. **Caption on-screen duration and in/out animation.** `caption.anim: instant-pop`, `animMs: 0` unverified.
6. **Screen shake** — existence outside 0:00–1:00, amplitude, trigger set. `shakeJitterPx`, `shakeCount9min: 9` unverified.
7. **Glitch / VHS / scanline / chromatic aberration** anywhere. No sample caught one; that is absence of evidence, not evidence of absence.
8. **All audio.** SFX count and density, music bed, whether cuts carry hits, ducking depth. The 6/min (pass 1) vs 20/min (stored) conflict is unresolved.
9. **Roster hold duration and punch-in duration.** Return confirmed; timing estimated at ≈1.4 s from catch rate only.
10. **Whether the roster returns at all seven boundaries** or only some. Caught at 1 of 7.
11. **Exact typeface identity.** Characterised (bold rounded oblique comic) but not named at 320×180.
12. **Exact accent hexes.** The peak-fill estimates in §6.2 are pulled from 1–2 px glyph strokes in a JPEG; treat as ±20 per channel.
13. **Whether any content box has a border thinner than ~6 px at 1080p.** The probe rules out anything thicker.
14. **True composition count per section.** Every sampled frame inside every section is a different composition, so all counts are lower bounds.
15. **Whether the creature cutout is ever colour-graded to a plate.** Section 5 shows it is not done systematically; a subtle grade would not survive this compression.
16. **The last 4.95 s (540.0–545.0 s).** No sample exists.

---

## 13. WHAT ONE VISUAL CALL EACH WOULD SETTLE — ranked for tomorrow's quota

Ordered by how much each would change what we build. Each is scoped to one call and written so the answer cannot time out.

**1. `0s–60s` — the motion and pacing core.** Highest value by a distance. Every unknown in §12 items 1–5 is present at once in this window, and pacing is the one thing our renderer must reproduce with zero verified numbers.
> "List every visual change in this 60 seconds as a table: timestamp in, timestamp out, duration in seconds, and what changed (new element added / whole composition replaced). Give the total count and the average. For each element that enters, state which direction it enters from, how far it travels as a percentage of frame width, and over how many seconds. Does every held image carry a continuous slow zoom — if so, in or out, and by roughly what percentage over the shot? Answer with timestamps and numbers only, no adjectives."

**2. `385s–415s` — the frozen-frame check.** This window contains the measured static span at `6:41.3–6:46.3` and the section 6 → 7 boundary. It settles §12 items 1 and 10 and decides whether `maxHoldSec: 4.0` and `staticRuntimePct: 0.0` survive as universal invariants or become house-only rules.
> "Between 6:36 and 6:50 the Bird Watcher stands in a misty city with three stick figures. Does the image move at all in that stretch — any zoom, pan, parallax or added element — or is it a completely frozen frame? Give the exact timestamps of the first and last visible change. Then describe the transition at about 6:30 from Breaking News to The Bird Watcher frame by frame: does a grid of creature thumbnails reappear, how long does it hold, and does the shot punch in to one cell?"

**3. Any 60 s window — audio only.** Settles all of §12 item 8, the only route to it, and cheap.
> "Ignore the visuals. Count every discrete sound effect in this 60 seconds and give the count and the per-minute rate. Describe the music bed. Does every hard cut carry a sound — whoosh, impact, riser, or nothing? Timestamp ten sound effects and say what each one sounds like and what visual event it lands on. State your counting rule."

**4. `195s–215s` — the mid-roll CTA in motion.** The still treatment is now measured; what is unknown is timing and animation. Also captures the section 3 → 4 boundary.
> "Across this 20 seconds: how long exactly does the stick-figure CTA hold, how many separate cards does it use, and what word is on each? How does each word animate in and out, and over how many seconds? Does the creature name title reappear before or after the CTA ends? Describe the cut back into the next creature's section frame by frame."

**5. `420s–460s` — caption and label behaviour on the black canvas.** Settles §12 items 4 and 5 on the section with the densest label load, and confirms the black/white canvas flip at `7:16`.
> "For every text element in this stretch: timestamp, exact words, how long it stays on screen, how it animates in and out, and where it sits as a fraction of frame width and height. At around 7:06 two labels appear ('rusted iron beams', 'shattered glass') — do they appear together or one at a time, and does each land on the spoken word? At 7:16 the background changes from black to white: is that a hard cut or a fade, and how long does it take?"

---

## 14. SOURCES AND REPRODUCTION

**Pass 2 (this session).**
```
yt-dlp --no-playlist --extractor-args "youtube:player_client=mweb" -J \
  "https://www.youtube.com/watch?v=lrY0ErBfytQ" > meta.json
# formats[] where format_id starts with "sb". mweb exposes sb0 = 320x180, 3x3 tiles, 13 sheets.
# android_vr / tv_embedded / web_embedded top out at 160x90 - always sweep clients.
# each sb entry carries rows, columns, width, height, fps (= 1/interval) and fragments[] URLs on i.ytimg.com.
# fetch each sheet, split into rows x columns tiles, timestamp tile i at i * (1/fps).
```
For this video: `sb0` = 13 sheets (12 × 960×540 with 3×3 tiles, 1 × 640×180 with 2 tiles) → **110 frames**, `fps` 0.2018348623853211 → **4.9545 s** interval → t = 0 → 540.05 s. Unmetered, unblocked, downloads in seconds. Every frame then measured with numpy/PIL — border-ring and whole-frame colour masks, bounding boxes, column/row run detection, edge and corner probes, per-hue peak-fill extraction, adjacent-frame difference — and read visually at 3× LANCZOS upscale in 19 six-up montages.

**Pass 1 (earlier session).** `mcp__NexLev__watch_youtube_video_and_ask`, `lrY0ErBfytQ`, `startOffset=0s`, `endOffset=60s` — the single successful visual call; source of every `[M60]` row.

**Transcript and metadata.** `mcp__NexLev__get_video_transcript` (274 cues, 1,661 words) and `mcp__NexLev__youtube_video_details` (545 s, 1,537,191 views, 8-chapter description list).

**Comparison.** `docs/teardown-ficknime-2026-08-09.md` for the sibling teardown of Ficknime `VZPZi8yb5mg`, produced with the same storyboard method.
