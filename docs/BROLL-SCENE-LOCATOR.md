# Forgecast — the scene locator

`forgecast/research/scenes.py`. Third of three notes; companions are `BROLL.md` (what was
decided) and `BROLL-LOGIC.md` (how the footage side works).

**What it does:** the operator says *"the scene where the truck flips in The Dark Knight"*.
It answers where that scene can lawfully be watched, where in the runtime it sits, and what
is actually known about the right to use it. It answers all three, or it says which one it
could not answer. It never fills a gap in.

---

## 1. It returns coordinates, not a file

The tempting shape is a thing that goes and fetches the scene. The app already has four
things that go and fetch: `vision.acquire` pulls a platform URL with yt-dlp,
`providers.search.fetch` pulls a page, `research.keyless` reads a listing without a key, and
`providers.sfx.fetch_named_sound` pulls a named cue. A fifth would not be a fifth capability
— it would be a fourth copy of the same subprocess call, with its own timeout, its own idea
of a proxy, and its own way of failing at three in the morning.

So it returns a **URL, an in, and an out**. `handoff()` emits `reference` / `start` /
`seconds` / `note` in the exact argument names `vision.acquire.acquire` and
`footage.strip_audio` already take, so nothing downstream re-derives a trim.

Discovery reuses the desk's existing reach: `keyless._run` for anything on YouTube,
`providers.search.provider_for()` for press sites. That seam matters beyond tidiness — the
test suite refuses a real yt-dlp run through `keyless._run`, so a locator built on it cannot
quietly start calling YouTube from a test.

---

## 2. The distinction the whole module turns on

"Licensed" answers two questions, and this module only gets one:

| Question | Answer |
|---|---|
| Is this a lawful place to find the scene? | Every source here says yes |
| May this footage be cut into my video? | **None of them answer that** |

A Movieclips upload *is* licensed — Fandango owns the channel, studios licensed the clips to
it, it is the right place to watch the scene. It does not follow that the scene may be
re-cut into someone's video.

So `licence` here is a statement about the **upload**:

```
licensed_distribution   Movieclips — studio-licensed
studio_official         the rights holder's own channel
press_kit               published for editorial coverage
by                      the uploader's own CC mark
not_established         everything else
```

The first three are **deliberately not licences** and deliberately **not** in
`footage.COMMERCIAL_LICENCES` — which is *imported* rather than restated. Two answers to
"may this be used" is how the two drift, and the first to drift would be the one that says
yes. `commercially_safe` is therefore false for every studio lane.

What the app owes in exchange for not deciding is the same thing the operator lane owes:
the position stated in words, on the result, where it will be read. **Publish is never
blocked.** Whether a two-second cut is fair dealing where the operator lives is their call
and their lawyer's, and a filter written here cannot make it.

---

## 3. The sources are an allow-list of identities

Fandango's Movieclips, studios' own channels, studio press/EPK sites, and YouTube's CC
filter. Nothing else — and specifically none of the streaming-rip sites, release indexes or
media-centre add-ons that a plain web search for a famous scene returns *above* every
legitimate result. There is no scraper for one and there will not be one.

`REFUSED_MARKERS` is a second gate every candidate from every lane passes. It is a check on
the allow-list rather than a filter doing real work — the web-search lane returns whatever
the index holds, and the day someone adds a domain in a hurry is the day a second gate earns
its place.

**Channels match on identity — handle or channel id — never display name.** A studio's name
with "HD" appended is not that studio, and a display-name match is exactly the door a
re-uploader walks through. An exact name match is accepted *only* when the entry carries no
identity field at all, and that result says so on itself: YouTube permits duplicate display
names, so a name is a presumption and a handle is a fact. An entry with a non-allow-listed
handle is rejected outright — otherwise an impostor named exactly like a studio walks through
the door built for a missing field.

---

## 4. The CC filter is never asked about a named film

YouTube offers exactly one Creative Commons option and the uploader ticks it themselves. On
a stranger's re-upload of a studio film that tick is not a licence — it is a mistake, and
honouring it would be the app laundering a rip through a checkbox.

So the CC lane runs **only when the description names no title**:

- *"the Falcon 9 booster landing on the drone ship"* → a scene someone may genuinely have
  shot and licensed. CC lane runs.
- *"the truck flip in The Dark Knight"* → names a film. CC lane skipped.

This makes `read_description` load-bearing: it returns `(film, action)`. When capitalisation
gives no signal — an operator typing all lowercase — **the tie goes to "this is a title"**.
Being wrong that way silences a lane; being wrong the other way is the one thing the module
exists to prevent.

---

## 5. Confidence is identification, never rights

Two axes, never collapsed:

- **confidence** — how sure the app is that this result is the scene asked for
- **licence** — what is known about using it

A high-confidence match to a clip nobody may reuse is the *ordinary* case here, and rolling
rights into the score would hide it. Ranking is by confidence, because an operator asking
where a scene is does not want a wrong scene handed to them for being better licensed.

Bands: `HIGH_CONFIDENCE = 0.65`, `MEDIUM_CONFIDENCE = 0.40`. Every match carries a
`confidence_reason` in words.

---

## 6. What a timecode can honestly be

`_window(duration)` has three outcomes:

| Upload | Window | Why |
|---|---|---|
| ≤ `CLIP_SECONDS` (900s) | `0.0 … duration` | The whole upload *is* the scene. That is the clip's own boundary, not a measured cut — expect a channel ident on the tail |
| > 900s | `None, None` | The scene is *inside* it and this module cannot say where |
| runtime unreported | `None, None` | Nothing to compute from |

**`None`, never `0.0`.** A caller reading 0.0 as a start would trim from the wrong place and
never find out. `trim_seconds` is `0.0` in that case, which `strip_audio` already reads as
"no trim" — the two are different facts and are kept different.

The one recovery for a long upload is the **uploader's chapter marks**: when one names what
the operator described, that is a real in and out read from metadata YouTube already
publishes. Capped at `CHAPTER_LOOKUPS = 3`, read with `--dump-single-json --skip-download`.

Trimming a guess off a short upload to look precise was rejected — inventing a number to
appear exact is the failure mode this module is built against.

---

## 7. `SceneMatch`

Shares its vocabulary with `providers.footage.FootageClip` on purpose — `licence`,
`commercially_safe`, `flag_reason`, `credit_line` mean the same things — so a run mixing a
located scene with licensed footage does not need two ideas of what a licence is.

Carries: `url`, `title`, `source`, `licence`, `channel`, `film`, `start_seconds`,
`end_seconds`, `duration_seconds`, `confidence`, `confidence_reason`, `flag_reason`, `notes`.

---

## 8. Where it is *not* wired

Worth stating plainly, because it is this project's recurring defect. The locator exists,
is tested (42 tests), and returns a handoff in the argument names the fetch path takes — but
**nothing in the pipeline calls it yet.** It is reachable from the agent and from code; it is
not yet part of any node's flow. Wiring it into the shot planner is open work, not done work.

---

## Invariants

1. A licensed *upload* is never treated as a licence to re-cut.
2. Those upload-licence strings stay out of `footage.COMMERCIAL_LICENCES`, which is imported
   rather than restated.
3. The CC lane is never asked about a named title.
4. Channels match on identity; a display-name match is a presumption and says so.
5. An undetermined window is `None`, never `0.0`.
6. Ranking is by identification confidence, never by rights.
7. No fifth fetcher — discovery goes through `keyless._run` and `providers.search`.
