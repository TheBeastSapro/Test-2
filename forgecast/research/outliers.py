"""Finding the videos that beat their cohort, and by how much.

A channel that picks topics by intuition produces well-made videos on random subjects.
The alternative is to look at what actually outperformed recently and work out what is
transferable about it. This module does the measuring half of that; judgement about
*what to make* stays with the operator.

## Why this is arithmetic and not a prompt

Every number here — how much a video beat its peers by, whether a cohort is big enough
to have a meaningful median, whether a video is old enough to score — is computable
from public statistics. Asking a language model to eyeball "is 240k views good for
this channel" produces a confident number with no method behind it, and the errors are
invisible because the output looks the same either way. So: the model chooses topics,
the arithmetic ranks them.

## The four corrections that matter

Naively, `outlier = views / median_views`. That is wrong in four ways, and each one
biases the result in a direction that costs money.

**1. Age.** A video published a year ago has had a year to accumulate views. Comparing
it to last week's upload rewards nothing but survival. Everything is normalised to
views per day, and a video's score is against peers *of similar age*, not all peers.

**2. Format.** Shorts and long-form have completely different view distributions —
mixing them makes every Short look like a triumph and every long-form video look like
a failure. They are scored in separate cohorts, always.

**3. Sample size.** A median over three videos is not a median, it is one of the three
videos. Below a threshold the score is reported as unreliable rather than dressed up
with a number.

**4. Youth.** A video published yesterday has a views-per-day figure dominated by the
initial notification push. Its score will be spectacular and meaningless. Videos below
a minimum age are excluded from both the baseline and the results.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime

# A Short is a Short by duration; platforms have moved the line, so this is the
# conservative version — anything over a minute is scored as long-form.
SHORT_MAX_SECONDS = 60.0

# Below this many videos in a cohort the median is not a summary of anything.
MIN_COHORT = 5

# A video younger than this has a views-per-day figure dominated by the initial push
# to subscribers, not by the algorithm deciding it is good.
MIN_AGE_DAYS = 3.0

# Multiples below this are noise: normal variance between videos on one channel runs
# to 2x without meaning anything.
SOFT_OUTLIER = 3.0
CLEAR_OUTLIER = 5.0
STRONG_OUTLIER = 10.0


@dataclass
class VideoStat:
    """One video's public numbers. Whatever source supplies them."""

    video_id: str
    title: str
    views: int
    published_at: datetime
    duration_seconds: float = 0.0
    channel: str = ""
    channel_subscribers: int = 0
    likes: int = 0
    comments: int = 0

    @property
    def cohort(self) -> str:
        """Which distribution this video belongs to.

        An unknown duration counts as long-form, not as a Short. The naive
        `duration <= 60` reads a missing value as zero and therefore as a Short — which
        matters because most pasted tables have no duration column at all, so *every*
        video would land in the Shorts cohort and the UI would report a "Shorts median"
        computed entirely from long-form videos. One honest cohort beats two mislabelled
        ones.
        """
        if self.duration_seconds <= 0:
            return "long"
        return "short" if self.duration_seconds <= SHORT_MAX_SECONDS else "long"

    def age_days(self, now: datetime | None = None) -> float:
        moment = now or datetime.now(UTC)
        published = self.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return max((moment - published).total_seconds() / 86400.0, 0.0)

    def views_per_day(self, now: datetime | None = None) -> float:
        # Clamped at one day: a video hours old would otherwise divide by a fraction
        # and report millions of views per day.
        return self.views / max(self.age_days(now), 1.0)


@dataclass
class Baseline:
    """What "normal" looks like for one cohort, and whether that is knowable."""

    cohort: str
    median_views_per_day: float
    sample_size: int
    reliable: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "cohort": self.cohort,
            "median_views_per_day": round(self.median_views_per_day, 2),
            "sample_size": self.sample_size,
            "reliable": self.reliable,
            "note": self.note,
        }


@dataclass
class Outlier:
    video: VideoStat
    multiple: float
    baseline: Baseline
    age_days: float
    views_per_day: float
    band: str                      # soft | clear | strong
    engagement_rate: float = 0.0
    reliable: bool = True
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "video_id": self.video.video_id,
            "title": self.video.title,
            "channel": self.video.channel,
            "views": self.video.views,
            "cohort": self.video.cohort,
            "age_days": round(self.age_days, 1),
            "views_per_day": round(self.views_per_day, 1),
            "multiple": round(self.multiple, 2),
            "band": self.band,
            "engagement_rate": round(self.engagement_rate, 4),
            "reliable": self.reliable,
            "baseline": self.baseline.as_dict(),
            "notes": self.notes,
        }


def band_for(multiple: float) -> str:
    if multiple >= STRONG_OUTLIER:
        return "strong"
    if multiple >= CLEAR_OUTLIER:
        return "clear"
    if multiple >= SOFT_OUTLIER:
        return "soft"
    return "normal"


def baselines(
    videos: list[VideoStat], *, now: datetime | None = None,
    min_age_days: float = MIN_AGE_DAYS, min_cohort: int = MIN_COHORT,
) -> dict[str, Baseline]:
    """Median views-per-day per cohort, with an honest reliability flag.

    Median rather than mean, and this is the whole reason the numbers are usable: a
    channel with one 10-million-view video has a mean that no video will ever beat, so
    a mean-based score would report that the channel has never had an outlier. The
    median is unmoved by the outliers it is being used to find.
    """
    out: dict[str, Baseline] = {}
    for cohort in ("short", "long"):
        rates = [
            video.views_per_day(now) for video in videos
            if video.cohort == cohort and video.age_days(now) >= min_age_days
        ]
        if not rates:
            out[cohort] = Baseline(cohort, 0.0, 0, False, "no videos in this cohort")
            continue
        median = statistics.median(rates)
        reliable = len(rates) >= min_cohort and median > 0
        note = ""
        if len(rates) < min_cohort:
            note = (f"only {len(rates)} video(s); a median needs at least "
                    f"{min_cohort} to mean anything")
        elif median <= 0:
            note = "median is zero — every video has no views"
        out[cohort] = Baseline(cohort, median, len(rates), reliable, note)
    return out


def find_outliers(
    videos: list[VideoStat],
    *,
    now: datetime | None = None,
    threshold: float = SOFT_OUTLIER,
    min_age_days: float = MIN_AGE_DAYS,
    min_cohort: int = MIN_COHORT,
    include_unreliable: bool = False,
) -> list[Outlier]:
    """Rank a set of videos by how far each beat its own cohort.

    Returns strongest first. Videos too young to score are dropped, and videos whose
    cohort is too small to have a baseline are dropped unless `include_unreliable`
    asks for them — in which case they carry a note saying why the number is soft.
    """
    if not videos:
        return []

    bases = baselines(videos, now=now, min_age_days=min_age_days,
                      min_cohort=min_cohort)

    found: list[Outlier] = []
    for video in videos:
        age = video.age_days(now)
        if age < min_age_days:
            continue
        base = bases[video.cohort]
        if base.median_views_per_day <= 0:
            continue
        if not base.reliable and not include_unreliable:
            continue

        rate = video.views_per_day(now)
        multiple = rate / base.median_views_per_day
        if multiple < threshold:
            continue

        notes: list[str] = []
        if not base.reliable:
            notes.append(base.note)
        if video.channel_subscribers and video.views > video.channel_subscribers * 20:
            # Worth flagging rather than scoring: views far beyond the subscriber base
            # mean the reach came from recommendation, not from the existing audience.
            notes.append("reach is far beyond the subscriber base — algorithmic, "
                         "not audience")

        engagement = 0.0
        if video.views:
            engagement = (video.likes + video.comments) / video.views

        found.append(Outlier(
            video=video, multiple=multiple, baseline=base, age_days=age,
            views_per_day=rate, band=band_for(multiple),
            engagement_rate=engagement, reliable=base.reliable, notes=notes,
        ))

    found.sort(key=lambda item: item.multiple, reverse=True)
    return found


# ------------------------------------------------------------------- ranking


@dataclass
class Candidate:
    """A topic under consideration, with the numbers used to rank it."""

    topic: str
    source_video_id: str = ""
    outlier_multiple: float = 1.0
    # 0..1. How likely this is to work when executed well.
    confidence: float = 0.5
    # 0..1. Whether the channel can actually make it with what it has.
    feasibility: float = 1.0
    rpm: float = 4.0                 # revenue per thousand views, USD
    production_credits: int = 0
    note: str = ""

    def score(self) -> float:
        """Expected value per unit of production cost.

        Feasibility multiplies rather than adds, deliberately. A brilliant idea the
        channel cannot execute is worth nothing, not "a lot, minus a bit" — and an
        additive model ranks it above a modest idea that could actually ship this week.
        """
        value = (self.outlier_multiple * self.confidence
                 * self.feasibility * max(self.rpm, 0.0))
        # +1 so a free idea does not divide by zero into infinity.
        return value / (self.production_credits + 1)

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "source_video_id": self.source_video_id,
            "outlier_multiple": round(self.outlier_multiple, 2),
            "confidence": round(self.confidence, 3),
            "feasibility": round(self.feasibility, 3),
            "rpm": self.rpm,
            "production_credits": self.production_credits,
            "score": round(self.score(), 4),
            "note": self.note,
        }


def rank(candidates: list[Candidate], *, limit: int = 0) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: item.score(), reverse=True)
    return ordered[:limit] if limit else ordered


def summarise(found: list[Outlier]) -> dict:
    """A compact report, including what was *not* answerable."""
    by_band: dict[str, int] = {}
    for item in found:
        by_band[item.band] = by_band.get(item.band, 0) + 1
    return {
        "count": len(found),
        "by_band": by_band,
        "unreliable": sum(1 for item in found if not item.reliable),
        "strongest": found[0].as_dict() if found else None,
    }
