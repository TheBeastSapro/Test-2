#!/usr/bin/env python3
"""
Find orphan fragments — short bursts of audio stranded in the silence between
words, left behind by a splice.

    python3 orphans.py --audio "Title (final).mp3"

Exit 0 = nothing stranded. Exit 1 = candidates found, listed with a verdict.

WHY THIS EXISTS
    Sapro reported a glitch on the Hashish chapter header and gave the window
    261.690-262.300. Six repair attempts failed, two of them damaged the audio,
    and a fresh take was rolled three times. The word was never the problem. A
    133 ms copy of its final "sh" was sitting alone at 262.469 — 169 ms PAST the
    end of the window he gave, so every fix aimed inside the window missed it by
    construction.

    That is the lesson this script encodes: the defect can lie outside the
    timestamp reported. Scan the whole file for the signature instead.

WHAT AN ORPHAN IS
    A short burst FENCED BY SILENCE ON BOTH SIDES. All three conditions matter:

        fenced left    >= --min-gap of silence before it
        fenced right   >= --min-gap of silence after it
        short          <  --max-island long

    The "short" condition is what keeps a sentence out of the results. A chapter
    gap is ~0.30 s, so the next line begins well inside any generous search
    window — but a line runs for seconds before the next silence, so it is never
    an island. An earlier version of this sweep had no right-hand fence and no
    length ceiling. It flagged the opening of the following line as a fragment,
    and silencing it turned "Captagon was invented for children" into "Captagon
    was in for children" — a word cut out of the middle of a good read and
    delivered to Sapro as a fix.

THE VERDICT IS DECIDED BY TRANSCRIPT, NOT BY LEVEL
    Geometry alone cannot tell a stranded fricative from a genuinely short word.
    So every candidate is put to the test that actually matters: mute it,
    re-transcribe the surrounding seconds, and compare the word sequence.

        words unchanged   -> ORPHAN   removing it costs no speech
        words changed     -> KEEP     it IS speech, whatever it looks like

    That is rule 7 — transcribe after every destructive edit — moved to before
    the edit, where it can still prevent one. A KEEP verdict is not advisory.

THIS SCRIPT NEVER MODIFIES AUDIO
    It reports. The edit stays a deliberate act, and the six-second excerpt still
    goes to Sapro for his yes. Silencing something that turns out to be speech is
    worse than the glitch it replaced: it passes every level and waveform check
    and surfaces only as a missing word.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def decode(path, sr=48000):
    """Decode anything ffmpeg reads to mono float at a known rate."""
    wav = Path(tempfile.mkdtemp()) / "decoded.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path),
         "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s24le", str(wav)],
        check=True)
    audio, rate = sf.read(wav)
    return audio, rate


def silence_mask(audio, floor_db):
    """
    Which samples count as silence.

    A mastered WAV writes exact zeros between sections, and exact zero is the
    cleanest possible fence. An MP3 does not survive that: lame plus a decoder
    put roughly -51 dBFS of noise into what used to be digital silence. Chasing
    an exact-zero fence on a decoded MP3 finds nothing, and a fence set below the
    codec noise finds nothing either.

    So: use exact zero when the file still has it, and otherwise measure the
    actual floor and fence just above it. Report which, because the answer
    changes what a result means.
    """
    if floor_db is not None:
        return np.abs(audio) <= 10 ** (floor_db / 20.0), floor_db, "given"

    if (audio == 0.0).sum() > len(audio) * 0.001:
        return audio == 0.0, None, "exact zero"

    quiet = np.abs(audio)
    measured = 20 * np.log10(np.percentile(quiet, 5) + 1e-12)
    floor = measured + 12.0
    return quiet <= 10 ** (floor / 20.0), floor, "measured noise floor"


def find_islands(audio, sr, min_gap, max_island, min_peak, floor_db):
    mask, floor, how = silence_mask(audio, floor_db)

    runs = []
    i, n, need = 0, len(mask), int(min_gap * sr)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= need:
                runs.append((i, j))
            i = j
        else:
            i += 1

    islands = []
    for k in range(len(runs) - 1):
        start, end = runs[k][1], runs[k + 1][0]
        dur = (end - start) / sr
        if not (0.005 < dur < max_island):
            continue
        seg = audio[start:end]
        peak = 20 * np.log10(np.abs(seg).max() + 1e-12)
        if peak < min_peak:
            continue
        islands.append({
            "start": start / sr,
            "end": end / sr,
            "dur_ms": dur * 1000,
            "peak_db": peak,
            "gap_before_ms": (runs[k][1] - runs[k][0]) / sr * 1000,
            "gap_after_ms": (runs[k + 1][1] - runs[k + 1][0]) / sr * 1000,
            "centroid_hz": centroid(seg, sr),
            "zcr": zcr(seg, sr),
        })
    return islands, floor, how, len(runs)


def centroid(x, sr):
    if len(x) < 64:
        return 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    return float((freqs * spec).sum() / (spec.sum() + 1e-12))


def zcr(x, sr):
    if len(x) < 2:
        return 0.0
    return float(((x[:-1] * x[1:]) < 0).sum() / len(x) * sr)


def adjudicate(audio, sr, islands, model_name, context):
    """
    Mute each candidate, re-transcribe around it, diff the words.

    The test is one-sided on purpose: it asks whether muting LOSES a word, not
    whether it changes the transcript. Those are not the same question, and the
    difference is the whole verdict.

    On the Hashish fragment, muting it ADDED a word. ASR read the header as
    "...nobody can prove. In 1798..." with the stranded fricative present, and
    "...nobody can prove. Hashish. In 1798..." once it was gone — the fragment
    was corrupting the word it came from badly enough to erase it. A rule that
    flagged any change would have called that KEEP and defended the defect it
    exists to find.

    So: every word present before must still be present after, in order. Words
    gained are not a hazard, they are evidence the fragment was doing damage.

    Punctuation is dropped too. ASR writes "Hashish!" next to a stranded
    fricative and "Hashish." without one — real signal about the defect, but not
    a lost word.
    """
    from faster_whisper import WhisperModel

    # float32, never int8. int8 hallucinates dropped words, and a hallucinated
    # drop here would read as "this candidate is speech" and hide a real orphan.
    model = WhisperModel(model_name, device="cpu", compute_type="float32")

    def words(buf):
        tmp = Path(tempfile.mkdtemp()) / "seg.wav"
        sf.write(tmp, buf, sr)
        segments, _ = model.transcribe(str(tmp), language="en",
                                       vad_filter=False, beam_size=5)
        out = []
        for seg in segments:
            for w in seg.text.split():
                w = "".join(c for c in w.lower() if c.isalnum() or c == "'")
                if w:
                    out.append(w)
        return out

    for isl in islands:
        lo = max(0, int((isl["start"] - context) * sr))
        hi = min(len(audio), int((isl["end"] + context) * sr))
        before = audio[lo:hi].copy()
        after = before.copy()
        after[int((isl["start"]) * sr) - lo:int((isl["end"]) * sr) - lo] = 0.0

        w_before, w_after = words(before), words(after)
        isl["words_before"] = w_before
        isl["words_after"] = w_after
        isl["lost"] = lost_words(w_before, w_after)
        isl["gained"] = len(w_after) - len(w_before) + len(isl["lost"])
        isl["orphan"] = not isl["lost"]
        isl["verdict"] = "ORPHAN" if isl["orphan"] else "KEEP"
    return islands


def lost_words(before, after):
    """
    Which words of `before` are missing from `after`, matched in order.

    A greedy subsequence walk, so a repeated word has to be matched as many times
    as it occurs — losing one "took" out of "took Alexandria, took Cairo" has to
    register as a loss, and comparing sets would hide it.
    """
    lost, i = [], 0
    for w in before:
        j = i
        while j < len(after) and after[j] != w:
            j += 1
        if j < len(after):
            i = j + 1
        else:
            lost.append(w)
    return lost


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--min-gap", type=float, default=0.040,
                    help="silence needed on EACH side to fence an island (s)")
    ap.add_argument("--max-island", type=float, default=0.260,
                    help="longer than this is a line, not a fragment (s)")
    ap.add_argument("--min-peak", type=float, default=-40.0,
                    help="quieter than this is a fade crumb, not audible (dBFS)")
    ap.add_argument("--floor", type=float, default=None,
                    help="silence threshold in dBFS; default auto-detects")
    ap.add_argument("--asr-model", default="distil-large-v3")
    ap.add_argument("--context", type=float, default=3.0,
                    help="seconds each side fed to ASR for the mute test")
    ap.add_argument("--no-transcribe", action="store_true",
                    help="geometry only. Every result stays UNJUDGED — nothing "
                         "may be removed on this basis alone.")
    args = ap.parse_args()

    audio, sr = decode(args.audio)
    islands, floor, how, n_runs = find_islands(
        audio, sr, args.min_gap, args.max_island, args.min_peak, args.floor)

    print(f"file        {args.audio}")
    print(f"duration    {len(audio)/sr:.3f}s")
    print(f"silence     {how}" + (f" ({floor:.1f} dBFS)" if floor is not None else ""))
    print(f"gaps        {n_runs} of >= {args.min_gap*1000:.0f} ms")
    print(f"candidates  {len(islands)}\n")

    if not islands:
        print("No orphan fragments. Nothing is stranded in the gaps.")
        return 0

    if args.no_transcribe:
        for isl in islands:
            isl["verdict"] = "UNJUDGED"
    else:
        islands = adjudicate(audio, sr, islands, args.asr_model, args.context)

    print(f"{'start':>9} {'end':>9} {'ms':>6} {'peak':>7} "
          f"{'gapL':>6} {'gapR':>6} {'cent':>6} {'zcr':>6}  verdict")
    for isl in islands:
        print(f"{isl['start']:9.3f} {isl['end']:9.3f} {isl['dur_ms']:6.1f} "
              f"{isl['peak_db']:7.2f} {isl['gap_before_ms']:6.0f} "
              f"{isl['gap_after_ms']:6.0f} {isl['centroid_hz']:6.0f} "
              f"{isl['zcr']:6.0f}  {isl['verdict']}")

    keeps = [i for i in islands if i["verdict"] == "KEEP"]
    for isl in keeps:
        print(f"\n  KEEP {isl['start']:.3f}: muting it LOSES {isl['lost']}")
        print(f"       with:    {' '.join(isl['words_before'])}")
        print(f"       without: {' '.join(isl['words_after'])}")

    for isl in islands:
        if isl["verdict"] == "ORPHAN" and isl.get("gained"):
            print(f"\n  ORPHAN {isl['start']:.3f}: muting it RECOVERS "
                  f"{isl['gained']} word(s) — the fragment was corrupting the read")
            print(f"       with:    {' '.join(isl['words_before'])}")
            print(f"       without: {' '.join(isl['words_after'])}")

    orphans = [i for i in islands if i["verdict"] == "ORPHAN"]
    print(f"\n{len(orphans)} orphan, {len(keeps)} keep, "
          f"{len([i for i in islands if i['verdict']=='UNJUDGED'])} unjudged.")
    if orphans:
        print("Removing an ORPHAN costs no speech — the mute test proves it.")
        print("Still send Sapro the six seconds around it before the full file.")
    if keeps:
        print("A KEEP is speech. Do not silence it. That is how a word gets eaten.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
