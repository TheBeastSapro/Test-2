#!/usr/bin/env python3
"""Re-render ONE sentence and splice it into its section.

Rule 7b, in Sapro's words: "you should never re roll the entire section for one
word fix... re roll only sentence or few words to match it because you just need
that word so why wasting too many credits just for one word?"

He is right on the arithmetic. `--regen` works on sections because sections are
what the chunker produces and what the cache is keyed by — but the section is the
unit of GENERATION, sized to the model's ~450-character sweet spot, and has
nothing to do with how big a defect is. Fixing "Parliament" by re-rolling section
19 costs 403 characters; the sentence holding it is 133. And re-rolling a section
also re-rolls every correct word in it, any of which can come back worse — which
already happened, when a header re-roll made two names worse than plain spelling.

Two things make the splice safe, both proven on this project:

  * CONDITIONING. The sentence is sent with the rest of the section as
    previous_text / next_text, so the model continues the delivery instead of
    starting cold. Without it a spliced sentence arrives at a different pace and
    pitch and sounds worse than the defect.

  * SILENCE EDGES. The cut is made inside real silence on both sides, so no click
    is possible. The Hashish repair worked exactly this way: a replacement clip
    placed verbatim, no gain, no tempo, no EQ, because its level already sat
    within 0.6 dB of its neighbours. This script measures that difference and
    prints it; it never applies gain, because matching by ear is what the
    conditioning is for.

It REFUSES rather than guessing: no silence at an edge means no safe cut, and the
caller is told to re-roll the section instead.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as gen  # noqa: E402

SR = 16000
FLOOR_MARGIN = 6.0        # dB above the take's own noise floor counts as silence
MIN_SIL = 0.040           # a usable cut needs at least this much silence


def _envelope(path):
    import numpy as np
    import librosa
    y, _ = librosa.load(path, sr=SR, mono=True)
    hop = 160
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-10)
    return y, db, SR / hop


def find_silence(path, lo, hi):
    """-> (start, end) of the longest silence in [lo, hi], or None.

    ASR word timestamps cannot be used for this: faster-whisper returns
    contiguous spans, so a real 150 ms hole reads as 0.000 s. Measured off the
    energy envelope instead.
    """
    import numpy as np
    y, db, fps = _envelope(path)
    floor = float(np.percentile(db, 10)) + FLOOR_MARGIN
    a, b = max(0, int(lo * fps)), min(len(db), int(hi * fps))
    if b <= a:
        return None
    quiet = db[a:b] < floor
    best, run, start = None, 0, None
    for i, q in enumerate(quiet):
        if q:
            run += 1
            start = i if run == 1 else start
        else:
            if run and (best is None or run > best[1] - best[0]):
                best = (start, i)
            run, start = 0, None
    if run and (best is None or run > best[1] - best[0]):
        best = (start, len(quiet))
    if not best or (best[1] - best[0]) / fps < MIN_SIL:
        return None
    return ((a + best[0]) / fps, (a + best[1]) / fps)


def level_db(path, lo=None, hi=None):
    import numpy as np
    import librosa
    y, _ = librosa.load(path, sr=SR, mono=True)
    if lo is not None:
        y = y[int(lo * SR):int(hi * SR)]
    return float(20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12))


def main():
    ap = argparse.ArgumentParser(description="Re-render one sentence and splice it in.")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--section", type=int, required=True, help="1-based section number")
    ap.add_argument("--sentence", required=True,
                    help="the sentence to re-render, verbatim from the section text")
    ap.add_argument("--profile")
    ap.add_argument("--approval", default="",
                    help="Sapro's own words approving this send. Required.")
    ap.add_argument("--use-existing-span", action="store_true",
                    help="reuse a previously rendered span.mp3 instead of sending "
                         "again — for retrying a splice that failed after the API "
                         "call had already been paid for")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the plan and the splice points, send nothing")
    a = ap.parse_args()

    sections = json.load(open(a.sections_json, encoding="utf-8"))["sections"]
    sec = sections[a.section - 1]
    text = sec["send_text"]
    if a.sentence not in text:
        raise SystemExit(f"Sentence not found verbatim in section {a.section}.\n"
                         f"Section text:\n  {text}")

    head, tail = text.split(a.sentence, 1)
    part = os.path.join(a.parts_dir, f"sec_{sec['index']:03d}.mp3")
    if not os.path.isfile(part):
        raise SystemExit(f"No existing take at {part} to splice into.")
    # Back up before touching anything, so the auto-revert below has something to
    # restore. Made unconditionally: the pre-write backup is what turned an
    # earlier destructive bug into a non-event.
    backup = part + ".pre-splice"
    if not os.path.isfile(backup):
        subprocess.run(["cp", part, backup], check=True)

    print(f"section {a.section}: {sec['chars']} chars")
    print(f"sentence          : {len(a.sentence)} chars   "
          f"({sec['chars'] - len(a.sentence)} saved vs re-rolling the section)")
    print(f"conditioning      : previous_text {len(head.strip())} chars, "
          f"next_text {len(tail.strip())} chars")

    # Where does the sentence sit in the existing take?
    #
    # This was proportional-to-characters, and it ate two words. The estimate put
    # the sentence 0.5 s later than it really was, the "longest silence within
    # +/-0.55 s" then locked onto an EARLIER pause, and the cut took "personal
    # insult" out with it. Silencing something that turns out to be speech is
    # worse than the defect it replaced, and it is invisible to every level and
    # waveform check — only the transcript caught it.
    #
    # So locate by what the take actually says: transcribe it, match the
    # sentence's first and last words in the word stream, and use their measured
    # times. The silence search is then a narrow +/-0.25 s around a real boundary
    # rather than a wide guess around an estimated one.
    import librosa
    import readcheck as rc
    dur = librosa.get_duration(path=part)
    model = rc.load_asr()
    segs, _ = model.transcribe(part, language="en", beam_size=5,
                               condition_on_previous_text=False, word_timestamps=True)
    heard = [(rc.normalize(w.word).strip(), float(w.start), float(w.end))
             for s_ in segs for w in (s_.words or [])]
    want = rc.normalize(a.sentence).split()
    hw = [h[0] for h in heard]
    hit = None
    for i in range(len(hw) - len(want) + 1):
        win = hw[i:i + len(want)]
        same = sum(1 for x, y in zip(win, want) if x == y)
        if same >= max(3, int(0.7 * len(want))):
            hit = (i, i + len(want) - 1)
            break
    if hit is None:
        raise SystemExit(
            "\nREFUSED: could not locate the sentence in the take's own transcript, "
            "so the cut points would be a guess. Re-roll the whole section instead.")
    p0, p1 = heard[hit[0]][1], heard[hit[1]][2]
    sil_a = find_silence(part, max(0, p0 - 0.25), p0 + 0.10)
    sil_b = find_silence(part, max(0, p1 - 0.10), min(dur, p1 + 0.25))
    print(f"take duration     : {dur:.2f}s   sentence approx {p0:.2f}-{p1:.2f}s")
    if not sil_a or not sil_b:
        raise SystemExit(
            "\nREFUSED: no silence found at "
            + ("the start edge" if not sil_a else "the end edge")
            + " of the sentence, so a clean cut is not possible.\n"
            "Re-roll the whole section instead — a splice without silence on both "
            "sides clicks, and a click is worse than the defect.")
    cut_a = (sil_a[0] + sil_a[1]) / 2
    cut_b = (sil_b[0] + sil_b[1]) / 2
    print(f"cut points        : {cut_a:.3f}s and {cut_b:.3f}s "
          f"(inside {(sil_a[1]-sil_a[0])*1000:.0f} ms and "
          f"{(sil_b[1]-sil_b[0])*1000:.0f} ms of silence)")

    if a.dry_run:
        print("\ndry run — nothing sent.")
        return 0
    if not a.approval.strip():
        raise SystemExit(
            f"\nSTOPPED. Sapro has not approved this send.\n"
            f"  WOULD SEND — 1 sentence, {len(a.sentence)} characters:\n"
            f"    {a.sentence}\n\n"
            f"Ask him, then pass his words back with --approval.\n")

    prof = gen.load_profile(a.profile)
    gen.check_profile(prof)
    print(f"approved by Sapro: “{a.approval.strip()[:90]}”")

    # One-section manifest: the sentence, conditioned on its own surroundings.
    span = [{"index": 0, "text": a.sentence, "send_text": a.sentence,
             "is_heading": False, "is_cta": False, "chars": len(a.sentence),
             "_prev": head.strip(), "_next": tail.strip()}]
    tmp = os.path.join(a.parts_dir, "_span")
    os.makedirs(tmp, exist_ok=True)
    newp = os.path.join(tmp, "span.mp3")
    if a.use_existing_span and os.path.isfile(newp):
        # A splice that failed AFTER the API call must never pay twice to retry.
        print(f"reusing the already-rendered span at {newp} — nothing sent")
    else:
        cl = gen.client(prof)
        audio, _ = gen.tts(cl, prof, span, 0, [])
        open(newp, "wb").write(audio)

    old_lvl = level_db(part, cut_a, cut_b)
    new_lvl = level_db(newp)
    print(f"level             : replaced {old_lvl:.2f} dB, new {new_lvl:.2f} dB, "
          f"difference {new_lvl - old_lvl:+.2f} dB")
    print("  (no gain is applied — if this is beyond about 1 dB, say so rather "
          "than correcting it silently)")

    out = os.path.join(tmp, "spliced.wav")
    lst = os.path.join(tmp, "concat.txt")
    for tag, args in (("head", ["-t", f"{cut_a:.3f}"]), ("tail", ["-ss", f"{cut_b:.3f}"])):
        subprocess.run(["ffmpeg", "-v", "error", "-i", part, *args,
                        "-ar", "44100", "-ac", "1", os.path.join(tmp, f"{tag}.wav"), "-y"],
                       check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", newp, "-ar", "44100", "-ac", "1",
                    os.path.join(tmp, "mid.wav"), "-y"], check=True)
    # ffmpeg resolves concat entries relative to the CONCAT FILE, not the cwd, so
    # a relative path here silently becomes <dir>/<dir>/head.wav and the demuxer
    # fails after the API call has already been paid for. Absolute, always.
    with open(lst, "w") as f:
        for t in ("head", "mid", "tail"):
            f.write(f"file '{os.path.abspath(os.path.join(tmp, t + '.wav'))}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", out, "-y"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-ar", "44100", "-ac", "1", part, "-y"], check=True)
    # VERIFY, THEN KEEP — never the other way round.
    #
    # This used to print "NOW: transcribe and diff" and trust the caller to do it.
    # The first real splice ate "personal insult" and the reminder did not stop it
    # being written; only a diff run afterwards caught it. A destructive edit that
    # asks to be checked is an unchecked edit, so the check is inline now and the
    # edit is reverted automatically when it fails.
    import difflib
    print("\nverifying the splice (destructive edit — must be proved harmless)")
    t, _ = rc.transcribe(model, part)
    want = rc.normalize(text).split()
    got = rc.normalize(t).split()
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    dropped = [want[i1:i2] for tag, i1, i2, _, _ in sm.get_opcodes() if tag == "delete"]
    print(f"  script {len(want)} words, heard {len(got)} words, ratio {sm.ratio():.4f}")
    if dropped:
        subprocess.run(["cp", backup, part], check=True)
        raise SystemExit(
            "\nREVERTED. The splice removed: "
            + "; ".join(" ".join(d) for d in dropped)
            + f"\n{part} is restored byte-for-byte from {backup}.\n"
            "Silencing something that turns out to be speech is worse than the "
            "defect it replaced, and it is invisible to every level and waveform "
            "check — only the transcript sees it.")
    print("  dropped runs: NONE — every script word still present")
    print(f"\nspliced into {part}   (backup at {backup})")
    print("NEXT: re-stitch and re-master; the section file is updated in place.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
