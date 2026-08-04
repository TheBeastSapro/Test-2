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

## The fifth correction, for dates that were never measured

Some sources do not give a publish date at all, only a label like "2 months ago", and a
date reconstructed from that can be out by half a month either way. Because the whole
score is views divided by age, an age that is out by 15 days reports a multiple that is
out in exact proportion — badly for a recent video, imperceptibly for an old one.

So a video carrying an approximate date is scored anyway and then checked: if half a
month of error is enough to drop its multiple below the threshold it was included at,
the number is reported with the range it could actually be in, and marked unreliable.
That is a per-video test rather than an age cutoff, because it is the arithmetic that
decides whether the error matters, and for a two-year-old video it never does.

## Several channels at once, and why they never share a median

The desk reads more than one competitor in a fetch, and the tempting shortcut — pool
everything and take one median — is the age mistake again in a different costume. A
50k-a-day channel and a 500-a-day channel pooled together produce a median neither of
them has ever been near: every video on the small channel scores under 1x and every
second video on the big one clears 3x. So the median is per channel, always, and a
video is only ever measured against its own channel's cohort.

## The videos the operator picked out by hand

The desk also takes specific video links alongside the channels — the ones somebody
already believes are the outliers worth copying. Those carry `is_priority` and are
treated differently in exactly two places:

* **They are kept out of every median.** Hand-picked hits dragged into the baseline
  raise the bar they are then measured against, so pasting your five best videos makes
  all five look average — and lowers every other video's multiple at the same time.
  That is a self-defeating merge, and `baselines` refuses it rather than trusting each
  caller to filter first.
* **They rank above the channel's own at the same multiple**, by `PRIORITY_RANK_WEIGHT`
  and no more. The multiple itself is never touched: it is measured, and a weighted
  number printed as a measurement would be a lie in the one column that has to be true.
"""

from __future__ import annotations

import math
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

# How far out a publish date can be when it was reconstructed from a relative label
# rather than measured. Months are the coarsest label a listing shows — "2 months ago"
# covers a 30-day window — so half a month is the worst case, and it is the only input
# the uncertainty below is computed from.
APPROXIMATE_DATE_ERROR_DAYS = 15.0

# What an operator's own pick is worth when ordering the list, and nothing else.
#
# It never touches the multiple, which stays measured. It exists because a video only
# gets into the priority box when somebody looked at it and decided it was the thing
# worth copying, and that decision is evidence the arithmetic does not have: a 4x they
# chose is a better next thing to study than a 6x nobody did.
#
# Two, specifically. Anything larger buries the channel's own strongest video under
# whatever was pasted — and the reason to paste a video is to compare it against that
# channel's best, not to hide it.
PRIORITY_RANK_WEIGHT = 2.0


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
    # True when `published_at` was reconstructed from a relative label rather than
    # measured. A fact about where the row came from, not a judgement about whether it
    # matters — `find_outliers` decides that per video, from the arithmetic.
    date_is_approximate: bool = False
    # True when the operator pasted this video's link themselves rather than it arriving
    # in a channel's listing. Also a fact about where the row came from: it says the
    # video was chosen, which is why it is kept out of the median and ranked above the
    # channel's own at the same multiple.
    is_priority: bool = False

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
    # Equal to `multiple` unless the publish date was approximate, in which case they
    # bracket where it could really be. A UI can print a range instead of a point.
    multiple_low: float = 0.0
    multiple_high: float = 0.0
    # The operator pasted this one. Carried onto the row so a UI can say so — a pasted
    # video that arrives silently among the channel's own is the merge this feature
    # exists to avoid.
    priority: bool = False

    @property
    def rank_score(self) -> float:
        """What this sorts on. The multiple is what it *measured*; these differ.

        Kept apart deliberately, and kept off `as_dict`'s `multiple`: the weight is a
        judgement about whose attention picked the video, and printing a judgement in
        the column that reports arithmetic is how a number stops being trustworthy.
        """
        return self.multiple * (PRIORITY_RANK_WEIGHT if self.priority else 1.0)

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
            "multiple_low": round(self.multiple_low or self.multiple, 2),
            "multiple_high": round(self.multiple_high or self.multiple, 2),
            "date_is_approximate": self.video.date_is_approximate,
            "priority": self.priority,
            "rank_score": round(self.rank_score, 2),
            "band": self.band,
            "engagement_rate": round(self.engagement_rate, 4),
            # A source that carries no like or comment counts computes 0.0, which in a
            # table is indistinguishable from a video nobody engaged with. The flag
            # lets the UI print "not known" instead of a number that was never read.
            "engagement_known": bool(self.video.likes or self.video.comments),
            "reliable": self.reliable,
            "baseline": self.baseline.as_dict(),
            "notes": self.notes,
        }


def _widest(low: float, high: float) -> tuple[str, str]:
    """A range printed so that rounding never contradicts the sentence around it.

    2.97 rounded to one decimal is 3.0, and "anywhere from 3.0x to 4.9x — it may not
    clear 3x at all" reads like a mistake even though the arithmetic is right. Rounding
    the ends outwards keeps the printed interval a superset of the real one, so the
    words and the numbers always agree.
    """
    return f"{math.floor(low * 10) / 10:.1f}", f"{math.ceil(high * 10) / 10:.1f}"


def approximate_date_span(multiple: float, age_days: float) -> tuple[float, float]:
    """The range a multiple could actually be in, if the publish date is a guess.

    views-per-day is views over age, so the multiple is inversely proportional to the
    age and nothing else has to be modelled: an age reported 15 days too low reports a
    rate — and therefore a multiple — too high by exactly `age / (age - 15)`.

    Both ends are clamped at one day, the same clamp `views_per_day` applies, so a
    two-week-old video does not come back with an upper bound of infinity.
    """
    span = max(age_days, 1.0)
    older = max(age_days + APPROXIMATE_DATE_ERROR_DAYS, 1.0)
    younger = max(age_days - APPROXIMATE_DATE_ERROR_DAYS, 1.0)
    return multiple * span / older, multiple * span / younger


def band_for(multiple: float) -> str:
    if multiple >= STRONG_OUTLIER:
        return "strong"
    if multiple >= CLEAR_OUTLIER:
        return "clear"
    if multiple >= SOFT_OUTLIER:
        return "soft"
    return "normal"


def _channel_key(video: VideoStat) -> str:
    """What counts as "the same channel" when grouping.

    Case- and space-folded because the name arrives as a string from whichever source
    read it, and a channel listing read with the API and a single video read from its
    own page must land in one group — otherwise the pasted video is measured against a
    baseline built from an empty set, which is to say against nothing.
    """
    return (video.channel or "").strip().casefold()


def _by_channel(videos: list[VideoStat]) -> dict[str, tuple[str, list[VideoStat]]]:
    """key -> (name as it should be printed, that channel's videos)."""
    grouped: dict[str, tuple[str, list[VideoStat]]] = {}
    for video in videos:
        key = _channel_key(video)
        name, rows = grouped.setdefault(key, (video.channel or "", []))
        rows.append(video)
        # The first non-empty name wins: a pasted table can carry the channel on some
        # rows and not others, and "" as a heading is not a channel anybody recognises.
        if not name and video.channel:
            grouped[key] = (video.channel, rows)
    return grouped


def baselines(
    videos: list[VideoStat], *, now: datetime | None = None,
    min_age_days: float = MIN_AGE_DAYS, min_cohort: int = MIN_COHORT,
) -> dict[str, Baseline]:
    """Median views-per-day per cohort, with an honest reliability flag.

    Median rather than mean, and this is the whole reason the numbers are usable: a
    channel with one 10-million-view video has a mean that no video will ever beat, so
    a mean-based score would report that the channel has never had an outlier. The
    median is unmoved by the outliers it is being used to find.

    Videos the operator pasted by hand are excluded, here rather than in each caller.
    They are picked *because* somebody thinks they outperformed, so letting them into
    the median raises the bar they are about to be measured against — five pasted hits
    on a 40-video channel make all five look average and quietly demote every other
    video on the channel at the same time. A filter one caller can forget is a filter
    that will be forgotten.
    """
    out: dict[str, Baseline] = {}
    for cohort in ("short", "long"):
        rates = [
            video.views_per_day(now) for video in videos
            if video.cohort == cohort and video.age_days(now) >= min_age_days
            and not video.is_priority
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


def baselines_by_channel(
    videos: list[VideoStat], *, now: datetime | None = None,
    min_age_days: float = MIN_AGE_DAYS, min_cohort: int = MIN_COHORT,
) -> dict[str, dict[str, Baseline]]:
    """One set of cohort medians per channel, keyed by the name to print.

    What a UI needs when a fetch read several competitors: a multiple means nothing
    without the number it is a multiple *of*, and with two channels on screen there are
    two such numbers. Showing one pooled figure over a strip of channels is the pooled
    median mistake with a label on it.
    """
    return {
        name or "(unnamed)": baselines(rows, now=now, min_age_days=min_age_days,
                                       min_cohort=min_cohort)
        for name, rows in _by_channel(videos).values()
    }


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

    Each video is measured against *its own channel's* median, so a fetch covering
    several competitors does not compare a small channel to a large one. Videos the
    operator pasted by hand are the two exceptions: they are kept whatever they
    measure — a pick that turns out to be a 1.4x is the answer to the question they
    asked, and dropping it silently is not — and they sort by `rank_score`.
    """
    if not videos:
        return []

    per_channel = {
        key: baselines(rows, now=now, min_age_days=min_age_days, min_cohort=min_cohort)
        for key, (_, rows) in _by_channel(videos).items()
    }
    # Only ever reached by a pasted video whose own channel was not among the ones
    # fetched. Not a substitute for that channel's median and never used as one — a
    # video scored against it says so on the row and is marked unreliable.
    pooled = baselines(videos, now=now, min_age_days=min_age_days,
                       min_cohort=min_cohort)

    found: list[Outlier] = []
    for video in videos:
        age = video.age_days(now)
        if age < min_age_days:
            continue

        base = per_channel.get(_channel_key(video), {}).get(video.cohort)
        borrowed = False
        if (base is None or base.median_views_per_day <= 0) and video.is_priority:
            base, borrowed = pooled[video.cohort], True
        if base is None or base.median_views_per_day <= 0:
            continue
        # A pasted video is scored against whatever baseline exists, soft or not: it was
        # asked about by name, so "here is the number, and here is why it is soft" beats
        # an empty row that reads as the link having failed.
        if not base.reliable and not include_unreliable and not video.is_priority:
            continue

        rate = video.views_per_day(now)
        multiple = rate / base.median_views_per_day
        if multiple < threshold and not video.is_priority:
            continue

        notes: list[str] = []
        reliable = base.reliable
        if not base.reliable:
            notes.append(base.note)
        if borrowed:
            reliable = False
            notes.append(
                "you pasted this one and its channel is not in this fetch, so it is "
                "measured against the median of the channels that are — add its "
                "channel above for a multiple that means something"
            )
        elif video.is_priority and multiple < threshold:
            notes.append(
                f"you pasted this one, so it is here whatever it measured: "
                f"{multiple:.1f}x, under the {threshold:g}x the rest of this list "
                f"had to clear"
            )

        low, high = multiple, multiple
        if video.date_is_approximate:
            low, high = approximate_date_span(multiple, age)
            shown_low, shown_high = _widest(low, high)
            if low < threshold:
                # The verdict this list exists to deliver is "this beat its cohort".
                # If half a month of error can take that away, saying so with the range
                # is the honest report; printing 3.1x alone is a number that looks
                # measured and is not.
                reliable = False
                notes.append(
                    f"the publish date is a guess from a relative label, so this is "
                    f"anywhere from {shown_low}x to {shown_high}x — it may not clear "
                    f"{threshold:g}x at all"
                )
            elif band_for(low) != band_for(high):
                notes.append(
                    f"the publish date is a guess from a relative label: still an "
                    f"outlier, but between {shown_low}x and {shown_high}x, so the band "
                    f"could be either side of the line"
                )

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
            engagement_rate=engagement, reliable=reliable, notes=notes,
            multiple_low=low, multiple_high=high, priority=video.is_priority,
        ))

    found.sort(key=lambda item: item.rank_score, reverse=True)
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
        # Counted separately from the total: "9 outliers" over a list where 3 of them
        # are the operator's own picks is a different report from 9 the desk found.
        "priority": sum(1 for item in found if item.priority),
        "strongest": found[0].as_dict() if found else None,
    }
