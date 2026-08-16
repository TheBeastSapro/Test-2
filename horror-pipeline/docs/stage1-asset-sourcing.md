# Stage 1: asset sourcing and the human approval gate — 2026-08-09

Implements BUILD-PACKET sections 3.1 to 3.5. Both tools were run for real against
the live Fandom API and CDN on 2026-08-09 and the numbers below are measured, not
projected. Companion documents: `cutout-evaluation-2026-08-09.md` (what happens to
an approved image next) and `upscale-evaluation-2026-08-09.md`.

**Why this stage exists.** Every canon failure in this channel's QC history traces
to one root cause: the materials sheet shipped without a locked per-creature image
shortlist, so the editor chose images himself. The wrong creature frozen for nine
seconds. Fan art contradicting the narration. An asset rotated 180 degrees so it
read as the opposite of the creature. Three mutually inconsistent designs in one
section. Every one of those is an image that would not have been in an approved
folder.

**Nothing renders until every image a sheet uses has `approved: true` and exactly
one image per creature carries `design_lock: true`.** The gate is not advisory.

---

## 1. The known-good command sequence

Run from `horror-pipeline/`. This is the exact sequence that was executed.

```bash
# 1. Find the wiki and the exact page title. Never skip this: resolve prints the
#    evidence and refuses to auto-pick, because resolution is a decision.
python3 tools/wiki_sources.py resolve "Trevor Henderson" --creature "Long Horse"

# 2. Enumerate, download, dedupe, write the shortlist. Hits the live API and CDN.
python3 tools/wiki_sources.py fetch trevorhenderson "Long Horse" long-horse \
        --project projects/demo

# 3. Fill in every description by LOOKING at each downloaded file. See section 4.

# 4. Open the approval gate. This is the mode that writes to disk.
python3 tools/contact_sheet.py serve projects/demo/materials/long-horse.json
#    -> http://127.0.0.1:8765/   tick, then click "Save to disk"

# 4b. Owner not on this machine? Emit a standalone page instead and have them
#     send the JSON back. Read-only, with a Download JSON fallback.
python3 tools/contact_sheet.py build projects/demo/materials/long-horse.json

# 5. Check the gate.
python3 tools/wiki_sources.py report projects/demo/materials/long-horse.json
```

### Measured output of step 1

```
resolving series='Trevor Henderson' creature='Long Horse'
  trevorhenderson                    Trevor Henderson Wiki
       - Long Horse
       - Long Horse/Gallery
       - Watchtower
       - The Needle
       - Cartoon Cat
```

Confirmed wiki `trevorhenderson`, sitename "Trevor Henderson Wiki", exact page
title `Long Horse`, gallery subpage `Long Horse/Gallery`.

### Measured output of step 2

```
32 filenames on Long Horse (+/Gallery)
27 kept, 5 dropped -> projects/demo/materials/long-horse.json
  dropped File:Darkest of Dreams .MP3: not an image (mime audio/mpeg)
  dropped File:My Savior.mp3: not an image (mime audio/mpeg)
  dropped File:Street HorSe.jpg: short side 270px < 400, wiki furniture
  dropped File:Screenshot 2020-04-24 ... .png: short side 337px < 400, wiki furniture
  dropped File:Longhorse june2026.png: short side 355px < 400, wiki furniture
```

Zero perceptual duplicates. The closest pair on this creature is at Hamming
distance 18 against a threshold of 6, so the dedupe was exercised and correctly
found nothing. Do not read that as the dedupe being unnecessary: the packet
records a Cartoon Cat gallery full of re-uploads.

### Measured output of step 5

```
long-horse  (trevorhenderson / Long Horse, fetched 2026-08-09)
  enumerated          32 (from 32 filenames on page)
  kept                27
  dropped             5
  described           27/27
  approved            0
  design-locked       0  NEEDS EXACTLY ONE
  under 900px         12  (may need upscaling or a bigger source)
  provenance          official-gallery 19, creator-account 6, fan-art 1, unknown 1
  cutout              10 cuttable, 17 plate-only, 0 unjudged
```

`approved 0` and `design-locked 0` are the correct state as delivered. Approval is
a canon decision and canon decisions are the owner's. Descriptions, provenance,
setting, time of day, design variant and cutout suitability are all filled in, so
the owner's pass is ticking boxes rather than researching. The three strongest
candidates carry a `RECOMMEND` line in their notes.

---

## 2. Bugs found and fixed in `wiki_sources.py`

The crawler had never been run. Five defects, all found by running it.

**1. Page order was silently replaced by the API's reply order.** `action=query`
with a pipe-joined `titles=` list does **not** return pages in the order you asked
for. Measured on this page: the request began `Screenshot_2020-04-26...`,
`Goodhorse.jpg`, `Darkest_of_Dreams_.MP3` and the reply began `Long Horse.jpg`,
`TheHorse.jpg`, `Goodhorse.jpg`. The `order` field was written from
`enumerate()` over the reply, so it recorded an arbitrary internal ordering while
still looking like a clean ascending sequence. Page order is a canon signal in
this pipeline (the packet: "the first images on a wiki page are almost always the
canon debut images"), so this was the most damaging of the five and the least
visible. Fixed by building a rank map from the enumerated filenames and
reattaching it by normalised title, then sorting. Title normalisation matters:
the API canonicalises `Long_Horse.jpg` to `File:Long Horse.jpg`.

**2. Non-image gallery members were downloaded in full and left as orphans.** The
Long Horse gallery embeds two MP3 files. Each was fetched (3.0 MB and 3.2 MB),
failed to decode, was recorded as dropped, and its `.bin` file was left sitting in
the image cache for every later tool to trip over. Fixed by skipping on the
reported mime before downloading, and by removing the file on every failure path
rather than only on the size and duplicate paths.

**3. Re-running `fetch` destroyed every human-entered field.** The tool rebuilt
`materials/<creature>.json` from scratch, so a second run wiped descriptions,
provenance, notes and approvals with no warning. This inverted the repo's own
stated priority, which is that the JSON is the durable artifact and the image
binaries are the rebuildable cache. Fixed: `fetch` now merges by wiki file title
and carries the human-owned fields forward, reporting how many it carried. If the
image's perceptual hash changed, the file was re-uploaded, so the human approved a
picture that no longer exists: the approval is **voided and reported** rather than
carried forward. `--refresh` restores the old destructive behaviour explicitly.

**4. `counts.enumerated` under-reported.** It recorded the number of imageinfo
results, so any filename the API declined to hydrate vanished from the accounting
entirely. Now records `filenames_on_page`, `enumerated`, `no_imageinfo`, `kept`
and `dropped` separately.

**5. `&format=original` was appended without checking for an existing query
string.** Fandom URLs always carry `?cb=`, so this never fired here, but a URL
without one would have been silently malformed. Now picks `?` or `&`.

`report` was also extended to print the provenance breakdown, the cutout split,
which images carry hard flags, and an explicit error if a hard-flagged image is
somehow approved.

---

## 3. The approval gate: `tools/contact_sheet.py`

Two modes. `serve` is the one you want.

| Mode | Writes to disk | Use when |
|---|---|---|
| `serve <materials.json>` | yes, via a POST to a loopback-only server | the owner is at this machine |
| `build <materials.json>` | no, offers "Download JSON" | the owner is elsewhere; the page is self-contained and survives being emailed |

A `file://` page cannot write to disk, which is the whole reason `serve` exists.
The server binds `127.0.0.1` only: it writes files, so it must never be reachable
off-machine.

### What each card shows

Three image panels in one row, aligned across every card so the page can be
scanned vertically:

| Panel | Content | Answers |
|---|---|---|
| 1 | source thumbnail | what the image is |
| 2 | the same frame gamma-lifted to 0.45 | what anatomy is actually there. On unlifted dark horror art the limbs are invisible on a normal monitor, which is the finding from the cutout evaluation |
| 3 | 1-bit silhouette preview | whether the shape is **findable**. Not whether it is correct |

The silhouette is model-free and instant: it thresholds distance from the frame's
dominant tone, so it behaves the same on a pale creature over a night sky and on a
dark creature over a light print. Per `cutout-evaluation-2026-08-09.md` section
8.2, the reviewer setting `cutout_suitable` is answering "is this shape findable",
and if the blob is a smear that includes the building the answer is no. An
`off-background ~N%` chip carries the same evaluation's proxy: under about 2
percent means no model will find an edge.

Then: the recorded description (editable, because the packet expects the owner to
correct them while ticking), `not_visible` one per line, setting, time of day,
design variant, provenance, cutout suitability and note, free notes, an `approved`
checkbox and a `design_lock` radio.

### The rules the page enforces

- **Design lock is a radio group**, one per creature, so two cannot be selected.
  Clicking the selected one clears it, otherwise there is no way back to zero.
  Zero selected is called out in red in the header banner. More than one in the
  file on load (only reachable by hand-editing) is reported and reduced to one
  server-side.
- **Design lock requires approval.** The radio is disabled until `approved` is
  ticked, and clearing `approved` clears the lock.
- **Hard flags block.** Ticking any of `licensed-character`,
  `real-identifiable-person`, `meme-photograph`, `identifiable-minor` forces the
  image unapproved and unlockable, turns the card red and stamps a `HARD FLAG`
  corner marker that is readable while scrolling. Enforced again server-side, so a
  crafted POST cannot approve a flagged image. The flag controls are visually
  quiet until set, deliberately: painting every card red would make red the
  page's resting state and the one genuinely flagged card would disappear.
- **Provenance is a label, never a rejection.** Fan art is tolerated per the
  owner's 21 Jul decision. The hard rule is that an image must never contradict
  the narration line it plays under, so `fan-art`, `game-model`,
  `wallpaper-scrape` and `unknown` are tinted amber to draw the eye and nothing
  more.
- **The page owns only the reviewer's fields.** `file`, `phash`, `source_url`,
  `size` and `meta` are machine-owned; a POST carrying them is ignored. The write
  is a merge into the file on disk, then an atomic replace, so a stale tab cannot
  truncate a record.

Header progress: images, described, approved, design lock, hard flagged, cutout
unjudged, plus a single banner that is either `BLOCKED: ...` with every reason
listed, or `GATE CLEAR`.

### Verified behaviour

Exercised against the running server on 2026-08-09:

- POST approving three images and locking one: written to disk, machine fields
  intact, descriptions intact.
- POST with `approved: true`, `design_lock: true` **and** a hard flag: both forced
  to false on disk.
- POST setting `design_lock` on three images: reduced to one on disk.
- POST attempting to overwrite `file`, `phash`, `source_url` and `size`: ignored,
  originals intact.

The state was restored to zero approvals afterwards, because the approvals are the
owner's to make.

---

## 4. The description pass, and why it is the safety mechanism

BUILD-PACKET 3.3: the `description` field is what the canon-contradiction
validator reads. Without it the validator has nothing to compare the narration
line against.

Every one of the 27 Long Horse descriptions was written after opening the actual
downloaded file, gamma-lifted where the source was too dark to read. None was
inferred from a filename. For Long Horse the canon points that had to be checked
per image are: a horse skull with **no lower jaw** (adding one is the single most
common fan-art mistake), an endless neck of vertebrae that always runs off-frame
with no visible end and no body, sparse black hair strands, and waxy skin.

`setting` and `time_of_day` are recorded on every image because canon-daylight
creatures must not be force-darkened later. Three images in this set are not
night: an overcast-sky painting, a multi-creature ensemble under a dull yellow
sky, and a stipple print on a light ground at mean luminance 0.75 that the house
darkening grade would destroy outright.

### What the pass found

Nine images carry a specific risk that is recorded in the description and repeated
in the notes:

| Image | Risk |
|---|---|
| `Meat horse.jpg` | **The only outright non-canon image.** Fleshed head, a living yellow eyeball in an intact socket, and a **lower jaw with teeth**. Contradicts three canon points at once. Sitting inside the official gallery, uploaded 2025 by an editor account. Marked `provenance: fan-art`, recommended reject. |
| `A Horse At Night High definition.jpg` | Four thin vertical columns read as **legs supporting a body**. Canon Long Horse has neither. Must not play under the no-body line. |
| `Allstars.jpg` | **Four different creatures in one frame**, only one of them Long Horse. This is precisely the failure that put the wrong creature on screen for nine seconds. |
| `Lh12.jpg` | **Two heads on screen at once.** Canon supports it, but it contradicts any line phrased as "the head at the end of the neck". |
| `LH1.jpg` | Eye drawn as a rendered **eyeball**, not the empty socket every other image shows. Do not cut between this and a photo composite inside one beat. |
| `Longhorse windmill.jpg` | Eye painted as a filled dark orb rather than a hollow socket. Same hazard, milder. |
| `LH4.jpg`, `Lh13.jpg`... | Baked-in text the OCR pass will read: a ten-bullet lore card, `HEllO!`, `Hey. Keep it up. You're doing. Great.`, `LONG HORSE` on a print border, `HAPPY HALLOWEEN FROM SLIMYSWAMPGHOST!` |
| `Longhorse blurry.png` | 567x428, no anatomy visible at all. Cannot support any narration line about the creature's shape. `provenance: unknown`. |

`LH4.jpg` is worth calling out separately: it is the creature's hand-lettered
**canon lore card** and its ten bullets are the text the script should be
validated against. Transcribed in full in the record. Among them: "skin is like
wax, pliable", "Its neck is infinite for all observing it", "Neck will always
terminate out of view of observers", "Non-hostile, though its appearance often
precedes disasters of misfortune".

No image in this set falls into any of the four blocking categories. `hard_flags`
is written as an explicit empty list on all 27 so that empty means "checked, none
found" rather than "never looked".

---

## 5. Gitignore contract

Already in `.gitignore` and worth restating, because it is easy to get backwards:

- `horror-pipeline/projects/*/materials/*/` — **ignored.** The image binaries are
  a rebuildable cache keyed off the `source_url` recorded in the JSON. One video
  is roughly 200 MB.
- `!horror-pipeline/projects/*/materials/*.json` — **committed.** The approval
  record is the durable artifact. Every source URL, phash, description, provenance
  label and approval flag lives here, and re-running `fetch` rebuilds the binaries
  from it without touching the human fields.
- `materials/contact-sheet.html` — **ignored.** It is 1.3 MB of inlined base64
  regenerated from the JSON by one command.

---

## 6. What is still open

- The owner's approval pass on `long-horse.json`: tick, set one design lock, save.
- The other six creatures in the Trevor roster. The sequence is identical; only
  the page title and the slug change. Gallery subpages for the whole wiki come
  from one call, `list=categorymembers&cmtitle=Category:Galleries`.
- The creator's own accounts (`@slimyswampghost`) are not API-accessible in any
  stable way and remain a manual drop folder entering the same approval flow with
  `provenance: creator-account`. Six images in this set already carry that label
  because their filenames are Instagram and Twitter CDN IDs.
- Wiring the approved shortlist into the sheet validator so an unapproved image
  hard-fails the build, which is the half of the gate that lives in Stage 3.
