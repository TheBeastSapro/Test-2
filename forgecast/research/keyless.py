"""Read a channel's public numbers without an API key.

## Why this exists

The research desk needed a YouTube Data API key, and the honest consequence was that
the most natural thing anyone can do here — paste a channel link — answered "no key
configured, paste the numbers instead". A feature nobody can use on a fresh install is
a feature that reads as broken, and it was reported as exactly that.

`yt-dlp` reads the same public page a browser does. No key, no quota, no account. It is
already a dependency of nothing here, so it is optional: present, and research works
from a link; absent, and the desk says so and still scores a pasted table.

## The catch, which is the whole design problem

A flat playlist listing gives view counts and durations but **no publish dates**, and
outlier scoring is built on views-per-day. Dates come from
`--extractor-args youtubetab:approximate_date`, and "approximate" is not a hedge:
YouTube's listing shows relative labels like "1 month ago", so the date is reconstructed
from that and can be up to about half a month out.

That error does not matter uniformly, which is the part worth getting right:

* A two-year-old video: ±15 days on 730 is under 2% of its age. Irrelevant.
* A three-month-old video: ±15 days on 90 is ~17%, which will not flip a 5× outlier
  but can absolutely flip a 3.2× one, and 3.0 is the threshold this app uses.
* A two-week-old video is dropped before scoring anyway, for being too young.

So every video read here is marked `date_is_approximate`, and the scorer works out per
video whether that can change the answer — see `outliers.approximate_date_span`. This
module states the fact; deciding what it costs is arithmetic, and it belongs next to the
rest of the arithmetic. The alternative — quietly treating a reconstructed date as
measured — produces a confident multiple with an invisible error bar, which is worse
than no number, because the whole point of this desk is that the numbers can be trusted.

The exact API path stays available and is preferred when a key is configured: it
returns real timestamps, so nothing from it is marked approximate.

## Reading specific videos, which is a different read with a different error bar

The desk also takes video links directly — the ones an operator already believes are
worth copying. Those are read from each video's own page (`video_stats`), not from a
listing, and that page states an upload date rather than "2 months ago". So nothing
from that path is marked approximate: attaching a ±15-day range to a date that was
published to the day overstates the error, and an overstated error bar sends the same
kind of wrong signal an understated one does — it would flag solid multiples as
"might not clear the bar" until the reader stops reading the flag.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime

from .outliers import VideoStat
from .sources import ParseResult

log = logging.getLogger("forgecast.research.keyless")

# What the caller should say about numbers that came from here, so the reader knows the
# dates were not measured before they act on a multiple.
SOURCE_NOTE = (
    "read from the public channel page with yt-dlp — no API key needed. Publish dates "
    "are reconstructed from relative labels, so any video where that could change the "
    "verdict carries a note and a range instead of a single multiple."
)

# The other note, for videos read one page at a time. Deliberately says the dates are
# the stated ones: the same fetch can mix both sources, and a reader told everything is
# approximate will discount the numbers that are not.
VIDEO_SOURCE_NOTE = (
    "read from each video's own public page with yt-dlp — no API key needed. These "
    "dates are the ones the page states rather than reconstructed from a relative "
    "label, so they carry no range."
)

# Where this path does not work, and it is not a small exception. yt-dlp reads the same
# public page a browser does, and YouTube answers a datacentre address with "Sign in to
# confirm you're not a bot" — so on any hosted install the keyless route is present,
# installed, correct, and refused. The same build on a laptop reads fine.
#
# One sentence, in the module that owns the path, because three pages offer it and three
# copies of a caveat is how two of them come to say something the third has stopped
# saying. It is a condition rather than a fact: this cannot know where it is running, so
# it says what to do if nothing comes back rather than predicting that nothing will.
BLOCKED_NOTE = (
    "On a hosted or datacentre install YouTube usually blocks that read — if nothing "
    "comes back, connect NexLev in Settings or set a YouTube API key."
)

# One request for the whole listing, so this is the only timeout that matters. Generous
# because a 200-video channel on a slow connection is a legitimately slow read, and the
# failure mode of being too eager is a research desk that times out on big channels —
# exactly the ones worth researching.
TIMEOUT_SECONDS = 240


class KeylessError(RuntimeError):
    """Something went wrong that the operator can act on. The message says what."""


def _executable() -> list[str] | None:
    """The argv prefix that runs yt-dlp. See `forgecast.ytdlp` for why it is not a path.

    A list now, because on Windows the answer is usually `python -m yt_dlp` rather than
    an executable: yt-dlp is a base dependency living in the app's own virtualenv, and
    the `.vbs` that starts the app never puts that virtualenv's `Scripts` on `PATH`.
    """
    from ..ytdlp import command
    return command()


def _run(command: list[str]) -> subprocess.CompletedProcess:
    """The one place a subprocess is started, so a test can stand in for it.

    Patching `subprocess.run` itself would replace it for everything else running in
    the same interpreter, including any worker thread that happens to be shelling out
    to ffmpeg. One function to substitute is cheaper than that risk.
    """
    return subprocess.run(command, capture_output=True, text=True,
                          timeout=TIMEOUT_SECONDS)


def available() -> tuple[bool, str]:
    """Can a channel be read without a key, and if not, what would fix it."""
    if _executable():
        return True, ""
    # Names the app's own installer rather than a pip command, and printed as plain
    # text under the fetch box, so it carries no backticks either. An operator handed
    # `pip install yt-dlp` has been handed the maintainer's job — and on a managed
    # Windows machine it is a job policy forbids, which is what the agent found out by
    # trying it four times and being refused by the sandbox on every one.
    from ..ytdlp import why_missing
    return False, why_missing()


def _listing_url(reference: str) -> str:
    """The uploads listing for whatever form of reference was pasted.

    `/videos` matters: a bare channel URL resolves to the channel's *featured* tab,
    which is a curated selection and not its uploads, so scoring it would compare a
    channel against its own highlights reel.
    """
    from ..agent.studio import parse_link

    link = parse_link(reference)
    if link.kind == "channel":
        return f"https://www.youtube.com/channel/{link.value}/videos"
    if link.kind == "handle":
        handle = link.value if link.value.startswith("@") else f"@{link.value}"
        return f"https://www.youtube.com/{handle}/videos"
    if link.kind == "video":
        raise KeylessError(
            "that is a single video, and an outlier is measured against its own "
            "cohort — give me the channel it is on."
        )

    bare = reference.strip()
    if bare.startswith("@"):
        return f"https://www.youtube.com/{bare}/videos"
    if bare.startswith("UC") and len(bare) > 20:
        return f"https://www.youtube.com/channel/{bare}/videos"
    raise KeylessError(f"could not tell what channel {reference!r} refers to")


def channel_uploads(reference: str, *, limit: int = 50) -> ParseResult:
    """A channel's recent uploads with view counts, durations and approximate dates.

    Returns the same `ParseResult` the pasted-table and API paths return, so nothing
    downstream needs to know which source it came from — except through the
    `date_is_approximate` flag, which is the one thing that genuinely differs.
    """
    binary = _executable()
    if not binary:
        raise KeylessError(available()[1])

    url = _listing_url(reference)

    from ..ytdlp import cookie_args
    command = [
        *binary, "--flat-playlist", "--dump-single-json",
        "--playlist-end", str(max(1, min(int(limit), 200))),
        # Without this every entry's timestamp is null and there is nothing to score.
        "--extractor-args", "youtubetab:approximate_date",
        "--no-warnings", "--ignore-config",
        # The listing read is refused far less often than the media fetch — it is a page,
        # not a stream — but it is refused, and when it is, the channel cannot be read at
        # all. One source of cookies for both, so an operator who fixes the download does
        # not have to discover the listing separately.
        *cookie_args(),
        url,
    ]
    try:
        finished = _run(command)
    except subprocess.TimeoutExpired as exc:
        raise KeylessError(
            f"reading that channel took longer than {TIMEOUT_SECONDS}s and was stopped. "
            f"Try a smaller limit."
        ) from exc
    except OSError as exc:
        raise KeylessError(f"could not run yt-dlp: {exc}") from exc

    if finished.returncode != 0 or not finished.stdout.strip():
        detail = (finished.stderr or finished.stdout or "").strip().splitlines()
        raise KeylessError(
            "yt-dlp could not read that channel:\n"
            + "\n".join(line for line in detail[-4:] if line)
        )

    try:
        payload = json.loads(finished.stdout)
    except ValueError as exc:
        raise KeylessError("yt-dlp returned something that was not JSON") from exc

    channel_name = payload.get("channel") or payload.get("uploader") or ""
    subscribers = int(payload.get("channel_follower_count") or 0)

    videos: list[VideoStat] = []
    skipped: list[str] = []
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            skipped.append("an entry that was not an object")
            continue
        video_id = entry.get("id") or ""
        title = (entry.get("title") or "").strip()
        views = entry.get("view_count")
        stamp = entry.get("timestamp")

        # A members-only or removed video appears in the listing with no view count.
        # Named rather than dropped silently, because "42 read, 3 skipped" is a fact
        # about the channel and a silent 39 is not.
        if views is None:
            skipped.append(f"{title or video_id}: no public view count")
            continue
        if stamp is None:
            skipped.append(f"{title or video_id}: no date, even an approximate one")
            continue
        if title.lower() in ("[private video]", "[deleted video]"):
            skipped.append(f"{video_id}: {title}")
            continue

        videos.append(VideoStat(
            video_id=video_id,
            title=title,
            views=int(views),
            published_at=datetime.fromtimestamp(int(stamp), UTC),
            duration_seconds=float(entry.get("duration") or 0.0),
            channel=channel_name,
            channel_subscribers=subscribers,
            # Always: every date on this path came out of a relative label.
            date_is_approximate=True,
        ))

    log.info("read %s uploads from %s without a key (%s skipped)",
             len(videos), channel_name or reference, len(skipped))
    return ParseResult(videos=videos, skipped=skipped)


def _published(entry: dict) -> datetime | None:
    """When a video page says it went out.

    Three fields because a premiere and an ordinary upload do not fill the same one:
    `release_timestamp` is when a scheduled video actually went live, `timestamp` is the
    upload moment, and `upload_date` is the YYYYMMDD the page states and is the only one
    always present. Taking `upload_date` first would date a premiere to when it was
    queued, which for a video that sat scheduled for a week is a week of age it never
    had — and age is the denominator of every score here.
    """
    for key in ("release_timestamp", "timestamp"):
        stamp = entry.get(key)
        if stamp:
            return datetime.fromtimestamp(int(stamp), UTC)
    day = str(entry.get("upload_date") or "").strip()
    if len(day) == 8 and day.isdigit():
        return datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC)
    return None


def video_stats(video_ids: list[str]) -> ParseResult:
    """Public numbers for specific videos, read from their own pages.

    Takes ids rather than links: resolving whatever was pasted into an id is the
    caller's job (`sources.as_video_id`), because the same resolution has to happen on
    the API path too and two copies of it would disagree about what a Shorts URL is.

    One process for the whole batch. The obvious alternative — a call per link — costs a
    process launch and a fresh TLS handshake each time, and a five-link paste then takes
    long enough that the operator assumes the page has hung.
    """
    binary = _executable()
    if not binary:
        raise KeylessError(available()[1])

    wanted = [str(video_id).strip() for video_id in video_ids if str(video_id).strip()]
    if not wanted:
        return ParseResult()

    command = [
        *binary, "--dump-json", "--skip-download",
        # A watch URL copied from the sidebar carries `&list=`, and without this yt-dlp
        # reads the whole playlist behind it — 200 videos where one was asked for.
        "--no-playlist",
        # One private link in a paste of six must not cost the other five.
        "--ignore-errors",
        "--no-warnings", "--ignore-config",
        *[f"https://www.youtube.com/watch?v={video_id}" for video_id in wanted],
    ]
    try:
        finished = _run(command)
    except subprocess.TimeoutExpired as exc:
        raise KeylessError(
            f"reading those videos took longer than {TIMEOUT_SECONDS}s and was stopped. "
            f"Paste fewer links."
        ) from exc
    except OSError as exc:
        raise KeylessError(f"could not run yt-dlp: {exc}") from exc

    # `--ignore-errors` exits non-zero when any link failed, so the return code cannot
    # decide whether this worked. Empty output can: nothing came back at all.
    if not finished.stdout.strip():
        detail = (finished.stderr or "").strip().splitlines()
        raise KeylessError(
            "yt-dlp could not read any of those videos:\n"
            + "\n".join(line for line in detail[-4:] if line)
        )

    read: dict[str, VideoStat] = {}
    for line in finished.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        video_id = entry.get("id") or ""
        published = _published(entry)
        views = entry.get("view_count")
        if not video_id or published is None or views is None:
            continue
        read[video_id] = VideoStat(
            video_id=video_id,
            title=(entry.get("title") or "").strip() or "(untitled)",
            views=int(views),
            published_at=published,
            duration_seconds=float(entry.get("duration") or 0.0),
            channel=entry.get("channel") or entry.get("uploader") or "",
            channel_subscribers=int(entry.get("channel_follower_count") or 0),
            likes=int(entry.get("like_count") or 0),
            comments=int(entry.get("comment_count") or 0),
            # Not approximate, and this is the one line that differs from the listing
            # path: this date came off the video's own page.
            date_is_approximate=False,
        )

    stderr_lines = [line for line in (finished.stderr or "").splitlines() if line.strip()]
    result = ParseResult()
    for video_id in wanted:
        stat = read.get(video_id)
        if stat is not None:
            result.videos.append(stat)
            continue
        # yt-dlp names the id in its error line, so the reason lands on the link it
        # belongs to instead of one pooled "something failed" for the whole paste.
        reason = next((line.strip() for line in stderr_lines if video_id in line), "")
        result.skipped.append(f"{video_id}: {reason or 'could not be read'}")

    log.info("read %s of %s pasted videos without a key",
             len(result.videos), len(wanted))
    return result
