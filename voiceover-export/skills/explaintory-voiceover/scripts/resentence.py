#!/usr/bin/env python3
"""Re-render ONE sentence inside a section, not the whole section.

Sapro's instruction, and it is the right economics. A section is ~400 characters;
the sentence that actually stumbled is often 60. Re-rolling the section bills
seven times what the defect is worth AND rolls the dice on the six sentences that
were already fine -- which is not theoretical: of eight sections re-rolled at
full width, four came back with MORE hesitations than the takes they replaced.

    python3 resentence.py --parts-dir P --sections-json S --profile prof.json \\
        --section 2 --sentence "The method was brutally simple." --profile ...

HOW THE SPLICE IS MADE SAFE
    The new sentence is butt-joined into the middle of an existing take, which is
    the same join that produced the ticks at 2:31 and 3:28. So both edges get the
    3 ms fade used at section boundaries, and the cut points are placed inside
    SILENCE either side of the sentence rather than on speech -- a cut in a quiet
    gap cannot step, whatever the samples do.

CONDITIONING
    The replacement is generated with the real neighbouring text as previous_text
    and next_text, so the model continues the take's delivery instead of starting
    a fresh read at a different energy. Without that the new sentence lands at a
    noticeably different level and pace, which is worse than the stumble it fixes.
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as gen  # noqa: E402

SR = 48000
FADE = 0.003


def log(m):
    print(f"[resentence] {m}", flush=True)


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def decode(path, rate=SR):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1",
                          "-ar", str(rate), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def word_times(path):
    import readcheck as rc
    m = rc.load_asr()
    wav = path + ".16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                    wav, "-y"], capture_output=True)
    segs, _ = m.transcribe(wav, language="en", beam_size=5, word_timestamps=True,
                           condition_on_previous_text=False)
    os.unlink(wav)
    return [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]


def locate(sentence, words):
    """-> (start, end) seconds of the sentence inside the take, or None."""
    want = [norm(w) for w in sentence.split() if norm(w)]
    heard = [norm(w) for w, _, _ in words]
    best, bi = 0.0, None
    for i in range(len(heard) - len(want) + 1):
        r = difflib.SequenceMatcher(a=want, b=heard[i:i + len(want)]).ratio()
        if r > best:
            best, bi = r, i
    if bi is None or best < 0.55:
        return None
    return words[bi][1], words[bi + len(want) - 1][2], best


def quiet_cut(x, t, search=0.25, rate=SR):
    """Nudge a cut point into the nearest quiet sample, so the splice is silent."""
    import numpy as np
    c = int(t * rate)
    lo, hi = max(0, c - int(search * rate)), min(len(x), c + int(search * rate))
    if hi <= lo:
        return c
    w = int(0.005 * rate)
    best, bi = None, c
    for i in range(lo, hi - w, w):
        e = float(np.sqrt(np.mean(x[i:i + w] ** 2)))
        if best is None or e < best:
            best, bi = e, i
    return bi


def edge_fade(x, rate=SR, dur=FADE):
    import numpy as np
    n = int(dur * rate)
    if len(x) < 2 * n or n < 1:
        return x
    y = x.copy()
    r = np.linspace(0, 1, n)
    y[:n] *= r
    y[-n:] *= r[::-1]
    return y


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--section", type=int, required=True, help="1-based section number")
    ap.add_argument("--sentence", required=True,
                    help="the sentence to replace; matched fuzzily against the take")
    ap.add_argument("--stability", type=float)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import numpy as np
    man = json.load(open(a.sections_json, encoding="utf-8"))
    secs = man["sections"]
    idx = a.section - 1
    sec = secs[idx]
    path = os.path.join(a.parts_dir, f"sec_{idx:03d}.mp3")

    sents = split_sentences(sec["send_text"])
    hit = max(sents, key=lambda s: difflib.SequenceMatcher(
        a=norm(a.sentence), b=norm(s)).ratio())
    log(f"section {a.section}: replacing “{hit[:60]}…”" if len(hit) > 60
        else f"section {a.section}: replacing “{hit}”")
    log(f"{len(hit)} characters instead of {sec['chars']} for the whole section "
        f"— {sec['chars'] - len(hit)} saved")

    words = word_times(path)
    loc = locate(hit, words)
    if not loc:
        raise SystemExit("Could not find that sentence in the take. Nothing changed.")
    s0, s1, conf = loc
    log(f"found at {s0:.2f}s–{s1:.2f}s in the take (match {conf:.2f})")
    if a.dry_run:
        return 0

    prof = gen.load_profile(a.profile)
    if a.stability is not None:
        prof["settings"]["stability"] = a.stability
    gen.check_profile(prof)

    # the sentence alone, conditioned on what actually surrounds it
    i = sents.index(hit)
    prev_t = " ".join(sents[:i])[-gen.CONTEXT_CHARS:] if i else (
        secs[idx - 1]["send_text"][-gen.CONTEXT_CHARS:] if idx else "")
    next_t = " ".join(sents[i + 1:])[:gen.CONTEXT_CHARS] if i + 1 < len(sents) else (
        secs[idx + 1]["send_text"][:gen.CONTEXT_CHARS] if idx + 1 < len(secs) else "")
    one = [{"send_text": prev_t, "is_heading": False, "is_cta": False},
           {"send_text": hit, "is_heading": False, "is_cta": False},
           {"send_text": next_t, "is_heading": False, "is_cta": False}]
    audio, _ = gen.tts(gen.client(prof), prof, one, 1, [])
    tmp = path + ".new.mp3"
    open(tmp, "wb").write(audio)

    old = decode(path)
    new = edge_fade(decode(tmp))
    c0, c1 = quiet_cut(old, s0), quiet_cut(old, s1)
    out = np.concatenate([edge_fade(old[:c0]), new, edge_fade(old[c1:])])

    bak = path + ".bak"
    if not os.path.exists(bak):
        os.rename(path, bak)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR),
                          "-ac", "1", "-i", "pipe:0", "-c:a", "libmp3lame",
                          "-b:a", "192k", path, "-y"], stdin=subprocess.PIPE)
    p.communicate(out.astype(np.float32).tobytes())
    os.unlink(tmp)
    log(f"spliced — take was {len(old)/SR:.2f}s, now {len(out)/SR:.2f}s "
        f"(original kept at {os.path.basename(bak)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
