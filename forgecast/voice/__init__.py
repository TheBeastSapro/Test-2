"""Voice casting: suggest voices from the reference, audition them, let a human pick."""

from .audition import render_samples, sample_line
from .casting import (
    VoiceCandidate,
    VoiceTarget,
    casting_summary,
    shortlist,
    target_from_reference,
)
from .catalogue import STOCK_VOICES, CatalogueVoice, by_name
from .discover import (
    MeasuredVoice,
    build_catalogue,
    load_catalogue,
    measured_summary,
    parse_voice,
)

__all__ = [
    "STOCK_VOICES",
    "CatalogueVoice",
    "MeasuredVoice",
    "VoiceCandidate",
    "VoiceTarget",
    "build_catalogue",
    "by_name",
    "casting_summary",
    "load_catalogue",
    "measured_summary",
    "parse_voice",
    "render_samples",
    "sample_line",
    "shortlist",
    "target_from_reference",
]
