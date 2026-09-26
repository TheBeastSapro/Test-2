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
import re
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


MAX_GAP = 2.0             # widest anchor-to-anchor window a cut may be searched in


def heard_tokens(segs, normalize):
    """-> [(token, start, end)], one entry per NORMALISED token.

    The normaliser turns one heard word into several ("I'd" -> "i would"), so
    tokens are flattened here and each carries its source word's times. Comparing
    whole heard words against script tokens is what put every later word one slot
    out of step.
    """
    out = []
    for s_ in segs:
        for w in (s_.words or []):
            for tok in normalize(w.word).split():
                out.append((tok, float(w.start), float(w.end)))
    return out


def locate(heard, section_text, sentence, normalize, dur):
    """-> ((L_lo, L_hi), (R_lo, R_hi)) windows holding the sentence's two edges.

    Aligns the WHOLE section's script against the take's transcript and anchors
    each edge on the nearest words that were heard correctly, on either side of
    it — not on the sentence's own words. The sentence being repaired is, by
    definition, the part that was misread: the old matcher looked for it by its
    own words, and refused the one case it exists for ("this stayed a drawing",
    heard as "this state of drawing", Project Pluto).

    Raises SystemExit when the anchors are too far apart for the silence search to
    be anything but a guess.
    """
    import difflib
    head, _ = section_text.split(sentence, 1)
    want = normalize(section_text).split()
    s0 = len(normalize(head).split()) if head.strip() else 0
    s1 = s0 + len(normalize(sentence).split()) - 1
    got = [h[0] for h in heard]
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    m = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            m[blk.a + k] = blk.b + k

    before = [i for i in m if i < s0]
    inside = [i for i in m if s0 <= i <= s1]
    after = [i for i in m if i > s1]
    if not inside:
        raise SystemExit("\nREFUSED: no word of the sentence was heard at all, so "
                         "there is nothing to confirm the anchors bracket it.")
    L_lo = heard[m[max(before)]][2] if before else 0.0
    L_hi = heard[m[min(inside)]][1]
    R_lo = heard[m[max(inside)]][2]
    R_hi = heard[m[min(after)]][1] if after else dur
    for name, lo, hi in (("start", L_lo, L_hi), ("end", R_lo, R_hi)):
        if hi - lo > MAX_GAP:
            raise SystemExit(
                f"\nREFUSED: the {name} edge could only be narrowed to "
                f"{lo:.2f}-{hi:.2f}s ({hi - lo:.2f}s) — too wide to pick the right "
                f"pause in. Re-roll the whole section instead.")
    return (L_lo, L_hi), (R_lo, R_hi)


def main():
    ap = argparse.ArgumentParser(description="Re-render one sentence and splice it in.")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--section", type=int, required=True, help="1-based section number")
    ap.add_argument("--sentence", required=True,
                    help="the sentence to re-render, verbatim from the section text")
    ap.add_argument("--replace-with",
                    help="send this wording instead of --sentence (a script fix, e.g. "
                         "'stayed a' -> 'was just a'). The splice is then verified "
                         "against the NEW wording, and the change must also be made "
                         "in the script and sections.json")
    ap.add_argument("--spend-log",
                    help="the run's spend.json (default: next to --sections-json)")
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

    part = os.path.join(a.parts_dir, f"sec_{sec['index']:03d}.mp3")
    if not os.path.isfile(part):
        raise SystemExit(f"No existing take at {part} to splice into.")
    # Back up before touching anything, so the auto-revert below has something to
    # restore. Made unconditionally: the pre-write backup is what turned an
    # earlier destructive bug into a non-event.
    backup = part + ".pre-splice"
    if not os.path.isfile(backup):
        subprocess.run(["cp", part, backup], check=True)

    # Where does the sentence sit in the existing take?
    #
    # This was proportional-to-characters, and it ate two words. The estimate put
    # the sentence 0.5 s later than it really was, the "longest silence within
    # +/-0.55 s" then locked onto an EARLIER pause, and the cut took "personal
    # insult" out with it. Silencing something that turns out to be speech is
    # worse than the defect it replaced, and it is invisible to every level and
    # waveform check — only the transcript caught it.
    #
    # So locate by what the take actually says — see locate() — and search for
    # silence only between correctly-heard neighbours.
    import librosa
    import readcheck as rc
    dur = librosa.get_duration(path=part)
    model = rc.load_asr()
    segs, _ = model.transcribe(part, language="en", beam_size=5,
                               condition_on_previous_text=False, word_timestamps=True)
    heard = heard_tokens(segs, rc.normalize)

    # The voice does not always pause at a full stop: in Project Pluto it ran
    # "…out of the room. Nope." straight through at -24 dB, and the only clean
    # silence was after "Nope.". When an edge has no silence, grow the span by one
    # sentence on that side and try again — a few more characters beats a re-roll
    # of the whole section, and beats a cut through speech by far.
    si = text.index(a.sentence)
    ei = si + len(a.sentence)
    ends = [m.end() for m in re.finditer(r'[.!?]["”’)]*(?=\s|$)', text)]
    def grow(b, f):
        s, e = si, ei
        before = [x for x in ends if x <= si]
        after = [x for x in ends if x > ei]
        if b:
            if b > len(before):
                return None
            s = before[-b - 1] if b < len(before) else 0
            while s < si and text[s].isspace():
                s += 1
        if f:
            if f > len(after):
                return None
            e = after[f - 1]
        return s, e
    tried = []
    for b, f in ((0, 0), (0, 1), (1, 0), (1, 1), (0, 2), (2, 0)):
        g = grow(b, f)
        if g is None:
            continue
        s, e = g
        span = text[s:e]
        head, tail = text[:s], text[e:]
        (L_lo, L_hi), (R_lo, R_hi) = locate(heard, text, span, rc.normalize, dur)
        # A span that opens (or closes) its section has no speech on that side to
        # cut around: the file edge IS the boundary, and the stitch puts the
        # silence between sections back.
        sil_a = (0.0, 0.0) if not head.strip() else \
            find_silence(part, max(0, L_lo - 0.05), L_hi + 0.05)
        sil_b = (dur, dur) if not tail.strip() else \
            find_silence(part, max(0, R_lo - 0.05), min(dur, R_hi + 0.05))
        tried.append((b, f, bool(sil_a), bool(sil_b)))
        if sil_a and sil_b:
            break
    else:
        raise SystemExit(
            "\nREFUSED: no silence at "
            + ", ".join(f"{'start' if not ok_a else 'end'} edge with {b} sentence(s) "
                        f"before / {f} after" for b, f, ok_a, ok_b in tried)
            + ".\nRe-roll the whole section instead — a splice without silence on "
            "both sides clicks, and a click is worse than the defect.")

    deleting = a.replace_with is not None and not a.replace_with.strip()
    repl = "" if deleting else (a.replace_with or a.sentence).strip()
    new_sentence = re.sub(r"\s+", " ", text[s:si] + repl + " " + text[ei:e]).strip()
    new_text = head + new_sentence + tail
    # Context the model hears either side, as generate.py gives a full section:
    # the neighbouring SECTIONS too, not only this section's own words. A
    # sentence that opens a section otherwise renders cold.
    idx = a.section - 1
    prev_sec = sections[idx - 1] if idx else None
    next_sec = sections[idx + 1] if idx + 1 < len(sections) else None
    ctx_prev = head.strip()
    if prev_sec and not prev_sec.get("is_heading") and len(ctx_prev) < gen.CONTEXT_CHARS:
        ctx_prev = (prev_sec["send_text"] + " " + ctx_prev).strip()
    ctx_next = tail.strip()
    if next_sec and len(ctx_next) < gen.CONTEXT_CHARS:
        ctx_next = (ctx_next + " " + next_sec["send_text"]).strip()
    ctx_prev = ctx_prev[-gen.CONTEXT_CHARS:]
    ctx_next = ctx_next[:gen.CONTEXT_CHARS]
    print(f"section {a.section}: {sec['chars']} chars")
    if (s, e) != (si, ei):
        print(f"span grown        : +{si - s} chars before, +{e - ei} after — no silence "
              f"at the sentence's own edge, so the cut moves to the next pause")
    print(f"span              : {len(new_sentence)} chars   "
          f"({sec['chars'] - len(new_sentence)} saved vs re-rolling the section)")
    print(f"  replaces        : “{span}”")
    print(f"  with            : “{new_sentence}”")
    if deleting and not new_sentence:
        print("mode              : DELETE — nothing is rendered, 0 characters sent")
    else:
        print(f"conditioning      : previous_text {len(ctx_prev)} chars, "
              f"next_text {len(ctx_next)} chars")
    p0, p1 = L_hi, R_lo
    print(f"take duration     : {dur:.2f}s   span approx {p0:.2f}-{p1:.2f}s")
    print(f"edge windows      : start {L_lo:.2f}-{L_hi:.2f}s, end {R_lo:.2f}-{R_hi:.2f}s "
          f"(between correctly-heard neighbours)")
    cut_a = (sil_a[0] + sil_a[1]) / 2
    cut_b = (sil_b[0] + sil_b[1]) / 2
    edge = lambda sil: ("the file edge" if sil[0] == sil[1] else
                        f"{(sil[1]-sil[0])*1000:.0f} ms of silence")
    print(f"cut points        : {cut_a:.3f}s ({edge(sil_a)}) and "
          f"{cut_b:.3f}s ({edge(sil_b)})")

    if a.dry_run:
        print("\ndry run — nothing sent.")
        return 0
    tmp = os.path.join(a.parts_dir, "_span")
    os.makedirs(tmp, exist_ok=True)
    cut_only = deleting and not new_sentence
    if cut_only:
        newp = None
    elif not a.approval.strip():
        raise SystemExit(
            f"\nSTOPPED. Sapro has not approved this send.\n"
            f"  WOULD SEND — 1 sentence, {len(new_sentence)} characters:\n"
            f"    {new_sentence}\n\n"
            f"Ask him, then pass his words back with --approval.\n")

    else:
        prof = gen.load_profile(a.profile)
        gen.check_profile(prof)
        print(f"approved by Sapro: “{a.approval.strip()[:90]}”")
        newp = os.path.join(tmp, "span.mp3")

    # tts() conditions a section on its NEIGHBOURS in the list it is given. This
    # used to pass a one-item list with the context in unused "_prev"/"_next"
    # keys, so every repair went out with no previous_text or next_text at all —
    # the conditioning the docstring promises never reached the API. The context
    # now travels as real neighbour entries.
    stub = lambda txt: {"index": -1, "text": txt, "send_text": txt, "is_heading": False,
                        "is_cta": False, "chars": len(txt)}
    span = ([stub(ctx_prev)] if ctx_prev else []) + [
        {"index": 0, "text": new_sentence, "send_text": new_sentence,
         "is_heading": False, "is_cta": False, "chars": len(new_sentence)}] + \
        ([stub(ctx_next)] if ctx_next else [])
    at = 1 if ctx_prev else 0
    if cut_only:
        pass
    elif a.use_existing_span and os.path.isfile(newp):
        # A splice that failed AFTER the API call must never pay twice to retry.
        print(f"reusing the already-rendered span at {newp} — nothing sent")
    else:
        cl = gen.client(prof)
        audio, _ = gen.tts(cl, prof, span, at, [])
        open(newp, "wb").write(audio)
        # Debit the run's ledger like every other render. This tool sent outside
        # it, so the Pluto run's spend.json read 2,053 after 2,137 had gone out —
        # the same blind spot as the old per-invocation budget.
        ledger = a.spend_log or os.path.join(os.path.dirname(os.path.abspath(
            a.sections_json)), "spend.json")
        gen.record_spend(ledger, len(new_sentence), a.section - 1)
        print(f"spend             : {len(new_sentence)} chars recorded in {ledger}")

    if not cut_only:
        old_lvl = level_db(part, cut_a, cut_b)
        new_lvl = level_db(newp)
        print(f"level             : replaced {old_lvl:.2f} dB, new {new_lvl:.2f} dB, "
              f"difference {new_lvl - old_lvl:+.2f} dB")
        print("  (no gain is applied — if this is beyond about 1 dB, say so rather "
              "than correcting it silently)")

    out = os.path.join(tmp, "spliced.wav")
    lst = os.path.join(tmp, "concat.txt")
    pieces = (["head"] if cut_a > 0 else []) + ([] if cut_only else ["mid"]) + \
        (["tail"] if cut_b < dur else [])
    if not pieces:
        raise SystemExit("\nREFUSED: that would delete the whole section — drop it "
                         "from the script instead.")
    for tag, args in (("head", ["-t", f"{cut_a:.3f}"]), ("tail", ["-ss", f"{cut_b:.3f}"])):
        if tag not in pieces:
            continue      # the sentence runs to the file edge on this side
        subprocess.run(["ffmpeg", "-v", "error", "-i", part, *args,
                        "-ar", "44100", "-ac", "1", os.path.join(tmp, f"{tag}.wav"), "-y"],
                       check=True)
    if not cut_only:
        subprocess.run(["ffmpeg", "-v", "error", "-i", newp, "-ar", "44100", "-ac", "1",
                        os.path.join(tmp, "mid.wav"), "-y"], check=True)
    # ffmpeg resolves concat entries relative to the CONCAT FILE, not the cwd, so
    # a relative path here silently becomes <dir>/<dir>/head.wav and the demuxer
    # fails after the API call has already been paid for. Absolute, always.
    with open(lst, "w") as f:
        for t in pieces:
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
    want = rc.normalize(new_text).split()
    got = rc.normalize(t).split()
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    dropped = [want[i1:i2] for tag, i1, i2, _, _ in sm.get_opcodes() if tag == "delete"]
    # The mirror case: a cut that lands INSIDE the old sentence keeps some of its
    # words, and they play again before the new take. That is a gained run, not a
    # lost one, so the dropped-words test alone passes it.
    extra = [got[j1:j2] for tag, _, _, j1, j2 in sm.get_opcodes()
             if tag == "insert" and j2 - j1 >= 2]
    if extra and not dropped:
        subprocess.run(["cp", backup, part], check=True)
        raise SystemExit(
            "\nREVERTED. The splice left extra words in: "
            + "; ".join(" ".join(e) for e in extra)
            + f"\n{part} is restored byte-for-byte from {backup}.")
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
