"""Insert the V2 mid-phrase rests into rendered audio, for nothing.

The measured difference between the reference narrators and a TTS read is that
they stop about once every ten words at places the punctuation does not mark.
The obvious way to ask for that is a ``<break>`` tag in the text — but a break
tag is billed like any other character, and at the measured rate it inflates a
script by 36-43%. On a 4,500-word script that is roughly 9,000 extra characters
bought purely to describe silence.

Silence does not need to be bought. A rest is a timing edit, and this pipeline
already does timing edits after the render — which is also the standing rule
here: repair first, generate last, because a gap is editable for free and only
a genuinely bad reading justifies credits.

So this module takes the delivered audio and opens the gaps itself:

  1. align the audio to the script with word-level ASR
  2. for each rest the planner chose, find the word boundary it belongs to
  3. slide the cut to the quietest point within a short window, so the splice
     lands between the words rather than inside one
  4. insert room tone of the planned length — never digital silence, which
     reads as a dropout in the middle of speech
  5. prove, sample for sample, that nothing but silence was added

Step 4 is the one that is easy to get wrong. A decoded MP3 has no exact zeros
in it; its quiet passages sit around -51 dBFS of codec noise. Splicing true
digital silence into that floor is audible as a hole. The tone inserted here is
sampled from the file's own existing pauses, so the noise floor continues
across the new gap.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

FADE_S = 0.003          # matches the 3 ms edge fade the section splicer uses
SEARCH_S = 0.080        # how far either side of the ASR boundary to hunt for quiet


@dataclass
class Insertion:
    at_s: float
    seconds: float
    after_word: str
    before_word: str
    site: str
    score: float = 0.0       # the planner's measured lift for this site


def _load(path):
    import librosa
    y, sr = librosa.load(str(path), sr=None, mono=True)
    return y, sr


def _align(path, model_size="base.en"):
    from faster_whisper import WhisperModel
    # float32 deliberately: at int8 the read-check hallucinated dropped words,
    # and this module's whole safety check is "did a word disappear".
    model = WhisperModel(model_size, device="cpu", compute_type="float32")
    segments, _ = model.transcribe(str(path), word_timestamps=True,
                                   vad_filter=False, beam_size=5)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"text": w.word.strip(), "start": w.start, "end": w.end})
    return words


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _quietest_point(y, sr, centre_s: float, search_s: float = SEARCH_S) -> float:
    """Slide the cut to the lowest-energy sample near the boundary.

    ASR boundaries land inside consonants often enough that cutting at the
    reported time alone produces clicks. The minimum of a short RMS window is a
    far better guess at where the words actually separate.
    """
    import numpy as np
    lo = max(0, int((centre_s - search_s) * sr))
    hi = min(len(y), int((centre_s + search_s) * sr))
    if hi - lo < 64:
        return centre_s
    win = max(int(0.005 * sr), 16)
    seg = y[lo:hi].astype("float64")
    energy = np.convolve(seg * seg, np.ones(win) / win, mode="same")
    return (lo + int(np.argmin(energy))) / sr


def _envelope_db(y, sr):
    """Frame energy of the whole file in dB, plus the silence threshold.

    Computed once. The first version convolved the entire signal inside
    _existing_gap, which was then called once per pause — on a 12-minute file
    with 321 pauses to open, that is 321 passes over 35 million samples, and it
    simply never finished. Anything O(length) has to live outside the loop.
    """
    import numpy as np
    frame = max(int(0.020 * sr), 32)
    rms = np.sqrt(np.convolve(y.astype("float64") ** 2,
                              np.ones(frame) / frame, mode="same"))
    db = 20 * np.log10(np.maximum(rms, 1e-10))
    return db, float(np.percentile(db, 85)) - 18.0


def _existing_gap(y, sr, centre_s: float, max_look: float = 0.60,
                  env=None) -> float:
    """How much silence the take already has at this boundary.

    Measured the same way styleprint measures a pause: frames below an adaptive
    threshold set relative to the file's own speech level, so it does not need
    a fixed dBFS assumption that a quiet render would break.
    """
    hop = max(int(0.005 * sr), 1)
    db_all, thresh = env if env is not None else _envelope_db(y, sr)

    c = int(centre_s * sr)
    lo, hi = c, c
    limit = int(max_look * sr)
    while lo > max(0, c - limit) and db_all[lo] < thresh:
        lo -= hop
    while hi < min(len(y) - 1, c + limit) and db_all[hi] < thresh:
        hi += hop
    return max(0.0, (hi - lo) / sr) if db_all[c] < thresh else 0.0


def _room_tone_template(y, sr):
    """The file's own quietest 50 ms. Found once per file, never per pause."""
    import numpy as np
    win = max(int(0.050 * sr), 64)
    if len(y) < win * 4:
        return np.zeros(win, dtype=y.dtype)
    # RMS over non-overlapping windows; take the quietest that is not the very
    # start or end of the file, where a fade-in can masquerade as room tone.
    n = len(y) // win
    trimmed = y[:n * win].reshape(n, win)
    rms = np.sqrt((trimmed.astype("float64") ** 2).mean(axis=1))
    inner = slice(1, max(2, n - 1))
    idx = int(np.argmin(rms[inner])) + 1
    return trimmed[idx].copy()


def _room_tone(template, sr, seconds: float):
    """`seconds` of room tone, tiled from the template.

    Digital silence would be wrong: the surrounding material has a noise floor,
    and a gap that drops below it is heard as a dropout rather than a pause.
    """
    import numpy as np
    need = int(seconds * sr)
    if need <= 0:
        return np.zeros(0, dtype=template.dtype)
    reps = int(need // len(template)) + 1
    return np.tile(template, reps)[:need].astype(template.dtype)


def plan_stretch(audio_path, target="serious_history", model_size="base.en",
                 floor=0.080, slots=("sentence", "clause"), cap=3.0):
    """Open the pauses a take already has, out to the reference proportions.

    The other route in this module ADDS rests where a script says there should
    be one. This one changes nothing about where the narrator stopped — it only
    lets each stop last as long as the reference's does.

    That distinction came from measuring a real take, and the measurement
    overturned the assumption behind the other route. The take was not missing
    mid-phrase pauses: it had 22.5 a minute against the reference's 23.3, at
    0.120s against 0.138s. Practically identical. What it did not have was any
    SPREAD. Its full stops rested 0.240s where the reference rests 0.498s, so a
    sentence ending sounded barely different from a comma — a ratio of 1.5x
    against the reference's 2.4x. Uniformly short pauses are what reads as
    machine-paced, not absent ones.

    So only the slots that are actually wrong are touched, and each pause is
    SCALED rather than set. Scaling by the ratio of the medians preserves the
    narrator's own relative dynamics — a pause they leaned on stays longer than
    one they did not — while expanding a compressed range to the reference's.
    Setting every pause into the reference band instead would replace one kind
    of uniformity with another, and on the measured take it inflated the
    runtime by 16.7% instead of the 7% the silence ratio actually calls for.

    Only lengthening is done, never shortening. Removing audio to shorten a
    pause risks clipping speech, and a take with this failure mode has nothing
    too long in it anyway.
    """
    import statistics
    import styleprint as sp
    from v2_profile import REFERENCE

    ref = REFERENCE[target]["pause_s"]
    words, duration, silences = sp.load_audio(audio_path, model_size=model_size)
    pauses = sp.pauses_from_silence(words, silences, floor=floor)

    slot_key = {"sentence": "sentence", "clause": "clause", "none": "midphrase"}
    factors, mine = {}, {}
    for slot in slots:
        durs = [p.dur for p in pauses if p.slot == slot]
        if not durs:
            continue
        med = statistics.median(durs)
        mine[slot] = round(med, 3)
        factors[slot] = max(1.0, ref[slot_key[slot]]["median"] / med)

    out = []
    for p in pauses:
        f = factors.get(p.slot)
        if not f or f <= 1.0:
            continue
        want = min(p.dur * f, cap)
        need = round(want - p.dur, 3)
        if need < 0.030:
            continue
        out.append(Insertion(at_s=p.t + p.dur / 2, seconds=need,
                             after_word=p.before.split()[-1] if p.before else "",
                             before_word=p.after.split()[0] if p.after else "",
                             site=f"stretch:{p.slot} {p.dur:.2f}->{want:.2f}"))
    stats = {"duration_s": duration, "n_words": len(words),
             "n_pauses": len(pauses), "n_to_stretch": len(out),
             "added_s": round(sum(i.seconds for i in out), 2),
             "slots": list(slots),
             "median_before": mine,
             "scale_factors": {k: round(v, 2) for k, v in factors.items()}}
    return out, stats


def _jitter_s(key: str, lo: float, hi: float) -> float:
    """Stable pseudo-random value in [lo, hi] — same input, same output.

    The references vary their pause lengths; setting every full stop to exactly
    the median would swap one kind of uniformity for another.
    """
    import hashlib
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return round(lo + (hi - lo) * (h / 0xFFFFFFFF), 3)


def _find_boundary(seq, cursor, left, right):
    """Locate the word pair a rest sits between, degrading gracefully.

    The script and the ASR sequence never line up exactly — numerals get
    spelled out, and on any difficult passage the transcriber simply mishears.
    An exact pair match is tried first because it is unambiguous; failing that
    the left word alone still identifies the boundary; failing that a close
    spelling does. Anything less certain than that is reported unmatched rather
    than guessed at, because a rest dropped in the wrong place is worse than a
    rest not dropped at all.
    """
    import difflib

    for j in range(cursor, len(seq) - 1):
        if seq[j] == left and (not right or seq[j + 1] == right):
            return j
    for j in range(cursor, len(seq) - 1):
        if seq[j] == left:
            return j
    best, best_score = None, 0.0
    for j in range(cursor, min(len(seq) - 1, cursor + 60)):
        score = difflib.SequenceMatcher(None, seq[j], left).ratio()
        if right and j + 1 < len(seq):
            score = (score + difflib.SequenceMatcher(None, seq[j + 1], right).ratio()) / 2
        if score > best_score:
            best, best_score = j, score
    return best if best_score >= 0.80 else None


def count_existing_rests(audio_path, words, model_size="base.en") -> int:
    """How many mid-phrase rests the take already has, anywhere in it.

    A render is never perfectly even — it rests a little on its own. Those
    rests count toward the target just as much as inserted ones, and ignoring
    them is what made the first test overshoot to one rest every 3.6 words
    against a target of 10.4. The budget has to be a deficit, not a quota.
    """
    import styleprint as sp
    y, sr = _load(audio_path)
    _, _, silences = sp.load_audio(audio_path, model_size=model_size)
    ends = {}
    for w in words:
        ends[round(w["end"], 2)] = w["text"]
    n = 0
    for a, b in silences:
        if b - a < 0.080:
            continue
        # a rest is "mid-phrase" when the word before it does not end a
        # sentence or clause — the same slot definition styleprint uses
        prev = None
        for w in words:
            if w["end"] <= a + 0.05:
                prev = w
            else:
                break
        if prev and not prev["text"].rstrip()[-1:] in ".!?,;:":
            n += 1
    return n


def plan_insertions(words, plans) -> list[Insertion]:
    """Match each planned rest to a boundary in the delivered audio.

    Matching is on the word pair either side of the rest rather than on an
    index, because the ASR sequence and the script never line up exactly —
    numerals get spelled out, and the odd word is misheard.
    """
    seq = [_norm(w["text"]) for w in words]
    out: list[Insertion] = []
    unmatched: list[str] = []
    cursor = 0
    for plan in plans:
        toks = [t for t in plan["tokens"]]
        for rest in plan["rests"]:
            i = rest["index"]
            left = _norm(toks[i]) if i < len(toks) else ""
            right = _norm(toks[i + 1]) if i + 1 < len(toks) else ""
            if not left:
                continue
            found = _find_boundary(seq, cursor, left, right)
            if found is None:
                unmatched.append(f"{' '.join(toks[max(0, i - 2): i + 1])} | "
                                 f"{' '.join(toks[i + 1: i + 3])}")
                continue
            cursor = found + 1
            out.append(Insertion(
                at_s=(words[found]["end"] + words[found + 1]["start"]) / 2,
                seconds=rest["seconds"], after_word=words[found]["text"],
                before_word=words[found + 1]["text"], site=rest.get("site", ""),
                score=rest.get("score", 0.0)))
    plan_insertions.unmatched = unmatched
    return out


def apply_insertions(in_path, out_path, insertions, model_size="base.en",
                     verify=True, increments=False) -> dict:
    """Write the insertions into the audio.

    ``increments`` says what ``Insertion.seconds`` means. The ADD route plans a
    rest's TOTAL length from the script, knowing nothing about the audio, so
    whatever gap the take already has there must be subtracted before writing.
    The STRETCH route measures the take first and already carries the shortfall,
    so subtracting again would deduct the existing gap twice — which it did, and
    a planned 56.9s of lengthening came out as 1.7s.
    """
    import numpy as np
    import soundfile as sf

    y, sr = _load(in_path)
    tone_src = _room_tone_template(y, sr)
    env = _envelope_db(y, sr)
    fade = max(int(FADE_S * sr), 1)

    pieces = []
    last = 0
    out_cursor = 0          # running length of `pieces`, so out_start stays O(1)
    applied = []
    skipped = []
    for ins in sorted(insertions, key=lambda x: x.at_s):
        cut = _quietest_point(y, sr, ins.at_s)
        idx = int(cut * sr)
        if idx <= last:
            continue

        # The planner works from the script and assumes the take rests nowhere.
        # Real renders do rest a little on their own, and stacking a full
        # planned gap on top of an existing one overshoots badly — on the test
        # render this drove the rate to one rest every 3.6 words against a
        # target of 10.4. So the gap already present is measured and only the
        # shortfall is added. Where the take already rests long enough, nothing
        # is inserted at all.
        if increments:
            have = 0.0                      # the plan is already the shortfall
            need = round(ins.seconds, 3)
        else:
            have = _existing_gap(y, sr, cut, env=env)
            need = round(max(0.0, ins.seconds - have), 3)
        if need < 0.030:
            skipped.append({"at_s": round(cut, 3), "already_rests_s": round(have, 3),
                            "planned_s": ins.seconds, "after": ins.after_word})
            continue

        head = y[last:idx].copy()
        if len(head) > fade:
            head[-fade:] *= np.linspace(1.0, 0.0, fade)
        gap = _room_tone(tone_src, sr, need)
        pieces.append(head)
        out_cursor += len(head)
        pieces.append(gap)
        applied.append({"at_s": round(cut, 3), "seconds": need,
                        "planned_s": ins.seconds,
                        "already_rested_s": round(have, 3),
                        "after": ins.after_word, "before": ins.before_word,
                        "site": ins.site,
                        # where the inserted tone sits in the OUTPUT, which is
                        # what the sample-level check needs to skip over
                        "out_start": int(out_cursor),
                        "out_len": int(len(gap)),
                        "in_at": idx})
        out_cursor += len(gap)
        last = idx
    tail = y[last:].copy()
    if len(tail) > fade:
        tail[:fade] *= np.linspace(0.0, 1.0, fade)
    pieces.append(tail)

    out = np.concatenate(pieces) if pieces else y
    sf.write(str(out_path), out, sr)

    result = {
        "input": str(in_path), "output": str(out_path),
        "sample_rate": sr,
        "duration_before_s": round(len(y) / sr, 3),
        "duration_after_s": round(len(out) / sr, 3),
        "added_s": round((len(out) - len(y)) / sr, 3),
        "insertions": applied,
        "n_inserted": len(applied),
        "n_skipped_already_resting": len(skipped),
        "skipped": skipped,
        "credits_spent": 0,
    }

    # The rule is: confirm after every destructive edit that no word was lost.
    # Re-transcribing is the wrong instrument for THIS edit. It was tried first
    # and reported a failure on audio that was provably intact: ASR re-segments
    # unstable material differently between two passes, so "army" came back as
    # "arm"+"we" and the word count rose by two. That is the transcriber moving,
    # not the audio.
    #
    # An insertion can be checked far more strictly than that, and without any
    # model in the loop: every original sample must still be present, in order.
    # Delete the inserted spans back out of the output and the input must
    # reappear exactly — apart from the few milliseconds at each splice where
    # the edge fade deliberately touched it. A word cannot go missing from
    # audio that is sample-for-sample the original.
    if verify:
        result.update(_verify_insertion_only(y, out, applied, fade))
    return result


def _verify_insertion_only(src, out, applied, fade) -> dict:
    """Assert the output is the input with silence inserted, and nothing else."""
    import numpy as np

    expected = len(src) + sum(a["out_len"] for a in applied)
    if len(out) != expected:
        return {"verified": False,
                "reason": f"length {len(out)} != input + inserted ({expected})"}

    keep = np.ones(len(out), dtype=bool)
    for a in applied:
        keep[a["out_start"]: a["out_start"] + a["out_len"]] = False
    recovered = out[keep]
    if len(recovered) != len(src):
        return {"verified": False,
                "reason": f"recovered {len(recovered)} samples, input has {len(src)}"}

    diff = np.abs(recovered.astype("float64") - src.astype("float64"))
    # Everything must match exactly except within the edge fades, which are an
    # intended modification of the original samples.
    tolerated = np.zeros(len(src), dtype=bool)
    for a in applied:
        cut = a["in_at"]
        tolerated[max(0, cut - fade): min(len(src), cut + fade)] = True
    offenders = int(np.count_nonzero((diff > 1e-6) & ~tolerated))
    return {
        "verified": offenders == 0,
        "samples_compared": int(len(src)),
        "samples_altered_outside_fades": offenders,
        "fade_samples_per_splice": int(fade),
        "reason": ("every original sample present and unaltered outside the "
                   "3 ms splice fades" if offenders == 0
                   else f"{offenders} samples changed outside the fade windows"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("audio", help="the rendered voiceover")
    ap.add_argument("--plan",
                    help="rest plan JSON from v2_style.py --emit-plan "
                         "(the ADD route: new rests where a script wants them)")
    ap.add_argument("--stretch", action="store_true",
                    help="the STRETCH route: leave pause placement alone and "
                         "open the pauses the take already has out to the "
                         "reference lengths. Needs no plan and no script.")
    ap.add_argument("--target", default="serious_history",
                    help="which reference to stretch toward")
    ap.add_argument("--slots", default="sentence,clause",
                    help="which pause classes to open up. Mid-phrase is "
                         "excluded by default because the measured take "
                         "already matched the reference there.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--asr-model", default="base.en")
    ap.add_argument("--no-deficit-budget", action="store_true",
                    help="insert every planned rest, ignoring the ones the take "
                         "already has (overshoots — for diagnosis only)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the post-edit transcript check (not advised)")
    ap.add_argument("--report", help="write the edit report here")
    a = ap.parse_args(argv)

    if a.stretch:
        ins, stats = plan_stretch(a.audio, target=a.target, model_size=a.asr_model,
                                  slots=tuple(a.slots.split(",")))
        print(f"{stats['n_words']} words, {stats['n_pauses']} pauses found")
        for k, f in stats["scale_factors"].items():
            print(f"  {k}: median {stats['median_before'][k]}s, scaling x{f}")
        print(f"{stats['n_to_stretch']} pauses to lengthen")
        print(f"would add {stats['added_s']}s "
              f"({stats['added_s'] / stats['duration_s']:+.1%} runtime)")
        if not ins:
            print("every pause already reaches the reference — nothing to do")
            return 0
        res = apply_insertions(a.audio, a.out, ins, a.asr_model,
                               verify=not a.no_verify, increments=True)
        print(f"stretched {res['n_inserted']} pauses, {res['added_s']:.2f}s added, "
              f"{res['credits_spent']} credits spent")
        print(f"{res['duration_before_s']:.2f}s -> {res['duration_after_s']:.2f}s")
        if "verified" in res:
            print(f"verify: {res['reason']}")
            if not res["verified"]:
                print("AUDIO ALTERED BEYOND THE GAPS — do not ship", file=sys.stderr)
                return 2
        if a.report:
            Path(a.report).write_text(json.dumps(res, indent=2), encoding="utf-8")
        return 0

    if not a.plan:
        ap.error("pass --plan for the add route, or --stretch for the stretch route")
    plan_doc = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    plans = plan_doc["sentences"]
    words = _align(a.audio, a.asr_model)
    ins = plan_insertions(words, plans)
    wanted = sum(len(p["rests"]) for p in plans)
    missed = getattr(plan_insertions, "unmatched", [])
    print(f"plan has {wanted} rests; matched {len(ins)} in the audio")
    for m in missed:
        print(f"  unmatched (left as-is): {m}")
    if not ins:
        print("nothing to insert", file=sys.stderr)
        return 1

    if not a.no_deficit_budget:
        from v2_profile import REFERENCE
        rate = REFERENCE[plan_doc.get("target", "agent_flappy")]["words_per_midphrase_pause"]
        have = count_existing_rests(a.audio, words, a.asr_model)
        want = int(round(len(words) / rate))
        budget = max(0, want - have)
        print(f"take already rests mid-phrase {have} times; target is ~{want} "
              f"for {len(words)} words, so the deficit is {budget}")
        if len(ins) > budget:
            ins = sorted(ins, key=lambda x: -x.score)[:budget]
            ins.sort(key=lambda x: x.at_s)
            print(f"  keeping the {len(ins)} highest-scoring sites")

    if not ins:
        print("the take already rests enough — nothing to insert")
        return 0

    res = apply_insertions(a.audio, a.out, ins, a.asr_model, verify=not a.no_verify)
    if res.get("n_skipped_already_resting"):
        print(f"skipped {res['n_skipped_already_resting']} — the take already "
              f"rests there")
    print(f"inserted {res['n_inserted']} rests, "
          f"{res['added_s']:.2f}s added, {res['credits_spent']} credits spent")
    print(f"{res['duration_before_s']:.2f}s -> {res['duration_after_s']:.2f}s")
    if "verified" in res:
        print(f"verify: {res['reason']}")
        if not res["verified"]:
            print("AUDIO ALTERED BEYOND THE INSERTED GAPS — do not ship this file",
                  file=sys.stderr)
            if a.report:
                Path(a.report).write_text(json.dumps(res, indent=2), encoding="utf-8")
            return 2
    if a.report:
        Path(a.report).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
