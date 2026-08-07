# Forgecast — B-roll: the logic

Companion to `BROLL.md`. That file says what was decided; this one says how it works and
why each number is where it is. Read the code before changing it — this describes intent,
the source is the truth.

Files: `forgecast/providers/footage.py`, `forgecast/style/sourcing.py`,
`forgecast/render/cutting.py`, `forgecast/research/scenes.py`, `forgecast/nodes/finalize.py`.

---

## 1. The clip, and the licence decision

`FootageClip` is the unit. Its shape deliberately mirrors `stock.StockAsset` where the
fields mean the same thing, so a run's credit file does not need to know whether a credit
came from a still or a clip.

Two frozensets carry the whole licence rule:

```
COMMERCIAL_LICENCES = {cc0, pdm, publicdomain, by, pexels, pixabay, usgov}
ATTRIBUTION_REQUIRED = {by, by-sa}
```

`commercially_safe` is a **property**, not a filter applied once:

```
if operator_directed:  return False        # regardless of the licence string
return licence.lower() in COMMERCIAL_LICENCES
```

The early return is the important line. An operator-directed clip is never safe *however it
is licensed*, because the app did not establish the licence — the operator did. A property
named `commercially_safe` returning true on someone else's say-so is a claim the app cannot
back.

Note what is absent from the set: `by-sa` (would oblige the whole video to the same
licence), `by-nc` (breached by monetisation), `by-nd` (breached by cutting), and the empty
string. A source that cannot answer gets no default.

`by-sa` appears in `ATTRIBUTION_REQUIRED` but not in `COMMERCIAL_LICENCES` — it needs a
credit *and* is refused. Both are true and they are separate questions.

### credit_line()

Operator-directed clips take a different branch that never prints a licence, whatever
string they carry. Everything else prints `title — creator (LICENCE) landing_url`, or the
source's own attribution string when it supplied one.

---

## 2. Searching

`find(query, *, limit, pexels_key, pixabay_key)` runs four sources and merges:

```
NASA  →  Internet Archive  →  Pexels  →  Pixabay
```

Ordered by **how firmly the licence is established**, not by footage quality: a public-domain
government clip needs no further thought, a vendor licence needs the operator not to be
reselling it as stock, and anything `by` accrues a credit line that must ship with the video.

Two behaviours worth preserving:

- **A source that fails is skipped, not fatal.** The caller wanted footage; three sources
  answering is an answer. Failures are logged, not raised.
- **A keyed source with no key returns `[]`** rather than erroring. Pexels/Pixabay keys
  *meter*, they do not bill — the same category as no key at all. (This is the one place
  the project's "subscriptions, not API keys" rule was interpreted rather than followed;
  flagged for the operator to rule on.)

Final filter is `commercially_safe`, then sort by `(needs_attribution, -width)` — so a clip
needing no credit wins ties, and wider wins after that.

### Internet Archive specifically

Searched by **collection**, never by keyword alone:

```
prelinger, feature_films, classic_tv, nasa, usgovfilms
```

The query becomes `(user query) AND (collection:… OR …) AND mediatype:movies`. Licence is
set to `publicdomain` **because of where the item lives**, not from its own metadata, which
is frequently absent and occasionally wrong.

### NASA specifically

Licence is `usgov`. Two exceptions are recorded rather than filtered, because neither is
decidable from a search result: contractor-produced material can carry restrictions, and
agency insignia may never imply endorsement. An app that silently dropped every result
mentioning a logo would be wrong more often than right.

---

## 3. The operator lane

`operator_clip(source, out_path, *, start, seconds, title, creator, note)`.

Refuses anything that is not a readable local file. That refusal is where "no fetcher
reaches an unlicensed index" is *enforced* rather than merely intended — the lane takes a
file, so there is nothing here that can be pointed at an index.

It then calls `strip_audio` and returns a clip with `licence="operator_supplied"` (a string
deliberately absent from `COMMERCIAL_LICENCES`), `operator_directed=True`, and a
`flag_reason` in words.

### strip_audio

```
ffmpeg -v error -y [-ss START] -i SOURCE [-t SECONDS] -an -c:v copy OUT
```

`-an` drops every audio stream. `-c:v copy` makes the common path a remux rather than a
re-encode.

**The fallback matters.** A stream copy cannot always start at an arbitrary frame, so on
non-zero exit the command is rewritten to `-c:v libx264 -preset veryfast` and retried. The
re-encode is taken silently because the alternative is telling an operator a perfectly good
file "failed" when a remux merely could not seek. Still `-an` on the second attempt — the
mute is not the thing being retried.

`-ss` before `-i` (input seeking, fast); `-t` after (output duration).

---

## 4. Scene locator

`research/scenes.py`, `locate(description, *, limit)`.

Its licence strings — `licensed_distribution`, `studio_official`, `press_kit` — are
**imported from `footage.COMMERCIAL_LICENCES` context and deliberately not members of it**.
A studio channel establishes *where to watch* a scene; it is not a licence to re-cut the
film. So `commercially_safe` is false for every studio lane, and `flag_reason` states what
*is* established before saying whose decision the rest is.

Three rules encoded:

- **The CC lane never runs on a named title.** `read_description` returns `(film, action)`;
  when a title is present the CC lane is skipped entirely. A stranger's CC tick on a studio
  re-upload is a mistake, not a licence, and honouring it would launder a rip through a
  checkbox. When capitalisation gives no signal the tie goes to "this is a title" — being
  wrong that way silences a lane, being wrong the other way is the thing the module exists
  to prevent.
- **Channels match on identity** (handle / channel id). An exact display-name match is
  consulted only when an entry carries no identity field at all, and carries a caveat. An
  entry with a non-allow-listed handle is rejected outright — otherwise an impostor named
  exactly like a studio walks through the door built for a missing field.
- **An undetermined window is `None`, not `0.0`.** An upload ≤ 15 min *is* the scene
  (window 0..runtime). Longer, and the scene is inside it: both bounds `None`, `timecode`
  empty, `trim_seconds` 0.0 — which `strip_audio` already reads as "no trim". The one
  recovery is the uploader's chapter marks.

Ranking is by identification confidence, never by rights. Someone asking where a scene is
does not want a different scene for being better licensed.

`handoff()` returns `reference` / `start` / `seconds` / `note` in the exact argument names
`vision.acquire.acquire` and `footage.strip_audio` already take.

---

## 5. How many plates a scene buys

`style/sourcing.py` measures; `render/cutting.py` spends.

### The measurement

For each adjacent pair of shots in the learned reference, `_new_colour_mass(after, before)`
asks **how much of `after` is colour that `before` did not have on screen.**

```
_MAX_RGB    = 441.673      # sqrt(3 * 255²) — every distance is a fraction of this
NEIGHBOUR   = 0.14         # nearer than this and it is the same colour, requantised
NEW_CONTENT = 0.10         # this much arriving colour makes it a new picture
```

For every palette entry in `after`, find the nearest colour in `before`; if that distance
exceeds `NEIGHBOUR`, add that entry's share to the mass.

**Why arriving colour and not a palette diff.** A crop of one plate cannot show a colour the
wider frame did not already contain. So a punch-in moves the *shares* enormously — tightening
on a subject can double its share and halve the background's — while nothing new appears. A
palette diff would score a reframe as the largest change in the video and buy six plates for
one picture.

**Why `NEIGHBOUR` is 0.14.** `visual._palette` quantises to three bits per channel, so a
colour that barely moves can still land one bucket over — 32 levels — in every channel at
once. That is a distance of 55, or 0.125 normalised: a quantisation artefact, not a new
object. 0.14 clears it and little else; the nearest genuinely new colour a cut can bring is
a bucket further out again, at 0.25.

**Why `NEW_CONTENT` is a tenth of the frame, not a share of it.** Per-shot palettes hold
three entries, so a subject owning a tenth of the frame is the third of them. This is the
white-background explainer case: the background is shared across every shot in the video and
the only thing that ever changes is the cut-out. Weigh the change against the whole frame and
that format reads as never cutting away.

`_changed` measures **both directions and keeps the larger**, because a cut *away* from a
detailed picture onto a plain one brings little new colour while plainly being a new picture.

`_variety` works over **boundaries, not shots** — n shots have n−1 — and returns
`(share, count)`. A reference with one shot has no boundaries, which is reported rather than
averaged in as zero.

### From measurement to spend

```
_shots_per_plate(variety) = clamp(1 / variety, 1.0, MAX_SHOTS_PER_PLATE=4.0)
```

The reciprocal, because that is what the share means read as a rate: change picture on one
cut in four and each picture is held across four shots. No curve is fitted and there is no
constant to tune — the ends are 1 and 4, and the measurement decides where between.

`MAX_SHOTS_PER_PLATE = 4.0` is a **viewer** bound, not a cost one: `apply.PUNCH_LEVELS`
offers two clearly separated framings, so four shots is A B A' B' and a fifth return to the
same still is where recognition beats the reframe.

`plate_carry(profile)` returns `None` — not a number — for an unmeasured or unusable
channel, and that distinction is load-bearing:

```
plates_for(seconds, spec, sourcing):
    carry = plate_carry(sourcing)
    if carry is None:  ceil(seconds / SECONDS_PER_PLATE)   # per second
    else:              ceil(shot_estimate(seconds, spec) / carry)   # per shot
```

**Unmeasured → plates per second.** With no reference to read, letting the cutting rate drive
the plate count means a fast-cutting channel pays twice for pictures nobody asked it to
change.

**Measured → plates per shot.** Here the cutting rate *does* belong in the bill, because the
same measurement that made it fast is the one saying the pictures genuinely change that
often.

`usable` gates this the way `budgets` is gated: confidence must be medium or high and at
least 8 shots measured. A variety read off four shots is an anecdote, and this anecdote buys
a plate on every shot of a whole video.

**The reserve reads the same profile.** `estimate_plates` and `animation_reserve` take both
`sourcing` and `render_spec`, so the hold and the spend are computed by one rule. This has
broken twice on this project; it is the invariant most worth protecting.

---

## 6. Attribution

`finalize._write_attribution` runs in the render node, collects `shots` artifacts carrying a
`licence` or `attribution` in their meta, builds `FootageClip`s and calls
`footage.attribution_markdown`.

A plate with neither key is a generated image — nothing was licensed, nothing is owed, and it
is skipped. When nothing is owed at all the function returns `None` and **writes no file**:
an empty credits file trains an operator to ignore the one that matters.

Emitted as an artifact rather than left in the workdir, so the credits travel with the video.

---

## Invariants worth not breaking

1. Nothing vouches for a licence it did not establish.
2. Audio comes off at ingest, never at render.
3. The reserve and the spend read one measurement.
4. A source that cannot answer the licence question gets no default.
5. Publish is never blocked by the operator lane; it is flagged with a reason in words.
