"""Keyframes that compile to ffmpeg expressions.

ffmpeg has no timeline. What it has is filters whose parameters can be *expressions*
evaluated per frame, with `t` as the current time in seconds. So an animation here is
not a sequence of operations — it is a piece of arithmetic that happens to describe
motion, and animating something means emitting the right expression string.

A track of keyframes compiles to nested `if(lt(t,…))` clauses. That is verbose but it
is also the only construct guaranteed available, and it evaluates in one pass with no
scripting layer. Easing is applied to the normalised progress inside each segment,
which is why easing is a property of the *segment* rather than of a keyframe.

The expressions are deliberately readable. When a filtergraph fails — and it will,
because ffmpeg's error messages for a bad expression are close to useless — being able
to read the emitted arithmetic is the difference between a five-minute fix and an hour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Easing = Literal["linear", "ease_in", "ease_out", "ease_in_out", "hold"]

# Easing curves as ffmpeg arithmetic on a normalised progress p in 0..1.
# `pow` and the comparison functions are core expression builtins, so these need no
# special ffmpeg build.
_EASINGS: dict[str, str] = {
    "linear": "{p}",
    "ease_in": "pow({p},2)",
    "ease_out": "(1-pow(1-({p}),2))",
    # Smoothstep: gentler than a cubic bezier and far shorter to emit.
    "ease_in_out": "(({p})*({p})*(3-2*({p})))",
    "hold": "0",
}


def _fmt(value: float) -> str:
    """Fixed notation, never scientific — ffmpeg's parser rejects `1e-05`."""
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


@dataclass(frozen=True)
class Keyframe:
    time: float
    value: float
    easing: Easing = "ease_out"


@dataclass
class Track:
    """One animated scalar, e.g. an element's x position or opacity."""

    name: str
    keys: list[Keyframe] = field(default_factory=list)

    def at(self, time: float, value: float, easing: Easing = "ease_out") -> Track:
        self.keys.append(Keyframe(time, value, easing))
        self.keys.sort(key=lambda key: key.time)
        return self

    @property
    def constant(self) -> float | None:
        """The single value, when this track never actually moves."""
        if not self.keys:
            return 0.0
        first = self.keys[0].value
        return first if all(key.value == first for key in self.keys) else None

    def expression(self, *, offset: float = 0.0, scale: float = 1.0) -> str:
        """Compile to an ffmpeg expression in `t`.

        `offset` shifts the whole animation later in the timeline; `scale` multiplies
        the output, which is how a 0..1 normalised track drives a pixel dimension
        without every caller repeating the arithmetic.
        """
        if not self.keys:
            return _fmt(0.0)

        constant = self.constant
        if constant is not None:
            return _fmt(constant * scale)

        clock = f"(t-{_fmt(offset)})" if offset else "t"

        # Build from the last segment backwards so each `if` falls through to the next.
        expression = _fmt(self.keys[-1].value * scale)
        for start, end in reversed(list(zip(self.keys, self.keys[1:], strict=False))):
            span = end.time - start.time
            if span <= 0:
                continue
            progress = f"(({clock}-{_fmt(start.time)})/{_fmt(span)})"
            eased = _EASINGS.get(end.easing, "{p}").format(p=progress)
            delta = (end.value - start.value) * scale
            segment = f"({_fmt(start.value * scale)}+({_fmt(delta)})*{eased})"
            expression = f"if(lt({clock},{_fmt(end.time)}),{segment},{expression})"

        # Before the first keyframe, hold its value rather than extrapolating.
        first = self.keys[0]
        return f"if(lt({clock},{_fmt(first.time)}),{_fmt(first.value * scale)},{expression})"

    def evaluate(self, time: float) -> float:
        """Python-side evaluation, for tests and for previewing without ffmpeg."""
        if not self.keys:
            return 0.0
        if time <= self.keys[0].time:
            return self.keys[0].value
        if time >= self.keys[-1].time:
            return self.keys[-1].value

        for start, end in zip(self.keys, self.keys[1:], strict=False):
            if start.time <= time <= end.time:
                span = end.time - start.time
                if span <= 0:
                    return end.value
                progress = (time - start.time) / span
                eased = _ease_python(end.easing, progress)
                return start.value + (end.value - start.value) * eased
        return self.keys[-1].value


def _ease_python(easing: str, progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    if easing == "linear":
        return progress
    if easing == "ease_in":
        return progress ** 2
    if easing == "ease_out":
        return 1 - (1 - progress) ** 2
    if easing == "ease_in_out":
        return progress * progress * (3 - 2 * progress)
    if easing == "hold":
        return 0.0
    return progress


def fade_in(duration: float = 0.4, *, start: float = 0.0) -> Track:
    return Track("alpha").at(start, 0.0, "linear").at(start + duration, 1.0, "ease_out")


def fade_out(duration: float, *, at: float) -> Track:
    return Track("alpha").at(at, 1.0, "linear").at(at + duration, 0.0, "ease_in")


def fade_in_out(total: float, *, rise: float = 0.35, fall: float = 0.35) -> Track:
    """Present for `total` seconds, easing in and out at the edges."""
    track = Track("alpha").at(0.0, 0.0, "linear").at(rise, 1.0, "ease_out")
    if total > rise + fall:
        track.at(total - fall, 1.0, "hold")
    track.at(max(total, rise + fall), 0.0, "ease_in")
    return track
