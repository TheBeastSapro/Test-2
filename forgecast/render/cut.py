"""Executing a paper edit: the file the plan has been describing.

## Why this exists

`ingest` measures, `edit` decides, `render` executes — and the third verb was missing for
supplied footage. `edit/plan.py` produced a readable, arguable list of what comes out and
why, the approval gate recorded an operator agreeing to it, and then nothing happened.
The approval said so in words: "the kept spans are the plan a cutting stage would execute;
nothing has been cut yet". This is that stage.

It is deliberately its own module rather than another function in `ffmpeg.py`. Everything
there builds a video out of pieces this app generated, at sizes and rates it chose. This
takes somebody else's file, at whatever it happens to be, and removes parts of it — a
different job with a different failure mode, which is that the result is a frame or a
breath away from what the plan said.

## Why it re-encodes

Cutting with `-c copy` cannot start a segment anywhere but a keyframe, so every cut point
moves to the nearest one behind it. Measured on a 16-second test file whose plan asked for
8.84 seconds out: the stream copy produced **14.93 seconds** — it kept nearly everything
the plan removed — and its audio and video no longer described the same edit. That is not
a tolerance, it is a different video. Re-encoding costs a generation and roughly a second
of CPU per ten seconds of 1080p, and it lands on the frame the plan named.

The encode goes through `ffmpeg.vcodec()` for the same reason every other clip in this app
does: `concat_clips` stream-copies, and a file at a rate nothing else uses is a file that
cannot be joined to anything later without its timestamps drifting against its audio.

## Why one pass rather than a piece per keep

The obvious build — extract each keep, concatenate the pieces — was measured and rejected
twice over. Every piece rounds up to a whole frame and the AAC encoder pads the tail of
each one, so a four-cut plan for 8.840s produced 8.954s and a sixty-cut plan would be a
second and a half long. Worse, the two streams accumulate that padding at different rates.

The other tempting build, `select`/`aselect` with a sum of `between()` terms, is one pass
and drifts outright: video is selected by whole frames and audio by whole 1024-sample
packets, so each cut keeps ~21 ms more audio than video. Measured over seven seams, the
sound ended up **175 ms** ahead of the picture — a fifth of a second of lip sync, from a
command that looks completely reasonable.

So: `trim`/`atrim` per keep and the **concat filter**, which joins the two streams at every
seam and therefore cannot let them separate. The same measurement puts the worst skew at
21 ms — under one audio packet, and it does not grow with the number of cuts.

## What it deliberately does not do

It does not decide anything. It takes the spans the plan already fixed, and the only spans
it changes are the ones ffmpeg cannot express (see `spans_for`). It does not grade, caption,
master or re-frame — a cut that quietly also changed the colour would be an edit the
operator never approved.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ffmpeg import (
    ACODEC,
    FFPROBE,
    RenderError,
    ffprobe_duration,
    resolve_fps,
    run_ffmpeg,
    vcodec,
)

log = logging.getLogger("forgecast.render.cut")

# Beyond this the filtergraph goes in a file rather than in an argument. Linux caps a
# single argv entry at 128 KB (MAX_ARG_STRLEN) and a graph runs about 160 bytes per keep,
# so a plan with roughly 800 cuts in it would fail with an errno nobody can read back to
# "your edit had too many cuts in it". `-filter_complex_script` has no such ceiling, and
# the file is also the thing to look at when a graph misbehaves.
GRAPH_IN_FILE_OVER = 2000

PROBE_TIMEOUT = 60


@dataclass
class Cut:
    """One executed edit: what was asked for, what came out, and where it went."""

    source: str
    path: str
    fps: int
    # Measured off the finished file rather than computed from the spans. The whole
    # failure this module guards against is arithmetic that agrees with itself and
    # disagrees with the video, so the number reported is the one ffprobe read back.
    seconds: float
    planned_seconds: float
    original_seconds: float
    spans: list[tuple[float, float]] = field(default_factory=list)
    # Keeps the plan asked for that ffmpeg cannot express, each with the reason. Named
    # rather than silently absorbed: a plan whose arithmetic no longer matches the file
    # has to say which of its decisions was the one that could not be carried out.
    dropped: list[str] = field(default_factory=list)
    has_audio: bool = True

    @property
    def removed_seconds(self) -> float:
        return round(max(0.0, self.original_seconds - self.seconds), 3)

    @property
    def drift(self) -> float:
        """How far the file landed from its own arithmetic, in seconds.

        Nonzero is normal and small — a frame either way at the tail. Large means the
        source disagreed with the plan about its own length, which is what happens when a
        plan is executed against a different file from the one it was measured on.
        """
        return round(self.seconds - self.planned_seconds, 3)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "path": self.path,
            "fps": self.fps,
            "seconds": self.seconds,
            "planned_seconds": self.planned_seconds,
            "original_seconds": self.original_seconds,
            "removed_seconds": self.removed_seconds,
            "drift": self.drift,
            "keeps": len(self.spans),
            "spans": [[round(a, 3), round(b, 3)] for a, b in self.spans],
            "dropped": list(self.dropped),
            "has_audio": self.has_audio,
        }

    def summary(self) -> str:
        return (f"{self.original_seconds:.0f}s → {self.seconds:.1f}s across "
                f"{len(self.spans)} keeps at {self.fps}fps"
                + ("" if self.has_audio else ", silent source"))


def probe(path: Path) -> tuple[float, float, bool]:
    """Duration, frame rate and whether there is any sound, in one call.

    `ingest.probe` reads all of this and more, and is deliberately not used: it is the
    measuring package, it sits above this one, and `ingest.probe` already imports
    `render.ffmpeg`. A cutter that could not run without the measuring package would also
    be a cutter that could not be used on a file somebody handed straight to it.
    """
    done = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format",
         "-show_streams", str(path)],
        capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    if done.returncode != 0:
        raise RenderError(f"{path.name} is not a media file ffmpeg can read: "
                          f"{done.stderr.strip()[:200]}")
    try:
        payload = json.loads(done.stdout or "{}")
    except ValueError as exc:
        raise RenderError(f"ffprobe returned no usable JSON for {path.name}") from exc

    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise RenderError(f"{path.name} has no video stream to cut")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration = float((payload.get("format") or {}).get("duration")
                     or video.get("duration") or 0.0)
    if duration <= 0:
        raise RenderError(f"{path.name} reports no duration")

    rate = str(video.get("avg_frame_rate") or "0")
    try:
        top, _, bottom = rate.partition("/")
        fps = float(top) / float(bottom or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    return round(duration, 3), round(fps, 3), has_audio


def _to_frame(at: float, frame: float) -> float:
    """The nearest frame boundary, with ties always going forward.

    `round` would do this and does not: it is half-to-even, so a keep landing exactly
    between two frames rounds one way at 0.75s and the other way at 2.25s. Two keeps of
    identical length then came out one frame apart, which is a difference nobody can
    explain from the plan they are both written in.
    """
    return round(math.floor(at / frame + 0.5) * frame, 6)


def spans_for(plan: Any, *, fps: int, duration: float
              ) -> tuple[list[tuple[float, float]], list[str]]:
    """The plan's keeps as spans ffmpeg can actually cut on, and what could not be.

    Four things happen here, and each of them is a failure that was observed rather than
    a defensive habit:

    * **Ordered.** The filtergraph is only cheap because the keeps ascend: each `trim`
      throws away every frame outside its window, so the branch for a later keep holds
      nothing while an earlier one is being written. Feed it descending spans and the
      branches waiting their turn buffer decoded frames instead — at 1080p that is 3 MB
      a frame, and the process grows until it is killed.
    * **Merged.** Two overlapping keeps play the overlap twice. A plan should not contain
      any, and `edit.plan` merges its removals for the same reason, but a plan can be
      written by hand or by a model and this is the last place to notice.
    * **Clamped.** A span past the end of the file is silently truncated by ffmpeg, so the
      arithmetic and the file disagree with no complaint from either.
    * **Snapped to the frame grid.** Trimming between two frames means the number of frames
      a keep yields depends on where its edges fell, which is why the unsnapped version of
      a 6.480s plan came out at 6.493s. Snapped, the same plan is exact.

    A keep too short to contain a single frame is dropped and reported. It is not a
    theoretical case: `edit.MIN_KEEP_SECONDS` is 0.25s and safely above it, but a
    hand-written 8 ms keep produced a file with *no video stream at all* and ffmpeg
    exited 0 — a broken output that reads as a successful render.
    """
    frame = 1.0 / max(fps, 1)
    raw = sorted((float(item.start), float(item.end)) for item in plan.kept)

    merged: list[list[float]] = []
    for start, end in raw:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    spans: list[tuple[float, float]] = []
    dropped: list[str] = []
    for start, end in merged:
        start = max(0.0, min(start, duration))
        end = max(0.0, min(end, duration))
        # Snapped by rounding rather than by flooring, so a keep never loses the frame it
        # was built around — the breath either side of a cut is 0.12s and a systematic
        # half-frame bias would eat a fifth of it at every join.
        low = _to_frame(start, frame)
        high = _to_frame(end, frame)
        if high - low < frame * 0.5:
            dropped.append(f"{start:.3f}–{end:.3f}s is shorter than one frame at "
                           f"{fps}fps and would have produced no picture")
            continue
        spans.append((low, high))
    return spans, dropped


def _graph(spans: list[tuple[float, float]], *, audio: bool) -> str:
    """The filtergraph: one trim per keep, joined by the concat filter.

    `setpts=PTS-STARTPTS` on each branch is what makes the pieces joinable — without it
    every segment carries its original timestamps and the concat filter lays them on top
    of one another. The `concat` filter itself is the reason the audio cannot drift: it
    advances both streams by the same segment boundary, so a rounding error at one seam is
    a rounding error and not the beginning of a slope.
    """
    count = len(spans)
    lines = [f"[0:v]split={count}" + "".join(f"[v{i}]" for i in range(count))]
    if audio:
        lines.append(f"[0:a]asplit={count}"
                     + "".join(f"[a{i}]" for i in range(count)))

    tail = []
    for index, (start, end) in enumerate(spans):
        lines.append(f"[v{index}]trim=start={start:.6f}:end={end:.6f},"
                     f"setpts=PTS-STARTPTS[vt{index}]")
        if audio:
            lines.append(f"[a{index}]atrim=start={start:.6f}:end={end:.6f},"
                         f"asetpts=PTS-STARTPTS[at{index}]")
        tail.append(f"[vt{index}][at{index}]" if audio else f"[vt{index}]")

    lines.append("".join(tail)
                 + (f"concat=n={count}:v=1:a=1[v][a]" if audio
                    else f"concat=n={count}:v=1:a=0[v]"))
    return ";".join(lines)


def execute(plan: Any, out_path: Path, *, source: Path | str | None = None,
            fps: int | None = None,
            on_note: Callable[[str], None] | None = None) -> Cut:
    """Cut the file the plan describes, and report what actually came out.

    `source` overrides the path recorded in the plan, for the case where the file has
    moved since it was measured. Everything else comes from the plan: this function makes
    no editorial decision of any kind, which is the property that lets an operator approve
    a plan and get the video it described rather than the video this code preferred.
    """
    say = on_note or (lambda _line: None)

    origin = Path(source) if source else Path(plan.source)
    if not origin.is_file():
        raise RenderError(f"the plan's source is not there any more: {origin}")

    duration, source_fps, has_audio = probe(origin)
    rate = resolve_fps(fps or source_fps or None)
    if fps is None and source_fps and abs(rate - source_fps) > 0.5:
        # Said out loud rather than discovered in the file. The pipeline encodes at 24, 30
        # or 60 because `concat_clips` stream-copies and a fourth rate cannot be joined to
        # the others; conforming a 25fps supplied video to 24 is a real change to somebody
        # else's footage and they should hear it from us.
        say(f"source is {source_fps:g}fps, which this pipeline does not encode — "
            f"conforming to {rate}fps")

    spans, dropped = spans_for(plan, fps=rate, duration=duration)
    for line in dropped:
        say(line)
    if not spans:
        raise RenderError("this plan keeps nothing — there is no video to make from it")

    planned = round(sum(end - start for start, end in spans), 3)
    say(f"cutting {len(spans)} keeps out of {duration:.1f}s "
        f"— {planned:.1f}s at {rate}fps")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph = _graph(spans, audio=has_audio)
    args = ["-i", str(origin)]
    if len(graph) > GRAPH_IN_FILE_OVER:
        script = out_path.with_suffix(".filtergraph.txt")
        script.write_text(graph, encoding="utf-8")
        args += ["-filter_complex_script", str(script)]
    else:
        script = None
        args += ["-filter_complex", graph]

    args += ["-map", "[v]"]
    if has_audio:
        args += ["-map", "[a]", *ACODEC]
    else:
        args += ["-an"]
    args += [*vcodec(rate), str(out_path)]

    try:
        run_ffmpeg(args, label="cut_plan")
    finally:
        if script is not None:
            script.unlink(missing_ok=True)

    made = round(ffprobe_duration(out_path), 3)
    cut = Cut(source=str(origin), path=str(out_path), fps=rate, seconds=made,
              planned_seconds=planned, original_seconds=duration, spans=spans,
              dropped=dropped, has_audio=has_audio)
    if abs(cut.drift) > 1.0 / rate * 2:
        # Logged rather than raised. The file exists and is watchable, and the number that
        # says how far it is from the plan is in the result either way — throwing it away
        # to raise an exception would leave the operator with neither.
        log.warning("cut of %s came out %.3fs from its plan (%.3fs vs %.3fs)",
                    origin.name, cut.drift, made, planned)
    say(f"cut {origin.name}: {cut.summary()}")
    return cut
