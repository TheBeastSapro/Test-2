"""What a file actually is, before anything decides what to do with it.

The one reading that cannot degrade. Everything else in this package is best-effort —
no `scenedetect`, no shots; no model, no transcript — but a file that will not probe is
not a video, and there is nothing to carry on with.

Read through `ffprobe` rather than a Python container parser because ffprobe is already
a hard dependency of rendering, it reads every container this app will ever be handed,
and it is the same tool the renderer will use downstream. Two libraries disagreeing
about a file's frame rate is a class of bug worth never having.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..render.ffmpeg import RenderError

PROBE_TIMEOUT = 60


@dataclass
class Media:
    """The facts about a file that every later decision needs."""

    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    size_bytes: int = 0

    @property
    def aspect(self) -> str:
        """The shape, named the way channels are configured.

        Nearest of the three this app renders rather than the exact ratio: a 1920x1088
        upload is 16:9 in every sense that matters, and reporting `30:17` would make it
        look like a format nothing supports.
        """
        if self.height <= 0:
            return "16:9"
        ratio = self.width / self.height
        return min((("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0)),
                   key=lambda item: abs(ratio - item[1]))[0]


def available() -> tuple[bool, str]:
    if not shutil.which("ffprobe"):
        return False, "ffprobe is not installed — it comes with ffmpeg"
    return True, ""


def _fraction(text: str) -> float:
    """`30000/1001` as a number.

    Frame rates arrive as fractions because that is what they are — 29.97 is 30000/1001
    and rounding it early is how audio drifts a frame every thousand.
    """
    try:
        if "/" in text:
            top, bottom = text.split("/", 1)
            return float(top) / float(bottom) if float(bottom) else 0.0
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def read(path: Path) -> Media:
    """Probe one file. Raises `RenderError` when it is not a video this can read."""
    ok, why = available()
    if not ok:
        raise RenderError(why)
    if not path.is_file():
        raise RenderError(f"{path} is not a file")

    try:
        done = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RenderError(f"could not probe {path.name}: {exc}") from exc
    if done.returncode != 0:
        raise RenderError(f"{path.name} is not a media file ffmpeg can read: "
                          f"{done.stderr.strip()[:200]}")

    try:
        payload = json.loads(done.stdout or "{}")
    except ValueError as exc:
        raise RenderError(f"ffprobe returned no usable JSON for {path.name}") from exc

    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RenderError(f"{path.name} has no video stream")

    fmt = payload.get("format") or {}
    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    if duration <= 0:
        raise RenderError(f"{path.name} reports no duration")

    return Media(
        duration=round(duration, 3),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        # `avg_frame_rate` over `r_frame_rate`: the latter is the container's timebase
        # and reads 90000 on some streams, which is not a frame rate anybody can cut to.
        fps=round(_fraction(str(video.get("avg_frame_rate") or "0")), 3),
        has_audio=audio is not None,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str((audio or {}).get("codec_name") or ""),
        size_bytes=int(fmt.get("size") or 0),
    )
