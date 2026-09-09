"""Windowed re-transcription of disputed words.

The section transcript is one pass over 20+ seconds; its language model can
smooth a real drop into fluent text, or invent one. A tight window around the
disputed word removes that context, so the acoustics decide.
"""
import json, os, subprocess, sys
sys.path.insert(0, ".claude/skills/explaintory-voiceover/scripts")
import verify

W = "vo-run/out/.vo_Weapons_With_a_Strange_Mechanism_From_Every_Era_Explained"
PARTS = f"{W}/parts"

# (section idx, anchor word to locate, what the script says should be there)
CASES = [
    (14, "trigger",   "Pull the trigger"),
    (15, "musketman", "a good musketman managed"),
    (21, "detonator", "no detonator holed her"),
    (34, "downrange", "sixty feet downrange"),
    (37, "stacked",   "The bullets sit stacked"),
]

for idx, anchor, expect in CASES:
    src = f"{PARTS}/sec_{idx:03d}.mp3"
    words = verify.transcribe_words(src)
    hit = None
    for i, w in enumerate(words):
        if verify.norm(w["word"]).startswith(verify.norm(anchor)[:5]):
            hit = i; break
    if hit is None:
        print(f"idx {idx}: anchor '{anchor}' not found in full-section pass")
        continue
    st = max(0.0, words[hit]["start"] - 2.0)
    en = words[hit]["end"] + 1.5
    clip = f"/tmp/win_{idx}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-ss", str(st), "-to", str(en),
                    "-i", src, clip], check=True)
    win = verify.transcribe_words(clip)
    heard = " ".join(w["word"].strip() for w in win)
    print(f"idx {idx}  window {st:.2f}-{en:.2f}s")
    print(f"   script : …{expect}…")
    print(f"   heard  : {heard}")
    print()
