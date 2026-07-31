"""Loudness, onsets, tempo, dead air — and whether the cuts land on the beat.

Cut-to-beat alignment is the reason this module exists. It is one of the clearest
fingerprints of a deliberate edit and it is invisible to any text or vision model:
you cannot see it in a transcript and you cannot see it in a frame. Two videos with
identical cuts-per-minute feel completely different depending on whether the cuts
land on musical onsets, and replicating a style without it produces an edit that is
technically correct and subtly wrong.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import numpy as np

from .probe import FFMPEG, VideoMeta

SAMPLE_RATE = 22050
HOP_SECONDS = 0.02          # 20ms envelope resolution
BEAT_TOLERANCE = 0.12       # a cut this close to an onset reads as "on the beat"
MIN_BPM, MAX_BPM = 60, 200

# Absolute floor for onset flux, alongside the adaptive gate. Without it a track
# with no attacks at all — a held tone, room noise, a music bed with no percussion —
# has a near-zero flux distribution, so an adaptive-only threshold sits in the
# numerical noise and every micro-fluctuation registers as a beat. Measured: a
# constant tone peaks at 0.056 flux, a real percussive hit reaches 7+. 0.35 is a
# ~42% jump in RMS: unambiguously an attack, six times above the noise ceiling.
MIN_ONSET_FLUX = 0.35


@dataclass
class AudioAnalysis:
    present: bool
    duration: float = 0.0
    loudness_mean: float = 0.0      # dBFS
    loudness_peak: float = 0.0
    dynamic_range: float = 0.0
    silence_ratio: float = 0.0
    longest_silence: float = 0.0
    onset_count: int = 0
    onset_times: list[float] = field(default_factory=list, repr=False)
    tempo_bpm: float | None = None
    tempo_confidence: str = "low"
    likely_music: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "present": self.present,
            "loudness_mean_dbfs": round(self.loudness_mean, 2),
            "loudness_peak_dbfs": round(self.loudness_peak, 2),
            "dynamic_range_db": round(self.dynamic_range, 2),
            "silence_ratio": round(self.silence_ratio, 4),
            "longest_silence_seconds": round(self.longest_silence, 3),
            "onset_count": self.onset_count,
            "onsets_per_minute": (
                round(self.onset_count / (self.duration / 60), 2) if self.duration else None
            ),
            "tempo_bpm": round(self.tempo_bpm, 1) if self.tempo_bpm else None,
            "tempo_confidence": self.tempo_confidence,
            "likely_music": self.likely_music,
            "note": self.note,
        }


@dataclass
class BeatAlignment:
    measured: bool
    cuts_on_beat_ratio: float | None = None
    median_offset: float | None = None
    verdict: str = "not_measured"
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "measured": self.measured,
            "cuts_on_beat_ratio": (
                round(self.cuts_on_beat_ratio, 3) if self.cuts_on_beat_ratio is not None else None
            ),
            "median_offset_seconds": (
                round(self.median_offset, 4) if self.median_offset is not None else None
            ),
            "verdict": self.verdict,
            "note": self.note,
        }


def _pcm(meta: VideoMeta, *, timeout: float = 600.0) -> np.ndarray | None:
    """Mono float32 in -1..1, or None when there is no usable audio."""
    if not meta.has_audio:
        return None
    cmd = [
        FFMPEG, "-v", "error", "-i", str(meta.path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-acodec", "pcm_s16le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0 or not proc.stdout:
        return None
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return samples if samples.size else None


def _envelope(samples: np.ndarray) -> tuple[np.ndarray, float]:
    hop = max(int(SAMPLE_RATE * HOP_SECONDS), 1)
    usable = (len(samples) // hop) * hop
    if usable == 0:
        return np.zeros(0, dtype=np.float32), HOP_SECONDS
    windows = samples[:usable].reshape(-1, hop)
    rms = np.sqrt((windows ** 2).mean(axis=1) + 1e-12)
    return rms.astype(np.float32), hop / SAMPLE_RATE


def _to_dbfs(value: float) -> float:
    return float(20 * np.log10(max(value, 1e-6)))


def analyse(meta: VideoMeta) -> AudioAnalysis:
    samples = _pcm(meta)
    if samples is None:
        return AudioAnalysis(present=False, note="no audio stream, or it failed to decode")

    rms, hop = _envelope(samples)
    if rms.size == 0:
        return AudioAnalysis(present=False, note="audio too short to analyse")

    duration = len(samples) / SAMPLE_RATE
    peak = float(rms.max())

    # Silence is relative to this video's own peak: an absolute dBFS gate
    # misjudges anything quietly mastered.
    gate = max(peak * 0.06, 1e-5)
    silent = rms < gate
    silence_ratio = float(silent.mean())
    longest_silence = _longest_run(silent) * hop

    onsets = _onsets(rms, hop)
    tempo, tempo_confidence = _tempo(onsets, duration)

    # Music is inferred, never asserted: sustained energy (little silence) plus a
    # steady onset pulse. Speech-only tracks have more silence and irregular onsets.
    onsets_per_minute = len(onsets) / (duration / 60) if duration else 0
    likely_music = (
        silence_ratio < 0.30 and onsets_per_minute > 25 and tempo_confidence != "low"
    )

    return AudioAnalysis(
        present=True,
        duration=duration,
        loudness_mean=_to_dbfs(float(rms.mean())),
        loudness_peak=_to_dbfs(peak),
        dynamic_range=_to_dbfs(peak) - _to_dbfs(float(np.percentile(rms, 10))),
        silence_ratio=silence_ratio,
        longest_silence=longest_silence,
        onset_count=len(onsets),
        onset_times=[round(float(t), 4) for t in onsets],
        tempo_bpm=tempo,
        tempo_confidence=tempo_confidence,
        likely_music=likely_music,
        note="music/speech split is inferred from silence and onset regularity",
    )


def _longest_run(mask: np.ndarray) -> int:
    longest = current = 0
    for value in mask:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _onsets(rms: np.ndarray, hop: float) -> np.ndarray:
    """Peak-picked positive flux of the log envelope.

    Log domain because perceived attack is ratio-based: a hit from 0.01 to 0.02 is
    as audible as 0.4 to 0.8, and a linear difference would only ever see the loud one.
    """
    if rms.size < 5:
        return np.zeros(0, dtype=np.float32)

    log_rms = np.log(rms + 1e-6)
    flux = np.diff(log_rms)
    flux[flux < 0] = 0.0
    if not flux.any():
        return np.zeros(0, dtype=np.float32)

    # Adaptive gate for this track, floored so a flat track yields no onsets.
    threshold = max(float(flux.mean() + 1.5 * flux.std()), MIN_ONSET_FLUX)

    times: list[float] = []
    min_gap = max(int(0.08 / hop), 1)   # 80ms refractory period
    last = -min_gap - 1
    for index in range(1, len(flux) - 1):
        value = flux[index]
        if (
            value >= threshold
            and value >= flux[index - 1]
            and value >= flux[index + 1]
            and index - last > min_gap
        ):
            times.append((index + 1) * hop)
            last = index
    return np.asarray(times, dtype=np.float32)


def _tempo(onsets: np.ndarray, duration: float) -> tuple[float | None, str]:
    """Dominant inter-onset period, read as BPM.

    Uses the histogram mode of inter-onset intervals rather than autocorrelation:
    fewer assumptions, and it degrades to an honest "low confidence" instead of
    inventing a tempo from four onsets.
    """
    if len(onsets) < 8 or duration <= 0:
        return None, "low"

    intervals = np.diff(onsets)
    intervals = intervals[(intervals > 60 / MAX_BPM) & (intervals < 60 / MIN_BPM)]
    if len(intervals) < 6:
        return None, "low"

    # 20ms bins over the plausible range.
    bins = np.arange(60 / MAX_BPM, 60 / MIN_BPM + 0.02, 0.02)
    counts, edges = np.histogram(intervals, bins=bins)
    if counts.max() == 0:
        return None, "low"

    peak_index = int(counts.argmax())
    period = float((edges[peak_index] + edges[peak_index + 1]) / 2)
    bpm = 60.0 / period

    share = counts[peak_index] / counts.sum()
    if share > 0.45 and len(intervals) >= 16:
        confidence = "high"
    elif share > 0.28:
        confidence = "medium"
    else:
        confidence = "low"
    return bpm, confidence


def beat_alignment(
    cut_times: list[float], audio: AudioAnalysis, *, tolerance: float = BEAT_TOLERANCE
) -> BeatAlignment:
    """Do the cuts land on audio onsets?"""
    if not audio.present or not audio.onset_times:
        return BeatAlignment(False, note="no onsets detected to compare against")
    if len(cut_times) < 3:
        return BeatAlignment(False, note="fewer than 3 cuts — not enough to judge")

    onsets = np.asarray(audio.onset_times, dtype=np.float32)
    cuts = np.asarray(cut_times, dtype=np.float32)
    offsets = np.abs(onsets[None, :] - cuts[:, None]).min(axis=1)

    ratio = float((offsets <= tolerance).mean())
    median_offset = float(np.median(offsets))

    if ratio >= 0.7:
        verdict = "cuts_locked_to_beat"
    elif ratio >= 0.4:
        verdict = "partially_beat_driven"
    else:
        verdict = "cuts_independent_of_audio"

    return BeatAlignment(
        measured=True,
        cuts_on_beat_ratio=ratio,
        median_offset=median_offset,
        verdict=verdict,
        note=f"within {tolerance * 1000:.0f}ms of a detected onset",
    )
