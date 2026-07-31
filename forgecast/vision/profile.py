"""StyleProfile: the measurements, and the render spec derived from them.

This is where analysis stops being a report and becomes something executable. A
paragraph describing an edit as "fast-paced with punchy zooms" cannot be applied to
anything. `RenderSpec` can: it carries a target shot length, a jitter range, a
transition mix, a zoom rate, a caption position and an ffmpeg colour-grade string,
which is precisely the input the render pipeline already takes.

That is the whole point of measuring rather than describing — the numbers survive
the trip from "what did they do" to "do that".
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .audio import AudioAnalysis, BeatAlignment
from .probe import VideoMeta
from .shots import ShotAnalysis
from .visual import ColourProfile, OverlayProfile

SCHEMA_VERSION = "1.0"


@dataclass
class RenderSpec:
    """Directly applicable edit parameters."""

    target_shot_seconds: float
    shot_seconds_range: tuple[float, float]
    cuts_per_minute: float
    jitter: float                      # 0 = metronomic, 1 = highly varied
    transition: str                    # cut | dissolve
    dissolve_share: float
    ken_burns: bool
    zoom_rate: float                   # zoom factor per second of a still
    captions: bool
    caption_position: str              # bottom_third | centre | top_third | none
    snap_cuts_to_beat: bool
    pacing: str                        # accelerating | steady | decelerating
    grade_filter: str                  # ffmpeg `eq` filter string
    target_brightness: float
    target_contrast: float
    target_saturation: float
    palette: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "target_shot_seconds": round(self.target_shot_seconds, 3),
            "shot_seconds_range": [round(v, 3) for v in self.shot_seconds_range],
            "cuts_per_minute": round(self.cuts_per_minute, 2),
            "jitter": round(self.jitter, 3),
            "transition": self.transition,
            "dissolve_share": round(self.dissolve_share, 3),
            "ken_burns": self.ken_burns,
            "zoom_rate": round(self.zoom_rate, 4),
            "captions": self.captions,
            "caption_position": self.caption_position,
            "snap_cuts_to_beat": self.snap_cuts_to_beat,
            "pacing": self.pacing,
            "grade_filter": self.grade_filter,
            "target_brightness": round(self.target_brightness, 2),
            "target_contrast": round(self.target_contrast, 2),
            "target_saturation": round(self.target_saturation, 4),
            "palette": self.palette,
        }


@dataclass
class StyleProfile:
    schema_version: str
    source: dict
    shot_rhythm: dict
    colour: dict
    motion: dict
    overlay: dict
    audio: dict
    beat_alignment: dict
    edit_signature: list[str]
    render_spec: RenderSpec
    confidence: dict
    semantic: dict | None = None
    per_shot: list[dict] = field(default_factory=list)

    def as_dict(self, *, include_shots: bool = True) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "edit_signature": self.edit_signature,
            "shot_rhythm": self.shot_rhythm,
            "colour": self.colour,
            "motion": self.motion,
            "overlay": self.overlay,
            "audio": self.audio,
            "beat_alignment": self.beat_alignment,
            "render_spec": self.render_spec.as_dict(),
            "semantic": self.semantic,
            "confidence": self.confidence,
        }
        if include_shots:
            payload["per_shot"] = self.per_shot
        return payload


# ------------------------------------------------------------------ synthesis


def build(
    meta: VideoMeta,
    shot_analysis: ShotAnalysis,
    colour: ColourProfile,
    per_shot: list[dict],
    overlay: OverlayProfile,
    audio: AudioAnalysis,
    alignment: BeatAlignment,
    *,
    semantic: dict | None = None,
) -> StyleProfile:
    rhythm = shot_analysis.as_dict(meta.duration)
    motion_summary = _summarise_motion(per_shot)
    spec = _render_spec(meta, shot_analysis, colour, motion_summary, overlay, alignment)

    return StyleProfile(
        schema_version=SCHEMA_VERSION,
        source={"path": str(meta.path), **meta.as_dict()},
        shot_rhythm=rhythm,
        colour=colour.as_dict(),
        motion=motion_summary,
        overlay=overlay.as_dict(),
        audio=audio.as_dict(),
        beat_alignment=alignment.as_dict(),
        edit_signature=_signature(meta, rhythm, colour, motion_summary, overlay, audio, alignment),
        render_spec=spec,
        confidence=_confidence(meta, shot_analysis, audio, overlay, semantic),
        semantic=semantic,
        per_shot=per_shot,
    )


def _summarise_motion(per_shot: list[dict]) -> dict:
    if not per_shot:
        return {"dominant": "unknown", "distribution": {}, "mean_magnitude": None}

    classes: dict[str, int] = {}
    moves: dict[str, int] = {}
    magnitudes: list[float] = []
    for shot in per_shot:
        motion = shot.get("motion") or {}
        classes[motion.get("classification", "unknown")] = (
            classes.get(motion.get("classification", "unknown"), 0) + 1
        )
        moves[motion.get("camera_move", "unknown")] = (
            moves.get(motion.get("camera_move", "unknown"), 0) + 1
        )
        if isinstance(motion.get("magnitude"), (int, float)):
            magnitudes.append(float(motion["magnitude"]))

    total = len(per_shot)
    return {
        "dominant": max(classes, key=lambda key: classes[key]),
        "dominant_camera_move": max(moves, key=lambda key: moves[key]),
        "distribution": {k: round(v / total, 3) for k, v in classes.items()},
        "camera_move_distribution": {k: round(v / total, 3) for k, v in moves.items()},
        "mean_magnitude": round(statistics.fmean(magnitudes), 4) if magnitudes else None,
    }


def _render_spec(
    meta: VideoMeta,
    shot_analysis: ShotAnalysis,
    colour: ColourProfile,
    motion: dict,
    overlay: OverlayProfile,
    alignment: BeatAlignment,
) -> RenderSpec:
    durations = [d for d in shot_analysis.durations if d > 0]
    median = statistics.median(durations) if durations else 4.0
    low = min(durations) if durations else median * 0.6
    high = max(durations) if durations else median * 1.6

    regularity = shot_analysis.regularity()
    jitter = 1.0 - regularity if regularity is not None else 0.35

    mix = shot_analysis.transition_mix()
    dissolve_share = mix.get("dissolve", 0.0)
    transition = "dissolve" if dissolve_share > 0.5 else "cut"

    # Ken Burns replicates a slow push on a still. Only enable it when the source
    # actually moves — applying it to a static-cut style invents motion that is not
    # part of the look, which is the most common way an "adapted" edit feels wrong.
    dominant_motion = motion.get("dominant", "unknown")
    dominant_move = motion.get("dominant_camera_move", "unknown")
    mean_magnitude = motion.get("mean_magnitude") or 0.0
    ken_burns = dominant_motion in {"subtle", "moderate", "high"} and dominant_move != "static"
    # 0.12 total zoom over a median shot is the visually equivalent default; scale it
    # by how much the source actually moved.
    zoom_rate = 0.0
    if ken_burns and median > 0:
        zoom_rate = min(0.35, max(0.02, mean_magnitude * 1.2)) / median

    captions = overlay.caption_zone != "none" and overlay.caption_persistence >= 0.4

    return RenderSpec(
        target_shot_seconds=median,
        shot_seconds_range=(low, high),
        cuts_per_minute=shot_analysis.cuts_per_minute(meta.duration),
        jitter=jitter,
        transition=transition,
        dissolve_share=dissolve_share,
        ken_burns=ken_burns,
        zoom_rate=zoom_rate,
        captions=captions,
        caption_position=overlay.caption_zone,
        snap_cuts_to_beat=alignment.verdict == "cuts_locked_to_beat",
        pacing=shot_analysis.pacing_trend(),
        grade_filter=_grade_filter(colour),
        target_brightness=colour.brightness,
        target_contrast=colour.contrast,
        target_saturation=colour.saturation,
        palette=colour.palette,
    )


def _grade_filter(colour: ColourProfile) -> str:
    """An ffmpeg `eq` string that moves neutral footage toward this look.

    Deliberately gentle. A grade inferred from average pixel statistics is a
    direction, not a LUT — pushing hard on it produces a caricature of the source
    rather than a match, and the error compounds when the source was already graded.
    """
    # Reference points for "ungraded": mid brightness 128, contrast 55, saturation 0.30.
    brightness = max(-0.25, min(0.25, (colour.brightness - 128) / 255 * 0.7))
    contrast = max(0.85, min(1.35, 1.0 + (colour.contrast - 55) / 55 * 0.35))
    saturation = max(0.7, min(1.5, 1.0 + (colour.saturation - 0.30) / 0.30 * 0.4))
    parts = [
        f"brightness={brightness:.3f}",
        f"contrast={contrast:.3f}",
        f"saturation={saturation:.3f}",
    ]
    return "eq=" + ":".join(parts)


def _signature(
    meta: VideoMeta,
    rhythm: dict,
    colour: ColourProfile,
    motion: dict,
    overlay: OverlayProfile,
    audio: AudioAnalysis,
    alignment: BeatAlignment,
) -> list[str]:
    """The short, human-readable fingerprint — what an editor would say out loud."""
    lines: list[str] = []

    cpm = rhythm.get("cuts_per_minute") or 0
    median = (rhythm.get("shot_length") or {}).get("median")
    if median:
        pace = "very fast" if median < 1.5 else "fast" if median < 3 else \
               "measured" if median < 6 else "slow"
        lines.append(f"{pace} cutting: {cpm:.0f} cuts/min, median shot {median:.1f}s")

    regularity = rhythm.get("regularity")
    if regularity is not None:
        if regularity > 0.7:
            lines.append(f"metronomic shot lengths (regularity {regularity:.2f})")
        elif regularity < 0.4:
            lines.append(f"deliberately uneven shot lengths (regularity {regularity:.2f})")

    trend = rhythm.get("pacing_trend")
    if trend in {"accelerating", "decelerating"}:
        lines.append(f"edit is {trend} through the runtime")

    dissolve = (rhythm.get("transition_mix") or {}).get("dissolve", 0)
    lines.append(
        f"transitions are {'mostly dissolves' if dissolve > 0.5 else 'hard cuts'}"
        + (f" ({dissolve:.0%} dissolve)" if dissolve else "")
    )

    lines.append(f"grade reads {colour.grade_label().replace('_', ' ')}")
    if colour.palette:
        lines.append("palette: " + ", ".join(item["hex"] for item in colour.palette[:3]))

    move = motion.get("dominant_camera_move")
    if move and move not in {"unknown", "unclear"}:
        lines.append(f"camera is predominantly {move.replace('_', ' ')}")

    if overlay.caption_zone != "none":
        lines.append(
            f"persistent on-screen text in the {overlay.caption_zone.replace('_', ' ')} "
            f"({overlay.caption_persistence:.0%} of frames)"
        )

    if audio.present:
        if audio.likely_music:
            tempo = f" at ~{audio.tempo_bpm:.0f} BPM" if audio.tempo_bpm else ""
            lines.append(f"music bed present{tempo}")
        if audio.silence_ratio < 0.08:
            lines.append("no dead air — wall-to-wall audio")
        elif audio.silence_ratio > 0.3:
            lines.append(f"{audio.silence_ratio:.0%} silence — breathing room between beats")

    if alignment.measured and alignment.cuts_on_beat_ratio is not None:
        lines.append(
            f"{alignment.cuts_on_beat_ratio:.0%} of cuts land on an audio onset "
            f"({alignment.verdict.replace('_', ' ')})"
        )

    return lines


def _confidence(
    meta: VideoMeta,
    shot_analysis: ShotAnalysis,
    audio: AudioAnalysis,
    overlay: OverlayProfile,
    semantic: dict | None,
) -> dict:
    notes: list[str] = []

    shot_confidence = "high"
    if len(shot_analysis.shots) < 4:
        shot_confidence = "low"
        notes.append(
            f"only {len(shot_analysis.shots)} shots detected — rhythm statistics are "
            "weak evidence below about 8 shots"
        )
    elif len(shot_analysis.shots) < 8:
        shot_confidence = "medium"

    if shot_analysis.noise_floor > 3:
        notes.append(
            f"high inter-frame noise floor (p95={shot_analysis.noise_floor:.1f}), so the "
            f"cut threshold rose to {shot_analysis.threshold:.1f} — heavy camera motion "
            "can hide short shots"
        )

    audio_confidence = "high" if audio.present else "none"
    if audio.present and audio.tempo_confidence == "low":
        audio_confidence = "medium"
        notes.append("tempo could not be established, so cut-to-beat is less meaningful")

    notes.append(
        "on-screen text is located by edge density, not read — no OCR in this build"
    )
    if semantic is None:
        notes.append(
            "no semantic pass: shot subjects, graphic style and text contents are not "
            "described. Add a vision provider to fill the `semantic` block"
        )

    return {
        "shot_detection": shot_confidence,
        "colour": "high",
        "motion": "medium",
        "overlay": "medium",
        "audio": audio_confidence,
        "semantic": "absent" if semantic is None else "present",
        "notes": notes,
    }
