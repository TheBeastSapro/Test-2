"""What several competitors have in common — the pass that runs after the scoring.

`research.outliers` answers one question per video: did this beat its own channel's
median, and by how much. That is the right question and it is the wrong *shape* for what
the desk is now used for. Nobody pastes five competitors to get five separate verdicts.
They paste five because they suspect the same thing is working on all of them and they
want it named, and five separate reports is that answer withheld.

## The distinction the whole module exists for

A pattern on one channel is that channel's habit. The same pattern on three is the
niche's convention, and only the second is worth building a schedule around. The two are
indistinguishable in the arithmetic — a share is a share — and exactly one number tells
them apart: how many **distinct channels** the supporting videos came from.

So every finding carries `channels`, `scope` is derived from its length and from nothing
else, and `scope_note` says it in the sentence a person reads rather than only in a field
a UI might forget to print. The failure that prevents is the expensive one: a quarter
spent copying a competitor's personal tic because a report called it a trend.

`usable` and `scope` are separate on purpose and it is worth being clear about why.
`usable` says there is enough data to state the thing at all; `scope` says how far it
generalises. Ten of one channel's outliers sharing a title shape is a solid fact about
that channel — usable, and still not a niche pattern.

## Why the shares pool across channels when the medians never do

`outliers` is emphatic that a *views* median must never be pooled across channels: a
50k-a-day channel and a 500-a-day channel share a median neither has been near. None of
that applies to what is measured here, because none of these quantities are per-channel
scales. A minute is a minute on every channel, a question mark is a question mark, and
ninety characters is a long title on all of them. What pooling can still hide is one loud
channel supplying eight of ten supporting videos — and the channel count on every finding
is precisely what exposes that, which is why it is not optional output.

## What can honestly be measured, and what cannot

The desk fetches titles, view counts, durations, publish dates, and — on the API path
only — likes and comments. Everything below is computed from those and from nothing else.

**Whether the outliers run longer than the ordinary uploads** — yes, where the rows carry
a duration at all. Per cohort, because a 45-second Short averaged with a 20-minute video
gives a median that describes neither.

**Whether a title shape over-indexes among the outliers** — yes. A leading number, a
question mark, a colon, an opening interrogative are all in the string that was fetched.

**Whether the channels keep to a schedule** — only where the dates were *measured*.
`keyless` reconstructs every listing date from a relative label, which puts it inside a
±15-day window; a gap between two such dates is not a cadence, and this refuses to print
one rather than print a plausible number.

**Why any of it worked** — *no*. The hook, the pacing, the script, the thumbnail, the
retention curve: nothing here has watched a video, and no arrangement of a title, a
duration and a view count can be made to say what happens inside one. `not_assessed`
carries those in the output rather than leaving their absence to be noticed, because a
report that silently omits the thumbnail comparison reads as a report that looked at
thumbnails and found nothing to say.

## Rejected: a model call to write this up

A narration layer was the obvious next step and it is deliberately not here. These
findings are counts and medians with their sample sizes attached; handing them to a model
to phrase produces the same content in prose that reads *more* confident than the counts
justify, and there is no mechanical check that the paraphrase kept the channel count in
it. The one sentence that must never be lost — "this is one channel, not three" — is
exactly the sentence a fluent rewrite drops. So there is no provider import, no network
call and no key here: it is arithmetic over numbers that were already fetched, and it
runs identically offline.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise

from .outliers import (
    APPROXIMATE_DATE_ERROR_DAYS,
    MIN_AGE_DAYS,
    SOFT_OUTLIER,
    Outlier,
    VideoStat,
    _channel_key,
    find_outliers,
)

# How many videos have to carry a pattern before it is a pattern at all.
#
# Four, not three. Three videos out of a fetch of forty is a coincidence with a name, and
# what it costs is not a bad paragraph but a quarter spent on a format nobody is actually
# using. `outliers.MIN_COHORT` refuses to call five videos a median for the same reason at
# the other end of the desk.
MIN_SUPPORT = 4

# How many *distinct channels* have to show it before it stops being one channel's habit.
# Two channels agreeing is a pair; three is the point at which "everyone here does this"
# is the simpler explanation than "these two both happen to".
MIN_CHANNELS_FOR_CONVENTION = 3

# How much longer or shorter the outliers have to run before the difference is worth a
# sentence. A quarter, because these medians are over a handful of videos and a 10% gap
# between two medians of six is one video moving.
DURATION_SHIFT = 0.25

# How much more often a title shape has to appear among the outliers than among the rest.
# Percentage points, absolute: a shape on 30% of the outliers and 5% of the rest is a
# finding; one on 95% of both is how every video in the niche is titled and says nothing
# about why these ones won.
SHARE_LIFT = 0.25

# How many characters between two median title lengths before it is worth saying.
TITLE_SHIFT = 8

# How many gaps between uploads before "how often they post" is a schedule rather than the
# two most recent uploads. Gaps, not videos — n uploads have n-1 of them.
MIN_GAPS = 4

# How far apart two channels' cadences can be and still be called the same schedule.
CADENCE_SPREAD = 1.5

# How much more engagement the outliers need before it is a difference and not rounding.
ENGAGEMENT_LIFT = 1.25

# How much longer a gap before an outlier has to be, against that channel's own usual gap,
# to count as "these landed after a break". A ratio rather than a number of days, because
# a week off is a long break on a daily channel and nothing at all on a monthly one.
GAP_LIFT = 1.25

# How far a finding reaches. Derived from the channel count and never set by hand, so a
# finding cannot claim a reach its supporting videos do not have.
SCOPE_CHANNEL = "channel"          # one channel — a habit
SCOPE_SHARED = "shared"            # two — agreement, not yet a convention
SCOPE_CONVENTION = "convention"    # three or more — the niche's convention
# Several channels, pointing opposite ways. Its own scope rather than a convention with a
# different sentence, because the convention wording — "the same thing on four different
# channels" — is precisely false about a finding whose content is that they differ.
SCOPE_SPLIT = "split"
SCOPE_PICKS = "picks"              # not a generalisation at all; named videos, measured

UNNAMED = "(unnamed)"

# The things this desk cannot answer, whatever it fetched. Printed with every synthesis
# rather than only when relevant: the operator has to know the difference between "we
# checked thumbnails and they were unremarkable" and "nothing here has ever seen one".
CANNOT_BE_MEASURED = (
    "Why any of it worked — the hook, the first thirty seconds, the script. That needs "
    "the audio or a transcript and the desk fetches neither.",
    "Pace: words per minute, cuts per minute, how fast it moves. Same reason. A title, a "
    "duration and a view count say nothing about what happens inside the video.",
    "Thumbnails: not fetched, and face-versus-text is a question about the image.",
    "Retention, watch time and click-through: private to whoever owns the channel. No "
    "public source carries them for a competitor.",
)


# --------------------------------------------------------------------------- findings


@dataclass
class Finding:
    """One thing the fetch supports, with everything needed to judge how much."""

    kind: str
    headline: str
    detail: str = ""
    # The distinct channels whose videos support this, by the name that gets printed.
    # The list rather than a count, because "which two" is the next question and a UI
    # that only has a number has to ask for the fetch again to answer it.
    channels: list[str] = field(default_factory=list)
    of_channels: int = 0
    support: int = 0            # how many measurements carry it
    compared_with: int = 0      # how many it was measured against
    # What `support` counts. Usually videos; a cadence finding counts the gaps between
    # uploads, and printing "3 videos" under a figure computed from fifty waits would
    # understate it by an order of magnitude in the field a reader uses to judge it.
    support_unit: str = "videos"
    scope: str = SCOPE_CHANNEL
    confidence: str = "low"
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Whether this should be stated as a finding, as opposed to merely listed.

        The same test `style.sourcing.SourcingProfile.usable` applies to a measurement
        taken off too few shots, and for the same reason: a pattern read off two videos
        is an anecdote, and an anecdote printed in the same typeface as a finding is
        indistinguishable from one. Thin findings are kept and shown separately rather
        than dropped — "three of them did this, which is not enough to call a pattern" is
        a useful thing to read and a silently missing row is not.
        """
        return self.confidence in {"medium", "high"}

    @property
    def scope_note(self) -> str:
        """How far this reaches, in the sentence a person actually reads.

        Not left to the caller. A finding whose reach lives only in a `channels` field is
        one careless template away from being printed as a niche trend, which is the one
        mistake this module exists to make impossible.
        """
        count = len(self.channels)
        if self.scope == SCOPE_PICKS:
            return "your picks, each measured against the channel it came from"
        if self.scope == SCOPE_SPLIT:
            return (f"{count} of the {self.of_channels} channels in this fetch, and they "
                    f"do not agree — this is where they differ, which is a finding and "
                    f"not a shared pattern.")
        if count <= 1:
            name = self.channels[0] if self.channels else "one channel"
            return (f"{name} only — one channel's habit, not a niche pattern. Another "
                    f"channel doing the same thing is what would make it one.")
        if count < MIN_CHANNELS_FOR_CONVENTION:
            return (f"{count} of the {self.of_channels} channels in this fetch — two "
                    f"channels agreeing is a pair, and one more would settle it.")
        return (f"{count} of the {self.of_channels} channels in this fetch — the same "
                f"thing on {count} different channels is the niche's convention, not "
                f"one channel's habit.")

    @property
    def support_note(self) -> str:
        """How much is behind this, in words, with the singular right.

        Assembled here rather than left to a template because the unit is not always
        videos — a cadence figure is measured from the gaps between uploads — and a
        template that appends an "s" prints "1 picks" under a finding. A seam like that
        in the sample size is where a reader stops trusting the numbers above it.
        """
        unit = self.support_unit
        if self.support == 1:
            unit = {"videos": "video", "picks": "pick",
                    "gaps between uploads": "gap between uploads"}.get(unit, unit)
        text = f"{self.support} {unit}"
        if self.compared_with:
            text += f" against {self.compared_with}"
        return text

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "headline": self.headline,
            "detail": self.detail,
            "channels": list(self.channels),
            "channel_count": len(self.channels),
            "of_channels": self.of_channels,
            "support": self.support,
            "support_unit": self.support_unit,
            "support_note": self.support_note,
            "compared_with": self.compared_with,
            "scope": self.scope,
            "scope_note": self.scope_note,
            "confidence": self.confidence,
            "usable": self.usable,
            "notes": list(self.notes),
        }


@dataclass
class Synthesis:
    """Everything one fetch supports across its videos, and what it could not check."""

    headline: str = ""
    findings: list[Finding] = field(default_factory=list)
    # What could not be assessed and why. Never empty — see `CANNOT_BE_MEASURED`.
    not_assessed: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    videos_considered: int = 0
    outliers_considered: int = 0
    picks_considered: int = 0

    @property
    def usable_findings(self) -> list[Finding]:
        return [item for item in self.findings if item.usable]

    @property
    def thin_findings(self) -> list[Finding]:
        return [item for item in self.findings if not item.usable]

    def as_dict(self) -> dict:
        """Two lists, not one flag to filter on.

        A caller handed a single list plus a boolean renders them the same way roughly
        half the time, and a two-video coincidence printed beside a twelve-video pattern
        in the same typeface is the whole failure. Splitting them here means the honest
        rendering is the easy one.
        """
        return {
            "headline": self.headline,
            "findings": [item.as_dict() for item in self.usable_findings],
            "thin": [item.as_dict() for item in self.thin_findings],
            "not_assessed": list(self.not_assessed),
            "channels": list(self.channels),
            "videos": self.videos_considered,
            "outliers": self.outliers_considered,
            "picks": self.picks_considered,
        }


def _confidence(support: int, channels: int) -> str:
    """How much of a generalisation a finding is, from the two numbers that decide it.

    Support alone is not enough and channel count alone is not either: forty videos off
    one channel is a confident statement about one channel, and one video each from three
    channels is three coincidences. High needs both.
    """
    if support < MIN_SUPPORT:
        return "low"
    if channels >= MIN_CHANNELS_FOR_CONVENTION:
        return "high"
    return "medium"


def _scope(channels: int) -> str:
    if channels >= MIN_CHANNELS_FOR_CONVENTION:
        return SCOPE_CONVENTION
    if channels >= 2:
        return SCOPE_SHARED
    return SCOPE_CHANNEL


def _finding(kind: str, headline: str, *, channels: list[str], support: int,
             of_channels: int, detail: str = "", compared_with: int = 0,
             notes: tuple[str, ...] | list[str] = (), support_unit: str = "videos",
             scope: str = "", confidence: str = "") -> Finding:
    """Build a finding with its scope and confidence derived rather than asserted.

    The two overrides exist for `SCOPE_PICKS`, which is not a generalisation from a
    sample at all — it is a measurement of videos somebody named — and so is not subject
    to the support threshold that stops a sample of two being called a pattern.
    """
    return Finding(
        kind=kind, headline=headline, detail=detail,
        channels=list(channels), of_channels=of_channels,
        support=support, support_unit=support_unit, compared_with=compared_with,
        scope=scope or _scope(len(channels)),
        confidence=confidence or _confidence(support, len(channels)),
        notes=list(notes),
    )


# ------------------------------------------------------------------------- plumbing


def _display_names(videos: list[VideoStat]) -> dict[str, str]:
    """channel key -> the name to print for it.

    `outliers._channel_key` is imported rather than re-derived, and that is not laziness.
    Two spellings of one channel — a listing read with the API and a single video read off
    its own page — must group here exactly as they group in the scoring. A second opinion
    about what makes two channels the same would eventually count one channel twice, and a
    finding supported by one channel counted twice is reported as a convention.
    """
    names: dict[str, str] = {}
    for video in videos:
        key = _channel_key(video)
        if key not in names or (not names[key] and video.channel):
            names[key] = video.channel or ""
    return {key: name or UNNAMED for key, name in names.items()}


def _name_of(video: VideoStat, names: dict[str, str]) -> str:
    return names.get(_channel_key(video), UNNAMED)


def _distinct(videos: list[VideoStat], names: dict[str, str]) -> list[str]:
    """The channels these videos came from, first seen first, no repeats."""
    out: list[str] = []
    for video in videos:
        name = _name_of(video, names)
        if name not in out:
            out.append(name)
    return out


def _grouped(videos: list[VideoStat], names: dict[str, str]) -> dict[str, list[VideoStat]]:
    groups: dict[str, list[VideoStat]] = {}
    for video in videos:
        groups.setdefault(_name_of(video, names), []).append(video)
    return groups


def _moment(video: VideoStat) -> datetime:
    """`published_at`, always timezone-aware.

    `VideoStat.age_days` quietly assumes UTC for a naive timestamp, and subtracting a
    naive datetime from an aware one raises instead of assuming anything — so one pasted
    row without a zone would take the cadence pass out for the whole fetch. Same
    assumption as the scorer makes, made in the same direction.
    """
    published = video.published_at
    return published if published.tzinfo else published.replace(tzinfo=UTC)


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 60:.0f} min"


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _direction(ratio: float, shift: float) -> str:
    if ratio >= 1 + shift:
        return "longer"
    if ratio <= 1 / (1 + shift):
        return "shorter"
    return "no different"


def _split(videos: list[VideoStat], found: list[Outlier], *,
           now: datetime | None) -> tuple[list[VideoStat], list[VideoStat], list[VideoStat]]:
    """`(outliers, the ordinary uploads, the operator's picks)`.

    Three details, each of which changes the answer:

    * **The outliers are the ones that cleared the bar**, not everything `find_outliers`
      returned — a pasted video is kept in that list whatever it measured, and a 0.4x
      video counted as an outlier would drag every median below toward the ordinary.
    * **The rest excludes the picks.** They were chosen because somebody believed they
      outperformed, so leaving them among the ordinary uploads biases exactly the
      comparison group the outliers are being measured against. Same reasoning as
      `outliers.baselines`, one layer up.
    * **The rest excludes videos too young to have been scored.** A video the scorer would
      not judge is a video this must not quietly file under "did not outperform"; it might
      yet.

    What stays in the rest is everything that did not come back an outlier, including
    videos whose cohort was too small to score. For describing how ordinary uploads are
    titled and how long they run, that is the right population — the question is what the
    channel normally does, not which of them are secretly good.
    """
    cleared = [item.video for item in found if item.band != "normal"]
    lifted = {video.video_id for video in cleared}
    rest = [
        video for video in videos
        if video.video_id not in lifted and not video.is_priority
        and video.age_days(now) >= MIN_AGE_DAYS
    ]
    picks = [video for video in videos if video.is_priority]
    return cleared, rest, picks


# ------------------------------------------------------------------------- duration


def _duration_findings(outliers: list[VideoStat], rest: list[VideoStat],
                       names: dict[str, str], of_channels: int) -> list[Finding]:
    """How long the outliers run against how long the ordinary uploads run.

    Per cohort, always. A 45-second Short and a 20-minute documentary in one median
    produce a number that describes neither, and every channel that posts both would come
    back with a "typical length" no video of theirs has ever been.
    """
    out: list[Finding] = []
    for cohort, label in (("long", "long-form"), ("short", "Shorts")):
        timed = [v for v in outliers if v.cohort == cohort and v.duration_seconds > 0]
        others = [v for v in rest if v.cohort == cohort and v.duration_seconds > 0]
        if len(timed) < 2 or len(others) < MIN_SUPPORT:
            continue

        channels = _distinct(timed, names)
        winner = _median([v.duration_seconds for v in timed])
        usual = _median([v.duration_seconds for v in others])
        if usual <= 0:
            continue
        low = min(v.duration_seconds for v in timed)
        high = max(v.duration_seconds for v in timed)
        # "Between 25 min and 25 min" is what a range reads as when a channel cuts every
        # video to the same length — which is a real and quite common finding, and saying
        # it as a range makes it look like a formatting fault instead.
        span = (f"All {len(timed)} of them run at {_minutes(low)}."
                if _minutes(low) == _minutes(high) else
                f"All {len(timed)} of them run between {_minutes(low)} and "
                f"{_minutes(high)}.")

        direction = _direction(winner / usual, DURATION_SHIFT)
        if direction == "no different":
            out.append(_finding(
                "duration",
                f"Length is not what separates the {label} outliers: "
                f"{_minutes(winner)} against {_minutes(usual)} for the rest.",
                detail=f"{span} A real answer, and worth having before a fetch gets read "
                       f"as saying the winners are the long ones.",
                channels=channels, support=len(timed), of_channels=of_channels,
                compared_with=len(others),
            ))
        else:
            out.append(_finding(
                "duration",
                f"The {label} outliers run {direction} than the ordinary uploads: "
                f"{_minutes(winner)} against {_minutes(usual)}.",
                detail=f"{span} Medians, over {len(timed)} outlier(s) and {len(others)} "
                       f"upload(s) that did not clear the bar.",
                channels=channels, support=len(timed), of_channels=of_channels,
                compared_with=len(others),
            ))

        out += _duration_disagreement(timed, others, names, of_channels, label)
    return out


def _duration_disagreement(timed: list[VideoStat], others: list[VideoStat],
                           names: dict[str, str], of_channels: int,
                           label: str) -> list[Finding]:
    """Channels pointing opposite ways about length, which is a finding in itself.

    Pooled, two channels that disagree cancel into "no difference" and the operator reads
    that as length not mattering. It matters on both of them; it matters in opposite
    directions, and that is the thing to know — there is no single length to copy.
    """
    per_channel: dict[str, str] = {}
    winners = _grouped(timed, names)
    ordinary = _grouped(others, names)
    for name, mine in winners.items():
        theirs = ordinary.get(name, [])
        if len(mine) < 2 or len(theirs) < MIN_SUPPORT:
            continue
        usual = _median([v.duration_seconds for v in theirs])
        if usual <= 0:
            continue
        per_channel[name] = _direction(
            _median([v.duration_seconds for v in mine]) / usual, DURATION_SHIFT
        )

    longer = [name for name, way in per_channel.items() if way == "longer"]
    shorter = [name for name, way in per_channel.items() if way == "shorter"]
    if not (longer and shorter):
        return []

    supporting = [v for v in timed if _name_of(v, names) in (*longer, *shorter)]
    return [_finding(
        "disagreement",
        f"The channels disagree about {label} length: on "
        f"{', '.join(longer)} the outliers run longer than that channel's ordinary "
        f"uploads, on {', '.join(shorter)} they run shorter.",
        detail="Each side is measured against its own channel's uploads, so this is a "
               "real difference between the channels and not a sampling artefact. There "
               "is no one length to copy here — pooled, these two cancel out and the "
               "fetch reads as though length did not matter to either of them.",
        channels=[*longer, *shorter], support=len(supporting),
        of_channels=of_channels, compared_with=len(others), scope=SCOPE_SPLIT,
    )]


# ---------------------------------------------------------------------------- titles

# Shapes that are in the string that was fetched, and nothing that is not. Every one of
# these is a decision the operator can copy into their own title box this afternoon —
# which is the test for whether a title finding is worth computing.
_TITLE_TESTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("open with a number", re.compile(r"^\W*\d")),
    ("ask a question", re.compile(r"\?")),
    ("open with how / why / what", re.compile(r"^\W*(how|why|what|when|where|who)\b", re.I)),
    # A space is required after the separator so hyphenated words — "state-of-the-art" —
    # are not read as a title split in two.
    ("split in two by a colon or a dash", re.compile(r"\S\s*[:–—-]\s+\S")),
    ("put a word in capitals", re.compile(r"\b[A-Z]{3,}\b")),
    ("carry a bracketed tag", re.compile(r"[\[(][^\])]{1,24}[\])]")),
)


def _title_findings(outliers: list[VideoStat], rest: list[VideoStat],
                    names: dict[str, str], of_channels: int) -> list[Finding]:
    """Title shapes that appear among the outliers and not among the rest.

    Over-indexing rather than raw frequency, and that is the whole method. Nine in ten
    titles in a niche have a number in them; reporting "the outliers use numbers" off that
    is true, useless, and indistinguishable in print from a finding that means something.
    What is worth a sentence is a shape the winners use and the ordinary uploads do not.
    """
    if len(outliers) < 2 or len(rest) < MIN_SUPPORT:
        return []

    out: list[Finding] = []
    for label, pattern in _TITLE_TESTS:
        hits = [v for v in outliers if pattern.search(v.title or "")]
        if len(hits) < 2:
            # One video is not a shape. It is a title.
            continue
        theirs = [v for v in rest if pattern.search(v.title or "")]
        lift = len(hits) / len(outliers) - len(theirs) / len(rest)
        if lift < SHARE_LIFT:
            continue
        channels = _distinct(hits, names)
        out.append(_finding(
            "title",
            f"The outliers {label} far more often than the rest: "
            f"{len(hits)} of {len(outliers)} against {len(theirs)} of {len(rest)}.",
            detail="Examples: " + "; ".join(f"“{v.title}”" for v in hits[:3]),
            channels=channels, support=len(hits), of_channels=of_channels,
            compared_with=len(rest),
        ))

    out += _title_length_finding(outliers, rest, names, of_channels)
    return out


def _title_length_finding(outliers: list[VideoStat], rest: list[VideoStat],
                          names: dict[str, str], of_channels: int) -> list[Finding]:
    winner = _median([float(len(v.title or "")) for v in outliers])
    usual = _median([float(len(v.title or "")) for v in rest])
    if not winner or not usual or abs(winner - usual) < TITLE_SHIFT:
        return []
    way = "longer" if winner > usual else "shorter"
    return [_finding(
        "title",
        f"The outliers carry {way} titles: {winner:.0f} characters against "
        f"{usual:.0f} for the uploads that did not clear the bar.",
        detail="Medians of the character count. Worth reading next to the shapes above — "
               "a colon and a subtitle is most of the difference when it goes this way.",
        channels=_distinct(outliers, names), support=len(outliers),
        of_channels=of_channels, compared_with=len(rest),
    )]


# --------------------------------------------------------------------------- cadence


def _cadence_findings(videos: list[VideoStat], outliers: list[VideoStat],
                      names: dict[str, str], of_channels: int,
                      refusals: list[str]) -> list[Finding]:
    """How often each channel posts, and whether the outliers followed a longer gap.

    Refused outright for any channel whose dates were reconstructed from relative labels.
    `keyless` marks every listing date approximate because that is what it is — "3 weeks
    ago" is a 30-day window — and `outliers.APPROXIMATE_DATE_ERROR_DAYS` puts the error at
    ±15 days per date, so a gap between two of them carries a month of slop. That is
    larger than most cadences this would report. A schedule computed from it would be a
    number with no measurement under it, which is the one thing this desk does not print.

    Picks are left in the timeline. A video the operator pasted is still an upload that
    channel made on the day it made it, and dropping it would open a hole in the schedule
    exactly where the interesting videos are.
    """
    out: list[Finding] = []
    cadence: dict[str, float] = {}
    # How many gaps each channel's figure was measured from. This, not the channel count,
    # is what `support` on a cadence finding means — three channels is three names, and
    # the evidence under them is the fifty-odd waits between their uploads.
    gap_counts: dict[str, int] = {}
    ratios: list[tuple[VideoStat, float]] = []
    approximate: list[str] = []
    too_short = 0
    lifted = {video.video_id for video in outliers}

    for name, rows in _grouped(videos, names).items():
        ordered = sorted(rows, key=_moment)
        if len(ordered) <= MIN_GAPS:
            too_short += 1
            continue
        if sum(1 for v in ordered if v.date_is_approximate) > len(ordered) / 2:
            approximate.append(name)
            continue

        gaps = [
            (_moment(later) - _moment(earlier)).total_seconds() / 86400.0
            for earlier, later in pairwise(ordered)
        ]
        usual = _median(gaps)
        if usual <= 0:
            continue
        cadence[name] = usual
        gap_counts[name] = len(gaps)

        # The gap each outlier landed after, as a multiple of that channel's own usual
        # gap. A ratio rather than days, because a week off is a long break on a daily
        # channel and nothing at all on a monthly one — pooling raw days across channels
        # would report the slowest channel's habits as everybody's.
        # `gaps[i]` is the wait before `ordered[i + 1]`, so the later video of each pair
        # is the one the gap belongs to. Pairing it with the earlier one instead would
        # credit every outlier with the break that followed it rather than the one it
        # came out of, which is the opposite claim.
        for later, gap in zip(ordered[1:], gaps, strict=True):
            if later.video_id in lifted:
                ratios.append((later, gap / usual))

    if approximate:
        refusals.append(
            f"Upload cadence on {', '.join(approximate)}: those publish dates were "
            f"reconstructed from labels like “3 weeks ago”, which puts each one "
            f"inside ±{APPROXIMATE_DATE_ERROR_DAYS:g} days. A gap measured between "
            f"two of them carries a month of slop, which is longer than most schedules "
            f"this would report. Configure a YouTube API key in Settings and the dates "
            f"come back measured."
        )
    if too_short and not cadence:
        refusals.append(
            f"Upload cadence: no channel in this fetch has more than {MIN_GAPS} gaps "
            f"between uploads to measure, and two or three gaps is not a schedule."
        )

    out += _cadence_agreement(cadence, gap_counts, of_channels)
    out += _gap_before_finding(ratios, names, of_channels)
    return out


def _cadence_agreement(cadence: dict[str, float], gap_counts: dict[str, int],
                       of_channels: int) -> list[Finding]:
    if not cadence:
        return []
    names = sorted(cadence, key=lambda name: cadence[name])
    support = sum(gap_counts.values())
    spread = max(cadence.values()) / max(min(cadence.values()), 1e-9)
    listing = ", ".join(f"{name} every {cadence[name]:.0f}d" for name in names)

    if len(cadence) == 1:
        (only,) = names
        return [_finding(
            "cadence",
            f"{only} posts every {cadence[only]:.0f} days.",
            detail=f"Median of {support} gaps between uploads. What this is not is the "
                   f"niche's schedule — a second channel in the fetch is what would say "
                   f"whether this is the shape of the niche or of one operator's week.",
            channels=names, support=support, of_channels=of_channels,
            support_unit="gaps between uploads",
        )]

    if spread <= CADENCE_SPREAD:
        return [_finding(
            "cadence",
            f"The channels keep to the same schedule, within a factor of "
            f"{spread:.1f}: {listing}.",
            detail=f"Measured from real timestamps, gap by gap, {support} of them across "
                   f"{len(cadence)} channels. A shared cadence is the cheapest convention "
                   f"to match and the most expensive to be wrong about, since it sets the "
                   f"whole production calendar.",
            channels=names, support=support, of_channels=of_channels,
            support_unit="gaps between uploads",
        )]

    return [_finding(
        "disagreement",
        f"The channels do not share a schedule — {spread:.1f}x between the fastest and "
        f"the slowest: {listing}.",
        detail="So cadence is not what this niche has in common, and matching any one of "
               "these is copying that channel rather than the niche.",
        channels=names, support=support, of_channels=of_channels,
        support_unit="gaps between uploads", scope=SCOPE_SPLIT,
    )]


def _gap_before_finding(ratios: list[tuple[VideoStat, float]], names: dict[str, str],
                        of_channels: int) -> list[Finding]:
    if len(ratios) < 2:
        return []
    values = [ratio for _, ratio in ratios]
    typical = _median(values)
    if typical < GAP_LIFT:
        return []
    supporting = [video for video, ratio in ratios if ratio >= GAP_LIFT]
    if len(supporting) < 2:
        return []
    return [_finding(
        "cadence",
        f"The outliers landed after a longer gap than usual — {typical:.1f}x the "
        f"channel's own typical gap, on {len(supporting)} of {len(ratios)} of them.",
        detail="Each gap is measured against the gap that channel usually leaves, not "
               "against a number of days, so a weekly channel and a monthly one can be "
               "counted together. It says nothing about cause: a video that took longer "
               "to make and a video that got a rested audience look identical from here.",
        channels=_distinct(supporting, names), support=len(supporting),
        of_channels=of_channels, compared_with=len(ratios),
    )]


# ------------------------------------------------------------------------ engagement


def _engagement_findings(outliers: list[VideoStat], rest: list[VideoStat],
                         names: dict[str, str], of_channels: int,
                         refusals: list[str]) -> list[Finding]:
    """Likes and comments per view, where the source carried any.

    The public-page reader carries neither for a channel listing, so on most fetches this
    refuses rather than reports. A zero would be indistinguishable from a video nobody
    engaged with — the same trap `Outlier.as_dict`'s `engagement_known` flag exists to
    avoid one row at a time.
    """
    known = [v for v in outliers if v.likes or v.comments]
    theirs = [v for v in rest if v.likes or v.comments]
    if not known and not theirs:
        refusals.append(
            "Whether the outliers get more likes or comments: this fetch carries no like "
            "or comment counts. The public-page reader does not return them for a channel "
            "listing; a YouTube Data API key in Settings does."
        )
        return []
    if len(known) < 2 or len(theirs) < MIN_SUPPORT:
        return []

    def rate(video: VideoStat) -> float:
        return (video.likes + video.comments) / video.views if video.views else 0.0

    winner = _median([rate(v) for v in known])
    usual = _median([rate(v) for v in theirs])
    if usual <= 0:
        return []
    if winner / usual < ENGAGEMENT_LIFT and usual / max(winner, 1e-9) < ENGAGEMENT_LIFT:
        return []

    way = "more" if winner > usual else "less"
    return [_finding(
        "engagement",
        f"The outliers draw {way} engagement per view: {winner * 100:.1f}% against "
        f"{usual * 100:.1f}%.",
        detail=f"Likes plus comments over views, median of {len(known)} against "
               f"{len(theirs)}. Which way the causation runs is not knowable from here.",
        channels=_distinct(known, names), support=len(known),
        of_channels=of_channels, compared_with=len(theirs),
    )]


# ----------------------------------------------------------------------- the picks


def _pick_findings(picks: list[VideoStat], rest: list[VideoStat], found: list[Outlier],
                   names: dict[str, str], of_channels: int) -> list[Finding]:
    """The operator's own picks against the medians of the channels they came from.

    Confidence is set rather than derived, and this is the one place that is right: these
    are not a sample anybody is generalising from, they are named videos with measured
    numbers. Running them through the support threshold would file a single deliberate
    pick under "too thin to call a pattern", which is true of a pattern and nonsense about
    a measurement.
    """
    if not picks:
        return []

    scored = {item.video.video_id: item for item in found}
    ordinary = _grouped(rest, names)
    fetched_channels = {_channel_key(video) for video in rest}

    lines: list[str] = []
    beat = 0
    cleared = 0
    measured = 0
    for video in picks:
        item = scored.get(video.video_id)
        label = video.title or video.video_id
        if item is None:
            lines.append(f"“{label}”: fetched, but not scored — nothing in this "
                         f"fetch shares its cohort, or it is too new to have a rate yet.")
            continue

        measured += 1
        beat += item.multiple >= 1.0
        cleared += item.band != "normal"

        # Which median the multiple is against, said in the same breath as the multiple.
        # Its own channel is only there when its own channel was fetched; otherwise
        # `find_outliers` measured it against everything read together, and "4.0x its
        # channel's median" followed by a caveat two clauses later is a sentence that
        # contradicts itself — the reader keeps the number and drops the caveat.
        own = _channel_key(video) in fetched_channels
        parts = [f"{item.multiple:.1f}x " + (
            "its channel's median views-per-day" if own else
            "the median of the channels in this fetch — its own channel is not among "
            "them, so add it above for a multiple that is like for like"
        )]

        theirs = [v for v in ordinary.get(_name_of(video, names), [])
                  if v.cohort == video.cohort and v.duration_seconds > 0]
        if video.duration_seconds > 0 and len(theirs) >= MIN_SUPPORT:
            usual = _median([v.duration_seconds for v in theirs])
            way = _direction(video.duration_seconds / usual, DURATION_SHIFT)
            parts.append(
                f"{_minutes(video.duration_seconds)} against a channel median of "
                f"{_minutes(usual)}" + ("" if way == "no different" else f" — {way}")
            )
        lines.append(f"“{label}”: " + ", ".join(parts) + ".")

    if not measured:
        headline = (f"None of your {len(picks)} pick(s) could be measured against a "
                    f"median at all.")
    else:
        # "the median they were measured against" rather than "their channel's", because
        # for a pick whose channel was not fetched those are different medians and the
        # line above is where that is spelled out.
        headline = (f"{beat} of your {measured} measured pick(s) beat the median they "
                    f"were measured against; {cleared} cleared {SOFT_OUTLIER:g}x.")

    return [_finding(
        "picks", headline,
        detail="Each pick is kept out of the median it is measured against, so pasting "
               "your best videos cannot raise the bar they then have to clear.",
        channels=_distinct(picks, names), support=len(picks), of_channels=of_channels,
        support_unit="picks", scope=SCOPE_PICKS, confidence="high",
        notes=lines,
    )]


# ------------------------------------------------------------------------- the pass


def _headline(outliers: list[VideoStat], rest: list[VideoStat],
              supporting: list[str], channels: list[str]) -> str:
    """The sentence above everything else, which has one job beyond counting.

    With one channel in the fetch it has to say that the whole report below is one
    channel's habits — before any of it is read, not in a footnote under it. That is the
    difference between a report somebody acts on correctly and the same report acted on as
    though it described the niche.
    """
    if not outliers and not rest:
        return "Nothing was fetched, so there is nothing to compare."
    if not outliers:
        return (f"Nothing cleared {SOFT_OUTLIER:g}x, so there is no outlier pattern to "
                f"describe. {len(rest)} upload(s) were read and none beat its own "
                f"channel's median by enough to be worth copying — which is an answer, "
                f"not a failure.")
    if len(supporting) <= 1:
        name = supporting[0] if supporting else UNNAMED
        if len(channels) <= 1:
            return (f"{len(outliers)} outlier(s), all on {name} — the only channel in "
                    f"this fetch. Everything below is that one channel's habit, and no "
                    f"amount of arithmetic can turn one channel into a niche pattern. "
                    f"Add competitors above and the same pass will say which of these "
                    f"they share.")
        return (f"{len(outliers)} outlier(s), all of them on {name}; the other "
                f"{len(channels) - 1} channel(s) here produced none. Everything below is "
                f"that one channel's habit.")
    return (f"{len(outliers)} outlier(s) across {len(supporting)} of the "
            f"{len(channels)} channel(s) in this fetch.")


def synthesise(videos: list[VideoStat], found: list[Outlier] | None = None, *,
               now: datetime | None = None) -> Synthesis:
    """What a fetch's videos have in common, across channels and against each other.

    `found` is the scored list the caller already has. It is optional only so a caller
    with raw statistics can ask this directly; when it is omitted the same
    `find_outliers` runs with the same defaults, so there is no second opinion here about
    what counts as an outlier.

    Everything is computed from the numbers in `videos`. There is no provider call, no
    key and no network, so this returns the same answer on a laptop with the wifi off as
    it does in production — which is the only way the findings can be checked by hand.
    """
    if found is None:
        found = find_outliers(videos, now=now)

    outliers, rest, picks = _split(videos, found, now=now)
    names = _display_names(videos)
    channels = _distinct(videos, names)
    supporting = _distinct(outliers, names)

    refusals: list[str] = []
    findings: list[Finding] = []
    of_channels = len(channels)

    timed = [v for v in videos if v.duration_seconds > 0]
    if videos and not timed:
        refusals.append(
            "How long the outliers run: not one row in this fetch carries a duration, so "
            "there is no length to compare. Everything was scored as long-form, which is "
            "the conservative reading and not a measurement."
        )
    elif videos and len(timed) < len(videos):
        refusals.append(
            f"Duration is missing from {len(videos) - len(timed)} of {len(videos)} rows, "
            f"so the length findings below are computed from the {len(timed)} that carry "
            f"one and describe only those."
        )

    if outliers:
        findings += _duration_findings(outliers, rest, names, of_channels)
        findings += _title_findings(outliers, rest, names, of_channels)
        findings += _engagement_findings(outliers, rest, names, of_channels, refusals)
    findings += _cadence_findings(videos, outliers, names, of_channels, refusals)
    findings += _pick_findings(picks, rest, found, names, of_channels)

    if outliers and not [item for item in findings if item.usable and item.kind != "picks"]:
        refusals.append(
            f"Nothing the outliers share that the ordinary uploads do not — not in "
            f"length, title shape, cadence or engagement. With {len(outliers)} outlier(s) "
            f"to look at, that is as likely to be too small a sample as it is to be a "
            f"real absence."
        )

    return Synthesis(
        headline=_headline(outliers, rest, supporting, channels),
        findings=findings,
        not_assessed=[*refusals, *CANNOT_BE_MEASURED],
        channels=channels,
        videos_considered=len(videos),
        outliers_considered=len(outliers),
        picks_considered=len(picks),
    )
