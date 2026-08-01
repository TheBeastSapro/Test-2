#!/usr/bin/env python3
"""Read a public tweet (and its thread) with no login, the way yt-dlp reads a
YouTube URL.

Uses the same public endpoint X serves to embedded tweets on third-party sites,
so nothing here needs cookies or an API key. Search and profile timelines have
no equivalent open endpoint — those still need twitter-cli with cookies.

    tweet https://x.com/jack/status/20
    tweet 20 --json
    tweet <url> --no-thread
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://cdn.syndication.twimg.com/tweet-result"
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
    """Walk up the reply chain so a mid-thread link reads in order."""
    chain = [(tweet, None)]
    node = tweet
    while follow_thread and node.get("parent") and len(chain) <= depth:
        node = node["parent"]
        chain.insert(0, (node, "in reply to"))
    quoted = tweet.get("quoted_tweet")
    if quoted:
        chain.append((quoted, "quoted"))
    return chain


def main():
    parser = argparse.ArgumentParser(description="Read a public tweet without logging in.")
    parser.add_argument("target", help="tweet URL or id")
    parser.add_argument("--json", action="store_true", help="print the raw payload")
    parser.add_argument("--no-thread", action="store_true", help="skip parent tweets")
    parser.add_argument("--depth", type=int, default=20, help="max parents to walk (default 20)")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

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
    print(("\n\n" + "-" * 60 + "\n\n").join(render(t, label) for t, label in chain))


if __name__ == "__main__":
    main()
