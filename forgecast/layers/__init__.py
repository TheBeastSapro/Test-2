"""Layers: taking a flat still apart so things can be put behind the subject.

A still is one image and nothing can be behind anything in it. Lift the subject onto its
own layer with an alpha channel and everything behind it becomes addressable — a title
the subject occludes, a background that moves at a different rate, a shadow that sits
correctly. That difference is most of what reads as "edited" rather than "generated".

* `matte` — cut the subject out, and refuse the cutout when it is not good enough.
* `compose` — put things behind it.

The refusal is the part that matters. A fringed matte is more obviously automatic than
no matte at all, so a bad one falls back to the plain still.
"""

from __future__ import annotations

from . import compose, matte
from .compose import Layered, text_behind
from .matte import Matte, cut

__all__ = ["Layered", "Matte", "compose", "cut", "matte", "text_behind"]
