"""Conform footage to a reference style.

Takes a source video and a StyleProfile and re-cuts, re-grades and re-frames the
source to match the reference's editing rhythm, keeping the original audio and the
original order of events.

Why the punch-in matters here, concretely: if you re-cut continuous footage at new
boundaries, nothing changes visually at those boundaries — frame N and frame N+1 are
still consecutive source frames, so there is no cut to see and a shot detector will
find none. Progressively tightening the crop across a scene's shots is what turns a
planned boundary into an actual edit. It is standard practice (the punch-in) and here
it is also what makes the applied rhythm measurable.

This doubles as the closed-loop test for the whole system: analyse a reference,
restyle something to match it, analyse the result, and check the numbers converged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .apply import StylePlan, build_plan, caption_margin
from .probe import FFMPEG, ProbeError, VideoMeta, probe, run
from .profile import RenderSpec

log = logging.getLogger("forgecast.vision.restyle")

VCODEC = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30"]


@dataclass
class RestyleResult:
    path: Path
    plan: StylePlan
    shot_count: int
    source: VideoMeta

    def as_dict(self) -> dict:
        return {
            "output": str(self.path),
            "shot_count": self.shot_count,
            "source": self.source.as_dict(),
            "plan": {
                key: value for key, value in self.plan.as_dict().items() if key != "shots"
            },
        }


def restyle(
    source: str | Path,
    spec: RenderSpec,
    out_path: str | Path,
    *,
    workdir: str | Path | None = None,
    beats: list[float] | None = None,
    width: int | None = None,
    height: int | None = None,
    keep_audio: bool = True,
) -> RestyleResult:
    meta = probe(source)
    out_path = Path(out_path)
    workdir = Path(workdir) if workdir else out_path.parent / f".{out_path.stem}_work"
    workdir.mkdir(parents=True, exist_ok=True)

    out_width = width or meta.width
    out_height = height or meta.height
    out_width -= out_width % 2
    out_height -= out_height % 2

    # The source's own runtime is the timeline. Treated as one "scene" unless the
    # caller supplies narration beats, because there is no voiceover structure to
    # respect when conforming existing footage.
    plan = build_plan([meta.duration], spec, beats=beats)
    if not plan.shots:
        raise ProbeError("style plan produced no shots")

    # Calibrate the grade against the source rather than assuming neutral footage:
    # run a candidate filter over a thin frame sample, measure it, correct the
    # residual. Cheap, and it is the difference between a grade that lands on the
    # reference and one that only points in its direction.
    from .grade import calibrate

    grade, source_colour, predicted = calibrate(meta, spec)
    log.info(
        "grade %s: source %s -> predicted brightness %.1f / saturation %.3f",
        grade, source_colour.grade_label(), predicted.brightness, predicted.saturation,
    )

    log.info(
        "restyling %s into %d shots (target %.2fs)",
        meta.path.name, len(plan.shots), spec.target_shot_seconds,
    )

    segments: list[Path] = []
    for index, shot in enumerate(plan.shots):
        target = workdir / f"shot_{index:04d}.mp4"
        crop = max(1.0, shot.punch_in)
        # Crop then scale back up: a tighter crop at the same output size is a
        # push-in, and the framing jump at the boundary is the visible cut.
        chain = (
            f"crop=iw/{crop:.4f}:ih/{crop:.4f},"
            f"scale={out_width}:{out_height},setsar=1"
        )
        if grade:
            chain = f"{chain},{grade}"

        proc = run(
            [
                FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                # -ss before -i seeks fast; re-encoding keeps the cut frame-accurate.
                "-ss", f"{shot.start:.4f}", "-t", f"{shot.duration:.4f}",
                "-i", str(meta.path),
                "-vf", chain, *VCODEC, "-an", str(target),
            ],
            label=f"shot {index}",
            timeout=600,
        )
        if proc.returncode != 0 or not target.exists():
            raise ProbeError(
                f"failed to cut shot {index}: "
                f"{proc.stderr.decode(errors='replace')[-200:]}"
            )
        segments.append(target)

    bed = _concat(segments, workdir / "bed.mp4")

    final = bed
    if keep_audio and meta.has_audio:
        final = _mux(bed, meta.path, workdir / "muxed.mp4")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(final),
         "-c", "copy", str(out_path)],
        label="finalise",
        timeout=600,
    )
    if proc.returncode != 0 or not out_path.exists():
        raise ProbeError(f"could not write {out_path}")

    plan.grade_filter = grade
    return RestyleResult(
        path=out_path, plan=plan, shot_count=len(plan.shots), source=meta
    )


def _concat(segments: list[Path], out_path: Path) -> Path:
    listing = out_path.with_suffix(".txt")
    listing.write_text(
        "\n".join(f"file '{segment.resolve().as_posix()}'" for segment in segments) + "\n",
        encoding="utf-8",
    )
    proc = run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out_path)],
        label="concat",
        timeout=900,
    )
    listing.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_path.exists():
        raise ProbeError(f"concat failed: {proc.stderr.decode(errors='replace')[-200:]}")
    return out_path


def _mux(video: Path, audio_source: Path, out_path: Path) -> Path:
    proc = run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-i", str(audio_source),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path)],
        label="mux",
        timeout=900,
    )
    if proc.returncode != 0 or not out_path.exists():
        raise ProbeError(f"mux failed: {proc.stderr.decode(errors='replace')[-200:]}")
    return out_path


__all__ = ["RestyleResult", "caption_margin", "restyle"]
