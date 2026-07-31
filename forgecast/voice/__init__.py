"""Voice casting: suggest voices from the reference, audition them, let a human pick."""

from .audition import render_samples, sample_line
from .casting import VoiceCandidate, VoiceTarget, casting_summary, shortlist, target_from_reference
from .catalogue import STOCK_VOICES, CatalogueVoice, by_name

__all__ = [
    "STOCK_VOICES",
    "CatalogueVoice",
    "VoiceCandidate",
    "VoiceTarget",
    "by_name",
    "casting_summary",
    "render_samples",
    "sample_line",
    "shortlist",
    "target_from_reference",
]
