# Forgecast — B-roll: decisions, what is built, what is open

A handoff note. Everything below was decided or built in one working session; it is written
to be readable by someone who was not there.

One of three: this file is the **decisions**. `BROLL-LOGIC.md` is how the footage side
works and why each threshold sits where it does. `BROLL-SCENE-LOCATOR.md` covers
`research/scenes.py` on its own, because the licence question there is a different question
and conflating the two is the mistake that module exists to prevent.

---

## 1. The sanctioned source list

These are the footage sources Forgecast is allowed to reach, decided by the operator:

- **Pexels / Pixabay** — free stock video under their own vendor licences
- **Internet Archive**, including Prelinger — public-domain film
- **NASA / NOAA / US government** — public domain as federal works
- **YouTube, Creative Commons filter only**
- **Storyblocks** — planned, API not yet integrated

Stills go through the existing Openverse path (`providers/stock.py`), which is keyless.

**Not on the list, and deliberately so:** piracy add-ons of the HDHub / Kodi-add-on class.
This was raised several times and declined each time. The reasoning, so it does not have to
be relitigated: those indexes carry unlicensed rips, "educational purposes" is not a blanket
exemption in any jurisdiction, and a fetcher pointed at them would live in the repo and ship
inside every zip the app produces. That is shipped infringement infrastructure regardless of
who runs it or why.

---

## 2. The licence model

The central rule: **nothing may vouch for a licence it did not establish.**

Licence is carried **per clip**, from the source that knows it — not applied once as a
filter at the top. This matters because the sanctioned sources have four incompatible ideas
of what "free" means:

| Source | What the licence actually is |
|---|---|
| Pexels, Pixabay | Vendor licence: free for commercial use, no attribution, but redistribution *as stock* is forbidden — a video does not do that, a footage pack would |
| Internet Archive | Per item, genuinely mixed. Prelinger is public domain; the item beside it may be a rip somebody uploaded |
| NASA / NOAA / gov | Public domain as a federal work, with two standing exceptions: contractor-made material may be restricted, and agency insignia may never imply endorsement |
| YouTube CC | `by` only — YouTube offers exactly one CC option — and the uploader may have ticked it wrongly, which the app cannot verify |

A source that cannot answer the licence question **does not get a default**.

`commercially_safe` is a property of the clip. Licences that a monetised, edited video would
breach are excluded outright: `by-sa` would oblige the whole video to the same licence,
`by-nc` is breached by monetisation, `by-nd` is breached by cutting.

**Internet Archive is searched by collection, never by keyword alone.** The site hosts a
great deal its uploaders had no right to post, and "it was on archive.org" is not a licence
— nor is age. The collection is what establishes one.

---

## 3. The operator-directed lane

The one path where the operator overrides the licence question. The app does not fetch, and
does not judge; it makes the operator's decision visible. Four guarantees:

1. **Audio is stripped at ingest, not at render.** A clip that arrives muted cannot be
   un-muted by a later stage, and every later stage is written by someone who does not know
   where the file came from. Doing it at render would make silence a property of a code path
   rather than of the file.
2. **An in/out timecode is accepted**, so a moment inside a longer file does not have to be
   trimmed by hand first.
3. **The run is flagged, with a reason in words** — not a boolean somebody has to interpret.
4. **Publish is never blocked.** The rights judgment on someone else's footage belongs to the
   person publishing the video.

An operator-directed clip is **never** `commercially_safe`, whatever licence string it
carries, and **never prints a licence** in the credit block. The app did not establish it;
printing "CC0" beside a file nobody checked would be the app vouching for a claim it never
made, and a credit block is exactly where such a claim would be believed.

Operator practice for reference clips (the operator's own convention, not enforced): muted,
around three seconds, under their own narration, with sound design covering the gap.

---

## 4. Modern film and TV — the honest position

Internet Archive reaches pre-1930 feature film and US television that lapsed through
copyright non-renewal. **It will not get you a scene from a series that aired last year.**
This was initially oversold and then corrected.

The legitimate routes to modern film/TV footage:

- **Movieclips** — Fandango-owned, studio-licensed, tens of thousands of *actual scenes*
  from modern films, uploaded deliberately as clips. This is the strongest source for "the
  bit where X happens" and it is fully licensed.
- **Studio press / EPK sites** — Netflix Media Center, WB Media Pass, Disney's press site.
  These publish stills and video for current titles, for exactly this kind of use.
- **Official studio channels** — scene clips and featurettes posted to promote back
  catalogue.

**A critical distinction that shaped the implementation:** a licensed *upload* is not a
licence to re-cut the film. A studio channel establishes *where to watch* a scene and
nothing more. So those sources are marked `licensed_distribution` / `studio_official` /
`press_kit`, and those strings are deliberately **absent** from the commercially-safe set.
The flag states what *is* established first, then says whose decision the rest is.

Related rule: **the CC filter is never asked about a named film.** A stranger's CC tick on a
studio re-upload is a mistake, not a licence, and honouring it would launder a rip through a
checkbox. That lane only runs when the request names no title.

---

## 5. The scene locator

Built to answer: "the scene where the truck flips in *The Dark Knight*" — find where it is
*legitimately* available and return a URL plus in/out timecode, which the existing fetch path
then uses.

Design notes worth carrying:

- It reuses the existing research / web-search / yt-dlp path. No new fetcher was built —
  a standing rule on this project.
- Channels are matched by **identity** (handle or channel id), not display name. An exact
  display-name match is consulted only when an entry carries no identity field at all, and
  such a result is caveated. Otherwise an impostor named exactly like a studio walks through
  the door built for a missing field.
- An undetermined window returns `None`, not `0.0`. An upload under ~15 minutes *is* the
  scene; longer, and the scene is inside it, in which case the uploader's chapter marks are
  the one recovery.
- Ranking is by **identification confidence, never by rights**. Someone asking where a scene
  is does not want a different scene for being better licensed.

---

## 6. Attribution

Credits are written beside the video and travel with it as an artifact — a credit file that
stays on one machine is the same failure one step later.

**Two sections, never flattened together:**

- **Footage credits** — what a licence *requires*
- **Operator-directed footage** — a record of a decision somebody made

In one list, the second reads as the first.

Found while building this: the app had been able to generate a stock-image credit block since
stock imagery was added, and **nothing had ever called it**. Every `by`-licensed photograph
had shipped without the credit its licence obliges. The code was there, the rule was written
in its own docstring, and the two were never connected.

---

## 7. How many pictures a scene buys

Adjacent to sourcing and worth carrying over. The app previously reframed **one** image four
times per scene. Right for a documentary; wrong for a reference showing six different
pictures in four seconds.

It now measures **content change across each cut** in the learned reference and drives
plates-per-scene from it. The measurement is *arriving colour*, not a palette diff: a crop of
one plate cannot show a colour the wider frame did not already hold, so a punch-in moves the
share numbers enormously while nothing new appears. A palette diff would score a reframe as
the largest change in the video.

It is weighed against a tenth of the frame rather than a share of it, because the
white-background explainer format shares its background across every shot — weigh the change
against the whole frame and that format reads as never cutting away, when in fact the cut-out
changes every time.

---

## 8. Open — the zero-cost path

The channel setup currently forces an image-to-video model choice, roughly $15–$98 per video.
The operator wants a **zero-cost route**, referred to as a "Forgecast Editor" tab.

The pieces already exist:

- keyless Openverse stills
- the licensed footage sources above
- local motion graphics and ffmpeg assembly, which cost nothing to run

What is missing is an option meaning **"no vendor — free sources only"**, so a run never
touches a paid endpoint. That is the honest shape of the feature, and it is real work rather
than a checkbox.

---

## Open items

- The zero-cost / free-sources-only mode (above)
- Storyblocks API
- `flat_background` and `background_colour` are measured and **read by nothing** — their
  real homes are plate prompting and the colour bed
- Learned `grade_filter`, `zoom_rate`, `caption_position` and `transition` reach the style
  and are **never applied at render**, so a learned look is discarded at the last step
