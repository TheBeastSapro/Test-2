"""styleprint — measure the delivery fingerprint of a narration.

The point of this module is that "sounds more human" becomes a number you can
compare. Take a fingerprint of a reference narrator, take the same fingerprint
of one of our own takes, and the difference tells you what to change instead of
leaving it to taste.

Two input paths, both producing the SAME fingerprint schema:

  captions  a YouTube ``json3`` auto-caption file. ASR-derived word onsets, so
            the timing is acoustic rather than editorial. No audio needed.
  audio     a wav/mp3, transcribed with faster-whisper for word identity and
            measured with an RMS envelope for pause boundaries. ASR word
            timestamps are NOT trusted for gaps — faster-whisper returns
            contiguous spans, so a real 150 ms hole reads as 0.000 s (see
            HANDOFF.md). Energy decides where silence is; ASR only decides what
            was said.

What it measures, and why each one matters for a "human" read:

  pause-by-slot     how long the narrator rests at a comma vs a full stop vs
                    nothing at all. A TTS voice pauses uniformly; a human's
                    comma is half its full stop and a third of its paragraph.
  holds             pauses long enough to be a deliberate beat (default 700 ms),
                    reported with the words on either side, because WHERE a
                    narrator holds is the style, not that they hold at all.
  articulation rate the words-per-minute of speech with the silence removed. A
                    narrator who sounds unhurried is usually speaking FAST and
                    resting often, not speaking slowly.
  rhythm            sentence lengths in sequence, and how often a long sentence
                    is answered by a short one.

Caveat carried in the output: pause length is inferred from inter-onset
intervals against a per-word expected-duration model, so a word that is
LENGTHENED for emphasis reads as a slightly longer pause. The NONE-slot median
is printed as a built-in check — if the model is honest it sits near zero.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Slot = the syntactic position a pause sits in, read off the trailing
# punctuation of the word before it. This is the axis a human narrator varies
# and a TTS voice flattens.
SLOT_SENT = "sentence"      # . ! ?
SLOT_CLAUSE = "clause"      # , ; :
SLOT_DASH = "dash"          # — – --
SLOT_ELLIPSIS = "ellipsis"  # ...
SLOT_NONE = "none"          # mid-phrase, no punctuation
SLOTS = (SLOT_SENT, SLOT_CLAUSE, SLOT_DASH, SLOT_ELLIPSIS, SLOT_NONE)

_TERMINAL = re.compile(r"[.!?]+[\"')\]]*$")
_CLAUSE = re.compile(r"[,;:]+[\"')\]]*$")
_DASH = re.compile(r"(--|[—–])[\"')\]]*$")
_ELLIPSIS = re.compile(r"(\.\.\.|…)[\"')\]]*$")


# Machine-generated captions carry channel annotation inline with speech:
# sound-event tags in brackets and ">>" speaker-change markers. Left in, they
# count as words, invent sentence boundaries, and — worst — the silence around
# a [music] tag reads as the narrator's longest dramatic hold when it is
# actually a passage with no narration in it. Everything matched here is
# annotation, and the boundary either side of it is withdrawn from the pause
# statistics rather than guessed at.
_NONSPEECH = re.compile(r"^(?:&gt;&gt;|>>)?\s*(?:\[[^\]]*\]|♪+|&gt;&gt;|>>)\s*$")
_SPEAKER_MARK = re.compile(r"^(?:&gt;&gt;|>>)\s*")


def is_nonspeech(text: str) -> bool:
    return bool(_NONSPEECH.match(text.strip()))


@dataclass
class Word:
    t: float          # onset, seconds
    text: str         # as spoken, punctuation retained
    end: float | None = None   # known offset, seconds (audio path only)
    # True when the boundary AFTER this word touched stripped annotation, so
    # the gap there is unattributable and must not enter the slot statistics.
    tainted: bool = False

    @property
    def bare(self) -> str:
        return re.sub(r"[^\w']", "", self.text)

    @property
    def slot(self) -> str:
        t = self.text.rstrip()
        if _ELLIPSIS.search(t):
            return SLOT_ELLIPSIS
        if _DASH.search(t):
            return SLOT_DASH
        if _TERMINAL.search(t):
            return SLOT_SENT
        if _CLAUSE.search(t):
            return SLOT_CLAUSE
        return SLOT_NONE


@dataclass
class Pause:
    t: float          # where the silence starts, seconds
    dur: float        # seconds
    slot: str
    before: str       # a few words leading in — context for a hold
    after: str


@dataclass
class Fingerprint:
    source: str = ""
    method: str = ""
    duration_s: float = 0.0
    n_words: int = 0
    speech_wpm: float = 0.0
    articulation_wpm: float = 0.0
    silence_ratio: float = 0.0
    pause_rate_per_min: float = 0.0
    slots: dict = field(default_factory=dict)
    holds: list = field(default_factory=list)
    section_gaps: list = field(default_factory=list)
    sentences: dict = field(default_factory=dict)
    wpm_buckets: list = field(default_factory=list)
    stripped: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# input: youtube json3 captions
# --------------------------------------------------------------------------

def load_json3(path: str | Path) -> list[Word]:
    """Word onsets from a YouTube json3 auto-caption file.

    Every segment carries an offset from its event's start, so absolute onset
    is ``tStartMs + tOffsetMs``. Newline-only append events are layout, not
    speech, and are dropped. Events can overlap when captions roll, so the
    result is sorted and de-duplicated on (onset, text).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw: list[Word] = []
    for ev in data.get("events", []):
        base = ev.get("tStartMs", 0)
        for seg in ev.get("segs") or []:
            txt = seg.get("utf8", "")
            if not txt.strip():
                continue
            raw.append(Word(t=(base + seg.get("tOffsetMs", 0)) / 1000.0,
                            text=txt.strip()))
    raw.sort(key=lambda w: w.t)

    deduped: list[Word] = []
    for w in raw:
        if deduped and abs(deduped[-1].t - w.t) < 1e-6 and deduped[-1].text == w.text:
            continue
        deduped.append(w)

    # Drop annotation, and taint the surviving word on either side of it.
    # "tainted" marks the word whose FOLLOWING gap spanned the annotation —
    # that is the one gap we cannot attribute, so it is the only one withdrawn.
    out: list[Word] = []
    stripped: list[str] = []
    for w in deduped:
        if is_nonspeech(w.text):
            stripped.append(w.text)
            if out:
                out[-1].tainted = True
            continue
        w.text = _SPEAKER_MARK.sub("", w.text).strip()
        if not w.text:
            continue
        out.append(w)
    load_json3.stripped = stripped   # method note: what was removed, for the record
    return out


# --------------------------------------------------------------------------
# input: audio + ASR + energy-based silence
# --------------------------------------------------------------------------

def load_audio(path: str | Path, model_size: str = "base.en") -> tuple[list[Word], float, list[tuple[float, float]]]:
    """Words from ASR, silences from the RMS envelope.

    Returns ``(words, duration, silences)``. The silences are the authority on
    gaps; the ASR spans are only used to name what sits on either side.
    """
    import numpy as np
    import librosa
    from faster_whisper import WhisperModel

    y, sr = librosa.load(str(path), sr=16000, mono=True)
    duration = len(y) / sr

    # RMS envelope, 20 ms hop. The threshold is adaptive: 18 dB below the
    # speech level (the 85th percentile of frame energy), floored so that a
    # quiet recording cannot make everything look like silence.
    hop = int(0.020 * sr)
    rms = librosa.feature.rms(y=y, frame_length=int(0.040 * sr), hop_length=hop)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-10))
    speech_level = float(np.percentile(db, 85))
    thresh = max(speech_level - 18.0, float(np.percentile(db, 5)) + 3.0)

    quiet = db < thresh
    silences: list[tuple[float, float]] = []
    start = None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            a, b = start * hop / sr, i * hop / sr
            if b - a >= 0.060:          # below this it is a stop consonant
                silences.append((a, b))
            start = None
    if start is not None:
        silences.append((start * hop / sr, len(quiet) * hop / sr))

    model = WhisperModel(model_size, device="cpu", compute_type="float32")
    segments, _ = model.transcribe(str(path), word_timestamps=True,
                                   vad_filter=False, beam_size=5)
    words: list[Word] = []
    for seg in segments:
        for w in (seg.words or []):
            words.append(Word(t=w.start, text=w.word.strip(), end=w.end))
    return words, duration, silences


# --------------------------------------------------------------------------
# pause estimation
# --------------------------------------------------------------------------

def _expected_duration_model(words: list[Word], q: float = 0.50):
    """Fit expected pause-free word duration against character count.

    Inter-onset interval = word duration + whatever pause follows. Taking a low
    quantile of IOI within each length bin selects the instances that had no
    pause after them, so a line fitted through those quantiles predicts
    articulation alone. Returns ``f(n_chars) -> seconds``.

    ``q`` was calibrated by sweeping 0.25..0.75 over both reference narrations.
    The ABSOLUTE pause lengths move with it (a sentence pause reads 0.56 s at
    q=0.25 and 0.42 s at q=0.75) but the RATIOS between slots barely move, and
    the median mid-phrase pause holds near 0.14 s at every setting — which is
    what says those gaps are real speech behaviour rather than an artefact of
    the fit. 0.50 is the median word duration: it puts the silence ratio near
    20% and the articulation rate inside the range narration actually occupies.
    Read slot medians as accurate to about +/-0.05 s, and slot RATIOS as solid.
    """
    bins: dict[int, list[float]] = {}
    for a, b in zip(words, words[1:]):
        if a.tainted:
            continue
        ioi = b.t - a.t
        if not (0.0 < ioi < 4.0):
            continue
        n = min(max(len(a.bare), 1), 14)
        bins.setdefault(n, []).append(ioi)

    pts = [(n, statistics.quantiles(v, n=100)[int(q * 100) - 1])
           for n, v in sorted(bins.items()) if len(v) >= 20]
    if len(pts) < 3:
        return lambda n: 0.055 * min(max(n, 1), 14) + 0.10

    # least squares through the per-bin quantiles
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    slope = max(slope, 0.010)
    return lambda n: max(0.060, intercept + slope * min(max(n, 1), 14))


def _context(words: list[Word], i: int, back: int = 6, fwd: int = 4) -> tuple[str, str]:
    before = " ".join(w.text for w in words[max(0, i - back + 1): i + 1])
    after = " ".join(w.text for w in words[i + 1: i + 1 + fwd])
    return before, after


def pauses_from_onsets(words: list[Word], q: float = 0.50,
                       floor: float = 0.080) -> tuple[list[Pause], object]:
    """Pause after each word, inferred from inter-onset intervals."""
    model = _expected_duration_model(words, q=q)
    out: list[Pause] = []
    for i, (a, b) in enumerate(zip(words, words[1:])):
        if a.tainted:            # the gap here spanned stripped annotation
            continue
        expected = a.end - a.t if a.end is not None else model(len(a.bare))
        gap = (b.t - a.t) - expected
        if gap < floor:
            continue
        before, after = _context(words, i)
        out.append(Pause(t=a.t + expected, dur=round(gap, 3), slot=a.slot,
                         before=before, after=after))
    return out, model


def pauses_from_silence(words: list[Word], silences: list[tuple[float, float]],
                        floor: float = 0.080) -> list[Pause]:
    """Measured silences, each attributed to the word it follows."""
    out: list[Pause] = []
    for a, b in silences:
        dur = b - a
        if dur < floor:
            continue
        idx = None
        for i, w in enumerate(words):
            if w.t <= a:
                idx = i
            else:
                break
        if idx is None or words[idx].tainted:
            continue
        before, after = _context(words, idx)
        out.append(Pause(t=round(a, 3), dur=round(dur, 3), slot=words[idx].slot,
                         before=before, after=after))
    return out


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------

def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)

    def pct(p):
        if len(s) == 1:
            return round(s[0], 3)
        k = (len(s) - 1) * p
        lo, hi = math.floor(k), math.ceil(k)
        return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)

    return {"n": len(s), "mean": round(statistics.mean(s), 3), "median": pct(0.50),
            "p10": pct(0.10), "p25": pct(0.25), "p75": pct(0.75),
            "p90": pct(0.90), "max": round(s[-1], 3)}


def fingerprint(words: list[Word], pauses: list[Pause], duration: float,
                source: str, method: str, hold_min: float = 0.70,
                section_min: float = 2.0, stripped: list[str] | None = None) -> Fingerprint:
    fp = Fingerprint(source=source, method=method,
                     duration_s=round(duration, 2), n_words=len(words))
    fp.stripped = {"n": len(stripped or []),
                   "tokens": sorted(set(stripped or [])),
                   "tainted_boundaries": sum(1 for w in words if w.tainted)}

    total_pause = sum(p.dur for p in pauses)
    speaking = max(duration - total_pause, 1e-6)
    fp.speech_wpm = round(len(words) / (duration / 60.0), 1)
    fp.articulation_wpm = round(len(words) / (speaking / 60.0), 1)
    fp.silence_ratio = round(total_pause / duration, 3)
    fp.pause_rate_per_min = round(
        len([p for p in pauses if p.dur >= 0.15]) / (duration / 60.0), 1)

    for slot in SLOTS:
        vals = [p.dur for p in pauses if p.slot == slot]
        fp.slots[slot] = _stats(vals)

    fp.holds = [asdict(p) for p in sorted(pauses, key=lambda p: -p.dur)
                if p.dur >= hold_min][:60]
    fp.section_gaps = [asdict(p) for p in pauses if p.dur >= section_min]

    # sentence rhythm
    lens, cur = [], 0
    for w in words:
        cur += 1
        if w.slot == SLOT_SENT:
            lens.append(cur)
            cur = 0
    if cur:
        lens.append(cur)
    buckets = {"1-3": 0, "4-7": 0, "8-12": 0, "13-20": 0, "21-30": 0, "31+": 0}
    for n in lens:
        key = ("1-3" if n <= 3 else "4-7" if n <= 7 else "8-12" if n <= 12
               else "13-20" if n <= 20 else "21-30" if n <= 30 else "31+")
        buckets[key] += 1
    punch = sum(1 for a, b in zip(lens, lens[1:]) if a >= 20 and b <= 5)
    fp.sentences = {
        "n": len(lens),
        "words": _stats([float(n) for n in lens]),
        "histogram": buckets,
        "pct_short_le5": round(100 * sum(1 for n in lens if n <= 5) / max(len(lens), 1), 1),
        "pct_long_ge20": round(100 * sum(1 for n in lens if n >= 20) / max(len(lens), 1), 1),
        "long_then_punch": punch,
        "long_then_punch_per_100_sent": round(100 * punch / max(len(lens), 1), 1),
        "sequence": lens,
    }

    # tempo over time, 30 s buckets
    if words:
        nb = int(duration // 30) + 1
        counts = [0] * nb
        for w in words:
            counts[min(int(w.t // 30), nb - 1)] += 1
        fp.wpm_buckets = [round(c * 2.0, 1) for c in counts]

    none_med = fp.slots[SLOT_NONE].get("median", 0.0)
    fp.checks = {
        "none_slot_median_s": none_med,
        "none_slot_median_ok": bool(none_med <= 0.20),
        "note": ("Pause is inferred, not measured, on the captions path: a word "
                 "lengthened for emphasis inflates the pause after it. If the "
                 "none-slot median drifts above ~0.20 s the duration model is "
                 "under-predicting and the slot means should be read as upper "
                 "bounds."),
    }
    return fp


def summarize(fp: Fingerprint) -> str:
    L = [f"# styleprint — {fp.source}", "",
         f"method: {fp.method}",
         f"duration {fp.duration_s:.1f}s | {fp.n_words} words",
         "",
         "## rate",
         f"- speech rate       {fp.speech_wpm} wpm  (clock time)",
         f"- articulation rate {fp.articulation_wpm} wpm  (silence removed)",
         f"- silence ratio     {fp.silence_ratio:.1%} of the runtime",
         f"- pauses >=150ms    {fp.pause_rate_per_min}/min",
         "",
         "## pause by slot (seconds)",
         "| slot | n | median | mean | p25 | p75 | p90 | max |",
         "|---|---|---|---|---|---|---|---|"]
    for slot in SLOTS:
        s = fp.slots.get(slot, {})
        if not s.get("n"):
            L.append(f"| {slot} | 0 | | | | | | |")
            continue
        L.append(f"| {slot} | {s['n']} | {s['median']} | {s['mean']} | "
                 f"{s['p25']} | {s['p75']} | {s['p90']} | {s['max']} |")

    sent = fp.sentences
    L += ["", "## sentence rhythm",
          f"- {sent['n']} sentences, median {sent['words'].get('median')} words, "
          f"p10 {sent['words'].get('p10')} / p90 {sent['words'].get('p90')}",
          f"- {sent['pct_short_le5']}% are <=5 words; {sent['pct_long_ge20']}% are >=20",
          f"- long(>=20) answered by short(<=5): {sent['long_then_punch']} times "
          f"({sent['long_then_punch_per_100_sent']} per 100 sentences)",
          "- histogram: " + ", ".join(f"{k}={v}" for k, v in sent["histogram"].items()),
          "", f"## holds >=0.70s ({len(fp.holds)} shown, longest first)"]
    for h in fp.holds[:25]:
        L.append(f"- {h['dur']:.2f}s @ {h['t']:.1f}s [{h['slot']}] "
                 f"...{h['before']} ⟨HOLD⟩ {h['after']}...")
    L += ["", f"## section gaps >=2.0s: {len(fp.section_gaps)}"]
    for g in fp.section_gaps[:15]:
        L.append(f"- {g['dur']:.2f}s @ {g['t']:.1f}s  ...{g['before']} ⟨GAP⟩ {g['after']}...")
    st = fp.stripped
    L += ["", "## source hygiene",
          f"- stripped {st.get('n', 0)} non-speech caption tokens "
          f"({', '.join(st.get('tokens') or []) or 'none'})",
          f"- {st.get('tainted_boundaries', 0)} boundaries withdrawn from the "
          f"pause statistics because the gap there spanned stripped annotation",
          "", "## checks",
          f"- none-slot median {fp.checks['none_slot_median_s']}s "
          f"({'ok' if fp.checks['none_slot_median_ok'] else 'HIGH — read slot values as upper bounds'})",
          f"- {fp.checks['note']}"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", help="a .json3 caption file, or an audio file")
    ap.add_argument("--json", help="write the fingerprint here")
    ap.add_argument("--md", help="write the readable summary here")
    ap.add_argument("--hold-min", type=float, default=0.70)
    ap.add_argument("--section-min", type=float, default=2.0)
    ap.add_argument("--quantile", type=float, default=0.50,
                    help="quantile used to fit pause-free word duration")
    ap.add_argument("--asr-model", default="base.en")
    a = ap.parse_args(argv)

    path = Path(a.input)
    if path.suffix == ".json3" or path.name.endswith(".json3"):
        words = load_json3(path)
        if not words:
            print("no words parsed", file=sys.stderr)
            return 1
        duration = words[-1].t + 1.0
        pauses, _ = pauses_from_onsets(words, q=a.quantile)
        stripped = getattr(load_json3, "stripped", [])
        method = f"captions/json3, inferred pauses (q={a.quantile})"
    else:
        words, duration, silences = load_audio(path, model_size=a.asr_model)
        pauses = pauses_from_silence(words, silences)
        stripped = []
        method = f"audio, RMS-measured silence + {a.asr_model} ASR"

    fp = fingerprint(words, pauses, duration, source=path.name, method=method,
                     hold_min=a.hold_min, section_min=a.section_min,
                     stripped=stripped)
    md = summarize(fp)
    if a.json:
        Path(a.json).write_text(json.dumps(asdict(fp), indent=2), encoding="utf-8")
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    if not a.json and not a.md:
        print(md)
    else:
        print(md.split("## holds")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
