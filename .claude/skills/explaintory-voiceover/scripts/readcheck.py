#!/usr/bin/env python3
"""
The listening pass — done by measurement, not by vibes.

`explaintory-vo-master` has a standing rule: never treat a listening model's
description of audio as data. So this does not ask a model what the take sounds
like. It transcribes each section with ASR and diffs the transcript against the
words the section was asked to say, then measures the audio itself.

What it catches, which is what actually forces a redo:
  * misread or substituted words
  * skipped or duplicated clauses
  * a section that cut off early
  * words the voice slurred (low ASR confidence over a run)
  * clipping, dead air, and mid-sentence hesitation
  * a speaking rate outside the channel's band (181 wpm human reference)

Built on the standard tools rather than hand-rolled text matching:
  faster-whisper       distil-large-v3 by default. Small models invent errors
                       ('bow' -> 'mow') and every one of those costs a needless
                       regeneration, so the read-check is only as trustworthy as
                       the model behind it.
  whisper_normalizer   OpenAI's EnglishTextNormalizer. Resolves British vs
                       American spelling (harbour/harbor, programme/program) and
                       spoken numbers ('nineteen forty three' -> 1943), which is
                       most of the apparent-mismatch noise.
  jiwer                WER and the reference/hypothesis alignment.
"""
import argparse
import json
import os
import re
import subprocess
import sys

# Channel reference, measured from the human VO stem (see explaintory-vo-master):
# overall 181 wpm, articulation 197 wpm. A raw TTS section outside this band has
# usually dropped or repeated text.
WPM_LOW, WPM_HIGH = 120.0, 240.0

# Share of a section's words that may diverge before it is redone.
#
# Set from measurement, not taste. On a 40-section render of KNOWN-GOOD audio,
# float32 ASR gives WER 0.000-0.138 with a median of 0.047 — the spread comes from
# proper-noun density, not from the voice. The original 0.05 sat below the median
# and flagged 38 of 40 good sections. 0.20 clears the worst good section with room
# and still catches a render that actually broke down.
WER_FLAG = 0.20

# A run of words the voice slurred: ASR confidence this low over this many words
# in a row means the delivery is genuinely unclear, not that a word is rare.
LOW_CONF = 0.45
LOW_CONF_RUN = 3

# At or below this many words a section is a chapter announcement, not prose.
# Rate and WER are both meaningless there and both produced false redos.
SHORT_SECTION_WORDS = 3

DEFAULT_ASR = "distil-large-v3"

# int8 quantisation invents text on this material. On a clean take it produced
# "COCA! ChAUDIO carried a message from CuscoCommentary to Kito, 1,250 miles of And
# quantity" and dropped "A Roman courier with a paved road" entirely — which read
# as the voice losing words when the words were plainly there. float32 on the same
# file returns it near-perfectly. The read-check is only worth running if it is
# right, so it pays the ~2x cost.
DEFAULT_COMPUTE = "float32"

_NORM = None
_MODEL = None


def log(m):
    print(f"[readcheck] {m}", flush=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


# ------------------------------------------------------------------ text
def normalizer():
    global _NORM
    if _NORM is None:
        from whisper_normalizer.english import EnglishTextNormalizer
        _NORM = EnglishTextNormalizer()
    return _NORM


def normalize(text):
    """Canonical form for comparison. The normalizer handles spelling and numbers;
    the pre-pass only settles how era markers get spaced, which it leaves alone."""
    t = re.sub(r"\b([bB])\.?\s*([cC])\.?(\s*[eE]\.?)?\b", r"BC", text)
    t = re.sub(r"\b([aA])\.?\s*([dD])\.?\b", r"AD", t)
    return normalizer()(t)


def diff_words(expected, heard):
    """-> (wer, [(kind, expected span, heard span, preceding context)])

    Spans that differ only in where the word boundaries fell — 'temple sat' heard
    as 'temples at' — are dropped. Those are the same sounds segmented differently
    by the transcriber, which is by definition not a misread, and the reported WER
    is recomputed without them so it stays a decision-grade number.
    """
    import jiwer
    ref, hyp = normalize(expected), normalize(heard)
    if not ref.strip():
        return 0.0, []
    out = jiwer.process_words(ref, hyp)
    r, h = out.references[0], out.hypotheses[0]
    spans, changed = [], 0
    for ch in out.alignments[0]:
        if ch.type == "equal":
            continue
        exp = " ".join(r[ch.ref_start_idx:ch.ref_end_idx])
        got = " ".join(h[ch.hyp_start_idx:ch.hyp_end_idx])
        if exp.replace(" ", "") == got.replace(" ", ""):
            continue
        changed += max(ch.ref_end_idx - ch.ref_start_idx, ch.hyp_end_idx - ch.hyp_start_idx)
        spans.append((ch.type, exp, got,
                      " ".join(r[max(0, ch.ref_start_idx - 4):ch.ref_start_idx])))
    return (changed / len(r) if r else 0.0), spans


def confidence_index(wordinfo):
    """normalized word -> mean ASR confidence, for judging a substitution."""
    acc = {}
    for w, p, _ in wordinfo:
        for tok in normalize(w).split():
            acc.setdefault(tok, []).append(p)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def classify(spans, conf=None, sure=0.60, guide=None):
    """Which divergences are worth spending credits on.

    A dropped or duplicated run of words cannot be anything but a defect. A
    single substituted word is the ambiguous case — it is either the voice
    misreading or the transcriber guessing — so it is settled by how well the
    transcriber heard it. 'chain' rendered as a confident 'crane' is a misread
    and changes the meaning of the sentence; a word heard hesitantly is not
    evidence of anything and is left to the WER threshold.
    """
    conf = conf or {}
    # The script's own pronunciation guide names every word the transcriber is
    # going to mangle. A span made only of those is the guide doing its job, not
    # the voice failing, so it is reported without costing a re-render.
    hard_words = {w.lower() for entry in (guide or {}) for w in entry.split()}
    hard = []
    for kind, exp, heard, ctx in spans:
        e, h = exp.split(), heard.split()
        if hard_words and e and all(w.lower() in hard_words for w in e):
            continue
        if kind == "delete" and len(e) >= 2:
            hard.append(("skipped", exp, heard, ctx))
        elif kind == "insert" and len(h) >= 2:
            hard.append(("repeated or added", exp, heard, ctx))
        elif kind == "substitute":
            if len(e) >= 2:
                hard.append(("misread", exp, heard, ctx))
                continue
            probs = [conf[w] for w in h if w in conf]
            if probs and sum(probs) / len(probs) >= sure:
                hard.append(("misread", exp, heard, ctx))
    return hard


# ------------------------------------------------------------------ audio
def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def measure(path):
    """Peak, clipping, and the silence map — ffmpeg only."""
    dur = probe_duration(path)
    p = run(["ffmpeg", "-v", "info", "-i", path, "-af",
             "astats=metadata=1:reset=0,silencedetect=n=-45dB:d=0.35",
             "-f", "null", "-"])
    err = p.stderr
    peaks = [float(v) for v in re.findall(r"Peak level dB:\s*(-?\d+\.?\d*)", err)]
    peak = max(peaks) if peaks else None
    # astats names the clip counter differently across ffmpeg builds ('Number of
    # clipped samples' is absent in some), so full-scale hits are read from the
    # peak, which every build reports.
    absmax = re.findall(r"Abs Peak count:\s*(\d+\.?\d*)", err)
    sil = [(float(s), float(e)) for s, e in
           zip(re.findall(r"silence_start:\s*(-?\d+\.?\d*)", err),
               re.findall(r"silence_end:\s*(-?\d+\.?\d*)", err))]
    return {"duration": dur, "peak_dbfs": peak,
            "at_ceiling": peak is not None and peak >= -0.1,
            "full_scale_samples": int(float(absmax[0])) if absmax else 0,
            "silences": sil}


# ------------------------------------------------------------------ asr
def load_asr(size=DEFAULT_ASR, compute=DEFAULT_COMPUTE):
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    from faster_whisper import WhisperModel
    log(f"loading ASR ({size}, cpu {compute}) — first run downloads the model")
    _MODEL = WhisperModel(size, device="cpu", compute_type=compute)
    return _MODEL


def transcribe(model, path):
    """-> (text, [(word, probability, start)])"""
    segs, _ = model.transcribe(path, language="en", beam_size=5,
                               condition_on_previous_text=False,
                               word_timestamps=True)
    text, words = [], []
    for s in segs:
        text.append(s.text.strip())
        for w in (s.words or []):
            words.append((w.word.strip(), float(w.probability), float(w.start)))
    return " ".join(text).strip(), words


def slurred_runs(words):
    """Consecutive words the model heard poorly — where the delivery is unclear."""
    runs, cur = [], []
    for w, p, t in words:
        if p < LOW_CONF:
            cur.append((w, t))
        else:
            if len(cur) >= LOW_CONF_RUN:
                runs.append(cur)
            cur = []
    if len(cur) >= LOW_CONF_RUN:
        runs.append(cur)
    return runs


# ------------------------------------------------------------------ check
def check_sections(sections, parts_dir, asr_size=DEFAULT_ASR, guide=None):
    model = load_asr(asr_size)
    results = []
    for sec in sections:
        i = sec["index"]
        path = os.path.join(parts_dir, f"sec_{i:03d}.mp3")
        if not os.path.isfile(path):
            results.append({"index": i, "problems": ["missing audio"], "regen": True})
            continue

        m = measure(path)
        words = len(sec["send_text"].split())
        wpm = words / (m["duration"] / 60) if m["duration"] > 0.2 else 0.0

        # A chapter announcement is one or two words — "Pervitin.", "Coca." — and
        # neither rate nor WER survives at that length. The word is said slowly and
        # deliberately on purpose, so wpm reads ~70 against a 180 body median and
        # looks like dropped text; and a single name the transcriber spells
        # "Pervatin" is a WER of 1.00 from one harmless miss. Both flagged real
        # chapter names for re-render. The audio checks below still apply, because
        # clipping and dead air mean the same thing at any length.
        too_short_to_rate = words <= SHORT_SECTION_WORDS

        heard, wordinfo = transcribe(model, path)
        wer, spans = diff_words(sec["send_text"], heard)
        hard = classify(spans, confidence_index(wordinfo), guide=guide)

        problems, regen = [], False
        for kind, exp, got, ctx in hard:
            problems.append(f"{kind}: after “…{ctx}” expected “{exp}” heard “{got}”")
        if hard or (wer > WER_FLAG and not too_short_to_rate):
            regen = True
        if too_short_to_rate and (hard or wer > WER_FLAG):
            # say it, spend nothing — a misheard chapter name is a lexicon question
            problems.append(f"chapter name “{sec['send_text'].strip()}” transcribed as "
                            f"“{heard.strip()}” — too short to judge by measurement; "
                            f"listen once, and seed the lexicon if it is really wrong")
            regen = False

        for r in slurred_runs(wordinfo):
            problems.append(f"slurred at {r[0][1]:.1f}s: “{' '.join(w for w, _ in r)}”")
            regen = True

        if m["duration"] < 0.25:
            problems.append("section is silent or near-empty")
            regen = True
        if wpm and not too_short_to_rate and not (WPM_LOW <= wpm <= WPM_HIGH):
            # An odd rate has two very different causes and only one of them is worth
            # credits. If the transcript matches the script, every word is present and
            # the section is merely fast or slow — a timing problem, which the master
            # fixes exactly and a re-roll would not. Only a rate that comes WITH
            # missing or duplicated words means the render actually lost text.
            if not hard and wer <= WER_FLAG:
                problems.append(
                    f"reads at {wpm:.0f} wpm — every word is there, so this is pace, "
                    f"not lost text. Levelled by the master's --max-wpm; "
                    f"re-rendering would not fix it")
            else:
                problems.append(f"speaking rate {wpm:.0f} wpm is outside "
                                f"{WPM_LOW:.0f}–{WPM_HIGH:.0f}, and the transcript "
                                f"disagrees — text was dropped or repeated")
                regen = True
        if m["at_ceiling"]:
            problems.append(f"peaks at {m['peak_dbfs']:+.2f} dBFS — against the ceiling "
                            f"({m['full_scale_samples']} full-scale samples)")
        # dead air inside a section: the model hesitating mid-thought. Edge silence is
        # normal (~0.2s) and the mastering pass retimes it, so only interior gaps count.
        for s, e in m["silences"]:
            if e - s >= 0.7 and s > 0.35 and e < m["duration"] - 0.35:
                problems.append(f"{e-s:.2f}s of dead air at {s:.1f}s inside the section")
                regen = True

        results.append({"index": i, "duration": round(m["duration"], 2),
                        "wpm": round(wpm), "peak_dbfs": m["peak_dbfs"],
                        "wer": round(wer, 4), "problems": problems, "regen": regen,
                        "hard": [list(x) for x in hard],
                        "text": sec["send_text"], "heard": heard})
    return results


def settle_repeats(results, seen):
    """Stop paying to re-render a word the voice says the same way every time.

    Two independent takes producing the same 'wrong' word means the render is
    consistent, so a third will not differ. Either it is a name the transcriber
    spells its own way ('Angolpo', 'Hiero') — harmless — or the voice really does
    say it wrong every time, which needs the script or a pronunciation fix rather
    than another take. Both are worth a human ear and neither is worth more credits.

    `seen` maps section index -> set of (expected, heard) pairs from earlier rounds
    and is updated in place. Returns the sections that settled this way.
    """
    settled = []
    for r in results:
        idx = r["index"]
        pairs = {(h[1], h[2]) for h in r.get("hard", []) if h[0] == "misread"}
        repeats = pairs & seen.get(idx, set())
        seen.setdefault(idx, set()).update(pairs)
        if not repeats:
            continue
        kept = [h for h in r["hard"] if (h[1], h[2]) not in repeats]
        for exp, got in sorted(repeats):
            r["problems"] = [p for p in r["problems"] if f"“{exp}”" not in p]
            r["problems"].append(
                f"“{exp}” came out as “{got}” on two separate takes — consistent, so "
                f"another render will not change it. Either a name the transcriber "
                f"spells its own way, or a pronunciation to fix in the script. Listen.")
        r["hard"] = kept
        r["settled"] = sorted(repeats)
        settled.append(r)
        # only the settled substitutions were holding this section open
        if not kept and r["wer"] <= WER_FLAG and not any(
                k in p for p in r["problems"]
                for k in ("skipped", "repeated", "slurred", "dead air",
                          "speaking rate", "silent or near-empty", "missing audio")):
            r["regen"] = False
    return settled


def report(results):
    for r in results:
        if r["problems"]:
            print(f"{'REDO' if r['regen'] else 'note'} section {r['index']+1} "
                  f"({r.get('wpm', 0)} wpm, {r.get('duration', 0)}s, wer {r.get('wer')})")
            for p in r["problems"]:
                print(f"     {p}")
        elif r["regen"]:
            print(f"REDO section {r['index']+1} (wer {r.get('wer')} over threshold)")
            print(f"     heard: {r.get('heard','')[:160]}")
    bad = [r for r in results if r["regen"]]
    print(f"\n{len(results)} sections · {len(bad)} need a redo")
    return bad


def main():
    ap = argparse.ArgumentParser(description="Read-check generated voiceover sections.")
    ap.add_argument("--sections-json", required=True, help="manifest from generate.py")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--asr-model", default=DEFAULT_ASR)
    ap.add_argument("--json", help="write full results here")
    a = ap.parse_args()

    man = json.load(open(a.sections_json, encoding="utf-8"))
    results = check_sections(man["sections"], a.parts_dir, a.asr_model)
    bad = report(results)
    if a.json:
        json.dump({"results": results, "asr_model": a.asr_model},
                  open(a.json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
