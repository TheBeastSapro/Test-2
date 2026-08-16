#!/usr/bin/env python3
"""Line the parsed script up against the transcript and write each section's
start and end time back into work/sections.json.  (Stage 2, the step
BUILD-PACKET section 4 implies: sections.json holds "script parsed into
sections with VO time ranges", and 4.4 requires section=(start, end) for
every anchor search.)

WHEN A STRETCH OF SCRIPT HAS NO MATCHING WORDS, DO NOT CONCLUDE THE VO IS
MISSING IT. Whisper silently drops words, especially under music, and
"the narrator never recorded the mid-roll CTA" is a serious conclusion to
get wrong. So every suspected gap is put to the RMS arbiter first
(BUILD-PACKET 4.3):

  flat, normal RMS through the window  -> the VO is there. Whisper dropped
                                          it, or the read was paraphrased.
                                          Nothing to record.
  RMS floored through the window       -> the VO really is missing it.
                                          THAT is a pickup the owner records.
  no elapsed time at all               -> the words were never spoken and
                                          consumed no audio. Also a pickup.

Measure RMS on the DRY voiceover. On a mixed track the bed holds the level
up through a real gap and the arbiter tells you a comfortable lie.

Usage:
  align_sections.py /abs/work/sections.json /abs/work/words.json /abs/work/rms.json
  align_sections.py /abs/work/sections.json /abs/work/words.json /abs/work/rms.json \\
      --gap-words 8 --floor -50 --dry-run

Options:
  --gap-words N   unmatched script words before a stretch counts as a gap (8)
  --floor DB      RMS window below this is silence (-50)
  --quiet-frac F  fraction of the window that must be below the floor for the
                  gap to be called real (0.6)
  --min-silence S continuous floored audio near a suspect gap that counts as a
                  real hole in the VO, in seconds (1.0). Normal breath pauses
                  in a read are a single 0.5s window, so 1.0 clears them.
  --dry-run       print the table, do not write sections.json back

Exit codes: 0 aligned clean, 1 usage or input error,
            2 at least one suspected REAL gap (pickup needed) or a gap that
              could not be arbitrated because no rms.json was supplied.
"""
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# One normaliser for the whole stage. anchors.norm folds spoken number words
# onto digits, because Whisper writes "30" where the script says "thirty";
# without that, every number in the script reads as a missing word here and
# as an unresolvable anchor there.
from anchors import norm  # noqa: E402


def abs_arg(p, what):
    if not os.path.isabs(p):
        sys.exit(f"ERROR: {what} must be an absolute path (got {p!r}). "
                 "The shell working directory is not stable between calls.")
    return p


def load_rms(path):
    """Accept the packet's flat list. hop is recovered from the t values."""
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("windows", [])
    if not data:
        sys.exit(f"ERROR: {path} holds no RMS windows")
    hop = round(data[1]["t"] - data[0]["t"], 4) if len(data) > 1 else 0.5
    return data, hop


def rms_verdict(rms, hop, t0, t1, floor, quiet_frac):
    """The arbiter. Returns (verdict, quiet_fraction, median_db)."""
    lo = max(0, int(t0 / hop))
    hi = min(len(rms), int(t1 / hop) + 1)
    win = [w["db"] for w in rms[lo:hi]]
    if not win:
        return "no-rms-coverage", 0.0, float("nan")
    quiet = sum(1 for d in win if d < floor) / len(win)
    med = sorted(win)[len(win) // 2]
    return ("real-gap" if quiet >= quiet_frac else "vo-present"), quiet, med


def nearest_silence(rms, hop, t0, t1, floor, min_silence, pad):
    """Longest floored run of at least min_silence seconds near [t0, t1].

    The window bracketed by the surrounding matched words is often useless for
    a real gap: Whisper does not timestamp what it never heard, so the words
    either side can end up adjacent and the window collapses to zero. What the
    owner needs is the actual hole in the audio to record into, so look for it
    in the RMS around the suspect point instead of trusting the transcript's
    idea of where the missing time is.
    """
    lo, hi = t0 - pad, t1 + pad
    best, run = None, None
    for w in rms:
        if lo <= w["t"] <= hi and w["db"] < floor:
            run = [w["t"], w["t"] + hop] if run is None else [run[0], w["t"] + hop]
        else:
            if run and run[1] - run[0] >= min_silence and (best is None or
                                                           run[1] - run[0] > best[1] - best[0]):
                best = run
            run = None
    if run and run[1] - run[0] >= min_silence and (best is None or
                                                   run[1] - run[0] > best[1] - best[0]):
        best = run
    return None if best is None else (round(best[0], 2), round(best[1], 2))


def tokenize(sections):
    """Flatten script narration to tokens, each remembering its section and
    its RAW line number in script.md."""
    toks, meta = [], []
    for si, s in enumerate(sections):
        lines = s.get("narration_lines") or [{"n": s.get("line_start", 0),
                                              "text": s.get("text", "")}]
        for line in lines:
            for raw in str(line["text"]).split():
                t = norm(raw)
                if t:
                    toks.append(t)
                    meta.append((si, line["n"]))
    return toks, meta


def main():
    argv, pos = sys.argv[1:], []
    gap_words, floor, quiet_frac, min_silence, dry = 8, -50.0, 0.6, 1.0, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
        elif a.startswith("--"):
            key, _, inline = a.partition("=")
            val = inline if inline else (argv[i + 1] if i + 1 < len(argv) else None)
            if not inline:
                i += 1
            if val is None:
                sys.exit(f"ERROR: {key} needs a value")
            if key == "--gap-words":
                gap_words = int(val)
            elif key == "--floor":
                floor = float(val)
            elif key == "--quiet-frac":
                quiet_frac = float(val)
            elif key == "--min-silence":
                min_silence = float(val)
            else:
                sys.exit(f"ERROR: unknown flag {key}")
        else:
            pos.append(a)
        i += 1
    if len(pos) not in (2, 3):
        sys.exit(__doc__)
    sec_path = abs_arg(pos[0], "sections.json")
    words_path = abs_arg(pos[1], "words.json")
    rms_path = abs_arg(pos[2], "rms.json") if len(pos) == 3 else None
    for p in (sec_path, words_path) + ((rms_path,) if rms_path else ()):
        if not os.path.isfile(p):
            sys.exit(f"ERROR: no such file: {p}")

    sections = json.load(open(sec_path, encoding="utf-8"))
    words = json.load(open(words_path, encoding="utf-8"))
    if not sections:
        sys.exit(f"ERROR: {sec_path} is empty. Run tools/parse_script.py first.")
    if not words:
        sys.exit(f"ERROR: {words_path} is empty. Run tools/transcribe.py first.")
    rms, hop = load_rms(rms_path) if rms_path else (None, 0.5)

    stoks, meta = tokenize(sections)
    vtoks = [norm(w["w"]) for w in words]
    if not stoks:
        sys.exit(f"ERROR: {sec_path} holds no narration text")

    sm = difflib.SequenceMatcher(None, stoks, vtoks, autojunk=False)
    s2v = {}
    for bi, bj, n in sm.get_matching_blocks():
        for k in range(n):
            s2v[bi + k] = bj + k

    vo_dur = words[-1]["e"]
    if rms:
        vo_dur = max(vo_dur, len(rms) * hop)

    # ---- per-section matched extents -------------------------------------
    ranges = []          # (first_script_tok, last_script_tok_exclusive)
    start_tok = 0
    for si in range(len(sections)):
        end_tok = start_tok
        while end_tok < len(meta) and meta[end_tok][0] == si:
            end_tok += 1
        ranges.append((start_tok, end_tok))
        start_tok = end_tok

    matched = []
    for si, (a, b) in enumerate(ranges):
        js = [s2v[i] for i in range(a, b) if i in s2v]
        if js:
            matched.append((words[min(js)]["s"], words[max(js)]["e"], len(js)))
        else:
            matched.append((None, None, 0))

    # ---- boundaries that tile the whole timeline -------------------------
    # Anchors are searched inside [start, end]; if the ranges left holes, an
    # anchor sitting in a hole would be unresolvable. So they tile.
    n = len(sections)
    cuts = [0.0] * (n + 1)
    cuts[n] = round(vo_dur, 3)
    for i in range(1, n):
        left = next((matched[k][1] for k in range(i - 1, -1, -1) if matched[k][1] is not None), None)
        right = next((matched[k][0] for k in range(i, n) if matched[k][0] is not None), None)
        if left is not None and right is not None:
            cuts[i] = round((left + right) / 2, 3)
        elif left is not None:
            cuts[i] = round(left, 3)
        elif right is not None:
            cuts[i] = round(right, 3)
        else:
            cuts[i] = cuts[i - 1]
    for i in range(1, n + 1):
        cuts[i] = max(cuts[i], cuts[i - 1])

    # ---- suspected gaps, then the arbiter --------------------------------
    gaps = []
    for si, (a, b) in enumerate(ranges):
        run = []
        for i in list(range(a, b)) + [None]:
            if i is not None and i not in s2v:
                run.append(i)
                continue
            if len(run) >= gap_words:
                p, q = run[0], run[-1]
                prev_j = next((s2v[k] for k in range(p - 1, -1, -1) if k in s2v), None)
                next_j = next((s2v[k] for k in range(q + 1, len(stoks)) if k in s2v), None)
                t0 = words[prev_j]["e"] if prev_j is not None else 0.0
                t1 = words[next_j]["s"] if next_j is not None else vo_dur
                lines = sorted({meta[k][1] for k in run})
                miss = " ".join(stoks[k] for k in run)
                silence = None
                if rms is not None:
                    pad = max(2.0, len(run) * 60.0 / 170.0)
                    silence = nearest_silence(rms, hop, t0, t1, floor, min_silence, pad)
                if silence:
                    verdict, qf, med = "real-gap", 1.0, float("nan")
                elif t1 - t0 < 0.5:
                    verdict, qf, med = "not-in-vo", 1.0, float("nan")
                elif rms is None:
                    verdict, qf, med = "unverified", 0.0, float("nan")
                else:
                    verdict, qf, med = rms_verdict(rms, hop, t0, t1, floor, quiet_frac)
                gaps.append({"section": sections[si]["index"], "words": len(run),
                             "script_lines": lines, "t0": round(t0, 2), "t1": round(t1, 2),
                             "verdict": verdict, "quiet_frac": round(qf, 2),
                             "median_db": None if med != med else round(med, 1),
                             "silence": silence, "text": miss[:160]})
            run = []

    # ---- per script line times -------------------------------------------
    # parse_script keeps raw line numbers so a gag lands on the beat the script
    # marked. This is what turns a marked joke line into a time range without
    # anyone having to guess which sentence it was.
    line_times = {}
    for i, (si, ln) in enumerate(meta):
        if i in s2v:
            w = words[s2v[i]]
            cur = line_times.get((si, ln))
            line_times[(si, ln)] = (min(cur[0], w["s"]) if cur else w["s"],
                                    max(cur[1], w["e"]) if cur else w["e"])

    # ---- write back -------------------------------------------------------
    for si, s in enumerate(sections):
        a, b = ranges[si]
        total = b - a
        s["line_times"] = [{"n": ln, "t0": round(t0, 3), "t1": round(t1, 3)}
                           for (sj, ln), (t0, t1) in sorted(line_times.items())
                           if sj == si]
        s["start"] = cuts[si]
        s["end"] = cuts[si + 1]
        s["vo_start"] = None if matched[si][0] is None else round(matched[si][0], 3)
        s["vo_end"] = None if matched[si][1] is None else round(matched[si][1], 3)
        s["matched_words"] = matched[si][2]
        s["script_words"] = total
        s["match_ratio"] = round(matched[si][2] / total, 3) if total else 0.0
        s["gaps"] = [g for g in gaps if g["section"] == s["index"]]
    if not dry:
        json.dump(sections, open(sec_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    # ---- summary ----------------------------------------------------------
    overall = len(s2v) / len(stoks)
    print("SUMMARY align_sections")
    print(f"  sections: {sec_path}")
    print(f"  words   : {words_path} ({len(words)} words, {words[0]['s']:.2f}-{words[-1]['e']:.2f}s)")
    print(f"  rms     : {rms_path or 'NOT SUPPLIED - gaps cannot be arbitrated'}")
    print(f"  match   : {len(s2v)}/{len(stoks)} script words found in transcript ({overall:.1%})")
    print()
    print(f"  {'idx':>3} {'kind':<8} {'creature/title':<26} {'start':>8} {'end':>8} "
          f"{'dur':>7} {'script':>7} {'match':>6}  status")
    for s in sections:
        label = (s.get("creature") or s.get("title") or "")[:26]
        st = "ok"
        bad = [g for g in s["gaps"] if g["verdict"] in ("real-gap", "not-in-vo")]
        soft = [g for g in s["gaps"] if g["verdict"] == "vo-present"]
        if bad:
            st = "*** GAP"
        elif any(g["verdict"] == "unverified" for g in s["gaps"]):
            st = "unverified"
        elif soft:
            st = "whisper-drop"
        elif s["match_ratio"] < 0.9:
            st = "loose"
        print(f"  {s['index']:>3} {s.get('kind', ''):<8} {label:<26} "
              f"{s['start']:>8.2f} {s['end']:>8.2f} {s['end'] - s['start']:>7.2f} "
              f"{s['script_words']:>7} {s['match_ratio']:>5.0%}  {st}")

    real = [g for g in gaps if g["verdict"] in ("real-gap", "not-in-vo")]
    soft = [g for g in gaps if g["verdict"] == "vo-present"]
    unver = [g for g in gaps if g["verdict"] in ("unverified", "no-rms-coverage")]
    print()
    if soft:
        print(f"  {len(soft)} gap(s) arbitrated as VO PRESENT (Whisper dropped it, "
              "or the read paraphrased). Nothing to record:")
        for g in soft:
            print(f"    section {g['section']} lines {g['script_lines']} "
                  f"{g['t0']}-{g['t1']}s  median {g['median_db']} dBFS, "
                  f"{g['quiet_frac']:.0%} below floor  |  {g['words']} words: {g['text'][:70]}")
    if unver:
        print(f"  {len(unver)} gap(s) COULD NOT BE ARBITRATED. Run tools/rms.py on the "
              "dry VO and re-run:")
        for g in unver:
            print(f"    section {g['section']} lines {g['script_lines']} {g['t0']}-{g['t1']}s")
    if real:
        print("  " + "!" * 68)
        print(f"  !!! {len(real)} SUSPECTED REAL GAP(S). THE VOICEOVER IS MISSING SCRIPT.")
        print("  !!! These are PICKUPS the owner has to record. Do not build over them.")
        for g in real:
            if g["silence"]:
                where = f"{g['silence'][0]}-{g['silence'][1]}s"
                why = (f"RMS floors out for {g['silence'][1] - g['silence'][0]:.1f}s "
                       f"below {floor:g} dBFS. RECORD THE PICKUP INTO THIS WINDOW")
            else:
                where = f"{g['t0']}-{g['t1']}s"
                why = ("no audio time elapsed at all: the narrator went straight "
                       "past these words")
            print(f"    section {g['section']}  script lines {g['script_lines']}  "
                  f"{where}  ({why})")
            print(f"      {g['words']} words missing: {g['text']}")
        print("  " + "!" * 68)
    if not (soft or unver or real):
        print("  gaps    : none. Every section resolved against the transcript.")
    print()
    print(f"  {'DRY RUN, nothing written' if dry else 'wrote   : ' + sec_path}")
    if real or unver:
        sys.exit(2)


if __name__ == "__main__":
    main()
