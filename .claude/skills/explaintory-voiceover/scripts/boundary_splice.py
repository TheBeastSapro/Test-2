#!/usr/bin/env python3
"""Splice a section's FIRST sentence, where regen_span refuses.

regen_span requires silence at both cut edges because a mid-audio cut without it
clicks. A section's first sentence has no silence in front of it and never will —
but its start edge is not a mid-audio cut at all, it is the SECTION BOUNDARY, and
generate.stitch() already ramps 3 ms of fade onto the start of every section
(SPLICE_FADE). So the one edge that cannot be cut into silence is the one edge
that cannot click.

Everything else is regen_span's: same render path, same conditioning, same
level report with no gain applied, same verify-then-keep with auto-revert.
"""
import json, os, subprocess, sys, difflib
S = "/home/user/Test-2/.claude/skills/explaintory-voiceover/scripts"
sys.path.insert(0, S)
import generate as gen, readcheck as rc
from regen_span import find_silence, level_db

W = sys.argv[1]; SEC1 = int(sys.argv[2]); SENT = sys.argv[3]
APPROVAL = sys.argv[4]; PROFILE = sys.argv[5]

secs = json.load(open(W + "/sections.json"))["sections"]
sec = secs[SEC1 - 1]
text = sec["send_text"]
if not text.startswith(SENT):
    raise SystemExit(f"Sentence is not at the START of section {SEC1}; use regen_span.")
tail = text[len(SENT):]
prev = secs[SEC1 - 2]["send_text"][-300:] if SEC1 >= 2 else ""
part = os.path.join(W, "parts", f"sec_{sec['index']:03d}.mp3")
backup = part + ".pre-boundary"
if not os.path.isfile(backup):
    subprocess.run(["cp", part, backup], check=True)

print(f"section {SEC1}: {sec['chars']} chars")
print(f"sentence          : {len(SENT)} chars   ({sec['chars']-len(SENT)} saved vs re-rolling)")
print(f"conditioning      : previous_text {len(prev.strip())} chars (from section {SEC1-1}), "
      f"next_text {len(tail.strip())} chars")

import librosa
dur = librosa.get_duration(path=part)
model = rc.load_asr()
segs, _ = model.transcribe(part, language="en", beam_size=5,
                           condition_on_previous_text=False, word_timestamps=True)
heard = [(rc.normalize(w.word).strip(), float(w.start), float(w.end))
         for s_ in segs for w in (s_.words or [])]
want = rc.normalize(SENT).split()
hw = [h[0] for h in heard]
hit = None
for i in range(len(hw) - len(want) + 1):
    if sum(1 for x, y in zip(hw[i:i+len(want)], want) if x == y) >= max(3, int(0.7*len(want))):
        hit = (i, i + len(want) - 1); break
if hit is None:
    raise SystemExit("REFUSED: could not locate the sentence in the take's transcript.")
p1 = heard[hit[1]][2]
sil_b = find_silence(part, max(0, p1 - 0.10), min(dur, p1 + 0.25))
if not sil_b:
    raise SystemExit("REFUSED: no silence at the END edge either. Re-roll the section.")
cut_b = (sil_b[0] + sil_b[1]) / 2
print(f"take duration     : {dur:.2f}s   sentence ends {p1:.2f}s")
print(f"cut points        : 0.000s (section boundary — stitch fades 3 ms here) "
      f"and {cut_b:.3f}s (inside {(sil_b[1]-sil_b[0])*1000:.0f} ms of silence)")

prof = gen.load_profile(PROFILE); gen.check_profile(prof)
print(f"approved by Sapro: “{APPROVAL[:90]}”")
span = [{"index": 0, "text": SENT, "send_text": SENT, "is_heading": False,
         "is_cta": False, "chars": len(SENT), "_prev": prev.strip(), "_next": tail.strip()}]
tmp = os.path.join(W, "parts", "_bspan"); os.makedirs(tmp, exist_ok=True)
newp = os.path.join(tmp, "span.mp3")
if os.path.isfile(newp) and os.environ.get("REUSE_SPAN"):
    print(f"reusing already-rendered span at {newp} — nothing sent")
else:
    audio, _ = gen.tts(gen.client(prof), prof, span, 0, [])
    open(newp, "wb").write(audio)

old_lvl = level_db(part, 0.0, cut_b); new_lvl = level_db(newp)
print(f"level             : replaced {old_lvl:.2f} dB, new {new_lvl:.2f} dB, "
      f"difference {new_lvl-old_lvl:+.2f} dB")
print("  (no gain is applied — flagged rather than corrected if beyond about 1 dB)")

subprocess.run(["ffmpeg","-v","error","-i",part,"-ss",f"{cut_b:.3f}",
                "-ar","44100","-ac","1",os.path.join(tmp,"tail.wav"),"-y"],check=True)
subprocess.run(["ffmpeg","-v","error","-i",newp,"-ar","44100","-ac","1",
                os.path.join(tmp,"mid.wav"),"-y"],check=True)
lst = os.path.join(tmp,"concat.txt")
with open(lst,"w") as f:
    for t in ("mid","tail"):
        f.write(f"file '{os.path.abspath(os.path.join(tmp,t+'.wav'))}'\n")
out = os.path.join(tmp,"spliced.wav")
subprocess.run(["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,"-c","copy",out,"-y"],check=True)
subprocess.run(["ffmpeg","-v","error","-i",out,"-codec:a","libmp3lame","-b:a","128k",
                "-ar","44100","-ac","1",part,"-y"],check=True)

print("\nverifying the splice (destructive edit — must be proved harmless)")
t, _ = rc.transcribe(model, part)
w2 = rc.normalize(text).split(); g2 = rc.normalize(t).split()
sm = difflib.SequenceMatcher(a=w2, b=g2, autojunk=False)
dropped = [w2[i1:i2] for tag,i1,i2,_,_ in sm.get_opcodes() if tag=="delete"]
print(f"  script {len(w2)} words, heard {len(g2)} words, ratio {sm.ratio():.4f}")
if dropped:
    subprocess.run(["cp",backup,part],check=True)
    raise SystemExit("\nREVERTED. The splice removed: "
                     + "; ".join(" ".join(d) for d in dropped)
                     + f"\n{part} restored byte-for-byte from {backup}.")
print("  dropped runs: NONE — every script word still present")
print(f"\nspliced into {part}   (backup at {backup})")
