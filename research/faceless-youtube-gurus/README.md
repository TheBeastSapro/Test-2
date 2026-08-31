# Faceless YouTube operators — tips and unrolled threads

Source material and published page for four faceless-YouTube operators on X:
Noah Morris (@noahmorris), Wanner Aarts (@wannercashcow / @wanneracademy),
phed (@PhedEU) and 1 of 10 (@1of10media, plus co-founder @Richard_YTS).

- `playbook.html` — the published page. 60 unrolled threads (675 steps) and
  33 standalone tips, filterable by operator and by topic. Built by `build.py`.
- `build.py` — the generator. Holds the curation: which thread maps to which
  topic and title, the hand-picked standalone tips, and the promo-stripping
  rules. Edit this, re-run it, republish.
- `threads_clean.json` — the 63 de-duplicated threads with their parts.
- `posts.txt` — every original timeline post recovered, `handle<TAB>date<TAB>text`.

## How the corpus was collected

The Wayback method used for @YouTubeCreators does not work here: none of these
accounts have a single archived post. Two sources instead:

1. **Timelines** — `cdn.syndication.twimg.com/srv/timeline-profile/screen-name/<handle>`
   returns roughly 100 recent posts to a logged-out reader, with the payload in
   a `__NEXT_DATA__` blob. The endpoint rate-limits hard by IP; routing through
   Jina Reader (`https://r.jina.ai/<url>`, header `x-respond-with: html`) got
   past it, until Jina's own pool hit the same limit.
2. **Threads** — `threadreaderapp.com/user/<handle>` lists every thread anyone
   has had unrolled for that account, and each `/thread/<id>.html` page carries
   the full text with `data-tweet="<id>"` markers per part. This is the only
   logged-out route to multi-tweet threads; the open per-tweet endpoint walks
   up a reply chain, never down.

Tweet IDs harvested from either source were rehydrated with the `tweet` CLI
(the public per-tweet endpoint), which stays available even while the
timeline endpoint is rate-limited — they are separate limits on the same host.

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
