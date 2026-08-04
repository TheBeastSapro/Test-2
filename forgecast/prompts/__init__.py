"""Turning what is known about a shot into the words a generator acts on.

Two halves, and only the first exists today:

* `moves` — the camera vocabulary. What the planner picks from, and the tested fragment
  each choice contributes to a prompt.
* the analysis-to-prompt bridge — `vision` measures a reference video and `ingest` reads
  a supplied one, and neither has ever written a prompt. That is the gap this package
  exists to close and it is the next thing built here.

Kept apart from `motion/`, which is the on-screen graphics layer — text, bands, cards
composited over a finished frame. That is a renderer. This is prose aimed at somebody
else's model, and the two share nothing but the word.
"""

from __future__ import annotations

from . import moves
from .moves import CameraMove, fragment_for, resolve

__all__ = ["CameraMove", "fragment_for", "moves", "resolve"]
