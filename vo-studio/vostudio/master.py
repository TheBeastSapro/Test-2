"""
The mastering chain — and the one place a fixed defect comes back.

The master runs LAST. That is what makes it dangerous: a beat it inserts overwrites
whatever the stitch got right, so a defect fixed four stages upstream reappears in
the delivered file and looks like the fix never worked. One reported beat survived
five upstream fixes for exactly this reason.

So every rule here asks what the voice actually did before changing it, rather than
applying a number because the script has a comma.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import soundfile as sf


@dataclass
class Gap:
    start: float
    end: float

    @property
    def dur(self) -> float:
        return self.end - self.start


def find_gaps(audio: np.ndarray, sr: int, floor_db: float = -45.0,
              min_dur: float = 0.020) -> list[Gap]:
    """
    Where the voice stopped, measured from the waveform.

    NOT from ASR word timestamps. faster-whisper returns contiguous spans — the end
    of one word is the start of the next — so a real 150 ms hole reads as 0.000 s.
    That cost hours once. An RMS envelope sees the hole because the hole is quiet.
    """
    win = max(1, int(sr * 0.010))
    n = len(audio) // win
    env = np.array([np.sqrt((audio[i*win:(i+1)*win] ** 2).mean() + 1e-20)
                    for i in range(n)])
    quiet = 20 * np.log10(env + 1e-12) < floor_db

    gaps, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * win / sr >= min_dur:
                gaps.append(Gap(i * win / sr, j * win / sr))
            i = j
        else:
            i += 1
    return gaps


def set_gap(audio: np.ndarray, sr: int, gap: Gap, target_s: float,
            edge_fade_ms: float) -> np.ndarray:
    """
    Grow or shrink one gap to a target length.

    The fade is applied to the audio on each side of the seam, not to the silence —
    silence has nothing to fade. Without it a lengthened gap steps from signal to
    zero in one sample and clicks.
    """
    a, b = int(gap.start * sr), int(gap.end * sr)
    n_fade = max(1, int(sr * edge_fade_ms / 1000.0))
    head, tail = audio[:a].copy(), audio[b:].copy()

    if len(head) > n_fade:
        head[-n_fade:] *= np.linspace(1.0, 0.0, n_fade)
    if len(tail) > n_fade:
        tail[:n_fade] *= np.linspace(0.0, 1.0, n_fade)

    return np.concatenate([head, np.zeros(int(target_s * sr)), tail])


def comma_times(audio: np.ndarray, sr: int, script: str, asr_words) -> list[float]:
    """
    Where in the audio each scripted comma falls.

    Uses ASR word timestamps to LOCATE words — which is what they are good for — and
    never to measure a gap, which is what they are useless for. faster-whisper returns
    contiguous spans, so asking it how long a pause is always answers 0.000 s. The
    gap itself is measured from the waveform by find_gaps().
    """
    from .script_prep import spell_numerals
    from .readcheck import normalize

    tokens = spell_numerals(script).split()
    # index of the script word each comma follows
    after: list[int] = []
    word_i = -1
    for tok in tokens:
        if re.search(r"[a-zA-Z0-9']", tok):
            word_i += 1
        if tok.rstrip().endswith(","):
            after.append(word_i)

    # ASR writes "1798"; the script says "seventeen ninety-eight". Expand the ASR
    # token the same way and let every word it became share that token's end time,
    # or alignment slips by two words at every year and silently loses the comma
    # after it. Caught on a 12-second excerpt: 3 of 4 commas located, and the missing
    # one was the year.
    heard: list[tuple[str, float]] = []
    for w in asr_words:
        raw = w.word.strip().lower().strip(".,!?;:")
        for part in normalize(spell_numerals(raw)) or [raw]:
            heard.append((part, w.end))
    script_words = normalize(" ".join(tokens))

    # Greedy walk: script word -> the ASR word that matches it, in order. Drift from
    # a misrecognised word costs one comma, not the alignment.
    ends: dict[int, float] = {}
    j = 0
    for i, sw in enumerate(script_words):
        k = j
        while k < len(heard) and heard[k][0] != sw:
            k += 1
        if k < len(heard):
            ends[i] = heard[k][1]
            j = k + 1
    return [ends[i] for i in after if i in ends]


def place_beats(audio: np.ndarray, sr: int, script: str, cfg, log=print,
                asr_words=None) -> np.ndarray:
    """
    Pad the pauses the punctuation asks for — except where the voice already ran through.

    THE BUG THIS EXISTS TO NOT REPEAT: the old master padded EVERY comma to 160 ms,
    including the ones the voice read straight past. It ran last, so it reinstated the
    beat after every upstream fix, and one reported defect survived five of them. It
    was one rule in eight places in a single script.

    THE BUG THIS ALMOST SHIPPED WITH: the first version padded every gap that merely
    LOOKED like a pause. Measured on 60 s of real read, that is 34 of them — against
    the 8 commas the whole script's defect ever involved. Most sub-target gaps are
    stop consonants and plosive closures inside words, not punctuation. Padding those
    inserts a beat mid-word.

    So a gap is padded only when a scripted comma actually lands on it. Without word
    timings there is no way to know that, so without them this does nothing at all —
    which is the safe direction to fail in.
    """
    if not re.search(r",", script):
        return audio
    if not asr_words:
        log("  no word timings — beats skipped. Punctuation cannot be located "
            "without them, and padding by gap shape alone pads mid-word.")
        return audio

    gaps = find_gaps(audio, sr)
    target = cfg.comma_pad_ms / 1000.0
    commas = comma_times(audio, sr, script, asr_words)

    matched, ran_through = [], 0
    for t in commas:
        # the gap that starts nearest just after the word the comma follows
        near = [g for g in gaps if -0.05 <= g.start - t <= 0.35]
        if not near:
            continue
        gap = min(near, key=lambda g: abs(g.start - t))
        if gap.dur < cfg.runthrough_threshold_s:
            ran_through += 1          # the voice read through it — that is the read
        elif gap.dur < target:
            matched.append(gap)

    log(f"  {len(gaps)} gaps | {len(commas)} commas located | "
        f"{len(matched)} padded to {cfg.comma_pad_ms:.0f} ms | "
        f"{ran_through} read through and left alone")

    # Apply back-to-front so earlier edits do not shift later gap positions.
    for gap in sorted(matched, key=lambda g: -g.start):
        audio = set_gap(audio, sr, gap, target, cfg.edge_fade_ms)
    return audio


def measure_loudness(audio: np.ndarray, sr: int) -> tuple[float, float]:
    """
    Integrated LUFS and true peak. MEASURED — never the target line from a log.

    Returns -inf LUFS for anything too short or too quiet to measure, which the
    caller must check. pyloudnorm RAISES on audio shorter than its 400 ms block,
    so a one-word test render used to come out of mastering as a traceback.
    """
    import pyloudnorm as pyln

    if len(audio) < int(sr * 0.4) + 1:
        lufs = float("-inf")
    else:
        lufs = float(pyln.Meter(sr).integrated_loudness(audio))

    # TRUE peak needs a real resample. np.interp is LINEAR, and a straight line
    # between two samples can never rise above either of them -- so the old
    # "4x oversampled" figure was mathematically identical to the sample peak
    # and the ceiling check below could essentially never fire. Measured
    # against a proper polyphase resample it was understating sibilance by
    # over 3 dB.
    if len(audio) < 16:
        up = audio
    else:
        try:
            from scipy.signal import resample_poly
            up = resample_poly(audio, 4, 1)
        except Exception:
            up = audio
    peak = float(np.abs(up).max()) if len(up) else 0.0
    return lufs, float(20 * np.log10(peak + 1e-12))


def normalize(audio: np.ndarray, sr: int, cfg, log=print) -> np.ndarray:
    """
    Loudness to target, then hold true peak under the ceiling.

    Gain only — no limiting. A limiter would reshape the read to buy level, and the
    read is the product. If the peak ceiling forces the level down, that is reported
    rather than clawed back with compression.
    """
    lufs, tp = measure_loudness(audio, sr)
    log(f"  measured {lufs:.2f} LUFS, true peak {tp:.2f} dBTP")

    # Silence measures -inf, and the gain from -inf is inf: the old code
    # multiplied the array by it and wrote a file full of NaN, which ffmpeg
    # then happily encoded. If there is nothing to normalise, say so and
    # return the audio untouched.
    if not np.isfinite(lufs):
        log("  nothing measurable to normalise — the audio is silent or too "
            "short. Left at its own level; DO NOT ship this without listening.")
        return audio

    out = audio * (10 ** ((cfg.target_lufs - lufs) / 20.0))
    _, tp_after = measure_loudness(out, sr)
    if tp_after > cfg.target_true_peak:
        trim = tp_after - cfg.target_true_peak
        out = out * (10 ** (-trim / 20.0))
        log(f"  true peak would hit {tp_after:.2f} dBTP — pulled back {trim:.2f} dB, "
            f"so loudness lands under target. Not limited on purpose.")

    final_lufs, final_tp = measure_loudness(out, sr)
    log(f"  delivered {final_lufs:.2f} LUFS, true peak {final_tp:.2f} dBTP")
    return out


def master(stitched: Path, script: str, out_path: Path, cfg, log=print) -> Path:
    """Beats, then loudness, then write. Order matters — level is set on final timing."""
    audio, sr = sf.read(stitched)
    log("Mastering:")
    audio = place_beats(audio, sr, script, cfg, log)
    audio = normalize(audio, sr, cfg, log)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sr, subtype="PCM_24")
    log(f"  wrote {out_path.name} ({len(audio)/sr:.3f}s)")
    return out_path
