"""Shared ffmpeg/ffprobe helpers for the sound-designer studio.

No third-party deps beyond numpy. ffmpeg + ffprobe must be on PATH.
"""
from __future__ import annotations

import json
import subprocess
import shutil
import sys
import wave
from dataclasses import dataclass


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"[sound-designer] '{binary}' not found on PATH. Install ffmpeg (apt-get install ffmpeg).")
    return path


FFMPEG = _require("ffmpeg")
FFPROBE = _require("ffprobe")


def run(cmd: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    """Run a command, raising with stderr on failure."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(cmd[:6])}...\n{tail}")
    return res


def probe(path: str) -> dict:
    """Return ffprobe JSON for format + streams."""
    res = run([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ])
    return json.loads(res.stdout)


def media_info(path: str) -> dict:
    """Normalized media info: duration, has_video, has_audio, size, fps."""
    info = probe(path)
    dur = float(info.get("format", {}).get("duration", 0.0) or 0.0)
    has_v = has_a = False
    width = height = 0
    fps = 0.0
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            has_v = True
            width = s.get("width", 0)
            height = s.get("height", 0)
            fr = s.get("avg_frame_rate", "0/0")
            try:
                num, den = fr.split("/")
                fps = float(num) / float(den) if float(den) else 0.0
            except Exception:
                fps = 0.0
        elif s.get("codec_type") == "audio":
            has_a = True
    return {
        "path": path, "duration": dur, "has_video": has_v, "has_audio": has_a,
        "width": width, "height": height, "fps": round(fps, 3),
    }


def decode_mono_pcm(path: str, sr: int = 16000):
    """Decode any media's audio to mono float32 samples in [-1, 1] at sr.

    Returns (samples: np.ndarray, sr: int). Empty array if no audio.
    """
    import numpy as np
    tmp_wav = f"/tmp/_sd_decode_{abs(hash(path)) % 10**8}.wav"
    try:
        run([FFMPEG, "-v", "error", "-y", "-i", path, "-vn",
             "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", tmp_wav])
    except RuntimeError:
        return np.zeros(0, dtype=np.float32), sr
    with wave.open(tmp_wav, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
    import os
    try:
        os.remove(tmp_wav)
    except OSError:
        pass
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return data, sr


def fmt_ts(seconds: float) -> str:
    """Seconds -> H:MM:SS.mmm timestamp."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:06.3f}"
    return f"{m}:{s:06.3f}"


@dataclass
class Interval:
    start: float
    end: float

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)
