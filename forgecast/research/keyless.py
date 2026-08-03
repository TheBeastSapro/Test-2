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
"""

from __future__ import annotations

import json
import logging
import shutil
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

# One request for the whole listing, so this is the only timeout that matters. Generous
# because a 200-video channel on a slow connection is a legitimately slow read, and the
# failure mode of being too eager is a research desk that times out on big channels —
# exactly the ones worth researching.
TIMEOUT_SECONDS = 240


class KeylessError(RuntimeError):
    """Something went wrong that the operator can act on. The message says what."""


def _executable() -> str | None:
    return shutil.which("yt-dlp")


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
    # No backticks. This string is printed as plain text under the fetch box on the
    # research page, where a backtick is a backtick and "Install it with `pip install
    # yt-dlp`" reads as a typo rather than as code.
    return False, (
        "yt-dlp is not installed, so a channel link cannot be read without a YouTube "
        "Data API key. Install it with: pip install yt-dlp — or add a key in Settings."
    )


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

    command = [
        binary, "--flat-playlist", "--dump-single-json",
        "--playlist-end", str(max(1, min(int(limit), 200))),
        # Without this every entry's timestamp is null and there is nothing to score.
        "--extractor-args", "youtubetab:approximate_date",
        "--no-warnings", "--ignore-config",
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
