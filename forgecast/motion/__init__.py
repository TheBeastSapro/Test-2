"""Motion graphics: keyframes, animated elements, and learnable presets.

The layering is deliberate and one-directional:

    keyframe.py   a value over time -> an ffmpeg expression string
    compose.py    elements (text, cards, bands) -> one filtergraph
    presets.py    a *look*, as data, that can be measured off a reference and saved

Nothing here talks to a provider or the database, so a motion look can be built,
rendered and inspected on its own before it is ever wired into a run.

`geo.py` and `worldmap.py` sit beside that stack rather than inside it. They are the
one thing here that is not an ffmpeg expression: a map is tens of thousands of
primitives a frame, positioned by a projection and clipped at the antimeridian, which
no filtergraph can express. Those two rasterise frames with Pillow and hand back a
clip, so everything downstream treats a map as ordinary footage.
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
from .worldmap import MAP_LIBRARY, Arc, MapSpec, MapStyle, Marker, render_clip, spec_from

__all__ = [
    "LIBRARY",
    "MAP_LIBRARY",
    "Arc",
    "Band",
    "Element",
    "ImageCard",
    "Keyframe",
    "MapSpec",
    "MapStyle",
    "Marker",
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
    "render_clip",
    "spec_from",
]
