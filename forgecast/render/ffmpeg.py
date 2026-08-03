"""ffmpeg wrapper: the one part of the pipeline no vendor does for you.

Everything here is synchronous subprocess work. Callers in async context should
use `asyncio.to_thread`, which is what the render node does.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.render")

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Normalising every intermediate clip to one codec/rate makes concat safe.
VCODEC = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30"]
ACODEC = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


class RenderError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    """Whether both binaries this module shells out to are actually present.

    Checked at the front door rather than at the render node. Without it the desktop
    app looks entirely healthy — research, script and voice all succeed — and then
    fails at the one stage that costs the most to reach.
    """
    return bool(shutil.which(FFMPEG) and shutil.which(FFPROBE))


@dataclass
class Scene:
    """One beat of the video: a visual, how long it holds, and its narration."""

    index: int
    seconds: float
    visual_path: Path | None = None      # still image or video clip
    narration: str = ""
    audio_path: Path | None = None
    meta: dict = field(default_factory=dict)
    # Every plate this scene may cut between, `visual_path` first. A scene that was only
    # ever given one visual leaves this empty and reads as `[visual_path]`, so callers
    # that predate subdivision keep working unchanged.
    plates: list[Path] = field(default_factory=list)

    @property
    def is_video(self) -> bool:
        return self.visual_path is not None and _is_video(self.visual_path)

    def plate(self, index: int) -> Path | None:
        """The plate a shot draws from, falling back to the first one it can use."""
        available = self.plates or ([self.visual_path] if self.visual_path else [])
        usable = [path for path in available if path is not None and path.exists()]
        if not usable:
            return None
        return usable[min(max(index, 0), len(usable) - 1)]


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}


def run_ffmpeg(args: list[str], *, label: str = "ffmpeg") -> None:
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-12:]
        raise RenderError(f"{label} failed (exit {proc.returncode}):\n" + "\n".join(tail))


def ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RenderError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RenderError(f"could not read duration of {path}") from exc


# ----------------------------------------------------------------- synthetic sources


def make_silent_audio(out_path: Path, seconds: float) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t", f"{max(seconds, 0.1):.3f}",
            *ACODEC,
            str(out_path),
        ],
        label="make_silent_audio",
    )
    return out_path


def make_tone_audio(out_path: Path, seconds: float, frequency: int = 220) -> Path:
    """Audible placeholder so a mock render is verifiable by ear, not just by size."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={max(seconds, 0.1):.3f}",
            "-af", "volume=0.08,afade=t=in:d=0.05,afade=t=out:st="
                   f"{max(seconds - 0.15, 0.05):.3f}:d=0.1",
            *ACODEC,
            str(out_path),
        ],
        label="make_tone_audio",
    )
    return out_path


def make_color_clip(
    out_path: Path,
    seconds: float,
    *,
    width: int = 1280,
    height: int = 720,
    color: str = "0x101820",
    label: str = "",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filters = [f"color=c={color}:s={width}x{height}:r=30:d={max(seconds, 0.1):.3f}"]
    args = ["-f", "lavfi", "-i", filters[0]]
    if label:
        safe = _escape_drawtext(label)
        args += [
            "-vf",
            f"drawtext=text='{safe}':fontcolor=white@0.85:fontsize={max(height // 18, 16)}"
            f":x=(w-text_w)/2:y=(h-text_h)/2",
        ]
    args += ["-t", f"{max(seconds, 0.1):.3f}", *VCODEC, "-an", str(out_path)]
    run_ffmpeg(args, label="make_color_clip")
    return out_path


def _escape_drawtext(text: str) -> str:
    cleaned = text.replace("\\", "").replace(":", " -").replace("'", "")
    cleaned = cleaned.replace("%", "").replace("\n", " ")
    return cleaned[:120]


# --------------------------------------------------------------------- clip building


def _punch_crop(punch_in: float) -> str:
    """A centre crop that tightens the framing by `punch_in`, or nothing at 1.0.

    Expressed relative to the input rather than in pixels so it composes with whatever
    scaling the caller already needed. `crop` floors odd results; every chain here ends
    in a scale to the even output size, so that never reaches the encoder.
    """
    if punch_in is None or punch_in <= 1.001:
        return ""
    return f"crop=iw/{punch_in:.4f}:ih/{punch_in:.4f},"


def still_to_clip(
    image_path: Path,
    out_path: Path,
    seconds: float,
    *,
    width: int = 1280,
    height: int = 720,
    ken_burns: bool = True,
    punch_in: float = 1.0,
) -> Path:
    """Animate a still so a slideshow does not look like a slideshow.

    `punch_in` tightens the framing before anything else happens, which is how one plate
    becomes several shots. See `render.cutting` for why a punched shot is rendered with
    `ken_burns=False`: the push would close most of the gap between adjacent framings and
    take the cut below the size at which it is visible at all.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(seconds, 0.2)
    frames = max(int(duration * 30), 2)
    punch = _punch_crop(punch_in)
    if ken_burns:
        # zoompan cost scales with input pixels, so oversample by 1.25x and no more —
        # 2x looks identical after the crop and runs four times slower.
        source_w, source_h = int(width * 1.25) // 2 * 2, int(height * 1.25) // 2 * 2
        zoom_step = round(0.12 / frames, 6)
        vf = (
            f"scale={source_w}:{source_h}:force_original_aspect_ratio=increase,"
            f"crop={source_w}:{source_h},"
            f"{punch}"
            f"zoompan=z='min(zoom+{zoom_step},1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30,"
            f"format=yuv420p"
        )
    else:
        vf = (
            f"{punch}"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )
    run_ffmpeg(
        [
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            # -t MUST stay an output option here. As an input option it caps the looped
            # input at `duration` seconds of frames, and zoompan then multiplies every
            # one of them by d — hundreds of times more frames than the clip needs.
            "-t", f"{duration:.3f}",
            *VCODEC,
            "-an",
            str(out_path),
        ],
        label="still_to_clip",
    )
    return out_path


def normalise_clip(
    src: Path,
    out_path: Path,
    seconds: float,
    *,
    width: int = 1280,
    height: int = 720,
    punch_in: float = 1.0,
    seek: float = 0.0,
) -> Path:
    """Trim/pad a provider clip to the exact scene length and uniform codec.

    `seek` and `punch_in` together turn one clip into several shots. `seek` alone would
    not: consecutive segments of a clip played in order are the clip, with no cut in it.
    The reframe is what the viewer reads as an edit; the seek is what stops the same
    seconds of footage being shown twice.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(seconds, 0.2)
    vf = (
        f"{_punch_crop(punch_in)}"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},format=yuv420p"
    )
    run_ffmpeg(
        [
            # Input-side seek so the decoder skips rather than decodes-and-discards; a
            # shot 50s into a plate should not cost 50s of decoding.
            *(["-ss", f"{seek:.3f}"] if seek > 0 else []),
            "-i", str(src),
            "-vf", vf,
            "-t", f"{duration:.3f}",
            # If the source is short, hold its last frame rather than cutting early.
            "-vsync", "cfr",
            *VCODEC,
            "-an",
            str(out_path),
        ],
        label="normalise_clip",
    )
    actual = ffprobe_duration(out_path)
    if actual < duration - 0.15:
        padded = out_path.with_name(f"{out_path.stem}_padded{out_path.suffix}")
        run_ffmpeg(
            [
                "-i", str(out_path),
                "-vf", f"tpad=stop_mode=clone:stop_duration={duration - actual:.3f}",
                *VCODEC, "-an", str(padded),
            ],
            label="pad_clip",
        )
        padded.replace(out_path)
    return out_path


def concat_clips(clips: list[Path], out_path: Path) -> Path:
    if not clips:
        raise RenderError("nothing to concatenate")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    listing = out_path.with_suffix(".concat.txt")
    listing.write_text(
        "\n".join(f"file '{clip.resolve().as_posix()}'" for clip in clips) + "\n",
        encoding="utf-8",
    )
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out_path)],
        label="concat_clips",
    )
    listing.unlink(missing_ok=True)
    return out_path


def mux(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    run_ffmpeg(
        [
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            *ACODEC,
            "-shortest",
            str(out_path),
        ],
        label="mux",
    )
    return out_path


def overlay_video(base: Path, overlay: Path, out_path: Path, *, scale: float = 0.28,
                  corner: str = "br") -> Path:
    """Picture-in-picture: drop the avatar pass onto the B-roll bed."""
    positions = {
        "br": "main_w-overlay_w-40:main_h-overlay_h-40",
        "bl": "40:main_h-overlay_h-40",
        "tr": "main_w-overlay_w-40:40",
        "tl": "40:40",
    }
    xy = positions.get(corner, positions["br"])
    run_ffmpeg(
        [
            "-i", str(base),
            "-i", str(overlay),
            "-filter_complex",
            f"[1:v]scale=iw*{scale}:-2[pip];[0:v][pip]overlay={xy}:shortest=0[v]",
            "-map", "[v]",
            "-map", "0:a?",
            *VCODEC,
            "-c:a", "copy",
            str(out_path),
        ],
        label="overlay_video",
    )
    return out_path


# ------------------------------------------------------------------------- subtitles


def write_srt(scenes: list[Scene], out_path: Path) -> Path:
    def stamp(total: float) -> str:
        ms = round(total * 1000)
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    cursor = 0.0
    counter = 1
    for scene in scenes:
        for start, end, text in cue_times(scene.narration, scene.seconds):
            lines += [
                str(counter),
                f"{stamp(cursor + start)} --> {stamp(cursor + end)}",
                text,
                "",
            ]
            counter += 1
        cursor += scene.seconds
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# Caption discipline. Two lines maximum — three is unreadable on a phone — and no cue
# held longer than MAX_CUE, because a caption that outlasts the sentence reads as a
# frozen video. The previous version put one cue on screen for a whole scene, so a
# 20-second scene showed the same block of text for 20 seconds.
MAX_LINE_CHARS = 40
MAX_LINES = 2
MAX_CUE_SECONDS = 4.0
MIN_CUE_SECONDS = 1.0
_SENTENCE_END = (". ", "! ", "? ", "; ")


def split_cues(narration: str) -> list[str]:
    """Break narration into blocks that fit two lines, preferring sentence ends."""
    text = " ".join(str(narration).split())
    if not text:
        return []

    budget = MAX_LINE_CHARS * MAX_LINES
    # Sentences first: a caption that breaks where the speaker breathes reads far
    # better than one that breaks where the character count ran out.
    pieces: list[str] = [text]
    for separator in _SENTENCE_END:
        expanded: list[str] = []
        for piece in pieces:
            parts = piece.split(separator)
            for index, part in enumerate(parts):
                tail = separator.strip() if index < len(parts) - 1 else ""
                joined = (part + tail).strip()
                if joined:
                    expanded.append(joined)
        pieces = expanded

    cues: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > budget:
            cues.append(current)
            current = piece
        else:
            current = candidate
        while len(current) > budget:
            head = current[:budget].rsplit(" ", 1)[0]
            if not head:
                break
            cues.append(head)
            current = current[len(head):].strip()
    if current:
        cues.append(current)
    return cues


def cue_times(narration: str, seconds: float) -> list[tuple[float, float, str]]:
    """Time the cues across a scene, weighted by length and clamped for readability.

    Time is shared out by character count rather than evenly: a six-word cue and a
    twenty-word cue do not take the same time to say, and giving them equal slots puts
    the captions out of step with the voice by the end of the scene.
    """
    cues = split_cues(narration)
    if not cues or seconds <= 0:
        return []

    total_chars = sum(len(cue) for cue in cues) or 1
    timings: list[tuple[float, float, str]] = []
    cursor = 0.0
    for index, cue in enumerate(cues):
        share = seconds * (len(cue) / total_chars)
        # The last cue absorbs the rounding so captions never run past the scene.
        span = (seconds - cursor) if index == len(cues) - 1 else share
        span = max(min(span, MAX_CUE_SECONDS), min(MIN_CUE_SECONDS, seconds - cursor))
        if span <= 0:
            break
        end = min(cursor + span, seconds)
        timings.append((cursor, end, _wrap(cue, MAX_LINE_CHARS)))
        cursor = end
        if cursor >= seconds:
            break
    return timings


def _wrap(text: str, width: int) -> str:
    words, out, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return "\n".join(out[:MAX_LINES])


def burn_subtitles(video_path: Path, srt_path: Path, out_path: Path) -> Path:
    style = (
        "FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,"
        "BorderStyle=3,Outline=1,Shadow=0,MarginV=42"
    )
    run_ffmpeg(
        [
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_path.resolve().as_posix()}':force_style='{style}'",
            *VCODEC,
            "-c:a", "copy",
            str(out_path),
        ],
        label="burn_subtitles",
    )
    return out_path


# ---------------------------------------------------------------------- orchestration


def _shot_clip(
    scene: Scene, cut, out_path: Path, *, width: int, height: int, subdivided: bool
) -> Path:
    """One visual segment of a scene, from whichever plate the plan assigned it."""
    plate = scene.plate(getattr(cut, "plate_index", 0))
    if plate is None:
        make_color_clip(
            out_path, cut.seconds, width=width, height=height,
            label=scene.narration[:80] or f"scene {scene.index}",
        )
        return out_path

    punch = float(getattr(cut, "punch_in", 1.0) or 1.0)
    if _is_video(plate):
        normalise_clip(
            plate, out_path, cut.seconds, width=width, height=height,
            punch_in=punch, seek=float(getattr(cut, "source_offset", 0.0) or 0.0),
        )
    else:
        still_to_clip(
            plate, out_path, cut.seconds, width=width, height=height,
            # See `render.cutting`: the Ken Burns push ends 12% in, which would leave the
            # next shot's 24% reframe reading as an 11% one — under the size at which a
            # cut is detected at all. The cut carries the motion instead.
            ken_burns=not subdivided,
            punch_in=punch,
        )
    return out_path


def _build_scene_clip(
    scene: Scene, target: Path, cuts: list, *, workdir: Path, width: int, height: int
) -> Path:
    """Build one scene's visual bed, as one clip or as several cut together."""
    if len(cuts) <= 1:
        # The single-shot path stays byte-for-byte what it was: one encode, no concat, and
        # the Ken Burns push still earns its place on a visual nobody cuts away from.
        only = cuts[0] if cuts else None
        if only is not None and scene.plate(only.plate_index) is not None:
            return _shot_clip(
                scene, only, target, width=width, height=height, subdivided=False
            )
        if scene.visual_path and scene.visual_path.exists():
            if scene.is_video:
                normalise_clip(
                    scene.visual_path, target, scene.seconds, width=width, height=height
                )
            else:
                still_to_clip(
                    scene.visual_path, target, scene.seconds, width=width, height=height
                )
        else:
            make_color_clip(
                target, scene.seconds, width=width, height=height,
                label=scene.narration[:80] or f"scene {scene.index}",
            )
        return target

    pieces = [
        _shot_clip(
            scene, cut,
            workdir / f"scene_{scene.index:03d}_shot_{cut.shot_index:03d}.mp4",
            width=width, height=height, subdivided=True,
        )
        for cut in cuts
    ]
    # Stream-copied: every piece came out of the same VCODEC settings, so re-encoding the
    # concat would cost a second generation loss for nothing.
    return concat_clips(pieces, target)


def assemble_video(
    scenes: list[Scene],
    out_path: Path,
    *,
    workdir: Path,
    narration_path: Path | None = None,
    width: int = 1280,
    height: int = 720,
    avatar_path: Path | None = None,
    subtitles: bool = True,
    motion_preset=None,
    motion_plans=None,
    motion_backend: str = "ffmpeg",
    loudness_target: str = "youtube",
    shot_cuts=None,
) -> Path:
    """Turn scenes + narration into one finished file.

    Visual bed -> optional motion graphics -> optional avatar PiP -> narration audio
    -> optional burned captions.

    `motion_preset` and `motion_plans` come from `render.motion_layer`. Both are
    optional and are planned by the caller rather than here, so the node that spends
    the credits also owns the record of what was animated.

    `shot_cuts` comes from `render.cutting` and is what stops a scene being one visual
    held for its whole narration. Absent, every scene is a single shot — the behaviour
    that existed before subdivision — so nothing here has to know whether a caller has
    been updated. Captions and motion graphics still see whole scenes: a cue timed to a
    1-second shot would be unreadable, and a title animating over a scene that cuts
    underneath it is the intended effect rather than a conflict.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    plan_by_scene = {item.scene_index: item for item in (motion_plans or [])}
    cuts_by_scene: dict[int, list] = {}
    for cut in (shot_cuts or []):
        cuts_by_scene.setdefault(cut.scene_index, []).append(cut)

    engine = None
    if motion_preset is not None and plan_by_scene:
        # Imported here, not at module scope: backends imports this module for its
        # Scene type, so a top-level import would be circular.
        from .backends import backend_for

        engine = backend_for(motion_backend)

    clips: list[Path] = []
    for scene in scenes:
        target = workdir / f"scene_{scene.index:03d}.mp4"
        _build_scene_clip(
            scene, target, cuts_by_scene.get(scene.index) or [],
            workdir=workdir, width=width, height=height,
        )

        item = plan_by_scene.get(scene.index)
        if engine is not None and item is not None and item.active:
            target = engine.render(
                target, workdir / f"scene_{scene.index:03d}_motion.mp4", item,
                preset=motion_preset, seconds=scene.seconds,
                width=width, height=height,
            )
        clips.append(target)

    bed = concat_clips(clips, workdir / "bed.mp4")

    if avatar_path and avatar_path.exists():
        bed = overlay_video(bed, avatar_path, workdir / "bed_pip.mp4")

    if narration_path and narration_path.exists():
        staged = mux(bed, narration_path, workdir / "with_audio.mp4")
    else:
        total = sum(scene.seconds for scene in scenes)
        silence = make_silent_audio(workdir / "silence.m4a", total)
        staged = mux(bed, silence, workdir / "with_audio.mp4")

    if subtitles:
        srt = write_srt(scenes, workdir / "captions.srt")
        if srt.stat().st_size > 0:
            staged = burn_subtitles(staged, srt, workdir / "with_captions.mp4")

    # Last, after every pass that could touch the audio. Voice providers disagree on
    # output level by more than 10 dB, so without this one video plays quiet and the
    # next plays hot — and the platform turns the hot one down anyway.
    if loudness_target and loudness_target != "archive":
        from .audio import normalise_video_audio

        try:
            measured = normalise_video_audio(
                staged, workdir / "mastered.mp4", platform=loudness_target,
            )
            if measured is not None and (workdir / "mastered.mp4").exists():
                staged = workdir / "mastered.mp4"
                log.info("mastered to %.2f LUFS (peak %.2f dBFS)",
                         measured.integrated_lufs, measured.true_peak_dbfs)
        except (RenderError, OSError) as exc:
            # An un-mastered video is worse than a mastered one but far better than
            # no video, and every earlier stage has already been paid for.
            log.warning("loudness mastering failed, shipping unmastered: %s", exc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(staged, out_path)
    return out_path
