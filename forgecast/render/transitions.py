"""Transitions between shots, from the 58 ffmpeg already has.

## Why this is not a downloaded pack

The obvious way to get "professional transitions" is to buy a pack — Envato, Motion
Array, RocketStock — unzip a few hundred MOV files with alpha, and composite them. Every
one of those is licensed to the person who bought it, usually per seat, usually
forbidding redistribution. Putting them in this repository would mean shipping somebody
else's paid work inside a zip that gets sent to other people, which is the same rule that
keeps the operator's own purchased documents out of the tree.

There is no need. `xfade` has been in ffmpeg since 4.3 and offers 58 transitions —
wipes, slides, circles, dissolves, pixelisation, radial sweeps, squeezes, zooms — all
computed, all resolution-independent, and already on every machine that can render at
all, because the launcher installs ffmpeg before anything else. What a bought pack adds
over these is texture: light leaks, film burns, glitch frames. Those are *footage*, and
footage is what the B-roll budget is for.

So this module is not a renderer. It is the part a pack cannot supply: knowing which of
the 58 to use, and when.

## Named for the cut they make, not for the effect

`xfade` calls one of them `smoothleft`. That says what the pixels do and nothing about
when a person would want it. Every entry below is named for its editorial job — the
question it answers is "what does this cut need to say", because that is the question
the style profile and the agent can actually answer.

The set is deliberately small. Fifty-eight choices is not a library, it is a menu nobody
reads, and a channel that uses thirty different transitions has no style at all — it has
a demo reel. Eleven are here, each earning its place by doing something the others
cannot, and `RETIRED` records the ones left out with the reason, so the next person does
not re-add `distance` believing nobody considered it.

## The duration is the whole craft

A transition's length matters more than its shape. Under about 0.25s nothing reads as a
transition at all — it reads as a glitch. Over about 1.2s in a documentary it reads as a
holiday slideshow. And a transition *consumes* footage: an xfade of `d` seconds overlaps
the two clips, so the finished video is `d` shorter per join. Timings that ignore that
drift out of sync with narration, which is the failure that matters, because narration
is the one track the viewer notices.

`plan()` does that arithmetic and refuses a transition longer than either shot can
afford, downgrading to a hard cut rather than eating a shot whole.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .ffmpeg import RenderError, concat_clips, run_ffmpeg

# Below this a transition reads as a dropped frame rather than as an intention.
MIN_SECONDS = 0.25
# Above this, in the formats this app makes, it reads as a slideshow.
MAX_SECONDS = 1.20
DEFAULT_SECONDS = 0.5

# A shot has to be meaningfully longer than the transition that eats into it. At 2x the
# transition length the shot is half overlap and the viewer never sees it settle.
MIN_SHOT_MULTIPLE = 3.0


@dataclass(frozen=True)
class Transition:
    """One transition, named for the cut it makes."""

    key: str
    # The `xfade` transition name. This is the only vendor-specific string here, so a
    # future GPU or Remotion path substitutes the renderer and keeps the catalogue.
    xfade: str
    label: str
    # When a person would reach for it. This is what the agent and the style profile
    # read, so it describes the edit rather than the pixels.
    use_when: str
    # 0.0 invisible, 1.0 loud. Used to match a channel's measured energy rather than to
    # rank quality — a hard cut is not a worse transition than a zoom, it is a quieter
    # one.
    intensity: float
    seconds: float = DEFAULT_SECONDS


CATALOGUE: tuple[Transition, ...] = (
    Transition(
        key="cut", xfade="", label="Hard cut", intensity=0.0, seconds=0.0,
        use_when="The default, and it should stay the default. Inside a beat, between "
                 "two shots making the same point, a cut is invisible and invisible is "
                 "what you want — every transition that is not a cut is the edit "
                 "announcing itself.",
    ),
    Transition(
        key="soften", xfade="fade", label="Soften", intensity=0.15, seconds=0.4,
        use_when="Two shots of the same subject that would strobe if cut — similar "
                 "framing, similar brightness. It hides the join rather than making one.",
    ),
    Transition(
        key="time_passes", xfade="fadeblack", label="Time passes", intensity=0.35,
        seconds=0.7,
        use_when="A jump forward in time or place. Through black is the oldest grammar "
                 "in film for 'later', and it is legible without being explained.",
    ),
    Transition(
        key="revelation", xfade="fadewhite", label="Revelation", intensity=0.5,
        seconds=0.6,
        use_when="The beat lands on something the viewer did not know. White is louder "
                 "than black and should be rare — twice in an eight-minute video is "
                 "already a lot.",
    ),
    Transition(
        key="advance", xfade="slideleft", label="Advance", intensity=0.4, seconds=0.45,
        use_when="Moving forward through a sequence — the next item, the next year, the "
                 "next step. Direction carries meaning, so keep it consistent: left is "
                 "forward for the whole video or it is noise.",
    ),
    Transition(
        key="go_back", xfade="slideright", label="Go back", intensity=0.4, seconds=0.45,
        use_when="The counterpart to Advance, for returning to something already shown. "
                 "Only meaningful if Advance is being used; on its own it is just a "
                 "slide.",
    ),
    Transition(
        key="reveal_under", xfade="wipeup", label="Reveal underneath", intensity=0.45,
        seconds=0.5,
        use_when="Pulling back a surface to show what was beneath it — the document "
                 "under the summary, the mechanism under the claim.",
    ),
    Transition(
        key="focus_in", xfade="circleclose", label="Focus in", intensity=0.55,
        seconds=0.6,
        use_when="Narrowing from the general to the single instance. It reads as "
                 "attention closing on one thing, which is what the narration is doing "
                 "at that moment.",
    ),
    Transition(
        key="open_out", xfade="circleopen", label="Open out", intensity=0.55,
        seconds=0.6,
        use_when="The reverse: one case opening into the whole picture. Pairs with "
                 "Focus in across a video without either becoming a tic.",
    ),
    Transition(
        key="hard_turn", xfade="pixelize", label="Hard turn", intensity=0.8,
        seconds=0.5,
        use_when="A deliberate break in register — the section where the video stops "
                 "explaining and starts arguing. Loud on purpose, so once per video.",
    ),
    Transition(
        key="press_in", xfade="zoomin", label="Press in", intensity=0.7, seconds=0.5,
        use_when="Escalation inside a beat that is building. It adds energy, so it "
                 "belongs on the rungs where the video is climbing and nowhere else.",
    ),
)

BY_KEY = {item.key: item for item in CATALOGUE}
DEFAULT_KEY = "cut"

# Considered and left out, with the reason. Without this the next person re-adds them,
# because from the ffmpeg list they all look like free variety.
RETIRED = {
    "distance": "reads as a rendering fault rather than a transition",
    "hblur": "indistinguishable from a soft focus pull, which the shot should do itself",
    "squeezev": "distorts faces and text; nothing in this app can guarantee neither is "
                "on screen",
    "radial": "the sweep is a screensaver; it has no editorial meaning to attach to",
    "diagtl": "diagonal wipes date the video to a specific decade of television",
    "hlwind": "beautiful and completely unmotivated — the eye asks why and there is no "
              "answer",
}


@dataclass(frozen=True)
class Join:
    """One boundary between two shots, decided."""

    left_index: int
    transition: Transition
    seconds: float

    @property
    def is_cut(self) -> bool:
        return not self.transition.xfade or self.seconds <= 0


def get(key: str) -> Transition:
    """One transition by key, falling back to a hard cut.

    Never raises. A style profile carrying a name from a newer build, or a typo the
    agent produced, should give the quietest possible edit rather than stopping a render
    that has already been paid for.
    """
    return BY_KEY.get((key or "").strip().lower(), BY_KEY[DEFAULT_KEY])


#: The learned style's transition vocabulary, mapped onto this catalogue's.
#:
#: These are two different vocabularies and nothing joined them, which is the real
#: reason this module went unused. `vision/profile.py` classifies a reference's joins as
#: `cut` or `dissolve` — a binary, because that is what can be measured reliably off
#: decoded frames. This catalogue is named for editorial intent. `get()` never raises
#: and falls back to a hard cut, so a style asking for "dissolve" got silently hard-cut
#: and looked like the feature working.
#:
#: `dissolve` maps to `soften` rather than to anything louder: a measured cross-dissolve
#: is the join being hidden, and `fadeblack` or `zoomin` would be inventing an intent
#: the measurement cannot support.
STYLE_KEYS = {"dissolve": "soften", "fade": "soften", "cut": DEFAULT_KEY}


def from_style(name: str) -> str:
    """A catalogue key for whatever the learned style called it.

    A name already in the catalogue passes through, so an operator or the agent can
    still ask for `time_passes` by name.
    """
    wanted = (name or "").strip().lower()
    if wanted in BY_KEY:
        return wanted
    return STYLE_KEYS.get(wanted, DEFAULT_KEY)


def for_intensity(intensity: float) -> Transition:
    """The transition closest to a measured energy, for a learned style.

    `style.editing` measures cuts per minute and motion; this is how that number
    becomes a choice. Nearest match rather than a threshold table, so a new entry in
    the catalogue is usable immediately.
    """
    return min(CATALOGUE, key=lambda item: abs(item.intensity - float(intensity)))


def plan(durations: list[float], keys: list[str] | None = None, *,
         default: str = DEFAULT_KEY, seconds: float | None = None) -> list[Join]:
    """Decide every boundary, and refuse the ones the shots cannot afford.

    `durations` is each shot's length in seconds. `keys` is the wanted transition per
    boundary — one shorter than `durations` — and anything missing uses `default`.

    The arithmetic is the point. An xfade overlaps its two clips, so a join of `d`
    seconds makes the finished video `d` shorter and pulls everything after it earlier
    against narration that did not move. A transition longer than a shot can afford is
    downgraded to a cut here rather than silently eating the shot, because a shot that
    is entirely transition is not a shot.
    """
    joins: list[Join] = []
    for position in range(max(0, len(durations) - 1)):
        wanted = get((keys[position] if keys and position < len(keys) else "") or default)
        length = float(seconds if seconds is not None else wanted.seconds)

        if not wanted.xfade or length <= 0:
            joins.append(Join(position, BY_KEY[DEFAULT_KEY], 0.0))
            continue

        length = max(MIN_SECONDS, min(MAX_SECONDS, length))
        # Both neighbours have to be able to give up their half of the overlap.
        shortest = min(durations[position], durations[position + 1])
        if shortest < length * MIN_SHOT_MULTIPLE:
            joins.append(Join(position, BY_KEY[DEFAULT_KEY], 0.0))
            continue

        joins.append(Join(position, wanted, round(length, 3)))
    return joins


def shortening(joins: list[Join]) -> float:
    """How much shorter the finished video will be than the sum of its shots.

    Exposed rather than left implicit because the caller has to re-time captions and
    narration against it. A renderer that quietly changes the duration is how a
    voiceover ends up a second ahead by the end of a video.
    """
    return round(sum(join.seconds for join in joins if not join.is_cut), 3)


@lru_cache(maxsize=1)
def available() -> bool:
    """Whether this ffmpeg has `xfade` at all.

    Checked rather than assumed. `xfade` arrived in ffmpeg 4.3, and a machine with a
    distribution build old enough to lack it should get hard cuts and a finished video,
    not a filter-graph error several minutes into a render.
    """
    binary = shutil.which("ffmpeg")
    if not binary:
        return False
    try:
        done = subprocess.run([binary, "-hide_banner", "-h", "filter=xfade"],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):                     # pragma: no cover
        return False
    return "transition" in (done.stdout or "")


def _filter_graph(joins: list[Join], durations: list[float]) -> tuple[str, str]:
    """The xfade chain, as (filter_complex, final_label).

    Built as a left-to-right chain because `xfade` takes exactly two inputs. Each
    `offset` is measured on the *accumulated* timeline, not on the original clip, and
    getting that wrong is the classic failure: offsets computed from raw start times
    drift by the total overlap so far, and the last transition fires after its own clip
    has ended.
    """
    steps: list[str] = []
    current = "[0:v]"
    elapsed = durations[0]

    for position, join in enumerate(joins):
        nxt = f"[{position + 1}:v]"
        label = f"[v{position}]"
        if join.is_cut:
            # Still a concat step, so the chain stays one graph rather than two code
            # paths that have to agree about labels.
            steps.append(f"{current}{nxt}concat=n=2:v=1:a=0{label}")
            elapsed += durations[position + 1]
        else:
            offset = max(0.0, elapsed - join.seconds)
            steps.append(
                f"{current}{nxt}xfade=transition={join.transition.xfade}"
                f":duration={join.seconds}:offset={offset:.3f}{label}")
            elapsed += durations[position + 1] - join.seconds
        current = label

    return ";".join(steps), current


def join_clips(clips: list[Path], joins: list[Join], durations: list[float],
               out_path: Path, *, hold_timeline: bool = True) -> Path:
    """Render the shots into one file, with the planned transitions.

    Falls back to `concat_clips` whenever there is nothing to do — no clips to join, no
    real transition among the joins, or an ffmpeg without `xfade`. That fallback is the
    behaviour this module replaced, so a machine that cannot do transitions produces
    exactly the video it produced before rather than an error.

    `hold_timeline` is on by default and is the difference between a feature and a bug.
    Every overlap makes the bed shorter, and the narration was recorded against the
    unshortened timeline — so a video with eight transitions ends four seconds before
    its own voiceover, and the drift accumulates towards the end where the payoff is.
    Holding the last frame for exactly the total overlap keeps the bed the length
    everything downstream already believes it is. Turn it off only if you are re-timing
    the audio yourself.
    """
    if not clips:
        raise RenderError("nothing to join")
    if len(clips) == 1:
        return concat_clips(clips, out_path)
    if not any(not join.is_cut for join in joins) or not available():
        return concat_clips(clips, out_path)
    if len(durations) != len(clips):                                  # pragma: no cover
        raise RenderError(
            f"{len(durations)} durations for {len(clips)} clips — the plan and the "
            "shots have gone out of step")

    graph, final = _filter_graph(joins, durations)
    argv: list[str] = []
    for clip in clips:
        argv += ["-i", str(clip)]
    lost = shortening(joins)
    if hold_timeline and lost > 0:
        # `tpad` on the end of the chain, holding the final frame. Cheaper and steadier
        # than re-timing every clip, and the held frame is the last shot of the video —
        # which is where a closing line is still being spoken.
        graph = f"{graph};{final}tpad=stop_mode=clone:stop_duration={lost:.3f}[vout]"
        final = "[vout]"

    argv += ["-filter_complex", graph, "-map", final,
             # Re-encoded, unavoidably: an overlap is new pixels, so `-c copy` is not on
             # the table here the way it is for a pure concat.
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-an", str(out_path)]
    run_ffmpeg(argv, label="join_clips")
    return out_path
