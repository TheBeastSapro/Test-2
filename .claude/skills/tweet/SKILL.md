---
name: tweet
description: Read a public tweet, thread, or the article a tweet links to, from an x.com / twitter.com URL with no login. Use whenever a Twitter/X status URL appears, or when asked what a tweet says, to summarize a thread, to follow the article behind a tweet, or to pull a tweet's text, media, or engagement numbers. Not for Twitter search, profile timelines, or posting — those need cookies.
---

# Reading tweets

`tweet` reads a public tweet the way `yt-dlp` reads a YouTube URL: hand it a
URL, get the content, no credentials involved.

```bash
tweet https://x.com/jack/status/20        # tweet, thread above it, linked article
tweet 1812256998588662068                 # bare id works too
tweet <url> --no-article                  # skip fetching linked pages
tweet <url> --no-thread                   # just this tweet
tweet <url> --json                        # raw payload
```

Output carries the author, timestamp, full text (long tweets included, t.co
links expanded), direct media URLs, and like/reply counts.

**Threads.** Replies walk up the parent chain automatically, so a link into the
middle of a thread reads in order. Each ancestor is labelled `earlier in
thread` when the same author wrote it, `replying to` when it belongs to someone
else's conversation. Quoted tweets are appended.

**Articles.** External links in the tweet are fetched through Jina Reader and
printed after it — two by default, 6000 characters each (`--max-articles`,
`--article-chars`). So "what is this tweet pointing at" is one command, not two.

Media URLs it prints are direct — pass them to `yt-dlp` or `curl` if the file
itself is needed.

## What needs cookies instead

The open endpoint addresses tweets by id and nothing else. These need
`twitter-cli` with cookies (`agent-reach configure twitter-cookies "..."`):

- **Replies below a tweet.** The parent chain goes up, never down. Reading a
  thread from its *first* post therefore shows only that post — the output says
  how many replies are hidden. Read from the *last* post to get the whole
  thread logged-out.
- **X's own long-form Articles** (`x.com/i/article/...`). No public endpoint
  serves these; the command exits 1 and says so.
- Searching tweets, profile timelines, followers, likes, and anything that
  posts or replies.

A deleted, private, or age-restricted tweet also exits 1 with the reason. That
is the endpoint refusing, not a bug to route around.
