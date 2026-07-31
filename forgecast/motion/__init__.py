"""Motion graphics: keyframes, animated elements, and learnable presets.

The layering is deliberate and one-directional:

    keyframe.py   a value over time -> an ffmpeg expression string
    compose.py    elements (text, cards, bands) -> one filtergraph
    presets.py    a *look*, as data, that can be measured off a reference and saved

Nothing here talks to a provider or the database, so a motion look can be built,
rendered and inspected on its own before it is ever wired into a run.
"""

from .compose import Band, Element, ImageCard, Scene, Text
from .keyframe import Keyframe, Track, fade_in, fade_in_out, fade_out
from .presets import (
    LIBRARY,
    MotionPreset,
    available,
    by_intensity,
    derive_from_profile,
    derive_intensity,
    get,
    learn,
)

__all__ = [
    "LIBRARY",
    "Band",
    "Element",
    "ImageCard",
    "Keyframe",
    "MotionPreset",
    "Scene",
    "Text",
    "Track",
    "available",
    "by_intensity",
    "derive_from_profile",
    "derive_intensity",
    "fade_in",
    "fade_in_out",
    "fade_out",
    "get",
    "learn",
]
