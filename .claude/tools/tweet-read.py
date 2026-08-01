#!/usr/bin/env python3
"""Read a public tweet, its thread, and whatever article it links to — no login,
the way yt-dlp reads a YouTube URL.

Uses the same public endpoint X serves to embedded tweets on third-party sites,
so nothing here needs cookies or an API key. Linked articles are pulled through
Jina Reader, the same channel Agent Reach uses for web pages.

    tweet https://x.com/jack/status/20
    tweet <url> --no-article      # skip fetching linked articles
    tweet <url> --no-thread       # just this tweet, no parents
    tweet 20 --json

Two things the open endpoint will not serve, both needing twitter-cli cookies:
replies *below* a tweet (so a thread read from its first post shows only that
post), and X's own long-form Articles at x.com/i/article/...
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://cdn.syndication.twimg.com/tweet-result"
READER = "https://r.jina.ai/"
ARTICLE_RE = re.compile(r"(?:twitter|x)\.com/i/article/(\d+)")
SELF_HOSTS = ("twitter.com", "x.com", "t.co", "pic.twitter.com")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ID_RE = re.compile(r"status(?:es)?/(\d+)")
BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def tweet_id(raw):
    """Accept a full URL or a bare id. Jack's first tweet is id 20, so a bare
    id cannot be length-checked — only a URL is matched by pattern."""
    raw = raw.strip()
    if raw.isdigit():
        return raw
    match = ID_RE.search(raw)
    if not match:
        raise ValueError("no tweet id found in %r" % raw)
    return match.group(1)


def token_for(tid):
    """The endpoint only checks that a token is present, not that it is the one
    the official embed script would have produced. Derive something stable per
    id so repeat reads look identical rather than random."""
    n = int(tid) % (36 ** 11)
    out = ""
    while n:
        n, rem = divmod(n, 36)
        out = BASE36[rem] + out
    return out or "a"


def fetch(tid, timeout):
    url = "%s?id=%s&token=%s&lang=en" % (ENDPOINT, tid, token_for(tid))
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def expand_links(text, entities):
    """Swap t.co shorteners back to the URLs they point at, and drop the ones
    that only stand in for attached media — those are listed separately."""
    entities = entities or {}
    for url in entities.get("urls", []):
        if url.get("url") and url.get("expanded_url"):
            text = text.replace(url["url"], url["expanded_url"])
    for item in entities.get("media", []):
        if item.get("url"):
            text = text.replace(item["url"], "")
    return text


def full_text(tweet):
    """Tweets over 280 characters keep their real body in note_tweet."""
    note = tweet.get("note_tweet") or {}
    result = (note.get("note_tweet_results") or {}).get("result") or {}
    text = result.get("text") or note.get("text") or tweet.get("text") or ""
    entities = result.get("entity_set") or tweet.get("entities")
    return expand_links(text, entities).strip()


def media_lines(tweet):
    lines = []
    for item in tweet.get("mediaDetails") or []:
        kind = item.get("type")
        if kind == "photo":
            lines.append("[photo] %s" % item.get("media_url_https", ""))
            continue
        variants = [
            v for v in (item.get("video_info") or {}).get("variants", [])
            if v.get("content_type") == "video/mp4"
        ]
        if variants:
            best = max(variants, key=lambda v: v.get("bitrate", 0))
            size = item.get("original_info") or {}
            lines.append("[%s %sx%s] %s" % (
                kind or "video",
                size.get("width", "?"),
                size.get("height", "?"),
                best.get("url", ""),
            ))
        else:
            lines.append("[%s] %s" % (kind or "media", item.get("media_url_https", "")))
    return lines


def linked_urls(tweet):
    """External links worth reading. X's own links point at media or at quoted
    tweets, both of which are already rendered inline."""
    found = []
    for url in ((tweet.get("entities") or {}).get("urls") or []):
        target = url.get("expanded_url") or url.get("url")
        if not target:
            continue
        host = urllib.parse.urlparse(target).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        if any(host == h or host.endswith("." + h) for h in SELF_HOSTS):
            continue
        if target not in found:
            found.append(target)
    return found


def read_article(url, timeout, limit):
    """Pull an article through Jina Reader — the same channel Agent Reach uses
    for web pages, and it needs no key.

    Shelling out to curl with its own user agent is deliberate. Jina sits
    behind Cloudflare, which checks that the user agent matches the TLS
    fingerprint: urllib gets a challenge page, and so does curl if it claims to
    be Chrome. Left alone, curl passes."""
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), READER + url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValueError((result.stderr or "curl exited %d" % result.returncode).strip())
    text = result.stdout.strip()
    if not text:
        raise ValueError("reader returned nothing")
    if text.startswith("{") and '"code":4' in text[:150]:
        raise ValueError("reader refused the page: %s" % text[:160])
    if "<title>Just a moment..." in text[:400]:
        raise ValueError("blocked by a Cloudflare challenge")
    if len(text) > limit:
        text = text[:limit].rstrip() + (
            "\n\n… [truncated at %d chars — raise with --article-chars]" % limit
        )
    return text


def render(tweet, label=None):
    user = tweet.get("user") or {}
    handle = user.get("screen_name", "unknown")
    header = "@%s (%s) · %s" % (
        handle,
        user.get("name", ""),
        (tweet.get("created_at") or "")[:19].replace("T", " ") + " UTC",
    )
    if label:
        header = "%s  [%s]" % (header, label)

    out = [header, "https://x.com/%s/status/%s" % (handle, tweet.get("id_str", "")), ""]
    out.append(full_text(tweet) or "(no text)")

    media = media_lines(tweet)
    if media:
        out += [""] + media

    stats = []
    if tweet.get("favorite_count") is not None:
        stats.append("%s likes" % tweet["favorite_count"])
    if tweet.get("conversation_count") is not None:
        stats.append("%s replies" % tweet["conversation_count"])
    if stats:
        out += ["", " · ".join(stats)]
    return "\n".join(out)


def collect(tweet, follow_thread, depth):
    """Walk up the reply chain so a mid-thread link reads in order. A parent by
    the same author is the tweet's own thread; a parent by someone else is the
    conversation it answers."""
    author = ((tweet.get("user") or {}).get("screen_name") or "").lower()
    chain = [(tweet, None)]
    node = tweet
    while follow_thread and node.get("parent") and len(chain) <= depth:
        node = node["parent"]
        speaker = ((node.get("user") or {}).get("screen_name") or "").lower()
        chain.insert(0, (node, "earlier in thread" if speaker == author else "replying to"))
    quoted = tweet.get("quoted_tweet")
    if quoted:
        chain.append((quoted, "quoted"))
    return chain


def main():
    parser = argparse.ArgumentParser(description="Read a public tweet without logging in.")
    parser.add_argument("target", help="tweet URL or id")
    parser.add_argument("--json", action="store_true", help="print the raw payload")
    parser.add_argument("--no-thread", action="store_true", help="skip parent tweets")
    parser.add_argument("--no-article", action="store_true", help="do not fetch linked articles")
    parser.add_argument("--depth", type=int, default=20, help="max parents to walk (default 20)")
    parser.add_argument("--max-articles", type=int, default=2, help="linked articles to fetch (default 2)")
    parser.add_argument("--article-chars", type=int, default=6000, help="per-article character cap")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    article = ARTICLE_RE.search(args.target)
    if article:
        sys.exit(
            "error: x.com/i/article/%s is one of X's long-form Articles. Those are "
            "not served to logged-out readers by any public endpoint — reading it "
            "needs twitter-cli with cookies "
            "(agent-reach configure twitter-cookies \"...\")." % article.group(1)
        )

    try:
        tid = tweet_id(args.target)
    except ValueError as exc:
        sys.exit("error: %s" % exc)

    try:
        data = fetch(tid, args.timeout)
    except urllib.error.HTTPError as exc:
        sys.exit("error: HTTP %s fetching tweet %s" % (exc.code, tid))
    except (urllib.error.URLError, OSError) as exc:
        sys.exit("error: could not reach the tweet endpoint: %s" % exc)
    except json.JSONDecodeError:
        sys.exit("error: tweet endpoint returned a non-JSON response")

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if not data or data.get("tombstone"):
        note = ((data.get("tombstone") or {}).get("text") or {}).get("text", "")
        sys.exit("error: tweet %s is unavailable%s" % (tid, " — " + note if note else
                                                       " (deleted, private, or age-restricted)"))

    chain = collect(data, not args.no_thread, args.depth)
    rule = "\n\n" + "-" * 60 + "\n\n"
    print(rule.join(render(t, label) for t, label in chain))

    # Anything below this tweet — the author's own continuation included — lives
    # behind the conversation API, which is not open. Say so rather than let the
    # output imply the thread ended here.
    replies = data.get("conversation_count")
    if replies and not args.no_thread:
        print(
            "\n[%s replies below this tweet are not readable logged-out; "
            "twitter-cli with cookies can fetch them]" % replies
        )

    if args.no_article:
        return

    seen, targets = set(), []
    for tweet, _ in chain:
        for url in linked_urls(tweet):
            if url not in seen:
                seen.add(url)
                targets.append(url)

    for url in targets[: args.max_articles]:
        print("\n" + "=" * 60 + "\nLINKED ARTICLE: %s\n" % url + "=" * 60 + "\n")
        try:
            print(read_article(url, args.timeout, args.article_chars))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print("[could not read this link: %s]" % exc)

    if len(targets) > args.max_articles:
        print("\n[%d more linked page(s) not fetched; raise --max-articles]"
              % (len(targets) - args.max_articles))


if __name__ == "__main__":
    main()
