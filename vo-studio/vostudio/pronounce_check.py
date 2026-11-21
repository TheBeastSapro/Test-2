#!/usr/bin/env python3
"""
Did the voice say the word RIGHT — not just say the right word?

    python3 pronounce_check.py --audio "Title (final).mp3" --script script.txt

"Quito" was misread and passed every automated gate the old pipeline had. It had
to: WER compares words, and ASR transcribes a mispronounced "Quito" as "Quito",
because ASR is a language model and it corrects what it hears. Sapro caught it by
ear. This is the gate that was missing.

WHY THIS SCREENS PHRASES AND NEVER JUDGES A WORD
    The obvious build -- phonemize the word, recognise the phones in its audio,
    measure the distance -- does not work, and the measurements are why. Run on
    single-word slices from a file Sapro confirmed was perfect:

        word         expected        heard        dist/phone
        Hashish      hæʃɪʃ           hɒsiː             0.237
        India        ɪndiə           ʔɛndiːa           0.217
        evidence     ɛvɪdəns         ɛbən              0.411
        prove        pɹuːv           tʰɒ               0.433
        no           noʊ             (nothing)         0.924
        army         ɑːɹmi           (nothing)         0.733

        median 0.494, range 0.217-0.924 on KNOWN-GOOD audio

    Half the phonetic features come back wrong on correctly-read words, and some
    words return no phones at all. There is no threshold in that range that
    separates a good read from a bad one -- a per-word checker built on it flags
    the entire file. That is the false-positive verifier this project has already
    lost an hour to once.

    The same recogniser on whole phrases, same audio:

        2.4 s phrase   36 expected phones   dist/phone 0.171
        3.4 s phrase   58 expected phones   dist/phone 0.317
        4.5 s phrase   70 expected phones   dist/phone 0.110

    Three to four times better. Phones are recognised from context, and a phrase
    supplies context a 300 ms word does not.

    So: measure per phrase, and flag a phrase only when it is an OUTLIER AGAINST
    THIS FILE'S OWN DISTRIBUTION. Never an absolute threshold -- the baseline moves
    with the voice, the sample rate, and the recogniser version. This is the same
    lesson as the WER threshold that sat below the median of good audio and failed
    everything.

WHAT IT OUTPUTS
    A ranked listening list, not a verdict. "These five seconds are anomalous,
    listen to them." Sapro's ear is the judge; this only tells him where to point it.
"""
import argparse
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


def phonemize_text(text: str) -> str:
    """
    Numerals go through the SAME expansion the generator used, or every year is a
    false positive.

    Caught by the first real run: "In 1798" flagged as the worst phrase in a
    60-second excerpt. The voice was right — it said "seventeen ninety-eight". The
    check was wrong: espeak expands 1798 to "one thousand seven hundred ninety-eight",
    so the expected phones were a different sentence from the one that was rendered.

    Any transform the script gets on the way to the model has to be applied here too.
    A checker that phonemizes different text than was spoken is measuring its own
    preprocessing.
    """
    from phonemizer import phonemize
    try:
        from .script_prep import spell_numerals
    except ImportError:                       # running as a standalone script
        from script_prep import spell_numerals
    return phonemize(spell_numerals(text), language="en-us", backend="espeak",
                     strip=True, with_stress=False, njobs=1).replace(" ", "")


def slice_audio(src: Path, start: float, end: float) -> Path:
    """16 kHz mono — what the phone recogniser expects."""
    out = Path(tempfile.mkdtemp()) / "seg.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start),
                    "-t", str(max(0.05, end - start)), "-i", str(src),
                    "-ar", "16000", "-ac", "1", str(out)], check=True)
    return out


def score_phrases(audio: Path, phrases, log=print):
    """
    phrases: iterable of (start_s, end_s, text).
    Returns each with its feature-edit distance per expected phone.
    """
    from allosaurus.app import read_recognizer
    import panphon.distance

    recognizer = read_recognizer()
    dist = panphon.distance.Distance()

    scored = []
    for i, (start, end, text) in enumerate(phrases):
        expected = phonemize_text(text)
        if not expected:
            continue
        heard = recognizer.recognize(str(slice_audio(audio, start, end)),
                                     "eng").replace(" ", "")
        d = dist.feature_edit_distance(expected, heard) / len(expected)
        scored.append({
            "index": i, "start": start, "end": end, "text": text,
            "expected": expected, "heard": heard,
            "n_expected": len(expected), "n_heard": len(heard), "distance": d,
        })
        log(f"  [{i+1}/{len(phrases)}] {d:.3f}  {text[:52]}")
    return scored


def flag_outliers(scored, k: float = 2.0, min_phones: int = 12):
    """
    Median + k*MAD, computed over this file.

    MAD rather than standard deviation because one genuinely bad phrase would
    inflate a standard deviation enough to hide itself. Phrases with very few
    expected phones are scored but never flagged -- that is the single-word regime
    where the measurement is noise.
    """
    usable = [s for s in scored if s["n_expected"] >= min_phones]
    if len(usable) < 4:
        return [], None, None

    values = [s["distance"] for s in usable]
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values]) or 1e-6
    threshold = median + k * mad

    for s in scored:
        s["threshold"] = threshold
        s["flagged"] = (s["n_expected"] >= min_phones and s["distance"] > threshold)
    return [s for s in scored if s.get("flagged")], median, threshold


def parse_script(path: Path):
    """One phrase per non-empty line: 'start end text' or plain text with --auto."""
    phrases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) == 3:
            try:
                phrases.append((float(parts[0]), float(parts[1]), parts[2]))
                continue
            except ValueError:
                pass
        phrases.append((None, None, line))
    return phrases


def phrases_from_asr(audio: Path, model: str = "distil-large-v3"):
    """
    No timed script? Take the phrases from ASR's own segmentation.

    This checks the voice against what ASR heard, not against the script, so it
    cannot catch a dropped word — readcheck.py does that. What it still catches is
    the case that matters here: ASR writes the correctly-spelled word while the
    audio says something else.
    """
    from faster_whisper import WhisperModel
    # float32 — int8 hallucinates, and a hallucinated segment boundary would
    # silently move the audio being scored out from under its text.
    m = WhisperModel(model, device="cpu", compute_type="float32")
    segments, _ = m.transcribe(str(audio), language="en", vad_filter=False, beam_size=5)
    return [(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--script", help="lines of 'start end text'; omit to use ASR segments")
    ap.add_argument("--k", type=float, default=2.0,
                    help="flag above median + k*MAD (default 2.0)")
    ap.add_argument("--min-phones", type=int, default=12,
                    help="phrases shorter than this are scored but never flagged")
    ap.add_argument("--asr-model", default="distil-large-v3")
    args = ap.parse_args()

    audio = Path(args.audio)
    phrases = parse_script(Path(args.script)) if args.script else None
    if not phrases or any(p[0] is None for p in phrases):
        print("No timed script — taking phrases from ASR segmentation.\n")
        phrases = phrases_from_asr(audio, args.asr_model)

    print(f"Scoring {len(phrases)} phrases against espeak-ng G2P ...\n")
    scored = score_phrases(audio, phrases)
    flagged, median, threshold = flag_outliers(scored, args.k, args.min_phones)

    if median is None:
        print("\nToo few scoreable phrases to establish a baseline. "
              "Nothing flagged — this is not a pass.")
        return 0

    print(f"\nbaseline median {median:.3f}   flag above {threshold:.3f} "
          f"(median + {args.k}*MAD)")
    print(f"{len(flagged)} phrase(s) worth listening to\n")

    for s in sorted(flagged, key=lambda x: -x["distance"]):
        mm, ss = divmod(s["start"], 60)
        print(f"  {int(mm)}:{ss:05.2f}  dist {s['distance']:.3f}   {s['text']}")
        print(f"       expected {s['expected'][:60]}")
        print(f"       heard    {s['heard'][:60]}")

    if flagged:
        print("\nThese are ANOMALIES, not errors. The recogniser is noisy even on "
              "good audio;\nwhat this says is 'the phones here fit the script worse "
              "than the rest of the file'.\nListen before changing anything. A real "
              "misreading is fixed in the lexicon,\nnot by re-rolling until it goes "
              "away.")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
