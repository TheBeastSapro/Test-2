"""Local visual analysis: reverse-engineer an editing style from the pixels.

Everything here is deterministic ffmpeg + numpy. No API key, no vendor, no network
once the file is local — which means it is free to run, reproducible, and cannot be
broken by a provider changing its response shape.

    from forgecast.vision import analyse_file
    profile = analyse_file("clip.mp4")
    print(profile.edit_signature)
    print(profile.render_spec.as_dict())
"""

from .acquire import Acquired, AcquireError, acquire
from .audio import AudioAnalysis, BeatAlignment
from .engine import analyse_file, analyse_reference
from .probe import ProbeError, VideoMeta, probe
from .profile import SCHEMA_VERSION, RenderSpec, StyleProfile
from .shots import Shot, ShotAnalysis
from .visual import ColourProfile, FrameSet, MotionProfile, OverlayProfile

__all__ = [
    "SCHEMA_VERSION",
    "AcquireError",
    "Acquired",
    "AudioAnalysis",
    "BeatAlignment",
    "ColourProfile",
    "FrameSet",
    "MotionProfile",
    "OverlayProfile",
    "ProbeError",
    "RenderSpec",
    "Shot",
    "ShotAnalysis",
    "StyleProfile",
    "VideoMeta",
    "acquire",
    "analyse_file",
    "analyse_reference",
    "probe",
]
