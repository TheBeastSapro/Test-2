"""Frame sampling, colour grade, camera motion, and on-screen graphic regions.

All numpy on downscaled frames. Downscaling is not a compromise here: grade,
motion and text-block position all survive it, and it turns a ten-minute video from
gigabytes of pixels into ~50MB that fits comfortably in memory.

One honest limitation stated up front: there is no OCR in this environment, so this
module locates on-screen text and graphics but cannot read them. It reports *where*
text lives, how much of the frame it occupies and how persistent it is — which is
what you need to replicate a caption style. Reading the words is the semantic
layer's job (see profile.py, `semantic` block).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import numpy as np

from .probe import FFMPEG, ProbeError, VideoMeta

# Sampling budget. 4fps resolves any camera move a viewer would notice; the frame
# cap keeps a feature-length input from exhausting memory.
SAMPLE_FPS = 4.0
MAX_FRAMES = 1200
SAMPLE_WIDTH = 160

# Rec. 709 luma weights — perceptual brightness, not a naive channel mean.
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass
class FrameSet:
    frames: np.ndarray          # (N, H, W, 3) uint8
    times: np.ndarray           # (N,) seconds
    fps: float

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def luma(self) -> np.ndarray:
        """(N, H, W) float32 perceptual brightness in 0-255."""
        return self.frames.astype(np.float32) @ LUMA

    def between(self, start: float, end: float) -> np.ndarray:
        mask = (self.times >= start) & (self.times < end)
        return self.frames[mask]

    def indices_between(self, start: float, end: float) -> np.ndarray:
        return np.flatnonzero((self.times >= start) & (self.times < end))


def sample(
    meta: VideoMeta, *, fps: float = SAMPLE_FPS, width: int = SAMPLE_WIDTH,
    max_frames: int = MAX_FRAMES, timeout: float = 900.0,
) -> FrameSet:
    """Decode the whole video once into a downscaled numpy array."""
    if meta.duration <= 0:
        raise ProbeError("cannot sample a video with unknown duration")

    # Back off the rate rather than truncating: a style read of the first two
    # minutes of a twenty-minute video would misrepresent the whole edit.
    effective_fps = fps
    if meta.duration * fps > max_frames:
        effective_fps = max(max_frames / meta.duration, 0.2)

    height = max(2, round(width * meta.height / max(meta.width, 1)))
    height += height % 2

    cmd = [
        FFMPEG, "-v", "error", "-i", str(meta.path),
        "-vf", f"fps={effective_fps:.6f},scale={width}:{height}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise ProbeError(
            f"frame sampling failed: {proc.stderr.decode(errors='replace')[-300:]}"
        )

    frame_bytes = width * height * 3
    count = len(proc.stdout) // frame_bytes
    if count == 0:
        raise ProbeError("frame sampling produced no frames")

    frames = np.frombuffer(
        proc.stdout[: count * frame_bytes], dtype=np.uint8
    ).reshape(count, height, width, 3)
    times = np.arange(count, dtype=np.float32) / effective_fps
    return FrameSet(frames=frames, times=times, fps=effective_fps)


# ---------------------------------------------------------------------- colour


@dataclass
class ColourProfile:
    brightness: float          # 0-255 mean luma
    contrast: float            # luma stdev
    saturation: float          # 0-1
    warmth: float             # -1 cool .. +1 warm (red minus blue, normalised)
    palette: list[dict] = field(default_factory=list)

    def grade_label(self) -> str:
        """A short, comparable description of the look."""
        parts: list[str] = []
        if self.brightness < 70:
            parts.append("dark")
        elif self.brightness > 175:
            parts.append("bright")
        if self.contrast > 70:
            parts.append("high_contrast")
        elif self.contrast < 30:
            parts.append("flat")
        if self.saturation > 0.45:
            parts.append("saturated")
        elif self.saturation < 0.15:
            parts.append("desaturated")
        if self.warmth > 0.12:
            parts.append("warm")
        elif self.warmth < -0.12:
            parts.append("cool")
        return "_".join(parts) if parts else "neutral"

    def as_dict(self) -> dict:
        return {
            "brightness": round(self.brightness, 2),
            "contrast": round(self.contrast, 2),
            "saturation": round(self.saturation, 4),
            "warmth": round(self.warmth, 4),
            "grade_label": self.grade_label(),
            "palette": self.palette,
        }


def colour_profile(frames: np.ndarray, *, palette_size: int = 5) -> ColourProfile:
    if frames.size == 0:
        return ColourProfile(0.0, 0.0, 0.0, 0.0, [])

    pixels = frames.reshape(-1, 3).astype(np.float32)
    luma = pixels @ LUMA
    channel_max = pixels.max(axis=1)
    channel_min = pixels.min(axis=1)
    # HSV saturation, guarding the black pixels where it is undefined.
    with np.errstate(divide="ignore", invalid="ignore"):
        saturation = np.where(channel_max > 0, (channel_max - channel_min) / channel_max, 0.0)

    red, blue = pixels[:, 0].mean(), pixels[:, 2].mean()
    warmth = (red - blue) / 255.0

    return ColourProfile(
        brightness=float(luma.mean()),
        contrast=float(luma.std()),
        saturation=float(np.nanmean(saturation)),
        warmth=float(warmth),
        palette=_palette(frames, palette_size),
    )


def _palette(frames: np.ndarray, size: int) -> list[dict]:
    """Dominant colours by 3-bit-per-channel quantisation.

    Deliberately not k-means: bucketing is deterministic, needs no extra
    dependency, and for "what colours does this channel use" a 512-bin histogram
    is indistinguishable from clustering.
    """
    pixels = frames.reshape(-1, 3)
    if len(pixels) > 200_000:  # plenty for a stable histogram
        step = len(pixels) // 200_000 + 1
        pixels = pixels[::step]

    quantised = (pixels >> 5).astype(np.uint16)  # 8 levels per channel
    keys = (quantised[:, 0] << 6) | (quantised[:, 1] << 3) | quantised[:, 2]
    unique, counts = np.unique(keys, return_counts=True)
    order = np.argsort(counts)[::-1][:size]

    total = counts.sum()
    out: list[dict] = []
    for index in order:
        key = int(unique[index])
        red = ((key >> 6) & 0b111) * 32 + 16
        green = ((key >> 3) & 0b111) * 32 + 16
        blue = (key & 0b111) * 32 + 16
        out.append({
            "hex": f"#{red:02x}{green:02x}{blue:02x}",
            "share": round(float(counts[index] / total), 4),
        })
    return out


# ---------------------------------------------------------------------- motion


@dataclass
class MotionProfile:
    magnitude: float           # 0-1 mean normalised inter-frame change
    peak: float
    classification: str        # static | subtle | moderate | high
    camera_move: str           # static | zoom | pan_or_handheld | unclear
    confidence: str = "medium"

    def as_dict(self) -> dict:
        return {
            "magnitude": round(self.magnitude, 4),
            "peak": round(self.peak, 4),
            "classification": self.classification,
            "camera_move": self.camera_move,
            "confidence": self.confidence,
        }


def motion_profile(frames: np.ndarray) -> MotionProfile:
    """Inter-frame change within a single shot, plus a camera-move guess.

    The move heuristic: under a zoom, content near the frame edge displaces further
    than content near the centre, so edge change outruns centre change. Under a pan
    or handheld drift the change is roughly uniform across the frame. It is a
    heuristic, not optical flow, so it reports its own confidence and says
    "unclear" rather than picking when the evidence is thin.
    """
    if len(frames) < 2:
        return MotionProfile(0.0, 0.0, "static", "static", confidence="low")

    luma = frames.astype(np.float32) @ LUMA
    diffs = np.abs(np.diff(luma, axis=0))
    per_frame = diffs.reshape(len(diffs), -1).mean(axis=1) / 255.0

    magnitude = float(per_frame.mean())
    peak = float(per_frame.max())

    if magnitude < 0.015:
        classification = "static"
    elif magnitude < 0.05:
        classification = "subtle"
    elif magnitude < 0.14:
        classification = "moderate"
    else:
        classification = "high"

    height, width = luma.shape[1], luma.shape[2]
    top, bottom = height // 4, height - height // 4
    left, right = width // 4, width - width // 4
    centre = diffs[:, top:bottom, left:right].mean() / 255.0
    edge_mask = np.ones((height, width), dtype=bool)
    edge_mask[top:bottom, left:right] = False
    edge = diffs[:, edge_mask].mean() / 255.0

    confidence = "medium"
    if magnitude < 0.015:
        camera_move, confidence = "static", "high"
    elif centre <= 1e-6:
        camera_move, confidence = "unclear", "low"
    else:
        ratio = edge / centre
        if ratio > 1.45:
            camera_move = "zoom"
        elif 0.75 <= ratio <= 1.3:
            camera_move = "pan_or_handheld"
        else:
            camera_move, confidence = "unclear", "low"

    return MotionProfile(magnitude, peak, classification, camera_move, confidence)


# --------------------------------------------------------------- text overlays


@dataclass
class OverlayProfile:
    caption_zone: str            # bottom_third | centre | top_third | none
    caption_persistence: float   # share of frames with text-like content there
    zone_scores: dict = field(default_factory=dict)
    graphic_density: float = 0.0
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "caption_zone": self.caption_zone,
            "caption_persistence": round(self.caption_persistence, 3),
            "graphic_density": round(self.graphic_density, 4),
            "zone_scores": {k: round(v, 4) for k, v in self.zone_scores.items()},
            "note": self.note,
        }


def overlay_profile(frames: np.ndarray, *, stride: int = 3) -> OverlayProfile:
    """Locate persistent text-like content by horizontal edge density per band.

    Text is dense in short-range horizontal gradients — letter strokes — in a way
    that photographic content rarely is at the same scale. So: compute horizontal
    gradient energy for the top, middle and bottom thirds, then ask which band is
    both energetic *and* consistently so. Consistency is what separates a burned
    caption track from a busy background that happens to sit low in frame.
    """
    if len(frames) < 2:
        return OverlayProfile("none", 0.0, {}, 0.0, note="too few frames")

    sampled = frames[::stride]
    luma = sampled.astype(np.float32) @ LUMA
    gradient = np.abs(np.diff(luma, axis=2))  # horizontal strokes

    height = gradient.shape[1]
    third = max(height // 3, 1)
    bands = {
        "top_third": gradient[:, :third, :],
        "centre": gradient[:, third: 2 * third, :],
        "bottom_third": gradient[:, 2 * third:, :],
    }

    overall = float(gradient.mean()) or 1.0
    zone_scores: dict[str, float] = {}
    persistence: dict[str, float] = {}
    for name, band in bands.items():
        per_frame = band.reshape(len(band), -1).mean(axis=1)
        zone_scores[name] = float(per_frame.mean() / overall)
        # "Text-like" here means clearly above this video's own average edge energy.
        persistence[name] = float((per_frame > overall * 1.25).mean())

    best = max(zone_scores, key=lambda key: zone_scores[key] * (0.5 + persistence[key]))
    best_persistence = persistence[best]

    # Require both elevated energy and consistency before calling it a caption.
    if zone_scores[best] < 1.12 or best_persistence < 0.25:
        return OverlayProfile(
            "none", best_persistence, zone_scores, overall / 255.0,
            note="no band shows persistent text-like edge density",
        )

    return OverlayProfile(
        caption_zone=best,
        caption_persistence=best_persistence,
        zone_scores=zone_scores,
        graphic_density=overall / 255.0,
        note="edge-density heuristic; text position only, contents not read (no OCR)",
    )
