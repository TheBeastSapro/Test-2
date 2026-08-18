#!/usr/bin/env python3
"""THE LAST GATE: prove the master did not change a word, before delivery.

    python3 delivery_gate.py --raw raw_stitched.wav --delivered "Title (final).mp3" \
                             --script <work>/script_lines.txt

Why this exists. Sapro reported he could not hear "pack" in "pack them tight".
He was right, and the master had done it: `fix_glitches()` in humanize.py removes
isolated bursts under 250 ms that sit near a digital splice, and it has no upper
LEVEL guard. A short word fenced by a comma pause on one side and its own stop
closure on the other is, by duration and isolation alone, indistinguishable from
a 35 ms scrap of a fricative. So it cut 165 ms at -8.2 dB out of the middle of a
sentence and "pack them tight" was delivered as "pick them tight". Every other
fragment it removed that run was 10-40 ms at -36 to -16 dB. The word was a 4x
duration outlier and 8 dB louder than anything else it touched, and nothing in
the pipeline noticed, because the master performs a destructive edit and never
transcribes afterwards.

Rule 7 already said "transcribe after every destructive edit and confirm no words
were lost". The master was the one destructive edit exempt from it, because the
read-check runs on the section takes BEFORE mastering and the QC pass measures
levels rather than words. So the file could pass every gate in the pipeline with
a word missing from it.

THREE-WAY, NOT TWO-WAY. Comparing the raw transcript to the delivered transcript
directly produces false alarms: the two files sound different, ASR segments them
differently, and window boundaries invent disagreements ("on itself" came back as
"stealth" at a chunk edge). So both are compared against the SCRIPT, and a
difference is only reported when the RAW agrees with the script and the DELIVERED
does not. That is the signature of damage done by mastering, and nothing else
produces it.

Exits non-zero if any word was lost or altered. Delivery must not proceed on a
non-zero exit.
"""
import argparse, difflib, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcheck as rc

WINDOW = 60.0
OVERLAP = 2.0


def transcribe_all(model, path, window=WINDOW):
    """-> [normalised words] for a whole file, in overlapping windows.

    Whole-file transcription invents dropped words on long audio — documented on
    four separate deliveries — so it is done in windows and joined.
    """
    import librosa
    dur = librosa.get_duration(path=path)
    out = []
    t = 0.0
    while t < dur:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-t",
                        f"{window + OVERLAP}", "-i", path, "-ar", "16000",
                        "-ac", "1", tmp, "-y"], check=True)
        segs, _ = model.transcribe(tmp, language="en", beam_size=5,
                                   condition_on_previous_text=False)
        out.append(" ".join(s.text for s in segs).strip())
        os.unlink(tmp)
        t += window
    return rc.normalize(" ".join(out)).split()


def matched(script, heard):
    """-> set of script indices the transcript actually contains."""
    sm = difflib.SequenceMatcher(a=script, b=heard, autojunk=False)
    ok = set()
    for i, _, k in sm.get_matching_blocks():
        ok.update(range(i, i + k))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="the stitch, before mastering")
    ap.add_argument("--delivered", required=True, help="the mastered file")
    ap.add_argument("--script", required=True, help="<work>/script_lines.txt")
    ap.add_argument("--asr-model", default=rc.DEFAULT_ASR)
    ap.add_argument("--cache", help="transcript cache path; defaults to sitting beside the delivered file")
    a = ap.parse_args()

    script = rc.normalize(
        " ".join(l.strip() for l in open(a.script, encoding="utf-8")
                 if l.strip())).split()
    # Transcribing twelve minutes twice is the expensive part; the analysis on top
    # of it is free. So transcripts are cached against each file's size and mtime,
    # and a bug in the REPORT then costs a re-read rather than a re-transcription.
    # It also keeps peak memory to one loaded model -- running two gates at once
    # put two 4.3 GB models in memory and the kernel killed one, which looked
    # exactly like a gate that had quietly passed.
    cache = {}
    cpath = a.cache or (os.path.splitext(a.delivered)[0] + ".gate-cache.json")
    def key(path):
        st = os.stat(path)
        return "%s:%d:%d" % (os.path.basename(path), st.st_size, int(st.st_mtime))
    if os.path.isfile(cpath):
        try:
            cache = json.load(open(cpath))
        except Exception:
            cache = {}
    state = {"model": None}
    print(f"[gate] script {len(script)} words")

    def words_for(path, label):
        k = key(path)
        if k in cache:
            print(f"[gate] {label:<9} {len(cache[k])} words (cached)")
            return cache[k]
        if state["model"] is None:
            state["model"] = rc.load_asr(a.asr_model)
        w = transcribe_all(state["model"], path)
        cache[k] = w
        json.dump(cache, open(cpath, "w"))
        print(f"[gate] {label:<9} {len(w)} words")
        return w

    raw = words_for(a.raw, "raw")
    del_ = words_for(a.delivered, "delivered")

    in_raw = matched(script, raw)
    in_del = matched(script, del_)
    lost = sorted(in_raw - in_del)

    if not lost:
        print(f"\n[gate] PASS — every one of the {len(in_raw)} script words the raw "
              f"take contains is still in the delivered file.")
        return 0

    # Group consecutive indices so one damaged phrase reports as one finding.
    #
    # This was written as `runs.append(cur), cur.clear(), cur.append(i)` inside an
    # expression, which appends a REFERENCE and then empties the very list it just
    # stored -- so every run in the report was the same object and one finding
    # printed eleven times. The detection was correct and the report was useless,
    # which is the worse of the two failures because it still looks like output.
    runs, cur = [], [lost[0]]
    for i in lost[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    print(f"\n[gate] FAIL — mastering changed {len(lost)} word(s) in {len(runs)} place(s).")
    print("       The raw take has these and the delivered file does not.\n")
    for r in runs:
        lo, hi = r[0], r[-1]
        print(f"  script[{lo}:{hi+1}]  ...{' '.join(script[max(0,lo-6):lo])} "
              f">>{' '.join(script[lo:hi+1])}<< {' '.join(script[hi+1:hi+7])}...")
    print("\n  Do NOT deliver. The master is the only destructive edit in the pipeline\n"
          "  that does not verify itself; re-run it with --keep-glitches and re-gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
