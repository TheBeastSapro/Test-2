"""Deciding what to do with footage, between measuring it and executing on it.

Three verbs, three packages, and this is the middle one:

* `ingest` measures a supplied video — probe, shots, silence, a word-timed transcript.
* `edit` decides — the paper edit, written down before anything is cut.
* `render` executes — the timeline, the transitions, the graphics, the mux.

The middle one was missing, so a decision was either implicit in whichever function ran
next or absent altogether. A professional editor writes the paper edit first and
assembles second; the same order here means the expensive stage is committed to by
something an operator can read and argue with beforehand.
"""

from __future__ import annotations

from . import plan
from .plan import Decision, EditPlan, tighten

__all__ = ["Decision", "EditPlan", "plan", "tighten"]
