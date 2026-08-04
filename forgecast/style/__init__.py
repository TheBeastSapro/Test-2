"""Editing style as a first-class, saveable thing.

`forgecast.vision` measures one video and produces a `StyleProfile`. That is an
observation. This package turns observations into something you can keep, name, apply
to future work, mix with another, and improve on:

    editing.py   EditingStyle — learned from one or more references, saved as JSON
    refine.py    the upgrade pass — named, defensible corrections to a learned baseline
    sound.py     SoundBrief and SoundPlan — what a video's sound should be, and where
                 each cue goes, from the same measurements

The split matters. `learn` is descriptive and must not editorialise: it reports what
the reference actually does, including where the reference is bad. `refine` is
prescriptive and must be explicit: every change it makes is recorded with the reason,
so the difference between "this is how they cut" and "this is how we cut" is always
visible rather than baked in.

`sound` is exported here for a blunter reason: it was written, tested and then reachable
only by its own test, so the app could measure that a reference "runs a bed at 128 BPM,
ducked hard" and still had no way for a render to ask. `nodes.sound` is the caller that
makes it real, and this is the door it comes through.
"""

from .editing import (
    SCHEMA_VERSION,
    EditingStyle,
    available,
    blend,
    delete,
    get,
    learn,
)
from .refine import REFINEMENTS, Refinement, refine
from .sound import SoundBrief, SoundCue, SoundPlan, brief_from, design, recommend

__all__ = [
    "REFINEMENTS",
    "SCHEMA_VERSION",
    "EditingStyle",
    "Refinement",
    "SoundBrief",
    "SoundCue",
    "SoundPlan",
    "available",
    "blend",
    "brief_from",
    "delete",
    "design",
    "get",
    "learn",
    "recommend",
    "refine",
]
