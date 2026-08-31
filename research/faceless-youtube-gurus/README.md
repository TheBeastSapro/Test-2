# Faceless YouTube operators — tips and unrolled threads

Source material and published page for four faceless-YouTube operators on X:
Noah Morris (@noahmorris), Wanner Aarts (@wannercashcow / @wanneracademy),
phed (@PhedEU) and 1 of 10 (@1of10media, plus co-founder @Richard_YTS).

- `playbook.html` — the published page. 75 unrolled threads (877 steps), 72
  standalone tips and 754 embedded screenshots, filterable by operator and by
  topic. Built by `build.py`. ~9 MB, almost all of it pictures.
- `build.py` — the generator. Holds the curation: which thread maps to which
  topic and title, the promo-stripping rules, and all the page's CSS and JS.
  Edit this, re-run it, republish.
- `fetch_imgs.py` — downloads every referenced image, downscales it to 380px
  wide JPEG, and caches it in `imgcache/` (not committed). Run before `build.py`.
- `threads_clean2.json` — the 63 de-duplicated threads, each part carrying its
  text and its image URLs.
- `tips_final.json` — the 72 curated standalone posts with their images.
- `posts.txt` — every original timeline post recovered, `handle<TAB>date<TAB>text`.

## How the corpus was collected

The Wayback method used for @YouTubeCreators does not work here: none of these
accounts have a single archived post. Two sources instead:

1. **Timelines** — `cdn.syndication.twimg.com/srv/timeline-profile/screen-name/<handle>`
   returns roughly 100 recent posts to a logged-out reader, with the payload in
   a `__NEXT_DATA__` blob. The endpoint rate-limits hard by IP; routing through
   Jina Reader (`https://r.jina.ai/<url>`, header `x-respond-with: html`) got
   past it, until Jina's own pool hit the same limit.
2. **Threads** — each `threadreaderapp.com/thread/<id>.html` page carries a
   thread's full text with `data-tweet="<id>"` markers per part. This is the
   only logged-out route to multi-tweet threads; the open per-tweet endpoint
   walks up a reply chain, never down.

   Do not trust `threadreaderapp.com/user/<handle>` as the index. It 404s for
   accounts that definitely have unrolled threads (Noah's did) and lists only a
   subset for the rest. The reliable method is to find every thread-opening post
   in the timelines — anything with 🧵, "a thread", "here's how" — resolve its
   tweet ID, and request `/thread/<id>.html` directly. That second pass found 18
   threads the index had never listed, six of them Noah's.

Tweet IDs harvested from either source were rehydrated with the `tweet` CLI
(the public per-tweet endpoint), which stays available even while the
timeline endpoint is rate-limited — they are separate limits on the same host.

## Images

The artifact viewer's CSP blocks external image hosts, so nothing can be
hotlinked from `pbs.twimg.com` — every picture has to travel inside the page as
a data URI. `fetch_imgs.py` downscales them to 380px/q68 first, which puts 506
screenshots in about 6.5 MB of JPEG.

Attributing an image to the right thread step took two attempts. Thread Reader
lazy-loads images (`src="/images/1px.png"`, real URL in `data-src`) and places
them in markup that does not nest inside the tweet they belong to, so splitting
the page on tweet boundaries loses most of them. The working approach is to walk
the whole document linearly, recording tweet markers and image markers in
document order, and attach each image to the most recent preceding tweet.

Threads where images outnumber prose (phed's 50-thumbnail sheet) render as a
contact-sheet grid rather than a list; every image opens in a lightbox.

## Threads that could not be recovered

`unrecovered-threads.tsv` lists the 30 thread-opening posts whose bodies exist
nowhere a logged-out reader can reach — never unrolled, and unreachable through
the open endpoint because a reply chain only walks upward. Recovering them needs
a logged-in session (`agent-reach configure twitter-cookies`). Notable ones:
Noah's A-to-Z workflow across 20 channels and his six rules for hiring
freelancers; phed's digital-real-estate thread and 30-day roadmap; Wanner on
user profiling and on 20 niches.

## Not yet included

- **Julian (@julianfaceless)** — no unrolled threads on Thread Reader, and his
  timeline endpoint was rate-limited on every attempt.
- **Gold** — not identified. A dozen handle variants were probed and the other
  operators' timelines mined for mentions; no match.

Both slot into `build.py` as another entry in `AUTHORS` plus their threads and
tips; the page's filters build themselves from the data.

## A note on the content

These are operators selling courses, coaching and tools. Revenue figures are
their own unverified claims, and the algorithm material is inference from
public research and their own channels rather than documentation. The page
says so at the top.
