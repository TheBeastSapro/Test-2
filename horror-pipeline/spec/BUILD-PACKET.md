# Claude Code Build Packet: Script + VO + Approved Images to Finished Video

**Version 1.0. Written against the working engines in `hp/engine` (Python + ffmpeg) and `hp/remotion` (Remotion v4.0.507), and against the channel's measured QC history.**

Read this end to end once. Then use section 10, "THE PROMPT", to start.

---

## 1. What Claude Code is being asked to do

Claude Code is being asked to act as the editor. You hand it a title, a finished script, a recorded voiceover, and a folder of images you have approved. It reads the script, lines the script up against the voiceover word by word, decides every cut, every keyword pop, every icon, every sound effect and every camera move, writes that decision list to a file, renders the video, measures the render with a script that grades the same numbers a human QC pass grades, and then edits its own decision list and re-renders until the numbers clear the bar. When it cannot fix something itself, it tells you exactly what it needs from you.

This is not a "make me a video" prompt. It is a build pipeline with a measurement loop bolted to the end of it. The measurement loop is the reason it works at all: without it, the model writes a plausible-looking edit and you have no idea whether the pacing is dead or the pops vanished in the last two minutes. With it, the model gets told "motion 12.1 percent, fail" and goes back and fixes it.

**Exact inputs it receives:**

| Input | Form | Notes |
|---|---|---|
| Title | one line of text | e.g. "Every Trevor Henderson Monster You Cannot Survive" |
| Script | one markdown file | sectioned, one creature per section, in running order |
| Voiceover | one audio file, wav or mp3 | the full narration for the whole video, one file |
| Approved images | one folder per creature | plus a `sources.json` recording where every file came from |
| Music bed and SFX | folders | dark ambient bed, plus the SFX kit |
| Fonts | folder | the house faces, checked in, never fetched at render time |

**Exact artifact it produces:**

A single H.264 MP4, 1920x1080, 30 fps, with a mixed and mastered stereo AAC track, plus a QC report text file with the measured numbers, plus contact sheets you can flick through in ten seconds. That is the deliverable. Everything else in the repo is intermediate.

**What it explicitly does not do:** it does not choose which images are canon, it does not write the script, it does not record voiceover, and it does not publish. Those are yours. See section 9.

---

## 2. Repo layout

Create this on your machine. One line each on what the file is for.

```
horror-engine/
  CLAUDE.md                       house rules the model re-reads every session (section 10)
  .claude/commands/               slash commands (section 10)
  README.md                       how to run it, for you, not for the model

  projects/
    <video-slug>/
      title.txt                   the video title
      script.md                   the approved script, sectioned
      vo.wav                      the full recorded voiceover
      materials/
        <creature>.json           the approved image shortlist + source URLs + descriptions
        <creature>/               the actual downloaded image files
        contact-sheet.html        the tick-off page you approve before any render
      work/
        words.json                word-level VO timings from Whisper
        sections.json             script parsed into sections with VO time ranges
        rms.json                  RMS per 0.5s, used to sanity-check Whisper gaps
      sheets/
        <section>.sheet.json      the edit sheet: the model's actual creative output
      audio/
        mix.wav                   final mastered mix
      out/
        <video-slug>.mp4          the deliverable
        qc.txt                    the QC report
        qc/                       frames, contact sheets, OCR dumps

  tools/
    wiki_sources.py               MediaWiki API crawler, dedupe, shortlist writer
    contact_sheet.py              builds materials/contact-sheet.html for approval
    transcribe.py                 faster-whisper word timings -> words.json
    rms.py                        RMS per 0.5s -> rms.json, the Whisper-gap check
    anchors.py                    resolves "the word THIRTY, 2nd occurrence" -> seconds
    parse_script.py               script.md -> sections.json
    validate_sheet.py             build-time rules check, runs BEFORE any render
    mix_audio.py                  bed + duck + SFX + two-pass linear loudnorm
    qc.py                         the measurement pass (port of hp/engine/qc.py)
    fix_from_qc.py                helper: turns a QC report into a task list

  remotion/                       PRIMARY renderer
    package.json
    remotion.config.ts            codec, bitrate, GL renderer, image format
    src/
      index.ts, Root.tsx          composition registration
      style.ts                    the house style as constants, single source of truth
      sheet.ts                    types + loader for sheets/<section>.sheet.json
      fonts.ts                    local font loading with delayRender
      Section.tsx                 one creature section, top-level composition
      components/
        ImageBox.tsx              boxed centred image + Ken Burns (transform only)
        TitleBar.tsx              persistent ALL CAPS creature name, top centre
        Pop.tsx                   keyword pops, band and on-image variants
        Icons.tsx                 stick figure, red X, arrow, warning, clock
        Gag.tsx                   the timed dry-joke visual, horror register only
        CreatureCard.tsx          section opener punch-in
        Glitch.tsx                RGB split + scanline burst
        Roster.tsx                the 8-card grid for intro and outro
    public/
      images/                     symlink or copy of the approved images
      fonts/                      the house faces
      audio/mix.wav               the mastered mix

  engine/                         FALLBACK renderer (the Python + ffmpeg v1)
    style.py, plates.py, render.py, build.py, sheets/
```

### Why Remotion is primary and ffmpeg is the fallback

Both engines exist and both produce a finished file. Use Remotion.

**Remotion wins on the things this channel is graded on.** Motion is rule number one here, and Remotion gives you real spring physics, SVG stroke-drawing for icons, CSS filters for the glitch bursts, and text stroke and letter-spacing that behave like a design tool rather than like a plotting library. The v1 Python renderer draws every frame by hand in Pillow, which means every new visual idea is fifty lines of arithmetic. In Remotion it is a div. The model writes better edits when the vocabulary is bigger.

Second, Remotion has a studio. `npm run studio` gives you a scrubbable timeline in a browser. You can look at 4:12, see the pop is wrong, and say so, without waiting for a render.

Third, and this is measurable: the v1 ffmpeg path encodes with `-crf 17` and lands at **1.89 Mbps** on this content, because a white canvas with a dark grainy plate in the middle is cheap for x264 to encode. The channel's QC bar wants well over 4 Mbps and treats 10 Mbps as the good benchmark. The Remotion config sets an explicit **14M** bitrate and the actual measured output is **14.15 Mbps**. Same pictures, seven times the data rate, and only one of those two files passes QC. You can of course fix the ffmpeg path by swapping CRF for ABR, and you should, but the point stands: the Remotion config already has this right.

**Keep the ffmpeg engine anyway.** Three reasons. It has no Chrome dependency, so it renders on a locked-down box or a cheap VPS where headless Chrome will not start. It is roughly an order of magnitude simpler to debug when something is wrong with the *sheet* rather than the *renderer*, because you can print the frame at t=41.3 in three lines of Python. And it is the reference implementation: `engine/style.py` is the canonical statement of the house style, and `remotion/src/style.ts` is a port of it. If the two ever disagree, the Python one is right and the port is wrong.

---

## 3. Stage 1: Asset sourcing

**This stage must run on your machine, not in a sandbox.** It needs to reach `fandom.com` and `static.wikia.nocookie.net` and download a few hundred image files. Every canon failure in this channel's QC history traces back to the same root cause, written down in the QC workflow doc in these words: the materials sheet shipped without a locked per-creature image shortlist, so the editor chose images himself. Fixing that one thing fixes the whole class of problem. So this stage runs first, it runs to completion, and nothing renders until you have ticked the shortlist off.

### 3.1 The API you are calling

Every Fandom wiki exposes a standard MediaWiki API at `https://<wiki>.fandom.com/api.php`. No key, no login, no scraping. The following calls were run live against `trevorhenderson.fandom.com` while writing this document, and the responses quoted are real.

**Call A: list the images used on a creature's page, in page order.**

```
https://trevorhenderson.fandom.com/api.php?action=parse&page=Cartoon%20Cat&prop=images&format=json&formatversion=2
```

Returns `{"parse":{"title":"Cartoon Cat","pageid":39971,"images":["Cartoonfeline.jpg"]}}`. Note what that tells you: the main article for Cartoon Cat only embeds one image. Page order matters because the first images on a wiki page are almost always the canon debut images, and the ones further down are variants.

**Call B: the gallery subpage, which is where the real haul is.**

Most creature articles on these wikis have a `/Gallery` subpage. That is the one you want.

```
https://trevorhenderson.fandom.com/api.php?action=parse&page=Cartoon%20Cat/Gallery&prop=images&format=json&formatversion=2
```

This returns 26 filenames, in the order they appear on the gallery page, starting `Cartoon-cat.jpeg`, `Tumblr_pdhiahSOFL1qktbieo1_1280.jpg`, `Cartoon_cat_1.jpeg`, `Heiscoming.jpg`, and so on.

**Call C: find out which creatures even have gallery subpages.**

```
https://trevorhenderson.fandom.com/api.php?action=query&list=categorymembers&cmtitle=Category:Galleries&cmlimit=500&cmtype=page&format=json&formatversion=2
```

Real response includes `Cartoon Cat/Gallery`, `Long Horse/Gallery`, `Siren Head/Gallery`, `The Good Boy/Gallery`, `Lil' Nugget/Gallery`. That single call gives you the map of the whole wiki before you touch anything else.

**Call D: turn filenames into real URLs plus metadata.** This is the generator form, and it is the one that does the actual work.

```
https://trevorhenderson.fandom.com/api.php?action=query&titles=Cartoon%20Cat&generator=images&gimlimit=500&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=400&format=json&formatversion=2
```

Real fields returned per image:

```
url        https://static.wikia.nocookie.net/trevor-henderson-inspiration/images/9/96/Heiscoming.jpg/revision/latest?cb=20200806142613
thumburl   .../Heiscoming.jpg/revision/latest/scale-to-width-down/400?cb=20200806142613
width      1536      height 2048      mime image/jpeg
extmetadata  {DateTime, ObjectName}
```

Three practical notes on that response, all verified.

1. The `url` already points at the full-resolution original. Do not strip the `?cb=` cache-buster, it is part of the URL.
2. `iiurlwidth=400` gives you a `thumburl` for free. Use those for the contact sheet so the approval page loads instantly and you only pull full-resolution files for the images you actually tick.
3. **Fandom populates `extmetadata` very thinly.** On this wiki you get `DateTime` and `ObjectName` and nothing else. There is no `LicenseShortName`, no `Artist`. Wikimedia Commons fills those in; Fandom generally does not. So do not build a licence gate that depends on a field that will always be empty. Record what you get, record the file page URL, and treat "it is in the creature's official wiki gallery" as the provenance claim, because that is exactly what the channel's rule says.

The other canon source in the brief is the creator's own accounts, for example `@slimyswampghost` for Trevor Henderson. Those are not API-accessible in any stable way. Handle them as a manual drop folder: you save the images, the script records them with `"source": "creator-account"` and the URL you took them from, and they enter the same approval flow.

### 3.2 The crawler, in sketch

`tools/wiki_sources.py`. Short, runnable, no cleverness.

```python
#!/usr/bin/env python3
"""Enumerate a creature's wiki gallery, download, dedupe, write a shortlist."""
import hashlib, json, os, sys, time
import requests
from PIL import Image
import imagehash                       # pip install imagehash

UA = {"User-Agent": "horror-engine/1.0 (channel asset sourcing; contact: you@example.com)"}

def api(wiki, **params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", 2)
    r = requests.get(f"https://{wiki}.fandom.com/api.php",
                     params=params, headers=UA, timeout=30)
    r.raise_for_status()
    time.sleep(0.4)                    # be polite, this is a free API
    return r.json()

def gallery_filenames(wiki, page):
    """Page-order filenames from the article and its /Gallery subpage."""
    names = []
    for p in (page, f"{page}/Gallery"):
        try:
            names += api(wiki, action="parse", page=p, prop="images")["parse"]["images"]
        except Exception:
            pass                       # no gallery subpage is normal
    seen, ordered = set(), []
    for n in names:                    # preserve order, drop repeats
        if n not in seen:
            seen.add(n); ordered.append(n)
    return ordered

def imageinfo(wiki, filenames):
    """Batch imageinfo, 50 titles at a time (MediaWiki's anonymous limit)."""
    out = []
    for i in range(0, len(filenames), 50):
        titles = "|".join("File:" + f for f in filenames[i:i + 50])
        d = api(wiki, action="query", titles=titles, prop="imageinfo",
                iiprop="url|size|mime|extmetadata", iiurlwidth=400)
        for pg in d.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            out.append({"title": pg["title"], "url": ii["url"],
                        "thumb": ii.get("thumburl"), "w": ii.get("width"),
                        "h": ii.get("height"), "mime": ii.get("mime"),
                        "page": ii.get("descriptionurl"),
                        "meta": {k: v.get("value") for k, v in
                                 (ii.get("extmetadata") or {}).items()}})
    return out

def download(rec, outdir):
    os.makedirs(outdir, exist_ok=True)
    ext = os.path.splitext(rec["title"])[1].lower() or ".jpg"
    fn = os.path.join(outdir, hashlib.sha1(rec["url"].encode()).hexdigest()[:12] + ext)
    if not os.path.exists(fn):
        r = requests.get(rec["url"], headers=UA, timeout=60)
        r.raise_for_status()
        open(fn, "wb").write(r.content)
    return fn

def main(wiki, page, creature, root):
    imgs = imageinfo(wiki, gallery_filenames(wiki, page))
    kept, seen_hashes = [], {}
    for order, rec in enumerate(imgs):
        try:
            fn = download(rec, f"{root}/materials/{creature}")
            im = Image.open(fn).convert("RGB")
        except Exception as e:
            print("skip", rec["title"], e); continue
        if min(im.size) < 400:                       # thumbnails and wiki chrome
            os.remove(fn); continue
        ph = str(imagehash.phash(im))                # perceptual, catches re-uploads
        if ph in seen_hashes:
            os.remove(fn); continue
        seen_hashes[ph] = fn
        kept.append({"order": order, "file": fn, "phash": ph,
                     "source_url": rec["url"], "wiki_page": rec["page"],
                     "size": list(im.size), "mime": rec["mime"],
                     "meta": rec["meta"],
                     "description": "",              # YOU or the model fills this in
                     "approved": False})
    os.makedirs(f"{root}/materials", exist_ok=True)
    path = f"{root}/materials/{creature}.json"
    json.dump({"creature": creature, "wiki": wiki, "page": page,
               "fetched": time.strftime("%Y-%m-%d"), "images": kept},
              open(path, "w"), indent=2)
    print(f"{len(kept)} images -> {path}")

if __name__ == "__main__":
    main(*sys.argv[1:])   # wiki page creature project_root
```

Run it like this:

```bash
python3 tools/wiki_sources.py trevorhenderson "Cartoon Cat" cartoon-cat projects/trevor-cannot-survive
```

### 3.3 The `description` field is the safety mechanism

Every record has a `description`. It is a plain sentence saying what is actually visible in that image. "Black cat figure peering around a doorway in an abandoned mall, night, no full body visible." "Skull, no lower jaw, side view." Claude Code fills these in by looking at each downloaded image, and you correct the ones it gets wrong while you are ticking the contact sheet anyway.

That field is what the canon-contradiction validator in section 5 reads. Without it, the validator has nothing to compare the narration line against, and you are back to hoping.

### 3.4 The dedupe

Perceptual hashing, not file hashing. Wiki galleries are full of the same picture uploaded twice at different JPEG qualities, and a byte hash will not catch that. `imagehash.phash` will. Also drop anything under 400 px on its short side: that is wiki interface furniture, badges and thumbnails, not artwork.

### 3.5 The human approval gate

`tools/contact_sheet.py` writes `materials/contact-sheet.html`: a plain page, one card per image, thumbnail, the file page link, the description, and a checkbox. You open it in a browser, tick what is canon, untick what is not, click Save, and it writes the `approved` flags back into `materials/<creature>.json`.

A single detail from the live test makes the case for this gate better than any argument. The Cartoon Cat gallery's 26 files include `Wp7577260-cartoon-cat-scary-wallpapers.jpg`. That is a fan wallpaper site scrape sitting in the official wiki gallery. It looks completely legitimate in a JSON list. It takes you about one second to reject it on sight in a contact sheet.

**Nothing renders until every image used by a sheet has `"approved": true`.** The sheet validator in section 5 hard-fails on an unapproved image, and the render script refuses to start if the validator failed. That is the whole point of the gate: it is not advisory.

This one step would have prevented every canon failure in this channel's QC history. Not most of them. Every one. The wrong-creature frozen for nine seconds, the Bridge Worm fan art that contradicted the narration, the Upside-Down Face rotated 180 degrees so it read as the opposite of the creature, the three mutually inconsistent Horned Serpent designs in one section, the full-body Horned Serpent shown under the line "no one has ever seen the whole thing". Every one of those is an image that would not have been in an approved folder.

---

## 4. Stage 2: Script and voiceover ingestion

The goal of this stage is one file, `work/words.json`, that says exactly when every spoken word happens. Everything downstream hangs off it.

### 4.1 Parsing the script

`tools/parse_script.py` splits `script.md` on its section headings into an ordered list of sections, each with a creature name, the narration text, and any lines the script marks as dry jokes or as CTA beats. Output is `work/sections.json`:

```json
[
  {"index": 1, "creature": "Cartoon Cat", "title": "Cartoon Cat",
   "text": "On August 4th 2018, a photograph appeared ...",
   "joke_lines": [12], "cta": false},
  {"index": 2, "creature": "Sewer Spider", "title": "The Sewer Spider", "...": "..."}
]
```

Keep the raw line numbers. The joke lines have to be findable later so the gag lands on the right beat and not two sentences early.

### 4.2 Word timings

`faster-whisper` is already installed and proven on this machine (version 1.2.1). WhisperX gives slightly better alignment because it runs a forced-alignment pass afterwards, but it drags in more dependencies. Start with faster-whisper. Move to WhisperX only if the anchors keep landing late.

`tools/transcribe.py`:

```python
#!/usr/bin/env python3
import json, sys
from faster_whisper import WhisperModel

audio, out = sys.argv[1], sys.argv[2]
model = WhisperModel("base.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    audio,
    word_timestamps=True,          # this is the whole reason we are here
    condition_on_previous_text=False,   # stops the repeated-line hallucination
    vad_filter=True,
    beam_size=5,
)
words = []
for seg in segments:
    for w in (seg.words or []):
        words.append({"w": w.word.strip(), "s": round(w.start, 3),
                      "e": round(w.end, 3), "p": round(w.probability, 3)})
json.dump(words, open(out, "w"), indent=1)
print(f"{len(words)} words, {words[-1]['e']:.1f}s")
```

The output format matches the one already in use in this repo, a flat list of `{"w", "s", "e"}`:

```json
[{"w":"The","s":0.0,"e":0.42},{"w":"Sewer","s":0.42,"e":0.7},{"w":"Spider.","s":0.7,"e":0.98}]
```

Transcribe the **raw voiceover**, before any music is added. Always. If you only have a mixed file, see the failure modes below, because they get much worse.

### 4.3 Two failure modes you will hit, and the check that resolves both

These are real, they both happened on this channel's material, and they will both cost you an hour if you do not know about them.

**Failure mode one: Whisper hallucinates repeated lines over a dense music bed.** On the 2026-08-03 QC pass, transcribing a mixed track produced the phrase "ever seen the whole thing" five times and "One reality" four times. None of those repeats were in the voiceover. If you had built an anchor resolver off that transcript, your pops would have landed on phantom words.

The mitigations, in order: transcribe the dry voiceover, not the mix; set `condition_on_previous_text=False`, which is what makes Whisper stop feeding its own output back into the prompt and looping; and re-transcribe any suspect window with `small.en` before you believe it.

**Failure mode two: Whisper silently drops words under music.** The same pass lost roughly 15 percent of the transcript. A dropped stretch looks exactly like a gap in the voiceover, and the natural conclusion, "the narrator never said the mid-roll CTA", is a serious conclusion to get wrong.

**The check that settles it: RMS per 0.5 seconds.** Before acting on any suspected gap, measure the actual energy in the voiceover over that window. If the RMS is flat and normal through the "gap", the voiceover is there and the transcript dropped it. If the RMS genuinely floors out, the gap is real.

`tools/rms.py`:

```python
#!/usr/bin/env python3
"""RMS per 0.5s. The arbiter for 'is this a real VO gap or a Whisper drop?'"""
import json, subprocess, sys
import numpy as np

src, out = sys.argv[1], sys.argv[2]
raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", src,
                      "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
hop = 24000                                    # 0.5 s at 48 kHz
n = len(x) // hop
env = np.sqrt(np.maximum((x[:n * hop].reshape(n, hop) ** 2).mean(1), 1e-12))
db = 20 * np.log10(env)
json.dump([{"t": round(i * 0.5, 2), "db": round(float(v), 2)}
           for i, v in enumerate(db)], open(out, "w"))
quiet = [round(i * 0.5, 1) for i, v in enumerate(db) if v < -50]
print(f"{n} windows; below -50 dBFS at: {quiet[:40]}")
```

Note the two `-nostdin -v error` flags on every ffmpeg call in this packet. Without them ffmpeg floods the session with hundreds of progress lines and Claude Code burns its context on `frame= 1042 fps=31 speed=1.04x`.

### 4.4 The anchor resolver

Here is the thing that makes the edit sheets survive a voiceover re-record.

Do not write `"t0": 25.95` in a sheet. Write "put this pop on the word THIRTY, second occurrence, offset -0.05 seconds". Then resolve it to a number at build time. If you re-record the voiceover and every timing in the video shifts by 1.4 seconds, you re-run the transcription and rebuild, and the whole edit re-syncs itself. If you had hardcoded seconds, you would be redoing the section by hand.

`tools/anchors.py`:

```python
#!/usr/bin/env python3
"""Resolve word anchors to seconds against work/words.json."""
import json, re

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

class Anchors:
    def __init__(self, words_path):
        self.words = json.load(open(words_path))
        self.norm = [norm(w["w"]) for w in self.words]

    def find(self, phrase, occurrence=1, section=None):
        """phrase may be one word or several. Returns (start, end) seconds."""
        target = [norm(p) for p in phrase.split() if norm(p)]
        lo, hi = (section or (0, 10 ** 9))
        hits = []
        for i in range(len(self.norm) - len(target) + 1):
            if self.norm[i:i + len(target)] != target:
                continue
            s, e = self.words[i]["s"], self.words[i + len(target) - 1]["e"]
            if lo <= s <= hi:
                hits.append((s, e))
        if len(hits) < occurrence:
            raise LookupError(
                f"anchor {phrase!r} occurrence {occurrence} not found "
                f"in {lo:.1f}-{hi:.1f}s (found {len(hits)})")
        return hits[occurrence - 1]

    def at(self, phrase, occurrence=1, offset=0.0, section=None):
        s, _ = self.find(phrase, occurrence, section)
        return round(s + offset, 3)
```

So a pop in a sheet reads:

```json
{"text": "THIRTY FEET", "anchor": {"phrase": "thirty", "occurrence": 2, "offset": -0.05},
 "dur": 2.0, "where": "on", "accent": true, "size": 92}
```

and the build step turns that into `t0` and `t1`.

**Restrict every anchor search to its own section's time range.** The word "thirty" will appear in four different creature sections. Passing `section=(sec.start, sec.end)` is what stops a pop for creature 6 from resolving into creature 2.

**When an anchor is not found, fail loudly and stop.** Do not fall back to a guessed time. A `LookupError` here almost always means the model invented a phrase the narrator never said, which is exactly the kind of thing you want to catch at build time rather than at 4:12 in the finished render.

---

## 5. Stage 3: Edit sheet generation

This is where the model does the creative work. Everything before it is plumbing and everything after it is machinery. The sheet is the edit.

One sheet per creature section, at `sheets/<section>.sheet.json`. One typed object. The renderer reads it and does what it says.

### 5.1 The schema

TypeScript, because the Remotion side imports these types directly and the compiler then catches a malformed sheet before it ever runs.

```ts
// remotion/src/sheet.ts
export type KB = 'in' | 'out' | 'pan';

/** An anchor is a spoken word or short phrase, not a timestamp. */
export type Anchor = {phrase: string; occurrence?: number; offset?: number};

export type Shot = {
  slot: number;             // 1-based index within the section
  t0: number;               // resolved seconds, absolute in the video
  t1: number;
  image: string;            // path relative to materials/, must be approved
  kb: KB;                   // Ken Burns direction. NEVER omitted, never 'none'
  kbFrom?: [number, number];// optional explicit start focal point, 0..1
  kbTo?: [number, number];  // optional explicit end focal point
  vo: string;               // the narration line playing over this shot
  why: string;              // one line: why this image for this line
  fullBleed?: boolean;      // deliberate cinematic push-in. Rare. Default false
};

export type Pop = {
  text: string;             // 1 to 4 words. NEVER a sentence
  anchor: Anchor;
  dur: number;              // seconds on screen, 1.6 to 2.4 typical
  where: 'band' | 'on';     // below the box on white, or inside the box
  accent: boolean;          // true = the red, use it for canon numbers
  size: number;
  kind: 'date' | 'number' | 'name' | 'place' | 'canon' | 'beat';
};

export type IconKind = 'redx' | 'person' | 'arrow' | 'warn' | 'clock';
export type Icon = {kind: IconKind; anchor: Anchor; dur: number;
                    x: number; y: number; size: number; meaning: string};

export type Gag = {
  anchor: Anchor; dur: number;
  visual: 'icon-joke' | 'text-card' | 'zoom-punch' | 'freeze-label';
  payload: string;          // e.g. "redx over stick figure, label DO NOT RUN"
  scriptLine: number;       // which script line this is the gag FOR
  register: 'horror';       // literal constant. There is no other legal value
};

export type Sfx = {file: string; anchor: Anchor; offset?: number; gain: number};
export type Burst = {anchor: Anchor; dur: number; amp: number};

export type Sheet = {
  section: number;
  creature: string;
  title: string;            // the persistent top-centre title, ALL CAPS at render
  t0: number; t1: number;   // section bounds in the full video timeline
  card?: {t0: number; t1: number; image: string};
  shots: Shot[];
  pops: Pop[];
  icons: Icon[];
  gags: Gag[];
  sfx: Sfx[];
  shakes: Burst[];
  glitches: Burst[];
};
```

Two fields exist purely to make the model think, and they are not decoration.

`Shot.why` forces a one-line justification for pairing this image with this narration line. It is what the canon validator reads back and it is what you skim when you review.

`Gag.register` is a constant with exactly one legal value, `'horror'`. It exists because an editor was failed for putting a Minion, a real-person meme photo, a cartoon chicken, and a pig with a laser pointer as the final frame of a horror video. Making the field exist and have one value means the model has to type the word "horror" every single time it writes a joke, which is a small but real friction against reaching for whatever is funny instead of whatever is in tone.

### 5.2 What the model is actually deciding

Per section, working from the section text, the word timings, and the approved image list:

- **Shots.** Which approved image is on screen for which narration line, and which way the camera moves. Between 2 and 4 seconds each. Longest legal shot is 8 seconds and you should almost never be near it.
- **Ken Burns direction per shot.** `in` for a reveal or a threat approaching, `out` for scale and context, `pan` for something long or something you are travelling along. Never the same direction three shots running, that reads as a slideshow with a wobble.
- **Pops.** The punch words. Dates, locations, canon numbers, names, the one-word verdicts. Anchored to the spoken word.
- **Icons.** Where the stick figure, the red X, the arrow, the clock, the warning triangle add meaning. A red X over a silhouette for death or absence. An arrow to direct the eye at the thing in the plate you want looked at.
- **Gags.** One or two per section, on the lines the script marked as dry jokes, in the horror register.
- **SFX.** A sound on every cut and every reveal. "A cut without a sound is a wasted cut."
- **Shakes and glitches.** On impacts and reveals only. These are seasoning, not a texture.

### 5.3 The build-time validator

`tools/validate_sheet.py`. Runs before any render. Exits non-zero on any ERROR and the render command refuses to start. This is a port of the checks already in `engine/build.py`, extended.

| # | Check | Rule | Level |
|---|---|---|---|
| 1 | Shot length | no shot longer than 8.0 s | ERROR |
| 2 | Shot length, house | warn above 6.5 s | WARN |
| 3 | Timeline continuity | no gaps or overlaps between consecutive shots | ERROR |
| 4 | Event density | merge shot starts, pop-ins, icon-ins and gags into one change track; no gap above 4.5 s | WARN |
| 5 | Event density, hard | no gap above 8.0 s in the change track | ERROR |
| 6 | Ken Burns present | every shot has a `kb` value; `none` is not a legal value | ERROR |
| 7 | Ken Burns variety | not more than 2 consecutive shots with the same direction | WARN |
| 8 | Image approved | every `shot.image` resolves to a record with `approved: true` | ERROR |
| 9 | Image reuse | the same image used in more than 2 shots in one section | WARN |
| 10 | Pop density | pops per section at or above the floor | ERROR |
| 11 | **Pop taper** | last section's pop count at or above 0.8 x the median of all sections | ERROR |
| 12 | Pop quality | at least half of a section's pops are `kind` date, number, name, place or canon, not `beat` | WARN |
| 13 | Pop length | no pop longer than 4 words or 28 characters | ERROR |
| 14 | Palette | every colour in the sheet is in {white, black, red accent} | ERROR |
| 15 | Title present | `title` non-empty, uppercases cleanly, article "The" consistent across sections | ERROR |
| 16 | Gag register | every gag has `register: 'horror'` and a `scriptLine` that is a marked joke line | ERROR |
| 17 | SFX coverage | at least 70 percent of cuts have an SFX within 0.6 s | WARN |
| 18 | Anchor resolution | every anchor resolves, inside its own section's range | ERROR |
| 19 | **Canon contradiction** | see below | ERROR |
| 20 | Final 5 seconds | the last shot of the video is a creature beauty shot or the roster, and is not a gag | ERROR |

**Check 11, the taper check, in words:** count pops in each section, take the median, and require the *last* section to be at least 80 percent of it. An editor was failed on this exact thing: dense pops through creature 5, two filler pops in 84 seconds by creature 7, zero editor-added pops in the 87-second finale. A plain per-section floor does not catch it because a floor of 2 lets a lazy finale through. Comparing the finale to the median does.

**Check 19, the canon contradiction check.** For every shot, take `shot.vo` (the narration line) and the recorded `description` of `shot.image`, and diff them for direct contradictions. This is a small, deliberately dumb rule table plus a model judgement call:

```python
CONTRADICTIONS = [
    # (phrase in the VO line, thing that must NOT be in the image description)
    (r"no lower jaw|jawless",         r"\bjaw\b(?!less)|full skull|mandible"),
    (r"never been seen|no one has ever seen the whole",
                                      r"full body|whole creature|entire"),
    (r"body (is )?(never|not) seen|only the legs",
                                      r"full body|abdomen visible|whole"),
    (r"in the background|never a foreground",
                                      r"foreground|close-up portrait"),
    (r"no face|faceless",             r"\bface\b|eyes visible"),
]
```

Run those regexes, and then have the model read every shot's `vo` plus `why` plus `description` triple and flag anything the table missed. The table catches the ones you have already been burned by. The model catches the new ones. Both write ERRORs.

This check is the automated version of the single hardest rule in the brief: the image on screen must never contradict the narration. It only works because stage 1 recorded a description for every approved image. That is why stage 1 comes first.

---

## 6. Stage 4: Render

Remotion renders the picture. Audio is muxed in separately after stage 5, because mastering audio inside a browser is a bad idea and because a separate mix file lets you fix the audio without re-rendering 18,000 frames.

### 6.1 Getting a browser

Remotion drives headless Chrome. Do this once per machine, before anything else:

```bash
npx remotion browser ensure
```

That downloads a matched Chrome Headless Shell into Remotion's cache. If you skip it, Remotion will try to find a system Chrome, and on a fresh Linux box it will fail with a message about not finding a browser executable. On a machine with no GPU, also set the software GL renderer, which is already in the config here:

```ts
// remotion.config.ts
Config.setChromiumOpenGlRenderer('swangle');
```

`swangle` is ANGLE over SwiftShader, software rasterisation. On a headless box without it you get either a crash or, worse, silently blank frames where the CSS filters used by the glitch component should be.

### 6.2 The config that matters

This is the working `remotion.config.ts` from this repo, with what each line is actually buying you:

```ts
import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('png');   // JPEG frames would chroma-subsample the red twice
Config.setCodec('h264');
Config.setVideoBitrate('14M');       // explicit ABR. See below. This is the important one
Config.setPixelFormat('yuv420p');    // required for the file to play everywhere
Config.setX264Preset('slow');
Config.setOverwriteOutput(true);
Config.setConcurrency(2);            // raise on a big machine, it is frames in parallel
Config.setChromiumOpenGlRenderer('swangle');
Config.setChromiumDisableWebSecurity(true);  // lets local file:// images load
```

### 6.3 The bitrate lesson, with numbers

This content is a mostly flat white canvas with one dark image box in the middle. x264 finds that extremely cheap to encode. Quality-based encoding, `-crf 17`, looks at the picture, decides it is easy, and spends almost nothing.

Measured on this repo, same 62.6-second section, same pictures:

| Path | Setting | Measured video bitrate |
|---|---|---|
| Python + ffmpeg v1 | `-crf 17` | **1.89 Mbps** |
| Remotion v2 | `--video-bitrate=14M` | **14.15 Mbps** |

The channel's QC bar fails below about 1 Mbps outright, wants above 4, and treats 10 Mbps as the good benchmark. An editor was failed with a 0.87 Mbps export. CRF alone will quietly walk you into that failure on white-canvas content while every frame looks fine in the preview.

So: set an explicit bitrate. On the command line it is `--video-bitrate=14M`; in the config it is `Config.setVideoBitrate('14M')`. Do not use CRF and bitrate together, the bitrate setting is the one that should win.

### 6.4 Animate transforms, never layout

This is the single most important rendering rule in the whole packet and it is the one that is least obvious.

Remotion renders by screenshotting a browser once per frame. If you animate a property that changes **layout**, like `width`, `height`, `left` or `top`, Chrome recomputes layout and snaps the result to whole device pixels. A slow Ken Burns move that should travel 0.4 pixels per frame therefore travels 0 pixels for two frames and then 1 pixel. The result is a move that stutters, and in the frame data it shows up as **duplicate frames**, which is exactly what the QC motion metric punishes: identical consecutive frames measure as zero percent pixel change and read as dead air.

If you animate a **compositor** property, `transform` and `opacity`, Chrome composites at sub-pixel precision and the move is smooth.

Wrong:

```tsx
<img style={{width: 1240 * scale, left: -offsetX}} />
```

Right, and this is what `ImageBox.tsx` in this repo already does:

```tsx
<img
  style={{
    position: 'absolute', left: 0, top: 0,
    width: coverW, height: coverH,          // fixed. never animated
    transformOrigin: '0 0',
    transform: `translate3d(${-ovX * px}px, ${-ovY * py}px, 0) scale(${scale})`,
    willChange: 'transform',
  }}
/>
```

`translate3d` rather than `translate` forces the element onto its own compositor layer. `willChange: 'transform'` tells Chrome to keep it there. The same rule applies to the creature card punch-in, the pops, the icons and the title bar: every one of them animates with `transform` and `opacity` only.

One consequence worth stating plainly: **do not ease the Ken Burns move.** Ease it and the shot visually stalls at both ends, which puts a low-motion window at the start and end of every single shot. Run the pan and zoom linearly for the full duration of the shot and put the easing on the things that pop in and out.

### 6.5 Rendering

```bash
cd remotion
npx remotion render Section out/section-03.mp4 \
  --props=../projects/<slug>/sheets/03.sheet.json \
  --muted \
  --video-bitrate=14M \
  --concurrency=4 \
  --log=error
```

`--muted` renders picture only. The mix comes from stage 5. `--props` passes the sheet in, so one composition renders any section.

For a full video, render each section to its own file and concatenate with ffmpeg's concat demuxer, or register one long composition and render it in one pass. Sections are better: a failed QC on creature 6 costs you one section re-render, not ten minutes of the whole video.

### 6.6 The mux, and a trap that is live in this repo right now

```bash
ffmpeg -nostdin -loglevel error -y \
  -i out/video.mp4 -i ../projects/<slug>/audio/mix.wav \
  -c:v copy -c:a aac -b:a 320k \
  -t <exact_duration> \
  out/<slug>.mp4
```

Note `-t <exact_duration>` rather than `-shortest`.

Here is why, measured in this repo. The composition is 62.600 seconds. The mix file that got copied into `remotion/public/audio/mix.wav` is 61.973 seconds. The mux script used `-shortest`, so the finished file is 61.973 seconds: the last 0.63 seconds of picture was silently thrown away. The QC pass checks the audio and video stream lengths agree to within 0.10 seconds, and that file fails it. Nothing in the render output warns you.

So: pin the duration explicitly with `-t`, pad the mix to the exact composition length with `apad` (stage 5 does this), and let the QC A/V-length check be the thing that tells you if you got it wrong.

---

## 7. Stage 5: Audio

Four buses: voiceover, ambient bed, SFX, master. `tools/mix_audio.py`. The chain below is a direct port of the one already working in `engine/build.py`.

### 7.1 The chain

```python
fc = [
  # VO: delay to its start offset, high-pass out rumble, gentle levelling only
  f"[0:a]adelay={ms}|{ms},aresample=48000,highpass=f=80,"
  f"acompressor=threshold=-12dB:ratio=1.6:attack=15:release=280,"
  f"aformat=channel_layouts=stereo[vo]",

  # BED: trimmed and padded to the exact duration, faded, set well below the VO
  f"[1:a]aresample=48000,atrim=0:{dur},apad=whole_dur={dur},"
  f"afade=t=in:st=0:d=1.2,afade=t=out:st={dur-2.0}:d=2.0,"
  f"volume=-19dB,aformat=channel_layouts=stereo[bed0]",
]

# SFX: one input per hit, each delayed to its cue and gain-staged
for k, (name, t, g) in enumerate(all_sfx):
    fc.append(f"[{k+2}:a]aresample=48000,volume={g-9}dB,"
              f"adelay={int(t*1000)}|{int(t*1000)},"
              f"aformat=channel_layouts=stereo[s{k}]")
fc.append("".join(sfx_labels) + f"amix=inputs={len(sfx_labels)}:normalize=0[sfx]")

# THE DUCK: the VO is the sidechain key, the bed is the thing that gets pushed down
fc.append("[vo]asplit=2[vo1][vokey]")
fc.append("[bed0][vokey]sidechaincompress="
          "threshold=0.02:ratio=6:attack=20:release=520:makeup=1[bed]")

fc.append(f"[vo1][bed][sfx]amix=inputs=3:normalize=0:duration=longest,"
          f"apad=whole_dur={dur},atrim=0:{dur},aresample=48000[out]")
```

Read `sidechaincompress` in the right order: the **first** input is what gets compressed (the bed), the **second** is the key that triggers it (a copy of the voiceover). `asplit` exists because you need the voiceover twice, once as audio and once as a control signal. A ratio of 6 with a 520 ms release gives a duck you can clearly hear without it pumping.

Write that out with `-c:a pcm_s24le` to `work/mix_raw.wav`. **No limiter anywhere in this chain.** Not one.

### 7.2 The two-pass linear loudnorm

This is the part that decides whether the cut gets rejected.

A cut was failed at **LRA 1.9**, over-limited to the point that the bed never audibly ducked and the sound effects could not punch. The cause is a chain that limits first and then runs a single-pass loudnorm. ffmpeg's `loudnorm` in single-pass mode is a **dynamic** normaliser: it rides the level over time. Ride the level and then squash it and you have destroyed the loudness range, which is precisely the number QC measures.

The fix is two passes and `linear=true`.

**Pass 1, measure and change nothing:**

```bash
ffmpeg -nostdin -hide_banner -i work/mix_raw.wav \
  -af loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json \
  -f null -
```

That prints a JSON block to stderr containing `input_i`, `input_tp`, `input_lra`, `input_thresh` and `target_offset`. Parse it. In Python, take the last `{...}` in stderr and `json.loads` it.

**Pass 2, apply, with the measured values and linear mode:**

```bash
ffmpeg -nostdin -loglevel error -y -i work/mix_raw.wav -af \
"loudnorm=I=-15:TP=-1.5:LRA=9:linear=true:\
measured_I=${input_i}:measured_TP=${input_tp}:measured_LRA=${input_lra}:\
measured_thresh=${input_thresh}:offset=${target_offset}:print_format=summary,\
aresample=48000,apad=whole_dur=${dur},atrim=0:${dur}" \
-c:a pcm_s16le audio/mix.wav
```

`linear=true` is only honoured when all five `measured_*` values are supplied. With them, ffmpeg applies a **single constant gain** to the whole file. One gain, applied evenly, cannot change the loudness range. The LRA that comes out is the LRA that went in.

Targets, and where they come from:

| Target | Value | Why |
|---|---|---|
| `I` | -15 LUFS | the middle of the -14 to -16 acceptance window |
| `TP` | -1.5 dBTP | QC fails at -1.0, so aim 0.5 dB inside the line |
| `LRA` | 9 LU | a ceiling hint, not a target to squash toward. QC fails below 3 |

Three habits that keep this honest. Aim the target loudness at the middle of the window rather than the edge, because the measured result drifts a few tenths. Note the `apad` then `atrim` at the end of pass 2: that is what guarantees the mix is exactly the composition length, which is what stops the `-shortest` truncation from section 6.6. And if the mix is genuinely too hot after linear normalisation, the fix is to turn the bed and the SFX down in the pre-master, not to add a limiter.

---

## 8. Stage 6: The self-QC loop

This is the point of the whole system. Without it you have a text generator producing a plausible-looking edit list. With it you have something that measures its own work against the same numbers a human reviewer uses, and keeps going until it clears them.

The loop:

```
build sheet -> validate -> render -> mux -> qc.py -> read the numbers
   ^                                                        |
   |                    fail                                v
   +----- edit the sheet, targeting the specific failure ---+
```

The working measurement script is already in this repo at `engine/qc.py`, 569 lines, and it prints a verdict table plus a defect list. Port it into `tools/qc.py` and point it at the finished MP4:

```bash
python3 tools/qc.py projects/<slug>/out/<slug>.mp4 --workdir projects/<slug>/out/qc --keep
```

### 8.1 The pass/fail table

| Metric | How it is measured | Target | Fail |
|---|---|---|---|
| **Motion** | percent of pixels changing by more than 12/255 between frames sampled at 2 fps, averaged | **>= 22%** (best cut to date 25.1%) | at or near 12.1% |
| Motion floor and peak | min and max of the same series | informational | |
| **Dead zones** | maximal runs of consecutive 0.5 s samples below 4% change | **zero runs >= 4 s** | any |
| Longest dead zone | the worst such run | < 4 s | > 8 s is a hard fail |
| **One asset held** | longest single shot | never > 8 s | > 8 s |
| **Integrated loudness** | `loudnorm=print_format=json`, `input_i` | **-16 to -14 LUFS** | outside |
| **True peak** | same, `input_tp` | **< -1.0 dBTP** | at or above |
| **Loudness range** | same, `input_lra` | **> 3 LU** | at or below (a cut failed at 1.9) |
| Clipped samples | `volumedetect` `histogram_0db` | 0 | any |
| **Cut/SFX sync** | hard cuts (frame delta > 60%) vs audio onsets, percent of cuts with an onset within 0.6 s | **>= 70%** | below |
| Dark but flat frames | content-box mean below 30/255 **and** p95 below 90 | 0 | any |
| Resolution and fps | ffprobe | 1920x1080 at 30 | otherwise |
| **Video bitrate** | ffprobe | **> 4 Mbps**, 10 Mbps is the benchmark | below 1 Mbps is an outright fail |
| Audio bitrate | ffprobe | >= 128 kbps | below |
| **Pop count per section** | OCR inventory grouped by section | at or above the floor, **and the last section at or above 0.8 x median** | taper |
| **Pop spelling** | OCR text vs the sheet's intended pop strings | exact match on at least one frame per pop | never matches |
| A/V length delta | audio stream length vs container duration | < 0.10 s | above |
| Trailing digital silence | run below -60 dBFS at the end | < 0.15 s | above |
| **Final 5 seconds** | frame mean and standard deviation over the last 5 s | no black frames, no blank white frames, content present | any |

Two measurement subtleties that are already baked into `engine/qc.py` and that you must not "simplify" out of it.

**Dead zones are never merged across a high-motion sample.** If you treat "low, low, spike, low, low" as one long dead zone you will report a 13-second hold that does not exist. That exact bogus reading happened. A run ends the moment a sample goes above threshold. Full stop.

**Content-box luminance, not whole-frame luminance.** This house style is a white canvas with a dark image box in the middle. Measure the whole frame and a pitch-black night shot reads at about 160 mean and looks fine. Find the dark box first, measure inside it. And before flagging a dark frame, check its p95: a mean of 16 with a p95 of 101 has bright anchors in it and is correct, not illegible.

### 8.2 The OCR trap

The pop check reads the words off the screen with Tesseract, and there are two ways to get it wrong.

**Trap one: global binarisation silently drops white-on-dark text.** Tesseract thresholds the whole page at once. This layout is a bright white canvas with a dark box in it, and the on-image pops are white text with a black stroke, inside that dark box. When Tesseract picks a threshold for the mostly-white page, the white pop text inside the dark box falls on the wrong side of it and disappears. That produced a false "3 pops missing" report.

The fix is **two passes per frame**:

```python
def ocr_frame(path, work):
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    out = list(_tess(im, work))                    # pass A: the page as-is
    b = _plate_bounds(im)                          # find the dark image box
    if b:
        x0, x1, y0, y1 = b
        crop = im[y0:y1, x0:x1]
        bw = 255 - ((crop > 190).astype(np.uint8) * 255)   # bright mask, inverted
        bw = cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        bw = cv2.copyMakeBorder(bw, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
        out += _tess(bw, work)                     # pass B: dark-on-light, doubled
    return out
```

Pass B isolates the bright pixels inside the content box, inverts them so the text is dark on light, doubles the size (Tesseract wants roughly 30 px cap height) and adds a white border (it dislikes text touching the edge). Run both passes on every frame and merge the results.

**Trap two: 1 fps under-samples the pops.** Pops are on screen for about 2 seconds and animate in over the first 0.2 s. At 1 fps you can catch a pop only during its animation, read half a word, and log a spelling error that does not exist. **Run OCR at 2 fps.** Also treat a pop as misspelled only if it never renders correctly on any frame; a partial read during the pop-in is not a defect.

One more, cheap and worth it: the QC pass also builds 5x4 contact sheets at one frame every 3 seconds. Look at them. Ninety percent of "that image is wrong" is visible in ten seconds of flicking through those, and no metric in the table will catch it.

### 8.3 What Claude Code does with a failure

The loop only works if the model makes the *specific* fix, not a general one. Give it this mapping and it will.

| QC failure | The fix in the sheet |
|---|---|
| Motion below 22% | increase Ken Burns travel on the slowest shots, shorten the longest shots, add pop-ins and icon-ins in the low-motion windows the report timestamps |
| Dead zone at t=X | look at the motion profile printout, find which shot covers X, split it or add an on-screen event inside it |
| Shot over 8 s | split it into two shots with different images, or two different Ken Burns moves on the same image |
| Pop taper in the last section | add date, number, name and canon-number pops to the finale, not filler connectives |
| Pop missing from OCR | check it is not off-canvas or behind an icon; check the contrast; if it reads on some frames, it is fine |
| Pop misspelled | fix the string in the sheet |
| Cut/SFX sync below 70% | add an SFX to each cut listed under "cuts without a nearby transient" |
| LUFS out of range | change the loudnorm `I` target, re-run stage 5 only, no re-render needed |
| LRA at or below 3 | you have a limiter in the chain, or you are not in linear mode. Remove it. See 7.2 |
| True peak at or above -1.0 | lower `TP` to -1.5 and re-run stage 5 |
| Bitrate low | explicit `--video-bitrate`, not CRF |
| Dark flat frames | those shots need a brighter approved image, or a lift. Never force night onto a canon-daylight creature |
| A/V length delta | `-t` instead of `-shortest`, and `apad` in the mix |
| Black or blank final frames | fix the last shot. It is the highest-leverage frame in the file |

**Stop conditions.** Cap the loop at 4 iterations per section. If it has not cleared after 4, stop and print what is still failing and what was tried. An unbounded loop will happily spend two hours and forty dollars chasing 21.8 percent motion up to 22 percent. Also require the loop to re-run the validator before every render, because the cheapest failures to catch are the ones caught before rendering 1,878 frames.

---

## 9. Stage 7: Human handoff

Be clear-eyed about this. The system automates about 90 percent of the work, and the 10 percent it does not automate is the part that decides whether the video is good.

**What still needs you, every time:**

**1. Canon design calls.** When a creature has two or three mutually incompatible canon designs, which one this video uses is a judgement call about the source material. That is not a decision the model can make from a wiki gallery, and when it has been left to make it, the result has been three inconsistent designs inside one section. Decide up front, per creature, and write it into the materials JSON.

**2. The approved-image tick-off.** Stage 1's contact sheet. Ten to fifteen minutes per video. Non-negotiable and non-delegable. Everything in the canon-failure history is downstream of this gate not existing.

**3. Voiceover pickups.** The model can tell you a line is missing from the recording. It cannot record it. On the 2026-08-03 video the entire scripted mid-roll CTA, 55 words, was never recorded at all, and no amount of editing fixes that. Expect one pickup session per video.

**4. Tone and register.** Whether a gag is funny or embarrassing. Whether the grade on creature 4 feels right. Whether a section drags. Numbers cannot see any of that. A 25.1 percent motion score and a dead-boring section are entirely compatible.

**5. The final watch-through.** Once, start to finish, at full size, before publish. Every metric in section 8 can pass on a video with a wrong creature in it.

**What you should expect the system to get right without you:** pacing, motion, pop density and placement, sound-effect sync, loudness and mastering, delivery specs, spelling of on-screen text, and consistency of the layout across every section. Those are the things editors get graded down on most often and they are all measurable, which is why they are the things worth automating.

**A useful way to think about the split:** the model is a very fast, very consistent, completely tasteless editor who never gets bored in section 7 and never lets pop density taper. You are the person with taste and canon knowledge. Do not spend your attention on the things it measures better than you.

---

## 10. THE PROMPT

### 10.1 The kickoff prompt

Put your project files in place first: `projects/<slug>/title.txt`, `script.md`, `vo.wav`. Then open Claude Code in the repo root and paste this whole block.

```
You are building a finished horror-explainer video for a YouTube channel. Read
CLAUDE.md first and treat it as binding for this session and every session after.

PROJECT: projects/<slug>
INPUTS ALREADY IN PLACE: title.txt, script.md, vo.wav
OUTPUT REQUIRED: projects/<slug>/out/<slug>.mp4 that passes tools/qc.py, plus
projects/<slug>/out/qc.txt with the measured numbers.

Work through these stages in order. Do not skip ahead. Stop and ask me at every
gate marked HUMAN GATE.

STAGE 1 ASSET SOURCING
- Read script.md, list every creature in running order, and for each one find its
  fandom wiki and page title. Confirm the page titles with the MediaWiki API
  before crawling, do not guess them.
- For each creature run tools/wiki_sources.py to enumerate the article and its
  /Gallery subpage via action=parse&prop=images, resolve every filename through
  action=query&generator=images&prop=imageinfo&iiprop=url|size|mime|extmetadata,
  download, drop anything under 400px on the short side, dedupe by perceptual
  hash, and write materials/<creature>.json with source_url, wiki_page and size
  for every image.
- Look at every downloaded image and fill in its "description" field: one plain
  sentence describing what is actually visible. Be literal. If a skull has no
  lower jaw, say so. If only legs are visible and the body is not, say so. This
  field is what the canon-contradiction validator reads later, so it has to be
  accurate rather than evocative.
- Build materials/contact-sheet.html with tools/contact_sheet.py.
- HUMAN GATE: tell me the contact sheet is ready and stop. I will tick the
  approved images and save. Do not continue until I say the approvals are in.

STAGE 2 SCRIPT AND VO
- tools/parse_script.py script.md -> work/sections.json
- tools/transcribe.py vo.wav work/words.json  (faster-whisper, base.en,
  word_timestamps=True, condition_on_previous_text=False)
- tools/rms.py vo.wav work/rms.json
- Line each script section up against the transcript to get each section's start
  and end time. If a stretch of script has no matching words, DO NOT conclude the
  VO is missing it. Check work/rms.json over that window first. Flat normal RMS
  means Whisper dropped it. Genuinely floored RMS means the VO is really missing
  it, and that is a HUMAN GATE: tell me, I need to record a pickup.
- Report the section boundaries as a table before moving on.

STAGE 3 EDIT SHEETS
- For each section write sheets/<NN>.sheet.json against the Sheet type in
  remotion/src/sheet.ts.
- Every shot is 2 to 4 seconds. Nothing above 8 seconds, ever. Every shot has a
  Ken Burns direction, there is no static shot.
- Every shot uses an APPROVED image only, and shot.why says in one line why that
  image belongs on that narration line.
- Pops are anchored to spoken words, never to hardcoded seconds. 2 to 4+ per
  section minimum, and the LAST section gets at least as many as the median
  section. Dates, locations, canon numbers, names. Never a full sentence.
- Icons: stick figure, red X for danger or absence, arrow, clock, warning mark.
- One or two gags per section, only on lines the script marks as jokes, and
  register is always "horror". No licensed characters, no real people, no meme
  photographs, no animals for laughs, and never a gag as the final frame.
- SFX on every cut and every reveal.
- Run tools/validate_sheet.py after every sheet and fix every ERROR before
  moving to the next section.

STAGE 4 AND 5 RENDER AND AUDIO
- npx remotion browser ensure, once.
- Render each section muted with an explicit --video-bitrate=14M. Never CRF.
- Build the mix with tools/mix_audio.py: bed at -19 dB, sidechain duck keyed off
  the VO, SFX bus, then TWO-PASS LINEAR loudnorm targeting I=-15 TP=-1.5 LRA=9.
  No limiter anywhere in the chain.
- Mux with -t <exact duration>, never -shortest.

STAGE 6 SELF-QC LOOP
- Run tools/qc.py on the muxed file and read the whole verdict table.
- For every FAIL, make the specific targeted fix in the sheet or the mix, then
  re-validate and re-render only what changed.
- Repeat until everything is PASS or WARN, maximum 4 iterations per section.
- If it will not clear after 4, stop and tell me exactly what is still failing,
  what you tried, and what you think it needs.
- Then show me the contact sheets and the last-5-seconds frames.

RULES FOR HOW YOU WORK
- Absolute paths everywhere. The working directory resets between commands.
- Every ffmpeg call gets -nostdin -loglevel error. Progress output floods context.
- Never invent a flag or an API field. If you are unsure it exists, check it.
- Never write a timestamp into a sheet where an anchor would do.
- Never use an image that is not marked approved.
- When something is ambiguous about canon or tone, ask me. Do not decide it.

Start with Stage 1. Tell me the creature list and the wiki pages you resolved
before you download anything.
```

### 10.2 `CLAUDE.md` for the repo

This file is read at the start of every session, so the house rules survive context resets. Keep it short enough that it is always read in full.

```
# House rules for this repo

We make 9 to 10 minute horror explainers, "Every X Monster Explained in N
Minutes", 7 to 8 creatures, one section each. Reference channel: Ficknime.

## Look
- White canvas throughout.
- Images boxed and centred, never stretched. Full bleed only for a deliberate
  cinematic push-in, and it must be marked as such in the sheet.
- Palette is strictly black, white, and ONE red accent (#D62020). No other
  colour appears anywhere, including in icons, gags and glitch effects.
- Persistent creature-name title, top centre, ALL CAPS, clean bold face, on
  every section. Same font, same position, same case, every time.

## Motion is rule number one
- No shot is ever fully static. Ken Burns on every held image.
- Icons and text always animate in. Nothing appears by cutting to it.
- Something changes on screen every 2 to 4 seconds. Never more than 8 seconds
  on one asset.
- Animate transform and opacity only. Never width, height, left or top: Chrome
  snaps layout to whole pixels and the render emits duplicate frames.
- Ken Burns moves run linearly across the whole shot. Do not ease them, easing
  makes the shot stall at both ends.

## Keyword pops, not subtitles
- 2 to 4+ per section, synced to the voiceover's punch words.
- Dates, locations, canon numbers, names, one-word verdicts.
- Never a full sentence. Four words or 28 characters, whichever is shorter.
- Density must HOLD THROUGH THE FINALE. The last section gets at least as many
  pops as the median section. Tapering pops is a graded failure here.

## Icon language
Stick figures. A red X over a silhouette for danger, death or absence. Arrows.
Clocks. Warning marks. Nothing else.

## Humour
One or two dry-joke lines per section get a timed visual gag, and the gag stays
in the horror register. Never a licensed character. Never a real identifiable
person. Never a meme photograph. Never an identifiable minor. Never an animal
for laughs. Never a gag as the final frame of the video.

## Canon images: the hardest rule
- Creature images come ONLY from the creature's fandom wiki gallery or the
  creator's own accounts (@slimyswampghost for Trevor Henderson).
- No fan art. No game models. No AI re-renders. No stock photo standing in for
  a word in the narration.
- Every image must be marked approved by the owner before it can be used.
- THE IMAGE MUST NEVER CONTRADICT THE NARRATION. If the VO says "no lower jaw",
  the skull on screen has no lower jaw. If the VO says "no one has ever seen the
  whole thing", the whole body is never on screen.
- One creature, one design, for the whole video.

## Audio
- Dark ambient bed under everything, clearly ducked under the VO via sidechain.
- SFX synced to visual cues. A cut without a sound is a wasted cut.
- -14 to -16 LUFS, true peak below -1 dBTP, LRA above 3 LU.
- Two-pass LINEAR loudnorm only. Never a limiter, never single-pass dynamic
  loudnorm. A cut was rejected at LRA 1.9 for being over-limited.

## Delivery
1920x1080 or better, 30 fps, H.264 MP4, explicit video bitrate of 14M. A
0.87 Mbps export was rejected. CRF alone under-shoots badly on white canvas.

## How to work in this repo
- Absolute paths. The working directory resets between bash calls.
- Every ffmpeg command gets -nostdin -loglevel error.
- Sheets use word anchors, not hardcoded timestamps.
- tools/validate_sheet.py runs before every render and its ERRORs are blocking.
- tools/qc.py runs after every render and its FAILs are blocking.
- Ask the owner about canon and tone. Decide everything else yourself.
```

### 10.3 Slash commands

Each of these is a markdown file in `.claude/commands/`. The filename becomes the command name. `$ARGUMENTS` is substituted with whatever you type after it.

**`.claude/commands/source-assets.md`**

```
Source and shortlist the approved-candidate images for: $ARGUMENTS

1. Resolve the creature's wiki and exact page title through the MediaWiki API.
   Confirm the title exists before crawling. Check for a /Gallery subpage.
2. Run tools/wiki_sources.py for that creature into the current project.
3. Open every downloaded image and write its "description" field: one literal
   sentence about what is visibly in the frame, especially anatomy the narration
   might contradict.
4. Flag anything that looks like fan art, a wallpaper-site scrape, a game model,
   or a different creature, and say so in the description.
5. Rebuild materials/contact-sheet.html and tell me it is ready.
Do not render anything.
```

**`.claude/commands/build-sheet.md`**

```
Write or rewrite the edit sheet for section: $ARGUMENTS

Use work/sections.json for the narration, work/words.json for word timings, and
only images marked approved in materials/*.json.
Follow CLAUDE.md exactly. Anchors, never timestamps.
When done, run tools/validate_sheet.py on it and fix every ERROR.
Then print a summary: shot count, average shot length, longest shot, pop count,
pop kinds, icon count, gag count, SFX count.
```

**`.claude/commands/render.md`**

```
Render: $ARGUMENTS   (a section number, or "all")

1. tools/validate_sheet.py on each affected sheet. Stop on any ERROR.
2. npx remotion browser ensure if the browser is not already cached.
3. npx remotion render Section out/<NN>.mp4 --props=<sheet> --muted
   --video-bitrate=14M --log=error
4. tools/mix_audio.py for the audio, two-pass linear loudnorm.
5. Mux with -t <exact duration>, not -shortest.
Report the output path, duration, and measured video bitrate.
```

**`.claude/commands/qc.md`**

```
Run the full QC pass on: $ARGUMENTS   (defaults to the current project's output)

python3 tools/qc.py <file> --workdir out/qc --keep

Print the verdict table verbatim. Then, in your own words:
- every FAIL with its timestamps
- every WARN worth acting on
- the pop count per section and whether the last section tapers
- what the contact sheets and the last-5-seconds frames actually look like
Do not fix anything yet. Just report.
```

**`.claude/commands/fix-from-qc.md`**

```
Read the most recent out/qc.txt and fix what it found: $ARGUMENTS

For each FAIL, make the SPECIFIC targeted fix, not a general improvement:
- motion low  -> more Ken Burns travel on the slowest shots, split the longest
                 shots, add events inside the timestamped low-motion windows
- dead zone   -> find the shot covering that timestamp and add an event in it
- shot > 8s   -> split it
- pop taper   -> add real pops (dates, numbers, names, canon) to the finale
- sync < 70%  -> add SFX to the cuts listed as having no nearby transient
- LUFS/TP/LRA -> re-run the mix only, no re-render needed
- bitrate     -> explicit --video-bitrate, never CRF
Re-validate, re-render only what changed, re-run QC, and show me the before and
after numbers side by side. Maximum 4 iterations, then stop and report.
```

**`.claude/commands/canon-check.md`**

```
Canon audit for: $ARGUMENTS   (a section, or "all")

For every shot in the sheet, put three things side by side: the narration line
(shot.vo), the approved image's recorded description, and shot.why.
Flag every contradiction, in either direction:
- narration says an anatomical absence, image shows it present
- narration says the whole thing has never been seen, image shows the whole thing
- narration describes one design, image is a different design of the creature
- a different creature entirely, a different franchise, a flipped or rotated
  asset that inverts the creature, an anachronism in a period scene
Also flag any two shots in the same section using mutually inconsistent designs.
Report as a table with timestamps. Fix nothing without asking me.
```

---

## 11. Cost, time, and what to do when it fails

### 11.1 Time

These are shapes, not promises. Your machine and your video length will move them.

| Stage | Machine time | Your time |
|---|---|---|
| 1. Asset sourcing, 8 creatures | 10 to 20 min of crawling and downloading | **10 to 15 min ticking the contact sheet** |
| 2. Script and VO ingestion | 3 to 10 min for a 10 min VO on CPU, faster on GPU | 2 min sanity-checking the section boundaries |
| 3. Edit sheets, 8 sections | mostly model thinking time | 10 min reading the sheets if you want to |
| 4. Render, 10 min at 30 fps | 20 to 60 min depending on cores and concurrency | none |
| 5. Audio | under a minute | none |
| 6. QC pass | 3 to 8 min per full-length run | 5 min reading the report and the contact sheets |
| 6b. Each fix iteration | re-render the affected sections only, so minutes not an hour | none |
| 7. Final watch-through | none | **10 min, and do not skip it** |

The parts that scale badly are rendering and QC, both of which decode or encode every frame. Render per section rather than per video and the fix loop stays cheap.

### 11.2 Cost

The only paid part is the model. Fandom's API is free, faster-whisper runs locally, ffmpeg and Remotion are free, and Tesseract is free.

Model cost is dominated by three things: reading images during asset sourcing, writing eight edit sheets, and each QC read-and-fix cycle. Keep it down with three habits, all of which also make the output better.

Always pass `-nostdin -loglevel error` to ffmpeg. Unfiltered ffmpeg progress output is the single largest source of wasted context in a pipeline like this.

Have tools print summaries, not dumps. `validate_sheet.py` should print the errors, not the sheet. `qc.py` prints a verdict table, not every frame.

Cap the fix loop at 4 iterations. Chasing 21.8 percent motion up to 22 percent is not worth a render cycle, and a WARN is a WARN for a reason.

### 11.3 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Remotion cannot find a browser | Chrome Headless Shell was never downloaded | `npx remotion browser ensure` |
| Render crashes or frames come out blank on a headless box | no GPU, hardware GL requested | `Config.setChromiumOpenGlRenderer('swangle')` |
| Images do not appear in the render | local file access blocked, or the path is not under `public/` | put images in `remotion/public/`, reference with `staticFile()`, keep `setChromiumDisableWebSecurity(true)` |
| Fonts render as a fallback face | font promise not awaited before the first frame | load fonts via `@remotion/fonts` `loadFont` inside `delayRender()`, and await `document.fonts.ready` before `continueRender()` |
| Motion measures low even though the edit looks busy | Ken Burns animated via layout properties, so Chrome is emitting duplicate frames | animate `transform: translate3d(...) scale(...)` only |
| Motion low, no duplicate frames | shots too long or moves too small | more travel, shorter shots, more pop-ins and icon-ins |
| Bitrate around 1 to 2 Mbps | encoding with CRF on flat white-canvas content | explicit `--video-bitrate=14M` |
| LRA measures below 3 | a limiter in the chain, or single-pass dynamic loudnorm | remove the limiter, use two-pass with all five `measured_*` values plus `linear=true` |
| LUFS correct but the bed swamps the voiceover | sidechain inputs the wrong way round | first input is compressed (bed), second is the key (VO copy from `asplit`) |
| Finished file is a fraction of a second short and A/V lengths disagree | muxed with `-shortest` against a slightly short mix | `apad` the mix to the exact duration and mux with `-t` |
| Whisper produces the same line several times over | dense music bed feeding the model its own output | transcribe the dry VO, set `condition_on_previous_text=False`, re-check the window with `small.en` |
| A chunk of script has no words in the transcript | Whisper dropped it under music, most likely | check `work/rms.json` first. Flat RMS through the window means the VO is there |
| QC reports pops missing that you can plainly see | Tesseract's global binarisation dropped white-on-dark text | run the second inverted bright-mask pass over the content box, at 2 fps |
| QC reports a pop misspelled that reads fine | OCR caught it mid animation-in | only fail a pop that never renders correctly on any frame |
| A 13-second dead zone reported that does not exist | low-motion runs merged across a high-motion blip | end a run at the first sample above threshold, never merge |
| Every night shot flagged as too dark | measuring whole-frame luminance on a white-canvas layout | measure inside the content box, and check p95 before calling it |
| An anchor will not resolve | the model invented a phrase the narrator never said, or the search ran across the whole video | restrict the search to the section's time range, then fix the phrase against `words.json` |
| Validator fails on an unapproved image | correct behaviour | approve it in the contact sheet, or pick a different image |
| Wiki page title 404s from the API | the article title is not what you assumed | `action=query&list=allpages` or `Category:Galleries` to get real titles, then retry |

### 11.4 If you only remember four things

1. **The approved-image gate is the whole ballgame.** Every canon failure this channel has had traces to images being chosen without an approved set. Fifteen minutes of ticking boxes removes an entire class of failure.
2. **Motion is measured, so make it measurable.** Transform-only animation, linear Ken Burns, something changing every 2 to 4 seconds. 22 percent is the bar, 25.1 percent is the best cut to date.
3. **Two-pass linear loudnorm, no limiter.** LRA is the number that gets a cut rejected and it is the one people never think to check.
4. **The QC loop is the product.** Anything can generate an edit list. The thing that makes this worth building is that it measures its own output against the same bar a human reviewer uses, and will not stop until it clears it.
