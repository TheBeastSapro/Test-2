---
name: tweet
description: Read a public tweet or thread from an x.com / twitter.com URL with no login. Use whenever a Twitter/X status URL appears, or when asked what a tweet says, to summarize a thread, or to pull a tweet's text, media, or engagement numbers. Not for Twitter search, profile timelines, or posting — those need cookies.
---

# Reading tweets

`tweet` reads a public tweet the way `yt-dlp` reads a YouTube URL: hand it a
URL, get the content, no credentials involved.

```bash
tweet https://x.com/jack/status/20        # tweet plus its parent chain
tweet 1812256998588662068                 # bare id works too
tweet <url> --no-thread                   # just this tweet
tweet <url> --json                        # raw payload
```

Output carries the author, timestamp, full text (long tweets included, t.co
links expanded), direct media URLs, and like/reply counts. Replies walk up the
parent chain automatically so a link into the middle of a thread reads in
order; quoted tweets are appended.

Video and image URLs it prints are direct — pass them to `yt-dlp` or `curl` if
the media itself is needed.

## What this cannot do

The open endpoint only serves tweets addressed by id. These need `twitter-cli`
with cookies configured (`agent-reach configure twitter-cookies "..."`):

- searching tweets (`twitter search`)
- profile timelines, followers, likes
- anything that posts, replies, or likes

If a tweet was deleted, made private, or is age-restricted, the command exits 1
and says so — that is the endpoint refusing, not a bug to route around.
