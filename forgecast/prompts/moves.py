"""Camera moves, as fragments a generator understands rather than as free text.

## The gap this closes

`nodes/media.py` asks the planner for a `motion` field — "e.g. slow push in, static, pan
left" — and then appends it to the shot prompt verbatim: `f"{prompt}. Camera: {motion}."`
Nothing validates it, nothing improves it, and nothing knows what any of it means. So a
planner that writes "dramatic sweeping movement" produces exactly that string in the
prompt, and the model does whatever it likes with it.

Meanwhile `skills/data/i2v-prompt-cookbook.md` carries 229 lines of real craft about
this — shot templates, verb banks, per-model fingerprints, failure modes. That document
teaches the *agent*. It has never touched the pipeline, which is still concatenating a
sentence and hoping.

This module is the executable half. Each move carries the fragment that has been found to
work, the shot lengths it needs, and what it is *for* — so the planner picks from a set
instead of inventing prose, and a prompt gets craft rather than a label.

## Why free text still works

`resolve()` matches whatever the planner wrote onto the nearest known move rather than
rejecting it. Three reasons, in order of how much they matter:

* Every existing run, every stored shot list and every channel style already contains
  free text. A validating parser would break all of them at once.
* The planner is a language model. It will write "slowly pushing in" the day after
  something teaches it to write "push_in", and a set that only accepts the second is a
  set that silently falls back to the default forever.
* An unrecognised move should degrade to the quietest sensible camera, not to an error
  several minutes into a paid render.

So the vocabulary is a ratchet, not a gate: whatever arrives is improved as far as it can
be recognised, and anything unrecognisable becomes a slow push in, which is the move that
is wrong least often.

## Why intensity is here

`style.editing` measures a reference's energy and `render.transitions` already reads that
number. A camera move has the same property — a crash zoom and a locked-off tripod are
the same shot at two energies — so the same number selects both, and a channel's cutting
and its camera stop disagreeing with each other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this a move has no room to read as a move. A push-in over 1.5 seconds is a jolt,
# and the generator renders it as a jump rather than as a camera.
MIN_MOVE_SECONDS = 2.5


@dataclass(frozen=True)
class CameraMove:
    """One camera behaviour, and the words that reliably produce it."""

    key: str
    label: str
    # Appended to the shot prompt. Written as an instruction to a camera operator,
    # present tense, with a duration cue — which is the shape the cookbook found models
    # follow most reliably. "Camera slowly pushes in" beats "push-in shot": the first
    # describes an action over time, the second is a noun the model may render as a
    # framing and hold.
    fragment: str
    when_to_use: str
    intensity: float
    # Words a planner might write for this. Matched as substrings, longest first, so
    # "slow push in" cannot be captured by a shorter entry belonging to something else.
    aliases: tuple[str, ...] = ()
    min_seconds: float = MIN_MOVE_SECONDS
    # What a still is animated with when this move is asked for and the shot is an
    # image. Stills default to Ken Burns and are ~10x cheaper than generated video, so
    # most shots take this path — a move with no still equivalent would silently become
    # a static frame on the majority of a video.
    ken_burns: str = "push"


CATALOGUE: tuple[CameraMove, ...] = (
    CameraMove(
        key="static", label="Locked off", intensity=0.0, ken_burns="none",
        fragment="camera is locked off on a tripod, completely still, no movement",
        aliases=("static", "still", "locked", "no movement", "fixed", "tripod"),
        min_seconds=0.0,
        when_to_use="When the subject is doing the moving, and when a talking head or a "
                    "document is on screen. A still camera is not a lazy choice — it is "
                    "the one that lets the viewer read what is in the frame.",
    ),
    CameraMove(
        key="push_in", label="Slow push in", intensity=0.3, ken_burns="push",
        fragment="camera pushes in slowly and steadily over the full shot, a gentle "
                 "dolly toward the subject",
        aliases=("push in", "pushing in", "dolly in", "slow zoom in", "creep in",
                 "move closer", "zoom in slowly"),
        when_to_use="The default, and the reason it is the default: it adds the feeling "
                    "of attention narrowing without asking the viewer to notice a "
                    "camera. Use it under narration that is building an idea.",
    ),
    CameraMove(
        key="pull_out", label="Pull out", intensity=0.35, ken_burns="pull",
        fragment="camera pulls back slowly and steadily over the full shot, revealing "
                 "more of the surroundings",
        aliases=("pull out", "pull back", "dolly out", "zoom out", "widen", "reveal "
                 "wider"),
        when_to_use="Revealing context the viewer did not have — the room the object is "
                    "in, the scale of the thing. Pairs with a narration line that widens "
                    "from one case to the pattern.",
    ),
    CameraMove(
        key="truck", label="Track sideways", intensity=0.4, ken_burns="pan",
        fragment="camera trucks steadily sideways on a dolly, parallel to the subject, "
                 "maintaining distance",
        aliases=("truck", "track", "dolly left", "dolly right", "slide", "lateral",
                 "crab"),
        when_to_use="Moving along something long — a shelf, a queue, a wall, a "
                    "production line. It surveys rather than approaches.",
    ),
    CameraMove(
        key="pan", label="Pan", intensity=0.35, ken_burns="pan",
        fragment="camera pans steadily, rotating on a fixed tripod to sweep across "
                 "the scene",
        aliases=("pan left", "pan right", "panning", "pan across", "pan"),
        when_to_use="Sweeping across something wider than the frame from a fixed "
                    "position. Not a truck: the camera turns where it stands rather "
                    "than travelling, so the foreground and background move at "
                    "different rates and the shot reads as looking rather than moving.",
    ),
    CameraMove(
        key="tilt", label="Tilt", intensity=0.35, ken_burns="pan",
        fragment="camera tilts steadily, pivoting vertically to reveal the height of "
                 "the subject",
        aliases=("tilt up", "tilt down", "tilt", "look up", "look down", "craning up"),
        when_to_use="Height, and the fact of it — a tower, a stack, a wall of "
                    "something. The vertical counterpart of a pan, and the shot that "
                    "makes scale legible without a wide.",
    ),
    CameraMove(
        key="whip_pan", label="Whip pan", intensity=0.9, ken_burns="pan",
        min_seconds=0.0,
        fragment="fast whip pan, camera snapping sideways with heavy motion blur",
        aliases=("whip pan", "whip", "swish pan", "snap pan"),
        when_to_use="A hard change of subject, used as punctuation between two "
                    "unrelated things. Architecture and objects only — a whip pan "
                    "across a face renders as a smear, and both prompt skills say so.",
    ),
    CameraMove(
        key="drift", label="Handheld drift", intensity=0.5, ken_burns="push",
        fragment="subtle handheld movement, small natural drift and breathing, "
                 "documentary feel, not shaky",
        aliases=("handheld", "drift", "organic", "documentary", "subtle movement",
                 "breathing"),
        when_to_use="Anywhere the shot should feel observed rather than composed. The "
                    "cheapest way to stop a generated shot looking generated — a "
                    "perfectly still synthetic frame is the tell.",
    ),
    CameraMove(
        key="orbit", label="Orbit", intensity=0.6, ken_burns="pan", min_seconds=3.5,
        fragment="camera orbits slowly around the subject, smooth arc, subject stays "
                 "centred in frame",
        aliases=("orbit", "arc", "circle", "rotate around", "around the subject"),
        when_to_use="One object that deserves to be understood in three dimensions — a "
                    "machine, a model, a product. Needs a longer shot than most; an "
                    "orbit that only gets two seconds reads as a wobble.",
    ),
    CameraMove(
        key="crane_down", label="Crane down", intensity=0.6, ken_burns="pull",
        min_seconds=3.0,
        fragment="camera cranes down from above, descending smoothly to eye level",
        aliases=("crane", "boom down", "descend", "from above", "top down", "overhead "
                 "to eye"),
        when_to_use="Arriving somewhere. It is the move that says 'here is the place', "
                    "so it belongs at the start of a section rather than inside one.",
    ),
    CameraMove(
        key="fpv", label="FPV flight", intensity=0.85, ken_burns="push",
        min_seconds=3.0,
        fragment="fast FPV drone flight moving continuously forward through the scene, "
                 "low altitude, momentum, motion blur",
        aliases=("fpv", "drone", "fly through", "flythrough", "rush through", "aerial "
                 "fast"),
        when_to_use="Energy, and only where energy is the point. It is loud, it dates "
                    "quickly, and three of them in one video is a showreel rather than "
                    "a documentary.",
    ),
    CameraMove(
        key="crash_zoom", label="Crash zoom", intensity=0.95, ken_burns="push",
        min_seconds=0.0,
        fragment="sudden fast crash zoom in on the subject, abrupt, snapping to a "
                 "tighter frame",
        aliases=("crash zoom", "snap zoom", "punch in", "fast zoom", "whip zoom",
                 "quick zoom"),
        when_to_use="Emphasis on one word or one object, once. It is punctuation, not "
                    "camerawork — used twice in a video it stops meaning anything.",
    ),
)

BY_KEY = {move.key: move for move in CATALOGUE}
DEFAULT_KEY = "push_in"

# Longest alias first, so "slow push in" is not captured by a shorter phrase belonging
# to a different move. Built once rather than sorted per call — `resolve` runs per shot,
# and a video is up to eighty shots.
_ALIASES: tuple[tuple[str, CameraMove], ...] = tuple(sorted(
    ((alias, move) for move in CATALOGUE for alias in (*move.aliases, move.key)),
    key=lambda pair: len(pair[0]), reverse=True))

_WORD = re.compile(r"[^a-z0-9]+")


def _normalise(text: str) -> str:
    return _WORD.sub(" ", str(text or "").lower()).strip()


def resolve(text: str) -> CameraMove:
    """The nearest known move to whatever the planner wrote.

    Never raises and never returns nothing. An unrecognised move becomes a slow push
    in, which is the camera that is wrong least often — see the module docstring on why
    this is a ratchet rather than a gate.
    """
    cleaned = _normalise(text)
    if not cleaned:
        return BY_KEY[DEFAULT_KEY]
    for alias, move in _ALIASES:
        if _normalise(alias) in cleaned:
            return move
    return BY_KEY[DEFAULT_KEY]


def for_intensity(intensity: float) -> CameraMove:
    """The move closest to a measured energy.

    The same number `render.transitions.for_intensity` reads, on purpose: a channel
    whose cutting is calm and whose camera is a crash zoom is two style decisions
    disagreeing inside one video.
    """
    return min(CATALOGUE, key=lambda move: abs(move.intensity - float(intensity)))


def fragment_for(text: str, *, seconds: float = 0.0) -> tuple[CameraMove, str]:
    """The move and the prompt fragment for it, downgraded if the shot is too short.

    A move that needs three seconds and is given one and a half does not render as a
    slower version of itself — it renders as a jump. Downgrading to a locked-off camera
    is the honest outcome, and it is silent in the prompt rather than announced, because
    the prompt is not the place to explain the app's own reasoning.
    """
    move = resolve(text)
    if seconds and move.min_seconds and seconds < move.min_seconds:
        move = BY_KEY["static"]
    return move, move.fragment


def catalogue() -> list[dict]:
    """For the agent and for a settings page: every move with what it is for."""
    return [{"key": move.key, "label": move.label, "intensity": move.intensity,
             "when_to_use": move.when_to_use, "min_seconds": move.min_seconds}
            for move in CATALOGUE]


def planner_vocabulary() -> str:
    """The list handed to the shot planner, so it picks instead of inventing prose.

    Keys and one clause each. The full `when_to_use` would be two thousand characters in
    a prompt that is already carrying a script — and the planner does not need the
    argument, it needs the options.
    """
    lines = [f"  {move.key} — {move.when_to_use.split('.')[0].strip()}."
             for move in CATALOGUE]
    return "One of: " + ", ".join(move.key for move in CATALOGUE) + "\n" + "\n".join(lines)
