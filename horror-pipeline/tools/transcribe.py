#!/usr/bin/env python3
"""vo.wav -> work/words.json  (Stage 2, BUILD-PACKET section 4.2)

Word-level VO timings from faster-whisper. Everything downstream hangs off
this file, so the three settings that matter are not optional:

  word_timestamps=True            the whole reason we are here
  condition_on_previous_text=False stops the repeated-line hallucination
  vad_filter=True                 keeps the model out of the room tone

Transcribe the RAW voiceover, before any music. A mixed track produces both
failure modes in BUILD-PACKET 4.3: invented repeats, and silently dropped
words. If a window looks wrong, re-check it with --model small.en and
--start/--end rather than believing the first pass.

Usage:
  transcribe.py /abs/vo.wav /abs/work/words.json
  transcribe.py /abs/vo.wav /abs/work/words-small.json --model small.en
  transcribe.py /abs/vo.wav /abs/work/win.json --model small.en --start 92 --end 118

Output: flat list of {"w","s","e","p"} in seconds, absolute to the source
file even when a window was transcribed (--start is added back).

Exit codes: 0 ok, 1 usage or runtime error, 3 transcript produced no words.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter


def abs_arg(p, what):
    if not os.path.isabs(p):
        sys.exit(f"ERROR: {what} must be an absolute path (got {p!r}). "
                 "The shell working directory is not stable between calls.")
    return p


def clip(src, start, end):
    """Cut a window with ffmpeg. -nostdin -v error or the session drowns."""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start}"]
    cmd += ["-i", src]
    if end:
        cmd += ["-to", f"{end - (start or 0.0)}"]
    cmd += ["-ac", "1", "-ar", "16000", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffmpeg clip failed: {r.stderr.strip()[:400]}")
    return tmp


def repeated_phrases(words, n=5, min_count=3):
    """BUILD-PACKET 4.3 failure mode one: hallucinated repeated lines."""
    toks = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in words]
    toks = [t for t in toks if t]
    grams = Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))
    return [(" ".join(g), c) for g, c in grams.most_common(5) if c >= min_count]


def main():
    argv = sys.argv[1:]
    pos, model_name, start, end, beam = [], "base.en", None, None, 5
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key, _, inline = a.partition("=")
            val = inline if inline else (argv[i + 1] if i + 1 < len(argv) else None)
            if not inline:
                i += 1
            if val is None:
                sys.exit(f"ERROR: {key} needs a value")
            if key == "--model":
                model_name = val
            elif key == "--start":
                start = float(val)
            elif key == "--end":
                end = float(val)
            elif key == "--beam":
                beam = int(val)
            else:
                sys.exit(f"ERROR: unknown flag {key}")
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        sys.exit(__doc__)
    audio = abs_arg(pos[0], "audio")
    out = abs_arg(pos[1], "words.json")
    if not os.path.isfile(audio):
        sys.exit(f"ERROR: no such audio file: {audio}")
    if end is not None and start is not None and end <= start:
        sys.exit(f"ERROR: --end {end} must be greater than --start {start}")

    from faster_whisper import WhisperModel

    src, tmp = audio, None
    if start is not None or end is not None:
        tmp = src = clip(audio, start, end)
    offset = start or 0.0

    t0 = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        src,
        word_timestamps=True,           # this is the whole reason we are here
        condition_on_previous_text=False,   # stops the repeated-line hallucination
        vad_filter=True,
        beam_size=beam,
    )
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"w": w.word.strip(),
                          "s": round(w.start + offset, 3),
                          "e": round(w.end + offset, 3),
                          "p": round(w.probability, 3)})
    took = time.time() - t0
    if tmp:
        os.unlink(tmp)

    if not words:
        sys.exit(f"ERROR: transcript is empty. Check that {audio} actually "
                 "contains speech (run tools/rms.py on it).")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(words, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    span = words[-1]["e"] - words[0]["s"]
    probs = [w["p"] for w in words]
    weak = [w for w in words if w["p"] < 0.5]
    reps = repeated_phrases(words)

    print("SUMMARY transcribe")
    print(f"  audio  : {audio}")
    print(f"  model  : {model_name} (cpu/int8, beam {beam}), {took:.1f}s wall")
    print(f"  window : " + ("full file" if tmp is None else f"{start}-{end}s of source"))
    print(f"  words  : {len(words)}")
    print(f"  span   : {words[0]['s']:.2f}s -> {words[-1]['e']:.2f}s ({span:.1f}s), "
          f"audio {info.duration:.1f}s")
    print(f"  rate   : {len(words) / span * 60:.0f} wpm spoken")
    print(f"  conf   : mean p {sum(probs) / len(probs):.3f}, {len(weak)} word(s) below 0.5")
    if reps:
        print("  REPEATS: possible hallucination, BUILD-PACKET 4.3 failure mode one")
        for phrase, c in reps:
            print(f"           {c}x {phrase!r}")
        print("           re-check that window with --model small.en before trusting it")
    else:
        print("  repeats: none (no 5-gram occurs 3+ times)")
    print(f"  wrote  : {out}")

    if weak and len(weak) / len(words) > 0.15:
        print(f"  WARNING: {len(weak) / len(words):.0%} of words below p 0.5, "
              "this transcript is not trustworthy for anchors", file=sys.stderr)


if __name__ == "__main__":
    main()
