# @YouTubeCreators tip log

Source material and published page for the creator tips posted by YouTube's
official creator account on X.

- `tips.html` — the published reference page. 161 tips, verbatim, grouped
  into 16 chapters by what each one helps you do. Published as an Artifact.
- `all-original-posts.tsv` — every original post (no replies, no retweets)
  recovered from the account, one per line: `YYYY-MM-DD<TAB>text`. 3,183 rows
  spanning 2011–2026. This is the corpus the tips were filtered out of; keep
  it so the filtering can be redone or widened without re-fetching.

## How the corpus was collected

The account's live timeline serves only its ~20 most recent posts to anyone
who isn't logged in, and X's search and profile endpoints need cookies. So:

1. **Enumerate** — the Wayback Machine's CDX API was queried for every
   archived permalink under `twitter.com/YouTubeCreators/status/*` and
   `x.com/YouTubeCreators/status/*`, yielding 18,701 unique post IDs.
   Snowflake IDs encode their own timestamp, so the set could be bucketed by
   date before anything was fetched.
2. **Rehydrate** — each ID was fetched fresh from X's public per-post
   endpoint via the `tweet` CLI. 18,440 posts by the account came back.
3. **Filter** — replies, retweets and posts by other accounts were dropped,
   leaving 3,183 originals, which were read and sorted by hand.

The most recent weeks came from the logged-out syndication timeline
(`cdn.syndication.twimg.com/srv/timeline-profile/screen-name/YouTubeCreators`),
which the archive hadn't caught up to yet. That endpoint rate-limits by IP
and returned 429 from this container on every attempt; routing the same URL
through Jina Reader (`https://r.jina.ai/<url>`) returned it immediately.

## Coverage

Archive coverage is dense but not total — a handful of 2026 dates have no
snapshot. The mid-2023 to mid-2025 stretch is genuinely thin on advice rather
than under-collected; the account ran on memes and product news through that
period. 2011–2017 is barely archived at all.
