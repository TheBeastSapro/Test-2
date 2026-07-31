"""Applying a motion preset to a rendered scene clip.

This is the seam between the two halves of the visual system: `forgecast.motion`
knows how to animate things, and `forgecast.render` knows what a scene contains.
Neither should know the other's internals, so the mapping lives here.

## Why this is a second pass

The motion elements could in principle be folded into the filtergraph that builds
each scene clip. They are not, for one reason: a scene's base clip is built by one of
three different paths (still with a Ken Burns push, normalised provider video, or a
generated colour card), and each already has a filtergraph tuned to its own problem.
Threading overlays through all three would triple the number of graphs that can break
while making each harder to read. A separate pass costs one extra encode per scene
that actually has motion — a few hundred milliseconds at 720p — and in exchange the
motion layer is testable on its own and cannot break plain rendering.

Scenes with nothing to animate are passed through untouched, so a run with motion
disabled pays nothing at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..motion import MotionPreset
from ..motion import Scene as MotionScene
from ..motion.presets import LIBRARY, by_intensity, get
from .ffmpeg import Scene as RenderScene

log = logging.getLogger("forgecast.render.motion")

# Below this the preset's own hold would exceed the scene and elements would be cut
# off mid-move, which reads worse than no motion at all.
MIN_SCENE_SECONDS = 1.2

# A headline is a phrase, not a sentence. Longer than this and it wraps or shrinks to
# the point where animating it is pointless.
MAX_HEADLINE_CHARS = 42


@dataclass
class MotionPlan:
    """What motion, if any, a scene gets — decided before anything renders."""

    scene_index: int
    kind: str                  # title | lower_third | kinetic | none
    lines: list[str]
    reason: str = ""

    @property
    def active(self) -> bool:
        return self.kind != "none"

    def as_dict(self) -> dict:
        return {"scene": self.scene_index, "kind": self.kind,
                "lines": self.lines, "reason": self.reason}


def resolve_preset(
    name: str = "",
    *,
    intensity: float | None = None,
    directory: Path | str = "./storage/motion_presets",
) -> MotionPreset:
    """Pick the preset for a run: a named one, else the nearest by intensity.

    A name that resolves to nothing is a warning rather than an error. A run that has
    already spent credits on a script and a voiceover should not die because a preset
    was renamed; falling back to the measured intensity gets a video out, and the log
    line says what happened.
    """
    if name:
        try:
            return get(name, directory=directory)
        except KeyError:
            log.warning("motion preset %r not found; falling back to intensity", name)
    if intensity is None:
        return LIBRARY["card_reveal"]
    return by_intensity(intensity)


def plan(scenes: list[RenderScene], *, preset: MotionPreset,
         headline: str = "") -> list[MotionPlan]:
    """Decide what each scene animates.

    The rules are deliberately conservative. Motion graphics earn their place at the
    top of a video and at the moments a viewer needs an anchor; sprinkled onto every
    scene they become wallpaper, and the burned caption track already carries the
    narration. So: a title on the opening scene, a lower third on the scene after it
    when there is something to name, and kinetic type only where the preset is fast
    enough that staged lines match the cutting rhythm.
    """
    plans: list[MotionPlan] = []
    for position, scene in enumerate(scenes):
        if scene.seconds < MIN_SCENE_SECONDS:
            plans.append(MotionPlan(scene.index, "none", [],
                                    f"scene is {scene.seconds:.1f}s"))
            continue

        explicit = scene.meta.get("motion") if isinstance(scene.meta, dict) else None
        if isinstance(explicit, dict) and explicit.get("kind"):
            plans.append(MotionPlan(
                scene.index, str(explicit["kind"]),
                [str(line) for line in (explicit.get("lines") or [])],
                "requested by the planner",
            ))
            continue

        if position == 0 and headline:
            plans.append(MotionPlan(scene.index, "title",
                                    [_trim(headline)], "opening scene"))
        elif position == 1 and headline:
            subhead = _first_phrase(scene.narration)
            plans.append(MotionPlan(scene.index, "lower_third",
                                    [_trim(headline), subhead],
                                    "names the subject early"))
        elif preset.intensity >= 0.7 and scene.narration:
            lines = _stage(scene.narration, scene.seconds, preset)
            plans.append(MotionPlan(
                scene.index, "kinetic" if len(lines) > 1 else "none", lines,
                f"preset intensity {preset.intensity:.2f}",
            ))
        else:
            plans.append(MotionPlan(scene.index, "none", [],
                                    "narration already carried by captions"))
    return plans


def apply(clip_path: Path, out_path: Path, item: MotionPlan, *,
          preset: MotionPreset, seconds: float, width: int = 1280,
          height: int = 720, fps: int = 30, timeout: float = 600.0) -> Path:
    """Render `clip_path` with the plan's elements composited over it."""
    if not item.active or not item.lines:
        return clip_path

    scene = MotionScene(duration=seconds, width=width, height=height, fps=fps,
                        background=clip_path)

    if item.kind == "title":
        # A title lands after the first beat, not on frame one: cutting straight to
        # animated type gives the viewer nothing to read it against.
        start = min(0.4, seconds * 0.15)
        scene.add(*preset.caption(
            item.lines[0], start=start, width=width, height=height,
            duration=min(seconds - start, preset.hold + preset.entry_duration),
            accent=True,
        ))
    elif item.kind == "lower_third":
        start = min(0.5, seconds * 0.2)
        headline, *rest = item.lines
        scene.add(*preset.lower_third(
            headline, rest[0] if rest else "", start=start,
            width=width, height=height,
            duration=min(seconds - start, preset.hold + 1.4),
        ))
    elif item.kind == "kinetic":
        per_line = max(0.6, (seconds - 0.3) / max(1, len(item.lines)))
        scene.add(*preset.kinetic(item.lines, start=0.2, width=width,
                                 height=height, per_line=per_line))
    else:
        return clip_path

    return scene.render(out_path, timeout=timeout)


# ------------------------------------------------------------------- text shaping
#
# On-screen type is not narration. It is read in a glance, so it breaks where the
# language breaks — at clauses and sentences, never at an arbitrary character count.
# "Why deep-sea cables keep breaking: What" and "breaking. The mechanism is" are both
# what a naive character/word split produces, and both look like a bug on screen.

# Longest line that reads comfortably at the preset's type size on a 16:9 frame.
MAX_LINE_CHARS = 34
# A staged line shorter than this is a fragment, not a phrase.
MIN_LINE_CHARS = 8
_CLAUSE_BREAKS = (": ", " — ", " – ", "; ", ". ", ", ")


def _trim(text: str, limit: int = MAX_HEADLINE_CHARS) -> str:
    """Shorten to `limit`, preferring a clause break over a hard cut."""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned

    for separator in _CLAUSE_BREAKS:
        head = cleaned.split(separator)[0].strip()
        if MIN_LINE_CHARS <= len(head) <= limit:
            return head

    # No usable break: fall back to whole words, which at least ends cleanly.
    clipped = cleaned[:limit].rsplit(" ", 1)[0].rstrip(",;:—–-")
    return clipped or cleaned[:limit]


def _first_phrase(narration: str, limit: int = 52) -> str:
    text = str(narration)
    for separator in (". ", "; ", ", "):
        # The separator has to actually be present. Splitting on one that is absent
        # returns the whole string, which then passes the length check and silently
        # turns "take the leading clause" into "take everything".
        if separator not in text:
            continue
        head = text.split(separator)[0]
        if MIN_LINE_CHARS <= len(head) <= limit:
            return head.strip()
    return _trim(text, limit)


def _phrases(text: str) -> list[str]:
    """Break prose into the smallest units that still read as language."""
    units = [" ".join(str(text).split())]
    for separator in (". ", "! ", "? ", "; ", ": ", " — ", " – ", ", "):
        expanded: list[str] = []
        for unit in units:
            parts = unit.split(separator)
            for index, part in enumerate(parts):
                # Keep terminal punctuation on the phrase it belongs to.
                tail = separator.strip() if index < len(parts) - 1 else ""
                piece = (part + tail).strip()
                if piece:
                    expanded.append(piece)
        units = expanded
    return units


def _stage(narration: str, seconds: float, preset: MotionPreset) -> list[str]:
    """Split narration into staged lines, sized so each is on screen long enough.

    Two constraints fight here: a line needs roughly 0.6s to be read at all, and the
    preset's stagger says how fast this style moves. The number of lines is whichever
    constraint is tighter, so a fast preset on a short scene stages fewer lines rather
    than flashing text nobody can read.

    Within that budget, lines are packed from whole phrases. A phrase too long to fit
    is split on words as a last resort — better a long line than a line that starts
    mid-word.
    """
    words = " ".join(str(narration).split()).split(" ")
    if len(words) < 4:
        return []

    phrases = _phrases(narration)
    by_time = max(1, int(seconds / max(0.6, preset.stagger * 2.4)))
    # The word count caps how many lines are worth staging, but a run of short
    # sentences — "Two facts. One cable. Nobody noticed." — is ideal staged material
    # and the word count alone would reject it.
    by_language = max(len(phrases), len(words) // 4)
    line_count = min(4, by_time, by_language)
    if line_count < 2:
        return []

    lines: list[str] = []
    current = ""
    for phrase in phrases:
        candidate = f"{current} {phrase}".strip()
        # Never carry a new sentence onto a line that already ended one. "breaking.
        # The mechanism is" is the kind of line that makes a viewer re-read.
        ends_sentence = current.endswith((".", "!", "?"))
        if current and (ends_sentence or len(candidate) > MAX_LINE_CHARS):
            lines.append(current)
            current = phrase
        else:
            current = candidate
        while len(current) > MAX_LINE_CHARS:
            head = current[:MAX_LINE_CHARS].rsplit(" ", 1)[0]
            if not head:
                break
            lines.append(head)
            current = current[len(head):].strip()
        if len(lines) >= line_count:
            break
    if current and len(lines) < line_count:
        lines.append(current)

    lines = [line for line in lines[:line_count] if len(line) >= 2]
    return lines if len(lines) > 1 else []
