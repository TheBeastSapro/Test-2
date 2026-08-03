"""Getting video statistics into the outlier scorer.

`research.outliers` does the arithmetic and takes `VideoStat` objects. This module is
the other half: turning whatever the operator actually has into those objects.

## Why paste is a first-class input, not a fallback

The obvious design is "connect an API key and we fetch everything". That is the right
long-term shape and `from_youtube_api` implements it. But it fails exactly when the
tool is most useful — sitting in front of a competitor's channel page, wanting to know
whether the video doing well is doing *unusually* well. Waiting on a quota'd API for a
question you can answer from a table on screen is friction with no payoff.

So there are four inputs, and none of them is privileged:

* **paste** — a table copied from anywhere, or JSON from another tool;
* **the YouTube Data API** — when a key is configured;
* **the public channel page**, read with yt-dlp and no key at all — see `keyless`;
* **an MCP research tool's output** — which arrives as JSON and goes through the same
  parser as a paste.

`read_channel` picks between the middle two so callers do not each grow their own
version of that decision.

Everything converges on `VideoStat` and is scored by the same code, so a number the
operator pasted and a number fetched from the API are treated identically. There is no
"real" path and "manual" path to drift apart.

## On being permissive

The parser accepts more shapes than it strictly should: several date formats, view
counts written as "1.2M" or "1,240,000", durations as seconds or as `PT4M13S` or as
`4:13`. That is deliberate. The alternative — one strict schema — means the operator
reformats data by hand before they can ask a question, and the tool stops being used.
What it will not do is guess a *missing* number: a row without views or a date is
reported as skipped, with the reason, rather than defaulted to something plausible.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .outliers import VideoStat

log = logging.getLogger("forgecast.research.sources")

# Column names seen in the wild, mapped to the field they fill. Lowercased and
# stripped of punctuation before lookup.
_ALIASES = {
    "videoid": "video_id", "id": "video_id", "video": "video_id", "url": "video_id",
    "link": "video_id", "watchurl": "video_id",
    "title": "title", "videotitle": "title", "name": "title",
    "views": "views", "viewcount": "views", "viewcounttext": "views",
    "totalviews": "views", "plays": "views",
    "published": "published_at", "publishedat": "published_at",
    "publisheddate": "published_at", "date": "published_at", "uploaded": "published_at",
    "uploaddate": "published_at", "publishtime": "published_at",
    "duration": "duration_seconds", "durationseconds": "duration_seconds",
    "length": "duration_seconds", "lengthseconds": "duration_seconds",
    "channel": "channel", "channeltitle": "channel", "channelname": "channel",
    "subscribers": "channel_subscribers", "subs": "channel_subscribers",
    "subscribercount": "channel_subscribers",
    "likes": "likes", "likecount": "likes",
    "comments": "comments", "commentcount": "comments",
}

_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


@dataclass
class ParseResult:
    videos: list[VideoStat] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"count": len(self.videos), "skipped": self.skipped}


# ------------------------------------------------------------------ field parsers


def parse_count(value) -> int | None:
    """"1,240,000" / "1.2M" / "3.4K views" / 1240000 -> 1240000."""
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return None
    text = str(value).strip().lower().replace(",", "").replace(" views", "").strip()
    match = re.match(r"^([\d.]+)\s*([kmb])?$", text)
    if not match:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None
    number = float(match.group(1))
    return int(number * _SUFFIXES.get(match.group(2) or "", 1))


def parse_duration(value) -> float:
    """Seconds, `PT4M13S`, `4:13` or `1:02:11` -> seconds. 0 when unknown.

    Zero rather than None because duration only decides the Short/long cohort, and an
    unknown duration scoring as long-form is the conservative answer — it will not
    inflate a Short's apparent performance against a long-form baseline.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    text = str(value).strip().upper()

    iso = re.match(r"^P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$", text)
    if iso and any(iso.groups()):
        hours, minutes, seconds = (float(g or 0) for g in iso.groups())
        return hours * 3600 + minutes * 60 + seconds

    if ":" in text:
        parts = [float(part or 0) for part in text.split(":")]
        total = 0.0
        for part in parts:
            total = total * 60 + part
        return total

    try:
        return float(text)
    except ValueError:
        return 0.0


_RELATIVE = re.compile(r"^(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago$")
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%b %d, %Y",
)
_RELATIVE_DAYS = {"second": 1 / 86400, "minute": 1 / 1440, "hour": 1 / 24,
                  "day": 1, "week": 7, "month": 30.44, "year": 365.25}


def parse_date(value, *, now: datetime | None = None) -> datetime | None:
    """An absolute timestamp, or a relative one like "3 weeks ago"."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    text = str(value).strip()

    relative = _RELATIVE.match(text.lower())
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2)
        return (now or datetime.now(UTC)) - timedelta(
            days=amount * _RELATIVE_DAYS[unit]
        )

    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _video_id(value: str) -> str:
    """Pull the id out of a watch URL, or pass through whatever was given."""
    text = str(value).strip()
    match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{6,})", text)
    return match.group(1) if match else text


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


# --------------------------------------------------------------------- the parsers


def _row_to_stat(row: dict, *, now: datetime | None) -> tuple[VideoStat | None, str]:
    mapped: dict = {}
    for key, value in row.items():
        field_name = _ALIASES.get(_normalise_key(key))
        if field_name and (field_name not in mapped or mapped[field_name] in ("", None)):
            mapped[field_name] = value

    title = str(mapped.get("title") or "").strip()
    views = parse_count(mapped.get("views"))
    published = parse_date(mapped.get("published_at"), now=now)

    label = title or str(mapped.get("video_id") or "(unnamed row)")
    if views is None:
        return None, f"{label}: no view count"
    if published is None:
        return None, f"{label}: no publish date"

    return VideoStat(
        video_id=_video_id(mapped.get("video_id") or title),
        title=title or "(untitled)",
        views=views,
        published_at=published,
        duration_seconds=parse_duration(mapped.get("duration_seconds")),
        channel=str(mapped.get("channel") or ""),
        channel_subscribers=parse_count(mapped.get("channel_subscribers")) or 0,
        likes=parse_count(mapped.get("likes")) or 0,
        comments=parse_count(mapped.get("comments")) or 0,
    ), ""


def from_json(text: str, *, now: datetime | None = None) -> ParseResult:
    """A JSON array of objects, or an object wrapping one under any single key."""
    payload = json.loads(text)
    if isinstance(payload, dict):
        # Tools wrap their results differently — {"items": [...]}, {"videos": [...]}.
        # Take the first list-valued key rather than requiring a specific name.
        payload = next(
            (value for value in payload.values() if isinstance(value, list)), []
        )
    if not isinstance(payload, list):
        raise ValueError("expected a JSON array of video objects")

    result = ParseResult()
    for entry in payload:
        if not isinstance(entry, dict):
            result.skipped.append(f"not an object: {entry!r:.40}")
            continue
        # YouTube Data API nests the interesting fields; flatten one level so the
        # alias table sees them.
        flat: dict = {}
        for key, value in entry.items():
            if isinstance(value, dict):
                flat.update(value)
            else:
                flat[key] = value
        stat, reason = _row_to_stat(flat, now=now)
        (result.videos.append(stat) if stat else result.skipped.append(reason))
    return result


def from_table(text: str, *, now: datetime | None = None) -> ParseResult:
    """CSV or tab-separated text with a header row."""
    sample = text.strip()
    if not sample:
        return ParseResult()
    delimiter = "\t" if sample.splitlines()[0].count("\t") >= 1 else ","
    reader = csv.DictReader(io.StringIO(sample), delimiter=delimiter)

    result = ParseResult()
    for row in reader:
        stat, reason = _row_to_stat(row, now=now)
        (result.videos.append(stat) if stat else result.skipped.append(reason))
    return result


def parse(text: str, *, now: datetime | None = None) -> ParseResult:
    """Whatever the operator pasted. JSON if it looks like JSON, otherwise a table."""
    stripped = (text or "").strip()
    if not stripped:
        return ParseResult()
    if stripped[0] in "[{":
        return from_json(stripped, now=now)
    return from_table(stripped, now=now)


# ---------------------------------------------------------------- YouTube Data API


class ResearchError(RuntimeError):
    pass


def from_youtube_api(channel: str, api_key: str, *, limit: int = 50) -> ParseResult:
    """Fetch a channel's recent uploads with their statistics.

    Three calls, in the order the API forces: resolve the channel to its uploads
    playlist, list that playlist, then fetch statistics for the ids in bulk. The bulk
    step matters — `videos.list` takes 50 ids per call, and doing it one at a time
    burns the daily quota on a single channel.
    """
    import httpx

    base = "https://www.googleapis.com/youtube/v3"
    handle = channel.strip()
    match = re.search(r"(?:channel/|@)([\w.-]+)", handle)
    if match:
        handle = match.group(1)

    with httpx.Client(timeout=20.0) as client:

        def get(path: str, **params) -> dict:
            response = client.get(f"{base}/{path}", params={"key": api_key, **params})
            if response.status_code != 200:
                raise ResearchError(
                    f"YouTube API {path} returned {response.status_code}: "
                    f"{response.text[:200]}"
                )
            return response.json()

        if handle.startswith("UC") and len(handle) > 20:
            info = get("channels", part="contentDetails,snippet,statistics", id=handle)
        else:
            info = get("channels", part="contentDetails,snippet,statistics",
                       forHandle=handle)
        items = info.get("items") or []
        if not items:
            raise ResearchError(f"no channel found for {channel!r}")

        channel_item = items[0]
        uploads = (channel_item["contentDetails"]["relatedPlaylists"]["uploads"])
        channel_name = channel_item["snippet"]["title"]
        subscribers = int(
            channel_item.get("statistics", {}).get("subscriberCount") or 0
        )

        video_ids: list[str] = []
        page_token = ""
        while len(video_ids) < limit:
            page = get("playlistItems", part="contentDetails", playlistId=uploads,
                       maxResults=min(50, limit - len(video_ids)),
                       **({"pageToken": page_token} if page_token else {}))
            video_ids += [
                item["contentDetails"]["videoId"] for item in page.get("items", [])
            ]
            page_token = page.get("nextPageToken", "")
            if not page_token:
                break

        rows: list[dict] = []
        for start in range(0, len(video_ids), 50):
            batch = get("videos", part="snippet,statistics,contentDetails",
                        id=",".join(video_ids[start:start + 50]))
            for item in batch.get("items", []):
                snippet, stats = item["snippet"], item.get("statistics", {})
                rows.append({
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt"),
                    "views": stats.get("viewCount"),
                    "likes": stats.get("likeCount"),
                    "comments": stats.get("commentCount"),
                    "duration": item.get("contentDetails", {}).get("duration"),
                    "channel": channel_name,
                    "subscribers": subscribers,
                })

    result = ParseResult()
    for row in rows:
        stat, reason = _row_to_stat(row, now=None)
        (result.videos.append(stat) if stat else result.skipped.append(reason))
    return result


def read_channel(reference: str, *, api_key: str = "",
                 limit: int = 50) -> tuple[ParseResult, str]:
    """A channel's uploads from whichever source can answer, and which one that was.

    The API first when a key is configured, because it returns measured timestamps and
    likes and comments; `keyless` otherwise. The fallback also covers a *failing* API,
    which is not a hedge — a quota that ran out mid-afternoon is the ordinary way this
    breaks, and the numbers are still sitting on the public page.

    Callers get the note back rather than having to know which path ran, because the
    caveat belongs in what the operator reads, not in a log line.
    """
    from . import keyless

    api_failure = ""
    if api_key:
        try:
            return (from_youtube_api(reference, api_key, limit=limit),
                    "read with the YouTube Data API key from Settings")
        except ResearchError as exc:
            api_failure = str(exc)
            log.info("youtube api failed for %s, trying yt-dlp: %s", reference, exc)

    try:
        return keyless.channel_uploads(reference, limit=limit), keyless.SOURCE_NOTE
    except keyless.KeylessError as exc:
        if api_failure:
            # The API error is the primary one: it is what the operator configured, so
            # its failure is the thing they can act on. The fallback's failure is
            # appended so it does not look like it was never tried.
            raise ResearchError(f"{api_failure}\nyt-dlp could not read it "
                                f"either: {exc}") from exc
        raise ResearchError(str(exc)) from exc
