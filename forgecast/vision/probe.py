"""Video metadata and the low-level ffmpeg calls the analysers share.

Everything downstream works from a local file path. Acquisition is a separate,
swappable concern (see acquire.py) for the same reason provider routing is
separate in the render pipeline: the thing that fetches bytes changes far more
often than the thing that measures them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class ProbeError(RuntimeError):
    pass


@dataclass
class VideoMeta:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    size_bytes: int = 0
    container: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def aspect_ratio(self) -> str:
        """Nearest common ratio — what a creator would actually call the format."""
        if not self.height:
            return "unknown"
        ratio = self.width / self.height
        for label, value in (
            ("9:16", 9 / 16), ("4:5", 4 / 5), ("1:1", 1.0),
            ("4:3", 4 / 3), ("16:9", 16 / 9), ("21:9", 21 / 9),
        ):
            if abs(ratio - value) < 0.06:
                return label
        return f"{ratio:.2f}:1"

    @property
    def orientation(self) -> str:
        if self.width < self.height:
            return "vertical"
        if self.width > self.height:
            return "horizontal"
        return "square"

    def as_dict(self) -> dict:
        return {
            "duration_seconds": round(self.duration, 3),
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 3),
            "aspect_ratio": self.aspect_ratio,
            "orientation": self.orientation,
            "has_audio": self.has_audio,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "size_bytes": self.size_bytes,
            "container": self.container,
        }


def run(cmd: list[str], *, label: str, timeout: float = 900.0) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"{label} timed out after {timeout:.0f}s") from exc
    return proc


def probe(path: str | Path) -> VideoMeta:
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"no such file: {path}")

    proc = run(
        [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        label="ffprobe",
        timeout=120,
    )
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed on {path}: {proc.stderr.decode(errors='replace')[:300]}")

    payload = json.loads(proc.stdout or b"{}")
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProbeError(f"{path} has no video stream")

    # Duration can be missing on the format for some containers; fall back to the
    # video stream, then to counting. A wrong duration silently corrupts every
    # per-minute metric downstream, so it is worth the fallbacks.
    duration = _first_float(fmt.get("duration"), video.get("duration"))
    if duration is None:
        duration = _count_duration(path)

    return VideoMeta(
        path=path,
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/0"),
        has_audio=audio is not None,
        video_codec=video.get("codec_name", ""),
        audio_codec=(audio or {}).get("codec_name", ""),
        size_bytes=int(fmt.get("size") or (path.stat().st_size if path.exists() else 0)),
        container=fmt.get("format_name", ""),
    )


def _first_float(*values) -> float | None:
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _parse_fps(rate: str) -> float:
    try:
        num, _, den = rate.partition("/")
        numerator, denominator = float(num), float(den or 1)
        return numerator / denominator if denominator else 0.0
    except (TypeError, ValueError):
        return 0.0


def _count_duration(path: Path) -> float:
    """Last resort: decode and read the final packet timestamp."""
    proc = run(
        [
            FFPROBE, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path),
        ],
        label="ffprobe packet scan",
        timeout=300,
    )
    times = [
        float(line) for line in proc.stdout.decode(errors="replace").split()
        if line.replace(".", "", 1).replace("-", "", 1).isdigit()
    ]
    if not times:
        raise ProbeError(f"could not determine duration of {path}")
    return max(times)
