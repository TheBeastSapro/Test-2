"""Editing style as a first-class, saveable thing.

`forgecast.vision` measures one video and produces a `StyleProfile`. That is an
observation. This package turns observations into something you can keep, name, apply
to future work, mix with another, and improve on:

    editing.py   EditingStyle — learned from one or more references, saved as JSON
    refine.py    the upgrade pass — named, defensible corrections to a learned baseline

The split matters. `learn` is descriptive and must not editorialise: it reports what
the reference actually does, including where the reference is bad. `refine` is
prescriptive and must be explicit: every change it makes is recorded with the reason,
so the difference between "this is how they cut" and "this is how we cut" is always
visible rather than baked in.
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

__all__ = [
    "REFINEMENTS",
    "SCHEMA_VERSION",
    "EditingStyle",
    "Refinement",
    "available",
    "blend",
    "delete",
    "get",
    "learn",
    "refine",
]
