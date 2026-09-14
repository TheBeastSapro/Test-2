import sys, difflib, re
sys.path.insert(0, ".claude/skills/explaintory-voiceover/scripts")
import verify
W = "vo-run/out/.vo_Weapons_With_a_Strange_Mechanism_From_Every_Era_Explained"
F = "vo-run/out/Weapons With a Strange Mechanism From Every Era Explained (final).mp3"
heard = [w for w in (verify.norm(t) for t, _, _, _ in verify.transcribe_words(F)) if w]
script = open(f"{W}/script_lines.txt").read()
sw = [w for w in (verify.norm(w) for w in re.findall(r"[A-Za-z0-9'’-]+", script)) if w]
print(f"script words: {len(sw)}")
print(f"heard  words: {len(heard)}")
sm = difflib.SequenceMatcher(None, sw, heard, autojunk=False)
print(f"similarity  : {sm.ratio():.4f}\n")
print("DIFFERENCES (script -> heard):")
n = 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        continue
    n += 1
    if n <= 40:
        print(f"  [{tag}] after '...{' '.join(sw[max(0,i1-5):i1])}'")
        print(f"      script: {' '.join(sw[i1:i2]) or '(nothing)'}")
        print(f"      heard : {' '.join(heard[j1:j2]) or '(NOTHING - DROPPED)'}")
print(f"\ntotal difference regions: {n}")
