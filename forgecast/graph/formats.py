"""Long-form and Shorts as first-class workspaces.

## Why this is a concept and not a filter

A channel making 12-minute documentaries and a channel making 40-second verticals
share almost nothing operationally. Different aspect ratio, different pipeline,
different length, different pacing, different caption discipline, and — the part that
actually matters day to day — different work. Mixing them into one list means every
screen shows twice as much as you need, and every new run starts with two dropdowns
you have to get right before anything happens.

So the format is picked once, at the top, and everything downstream inherits it: the
pipeline, the aspect ratio, the default length, which channels are listed, which runs
are listed. Picking a format is the only navigation decision; after that the app is
about one kind of video.

## Why a channel's format is derived rather than stored

A column would need a migration and could disagree with the channel's own aspect
ratio, and then two screens would tell you different things about the same channel.
The aspect ratio already says which format a channel is for — vertical is a Short,
anything else is not — so that is the single source of truth, and there is nothing to
keep in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

LONGFORM = "longform"
SHORTS = "shorts"


@dataclass(frozen=True)
class Format:
    """One kind of video, and everything that follows from choosing it."""

    slug: str
    label: str
    icon: str
    pipeline: str
    aspect_ratio: str
    default_seconds: int
    blurb: str
    # What a new channel in this format gets, so the create form is pre-shaped.
    length_min: int
    length_max: int

    def as_dict(self) -> dict:
        return {
            "slug": self.slug, "label": self.label, "pipeline": self.pipeline,
            "aspect_ratio": self.aspect_ratio, "default_seconds": self.default_seconds,
        }


FORMATS: dict[str, Format] = {
    LONGFORM: Format(
        slug=LONGFORM,
        label="Long-form",
        icon="▬",
        pipeline="faceless_longform",
        aspect_ratio="16:9",
        default_seconds=480,
        blurb="Narrated 8–12 minute video with generated B-roll and captions.",
        length_min=120,
        length_max=3600,
    ),
    SHORTS: Format(
        slug=SHORTS,
        label="Shorts",
        icon="▮",
        pipeline="faceless_shorts",
        aspect_ratio="9:16",
        default_seconds=45,
        blurb="Vertical hook-first clip under 60 seconds.",
        length_min=15,
        length_max=90,
    ),
}

DEFAULT_FORMAT = LONGFORM

# Which format each shipped pipeline belongs to. A pipeline this does not name falls
# to long-form, which is the conservative answer: a 16:9 workspace shows an unfamiliar
# run rather than hiding it.
_PIPELINE_FORMAT = {
    "faceless_longform": LONGFORM,
    "faceless_shorts": SHORTS,
}

# Aspect ratios that mean "vertical". Everything else is long-form.
_VERTICAL = {"9:16", "4:5", "9:18"}


def get(slug: str | None) -> Format:
    """Resolve a slug, falling back to the default rather than raising.

    A bad slug arrives from a stale bookmark or a hand-typed URL, and the useful
    response to that is the app, not a 404.
    """
    return FORMATS.get(str(slug or "").strip().lower(), FORMATS[DEFAULT_FORMAT])


def format_of_pipeline(pipeline: str) -> str:
    return _PIPELINE_FORMAT.get(str(pipeline), LONGFORM)


def format_of_channel(channel) -> str:
    """A channel belongs to the format its aspect ratio implies."""
    return SHORTS if getattr(channel, "aspect_ratio", "") in _VERTICAL else LONGFORM


def channels_in(channels: list, slug: str) -> list:
    return [item for item in channels if format_of_channel(item) == slug]


def runs_in(runs: list, slug: str) -> list:
    return [item for item in runs if format_of_pipeline(getattr(item, "pipeline", "")) == slug]


def counts(channels: list, runs: list) -> dict[str, dict[str, int]]:
    """Per-format tallies for the nav, so each tab can show what is behind it."""
    return {
        slug: {
            "channels": len(channels_in(channels, slug)),
            "runs": len(runs_in(runs, slug)),
        }
        for slug in FORMATS
    }
