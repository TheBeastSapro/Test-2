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
# Frame rates this pipeline will encode at, and why the list is short.
#
# 24 is the film rate and reads as film. 30 is the default and the right answer for
# almost everything here. 60 exists because it was asked for, and it is worth being
# straight about what it does and does not buy on this kind of footage:
#
#   * The image-to-video vendors return 24 or 30 natively — WAN returns 16. Encoding
#     those at 60 duplicates frames. It doubles the file and the encode time and adds no
#     information, because there is none to add.
#   * It is genuinely better for high-motion capture — gaming, sport, screen recording —
#     which is not what this pipeline produces.
#   * `motion/paper.py` counts its holds in frames, so a style that steps every third
#     frame steps twice as fast at 60 and reads smoother, which is the one quality it
#     exists to remove. `paper.hold_for_fps` scales it.
#
# So it is offered, with the trade stated, rather than either hidden or recommended.
SUPPORTED_FPS: tuple[int, ...] = (24, 30, 60)
DEFAULT_FPS = 30


def resolve_fps(fps: int | None = None) -> int:
    """The frame rate to encode at, snapped to one this pipeline supports.

    Snapped rather than trusted, because the rate is not only an encoder flag: it is
    baked into filter strings and into the concat. An unsupported value would produce
    pieces at one rate and a stream copy expecting another.
    """
    wanted = int(fps or DEFAULT_FPS)
    if wanted in SUPPORTED_FPS:
        return wanted
    return min(SUPPORTED_FPS, key=lambda option: abs(option - wanted))


# Encoders this pipeline knows how to drive, and what each is for.
#
# Everything here renders locally on the operator's own machine, so the whole cost of a
# render is time — unlike every other stage, which is time *and* a vendor's bill. That
# makes the encoder the one place where somebody's hardware can pay for itself.
#
#   cpu   libx264. The default, and the one that is always present. Quality per bit is
#         still the best of the three and it needs nothing installed.
#   nvidia h264_nvenc. Substantially faster on any NVIDIA card from the last several
#         generations, including small ones — an RTX 3050 cannot generate a single frame
#         of video but encodes one perfectly well, because encoding is a fixed-function
#         block rather than the tensor cores.
#   intel  h264_qsv. The same trade on Intel integrated graphics, which a laptop has
#         whether or not it has anything else.
#
# The trade is real and is not hidden: at a matched quality target, NVENC and QSV produce
# a slightly larger file than x264 for the same look, or a slightly worse look at the same
# size. On an eight-minute 1080p render that is a trade most people would take and some
# would not, which is why it is a setting rather than a default.
ENCODERS: dict[str, dict] = {
    "cpu": {
        "label": "CPU (libx264)",
        "codec": "libx264",
        # Quality-targeted rather than bitrate-targeted, so a still scene costs few bits
        # and a busy one costs more, which is what makes a long video look even.
        "quality": ["-preset", "veryfast", "-crf", "20"],
        "note": "Always available. Best quality per byte, and the slowest.",
    },
    "nvidia": {
        "label": "NVIDIA GPU (NVENC)",
        "codec": "h264_nvenc",
        # `-cq` is NVENC's constant-quality control and is the analogue of `-crf`. `p4`
        # is the middle preset; the fastest ones visibly smear motion, which on Ken Burns
        # pushes and paper-collage steps is exactly where it would show.
        "quality": ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"],
        "note": "Much faster on any NVIDIA card. Slightly larger files for the same look.",
    },
    "intel": {
        "label": "Intel GPU (Quick Sync)",
        "codec": "h264_qsv",
        "quality": ["-preset", "medium", "-global_quality", "23"],
        "note": "Faster on Intel integrated graphics. Slightly larger files.",
    },
}

DEFAULT_ENCODER = "cpu"


def available_encoders() -> dict[str, bool]:
    """Which of them this machine can actually run, proved by encoding a frame.

    A trial encode rather than `ffmpeg -encoders`, and the difference is not academic.
    That listing reports what the binary was *built* with, which on a great many builds
    includes `h264_nvenc` on machines with no NVIDIA driver at all — the encoder is
    listed, is selected, and then fails at the first clip with `Cannot load libcuda.so.1`.
    Picking one that way loses a render minutes in, after a script, a voiceover and
    eighty generated shots have already been paid for.

    It is the same rule `toolchain.install_npm_package` follows about npm: the tool
    saying it succeeded is not evidence that this machine can run what it produced. So
    the question is asked in the only form that answers it — encode one frame of a
    32x32 test pattern and see whether a file comes out.

    Cached, because it shells out once per encoder and a render resolves this per clip.
    """
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE

    found: dict[str, bool] = {}
    for key, spec in ENCODERS.items():
        if spec["codec"] == "libx264":
            # Always present, and probing it would mean a render on a machine with no
            # working encoder at all reported nothing usable rather than the one thing
            # that is.
            found[key] = True
            continue
        found[key] = _encodes(spec)

    _ENCODER_CACHE = found
    return _ENCODER_CACHE


def _encodes(spec: dict) -> bool:
    """Can this encoder produce a frame here, right now.

    Tiny and to the null muxer: 32x32 for one frame is a few milliseconds of work, and
    writing nowhere means the probe cannot leave a file behind on a failure path.
    """
    try:
        done = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=32x32:d=0.04",
             "-c:v", spec["codec"], *spec["quality"],
             "-frames:v", "1", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
            # ffmpeg reads stdin for its interactive keys, and an inherited stdin is
            # whatever the parent had. In a process whose stdin is a live protocol
            # stream — the agent's stdio MCP server is exactly that — it swallows the
            # first bytes of the next message and the peer sees a truncated line. That
            # is not hypothetical: adding this probe broke the MCP handshake test, and
            # the failure looked like a JSON parse error a long way from the cause.
            stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return False
    # Both, because ffmpeg has been seen to exit 0 on an encoder that could not open —
    # the failure lands on stderr and the exit code does not always follow it.
    return done.returncode == 0 and "rror" not in (done.stderr or "")


_ENCODER_CACHE: dict[str, bool] | None = None


def resolve_encoder(name: str = "") -> str:
    """The encoder to use, downgraded to CPU when the asked-for one is not present.

    Downgraded rather than refused, and it is the same argument `render/backends.py`
    makes about the motion renderer: a run that has already spent money must finish. An
    encoder that is missing is a slower render, not a lost one.

    Unlike that case, this downgrade is invisible in the output — the video looks the
    same either way — so it does not need surfacing on a page. It is logged, which is
    what somebody wondering why the render took twenty minutes will read.
    """
    wanted = (name or DEFAULT_ENCODER).strip().lower()
    if wanted not in ENCODERS:
        return DEFAULT_ENCODER
    if available_encoders().get(wanted):
        return wanted
    if wanted != DEFAULT_ENCODER:
        # "could not encode here", not "is not installed". The common case is an ffmpeg
        # built with NVENC on a machine with no NVIDIA driver, where the encoder is
        # present, is listed, and cannot open — so a message naming the build would send
        # somebody to reinstall ffmpeg to fix a driver.
        log.warning("%s could not encode on this machine, so the render is on the CPU. "
                    "The encoder is usually present in the build and missing its driver.",
                    ENCODERS[wanted]["label"])
    return DEFAULT_ENCODER


def vcodec(fps: int | None = None, encoder: str = "") -> list[str]:
    """Encoder settings for one rate.

    Every piece of a render has to come out of this same call. `concat_clips` stream-
    copies rather than re-encoding — a second generation loss for nothing — and a stream
    copy of pieces at mixed frame rates produces a file whose timestamps drift against
    its audio, which shows up as lip-sync slipping later in a long video and nowhere near
    the code that caused it.

    The same is true of the encoder, and more sharply: concatenating an NVENC piece and
    an x264 piece by stream copy produces a file some players stutter on at the join.
    Both have to be settled once, here.
    """
    spec = ENCODERS[resolve_encoder(encoder)]
    return ["-c:v", spec["codec"], *spec["quality"], "-pix_fmt", "yuv420p",
            "-r", str(resolve_fps(fps))]


#: The default settings, for the callers that have no per-run rate to honour.
VCODEC = vcodec()
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
    # `-nostdin` and a closed stdin, belt and braces. ffmpeg reads stdin for interactive
    # keys, so a render started from a process whose stdin carries a protocol stream will
    # eat bytes out of it — see `_encodes` for the case that caught this. The flag covers
    # ffmpeg's own reading; DEVNULL covers anything else the child does with the handle.
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)
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
        stdin=subprocess.DEVNULL,
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
    fps: int | None = None,
    encoder: str = "",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rate = resolve_fps(fps)
    filters = [f"color=c={color}:s={width}x{height}:r={rate}:d={max(seconds, 0.1):.3f}"]
    args = ["-f", "lavfi", "-i", filters[0]]
    if label:
        safe = _escape_drawtext(label)
        args += [
            "-vf",
            f"drawtext=text='{safe}':fontcolor=white@0.85:fontsize={max(height // 18, 16)}"
            f":x=(w-text_w)/2:y=(h-text_h)/2",
        ]
    args += ["-t", f"{max(seconds, 0.1):.3f}", *vcodec(rate, encoder), "-an", str(out_path)]
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
    fps: int | None = None,
    encoder: str = "",
) -> Path:
    """Animate a still so a slideshow does not look like a slideshow.

    `punch_in` tightens the framing before anything else happens, which is how one plate
    becomes several shots. See `render.cutting` for why a punched shot is rendered with
    `ken_burns=False`: the push would close most of the gap between adjacent framings and
    take the cut below the size at which it is visible at all.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(seconds, 0.2)
    rate = resolve_fps(fps)
    frames = max(int(duration * rate), 2)
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
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={rate},"
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
            *vcodec(rate, encoder),
            "-an",
            str(out_path),
        ],
        label="still_to_clip",
    )
    return out_path


#: How much of a source has to remain after a seek for the seek to be worth making.
#: Input-side `-ss` lands on the nearest keyframe at or before the timestamp, so a seek
#: clamped to the last frame can still leave nothing decodable — a 3.0s clip clamped to
#: 2.967s wrote the same empty file the clamp was added to prevent.
SEEK_TAIL = 0.25


def normalise_clip(
    src: Path,
    out_path: Path,
    seconds: float,
    *,
    width: int = 1280,
    height: int = 720,
    punch_in: float = 1.0,
    seek: float = 0.0,
    fps: int | None = None,
    encoder: str = "",
) -> Path:
    """Trim/pad a provider clip to the exact scene length and uniform codec.

    `seek` and `punch_in` together turn one clip into several shots. `seek` alone would
    not: consecutive segments of a clip played in order are the clip, with no cut in it.
    The reframe is what the viewer reads as an edit; the seek is what stops the same
    seconds of footage being shown twice.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(seconds, 0.2)
    rate = resolve_fps(fps)

    # A seek past the end of the source decodes no frames at all, and ffmpeg writes a
    # 262-byte file with no duration rather than failing — so the run dies later at the
    # concat, having already paid for everything upstream. `-vsync cfr` below holds the
    # last frame of a source that is merely *short*; it cannot hold a frame that was
    # never decoded.
    #
    # Reachable whenever a video plate is about as long as one shot, which is exactly
    # what the canon lane's animated shots are: a drift clip is rendered at its own
    # shot's length, 3.03s, and the cutting plan seeks 6s into it for the second shot
    # that shares it. Clamped rather than refused, because the footage that is there is
    # a perfectly good shot.
    # A tail rather than a frame. Input-side `-ss` seeks to the nearest keyframe at or
    # before the timestamp, and clamping to one frame's width off the end can still land
    # somewhere with nothing decodable after it — measured: a 3.0s clip clamped to 2.967s
    # produced the same empty file. A quarter of a second always holds frames, and a
    # source with less than that left to give is not worth seeking into at all.
    if seek > 0:
        try:
            available = ffprobe_duration(src)
        except RenderError:
            available = 0.0
        if available > 0:
            seek = min(seek, available - SEEK_TAIL)
            if seek < SEEK_TAIL:
                seek = 0.0

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
            *vcodec(rate, encoder),
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
                *vcodec(rate, encoder), "-an", str(padded),
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


def overlay_video(base: Path, overlay: Path, out_path: Path, *, fps: int | None = None,
                  encoder: str = "", scale: float = 0.28,
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
            *vcodec(resolve_fps(fps), encoder),
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


def burn_subtitles(video_path: Path, srt_path: Path, out_path: Path, *,
                   fps: int | None = None, encoder: str = "") -> Path:
    style = (
        "FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,"
        "BorderStyle=3,Outline=1,Shadow=0,MarginV=42"
    )
    run_ffmpeg(
        [
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_path.resolve().as_posix()}':force_style='{style}'",
            *vcodec(resolve_fps(fps), encoder),
            "-c:a", "copy",
            str(out_path),
        ],
        label="burn_subtitles",
    )
    return out_path


# ---------------------------------------------------------------------- orchestration


def _shot_clip(
    scene: Scene, cut, out_path: Path, *, width: int, height: int, subdivided: bool,
    fps: int | None = None,
    encoder: str = "",
) -> Path:
    """One visual segment of a scene, from whichever plate the plan assigned it."""
    plate = scene.plate(getattr(cut, "plate_index", 0))
    if plate is None:
        make_color_clip(
            out_path, cut.seconds, width=width, height=height, fps=fps,
            label=scene.narration[:80] or f"scene {scene.index}",
        )
        return out_path

    punch = float(getattr(cut, "punch_in", 1.0) or 1.0)
    if _is_video(plate):
        normalise_clip(
            plate, out_path, cut.seconds, width=width, height=height,
            punch_in=punch, seek=float(getattr(cut, "source_offset", 0.0) or 0.0),
            fps=fps, encoder=encoder,
        )
    else:
        still_to_clip(
            plate, out_path, cut.seconds, width=width, height=height,
            # See `render.cutting`: the Ken Burns push ends 12% in, which would leave the
            # next shot's 24% reframe reading as an 11% one — under the size at which a
            # cut is detected at all. The cut carries the motion instead.
            ken_burns=not subdivided,
            punch_in=punch,
            fps=fps, encoder=encoder,
        )
    return out_path


def _build_scene_clip(
    scene: Scene, target: Path, cuts: list, *, workdir: Path, width: int, height: int,
    fps: int | None = None,
    encoder: str = "",
) -> Path:
    """Build one scene's visual bed, as one clip or as several cut together."""
    if len(cuts) <= 1:
        # The single-shot path stays byte-for-byte what it was: one encode, no concat, and
        # the Ken Burns push still earns its place on a visual nobody cuts away from.
        only = cuts[0] if cuts else None
        if only is not None and scene.plate(only.plate_index) is not None:
            return _shot_clip(
                scene, only, target, width=width, height=height, subdivided=False,
                fps=fps, encoder=encoder,
            )
        if scene.visual_path and scene.visual_path.exists():
            if scene.is_video:
                normalise_clip(
                    scene.visual_path, target, scene.seconds, width=width,
                    height=height, fps=fps, encoder=encoder,
                )
            else:
                still_to_clip(
                    scene.visual_path, target, scene.seconds, width=width,
                    height=height, fps=fps, encoder=encoder,
                )
        else:
            make_color_clip(
                target, scene.seconds, width=width, height=height, fps=fps,
                label=scene.narration[:80] or f"scene {scene.index}",
            )
        return target

    pieces = [
        _shot_clip(
            scene, cut,
            workdir / f"scene_{scene.index:03d}_shot_{cut.shot_index:03d}.mp4",
            width=width, height=height, subdivided=True, fps=fps, encoder=encoder,
        )
        for cut in cuts
    ]
    # Stream-copied: every piece came out of the same VCODEC settings, so re-encoding the
    # concat would cost a second generation loss for nothing.
    return concat_clips(pieces, target)


def _join_scenes(clips: list[Path], scenes: list[Scene], out_path: Path, *,
                 transition: str = "", dissolve_share: float = 0.0) -> Path:
    """Put the scene clips end to end, dissolving the share the reference dissolves.

    `render/transitions.py` was written complete — a catalogue, a planner that refuses
    an overlap the shots cannot afford, an `available()` guard for an ffmpeg without
    `xfade`, and a `hold_timeline` that keeps the bed the length the narration was
    recorded against. It had no caller. Every video this app has ever made went through
    `concat_clips`, which is a hard cut, so the transition a style measured off its
    reference was recorded and never applied.

    That mattered in the direction nobody checked. A reference that hard-cuts got hard
    cuts and looked right by accident; a reference that dissolves got hard cuts too.

    Which boundaries dissolve comes from `dissolve_share` — the measured fraction of the
    reference's own joins that were not cuts. Spread evenly rather than taken from the
    front, because a video that dissolves its first third and cuts the rest reads as two
    edits stitched together.
    """
    if not clips:
        raise RenderError("nothing to concatenate")

    share = max(0.0, min(1.0, float(dissolve_share or 0.0)))
    if len(clips) < 2 or not transition or share <= 0:
        return concat_clips(clips, out_path)

    from . import transitions as tr

    # The style says `cut` or `dissolve`; the catalogue is named for editorial intent.
    # Translating here rather than at the call site is what was missing — `get()` never
    # raises and falls back to a hard cut, so an unmapped name silently produced the
    # behaviour the wiring was meant to replace, and looked like it had worked.
    key = tr.from_style(transition)
    if key == tr.DEFAULT_KEY:
        return concat_clips(clips, out_path)

    if not tr.available():
        log.info("this ffmpeg has no xfade — joining with hard cuts")
        return concat_clips(clips, out_path)

    durations = [float(scene.seconds) for scene in scenes[:len(clips)]]
    boundaries = len(clips) - 1
    wanted = round(boundaries * share)
    # Evenly spaced: boundary i dissolves when its position in the run crosses the next
    # multiple of the spacing. With share=0.5 and 8 boundaries that is every other one.
    keys = ["cut"] * boundaries
    if wanted:
        step = boundaries / wanted
        for index in range(wanted):
            keys[min(boundaries - 1, int(index * step))] = key

    joins = tr.plan(durations, keys)
    return tr.join_clips(clips, joins, durations, out_path, hold_timeline=True)


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
    # How this channel joins its shots, measured off its reference. Empty or "cut"
    # keeps the hard-cut concat every render used before this existed.
    transition: str = "",
    dissolve_share: float = 0.0,
    motion_preset=None,
    motion_plans=None,
    motion_backend: str = "ffmpeg",
    loudness_target: str = "youtube",
    shot_cuts=None,
    fps: int | None = None,
    encoder: str = "",
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
            workdir=workdir, width=width, height=height, fps=fps, encoder=encoder,
        )

        item = plan_by_scene.get(scene.index)
        if engine is not None and item is not None and item.active:
            target = engine.render(
                target, workdir / f"scene_{scene.index:03d}_motion.mp4", item,
                preset=motion_preset, seconds=scene.seconds,
                width=width, height=height, fps=resolve_fps(fps),
            )
        clips.append(target)

    bed = _join_scenes(clips, scenes, workdir / "bed.mp4",
                       transition=transition, dissolve_share=dissolve_share)

    if avatar_path and avatar_path.exists():
        bed = overlay_video(bed, avatar_path, workdir / "bed_pip.mp4", fps=fps,
                            encoder=encoder)

    if narration_path and narration_path.exists():
        staged = mux(bed, narration_path, workdir / "with_audio.mp4")
    else:
        total = sum(scene.seconds for scene in scenes)
        silence = make_silent_audio(workdir / "silence.m4a", total)
        staged = mux(bed, silence, workdir / "with_audio.mp4")

    if subtitles:
        srt = write_srt(scenes, workdir / "captions.srt")
        if srt.stat().st_size > 0:
            staged = burn_subtitles(staged, srt, workdir / "with_captions.mp4",
                                     fps=fps, encoder=encoder)

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
