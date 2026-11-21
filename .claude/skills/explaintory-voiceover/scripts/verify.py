#!/usr/bin/env python3
"""
The gate in front of delivery. Nothing goes to Sapro until this passes.

Every check here exists because something got through to him that should not
have. The rule is his: never assume it is checked.

    python3 verify.py --audio "Title (final).mp3" --script script_lines.txt

Exit 0 = deliverable. Exit 1 = do not send it.

WHAT THIS IS NOT
    It is not listening. Nobody here can hear the file, and pretending otherwise
    is how a 150 ms pause in the middle of "between 1547 and 1550" reached him
    with "QC clean" written next to it. What this does is measure the things a
    listener would notice, so that the gap between "measured" and "heard" is as
    small as it can be made -- and state plainly what is still outside it.

WHAT IT CHECKS
    words         every word of the script present, in order, via ASR
    pauses        every silence traced back to a reason in the script
    chapters      each chapter announcement has its gap
    loudness      MEASURED integrated LUFS and true peak, never the target line
    signal        clipping, DC, noise floor, dead air
    length        duration and speaking rate against the channel reference

THE PAUSE CHECK IS THE POINT
    A pause in the wrong place passes every other gate. The words are all there,
    so WER is clean; the waveform is fine, so QC is clean. The only way to catch
    it is to ask of every silence: what in the script put it here? A silence with
    no punctuation, no paragraph break, no chapter boundary and no curated break
    behind it is unexplained, and unexplained is what "1547 || and 1550" was.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000

# A silence this long mid-speech is long enough to hear as a beat. Below it the
# ear reads a stop consonant or a breath, not a pause.
# Measured on a delivered master: ordinary speech leaves 90-120 ms holes at stop
# consonants and breaths all through a read, and flagging those buries the real
# defect in noise. The master's own smallest inserted beat is a comma at 160 ms,
# so a pause that nobody can explain only matters from about there.
AUDIBLE_PAUSE = 0.140

# Channel reference from the human VO stem (see explaintory-vo-master).
REF_OVERALL, REF_ARTIC = 181.0, 197.0


def log(m):
    print(f"[verify] {m}", flush=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


# ------------------------------------------------------------------ measurement
def duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    return float(p.stdout.strip() or 0)


def loudness(path):
    """MEASURED integrated LUFS and true peak.

    Not the loudnorm target printed by the master before its filter runs. That
    line was quoted as a result twice; both times the file was 0.5 LU quieter and
    0.2 dB louder at the peak than the number handed over.
    """
    p = run(["ffmpeg", "-v", "info", "-i", path, "-af", "ebur128=peak=true",
             "-f", "null", "-"])
    err = p.stderr
    lufs = re.findall(r"I:\s*(-?\d+\.?\d*)\s*LUFS", err)
    peak = re.findall(r"Peak:\s*(-?\d+\.?\d*)\s*dBFS", err)
    lra = re.findall(r"LRA:\s*(-?\d+\.?\d*)\s*LU", err)
    return (float(lufs[-1]) if lufs else None,
            float(peak[-1]) if peak else None,
            float(lra[-1]) if lra else None)


def silences(path, floor_db=-40, min_dur=0.05):
    p = run(["ffmpeg", "-v", "info", "-i", path, "-af",
             f"silencedetect=n={floor_db}dB:d={min_dur}", "-f", "null", "-"])
    out, start = [], None
    for m in re.finditer(r"silence_(start|end): ([\d.]+)", p.stderr):
        if m.group(1) == "start":
            start = float(m.group(2))
        elif start is not None:
            out.append((start, float(m.group(2))))
            start = None
    return out


def transcribe_words(path, asr="distil-large-v3"):
    import readcheck as rc
    m = rc.load_asr(asr)
    wav = path
    if not path.lower().endswith(".wav"):
        wav = os.path.join(os.path.dirname(os.path.abspath(path)), ".verify16k.wav")
        run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", wav, "-y"])
    segs, _ = m.transcribe(wav, language="en", beam_size=5,
                           word_timestamps=True,
                           condition_on_previous_text=False)
    return [(w.word.strip(), w.start, w.end, w.probability)
            for s in segs for w in (s.words or [])]


# ------------------------------------------------------------------ the pause check
def audit_boundaries(script_path, words=None, sil=None, toks=None,
                     min_gap=0.140):
    """Predict where the master will put a beat, and name the ones that are wrong.

    Done against the SCRIPT, not against pauses.csv. The report's `context` column
    is built from the aligner's token stream, which drops bare numerals -- so
    "between 1547 and 1550" is written there as "between || and", and any rule
    reading it sees a comma-less "between" and invents 35 failures that do not
    exist. The script has the years; the report does not.

    The one wrong decision the master makes is a beat inside a date range, where
    the two years and their joiner are a single span.

    A range in the script is only a FINDING if the beat is actually there in this
    audio. Predicting it from the script alone marks a fixed file as broken --
    the ranges still exist in the text after the master stops splitting them.
    """
    lines = open(script_path, encoding="utf-8").read().split("\n")
    seq = [w for line in lines for w in line.split()]
    bad = []
    for i in range(len(seq) - 2):
        w, nxt, after = seq[i], seq[i + 1], seq[i + 2]
        if not _year(w) or _year(nxt):
            continue
        if nxt.strip(".,;:").lower() not in RANGE_JOINERS or not _year(after):
            continue
        ctx = " ".join(seq[max(0, i - 4):i + 5])
        if words is None or sil is None:
            bad.append(f"date range “{w} {nxt} {after}” — “…{ctx}…” (audio not checked)")
            continue
        before = seq[i - 1] if i else ""
        after2 = seq[i + 3] if i + 3 < len(seq) else ""
        gap = _gap_after(w, nxt, words, sil, before)
        if gap is None:
            bad.append(f"date range “{w} {nxt} {after}” could not be located in the "
                       f"audio — NOT checked, do not read this as a pass "
                       f"— “…{ctx}…”")
        elif gap >= min_gap:
            bad.append(f"{gap*1000:.0f} ms beat inside the date range "
                       f"“{w} {nxt} {after}” — “…{ctx}…”")
    return bad


def _gap_after(w, nxt, words, sil, before=""):
    """Largest silence inside the spoken date range, or None if it cannot be found.

    Does NOT look for the year itself. The transcriber does not return "1547" as
    one token -- it splits the number -- so matching on it finds nothing and the
    check silently passes a file that has the defect. The anchors are the ordinary
    words on either side of the range ("...roads BETWEEN 1547 and 1550, DESCRIBED
    ..."), which transcribe reliably, and the span between them is searched.
    """
    nb, nj = norm(before), norm(nxt)
    if not nb or not nj:
        return None
    for i in range(len(words)):
        if norm(words[i][0]) != nb:
            continue
        # Search only as far as the JOINER, never past the second year.
        #
        # An earlier version ran the span from the word before the range to the
        # word after it, which swallowed the legitimate beat that follows the
        # second year -- the sentence stop in "...between 1966 and 1969. Heroin
        # was..." -- and reported a correctly-mastered file as split. The defect
        # lives between the first year and the joiner and nowhere else.
        for j in range(i + 1, min(i + 8, len(words))):
            if norm(words[j][0]) != nj:
                continue
            lo, hi = words[i][2], words[j][1]
            if hi <= lo:
                return 0.0
            hits = [b - a for a, b in sil if a >= lo - 0.05 and b <= hi + 0.05]
            return max(hits) if hits else 0.0
    return None


def script_tokens(script_path):
    """-> [(word, ends_sentence, ends_clause, ends_paragraph, is_chapter)]"""
    lines = open(script_path, encoding="utf-8").read().split("\n")
    toks = []
    for li, line in enumerate(lines):
        ws = line.split()
        if not ws:
            continue
        chapter = len(ws) <= 3 and line.strip().endswith(".")
        for i, w in enumerate(ws):
            last = i == len(ws) - 1
            toks.append((w,
                         bool(re.search(r"[.!?][\"']?$", w)),
                         bool(re.search(r"[,;:][\"']?$", w)),
                         last,
                         chapter))
    return toks


RANGE_JOINERS = {"and", "to", "or", "until", "through", "till"}


def _year(w):
    return bool(re.match(r"^\d", w or "")) or bool(
        re.match(r"^(BC|AD|BCE|CE)[.,;:]?$", w or "", re.I))


def explain_pauses(words, toks, curated, sil, min_pause=AUDIBLE_PAUSE):
    """Map every audible silence back to the script.

    Returns (explained, unexplained). A pause is explained when the script word
    before it ends a sentence, clause or paragraph, announces a chapter, is one
    half of a curated break, or is a date the master gives its standard beat to.
    Anything else is a beat nobody asked for.

    MEASURED FROM THE SILENCE MAP, NOT FROM ASR WORD BOUNDARIES. The first
    version of this subtracted one word's end time from the next word's start,
    and it missed the very bug it was written for: faster-whisper hands back
    contiguous word spans, so the 150 ms hole inside "1547 || and 1550" showed up
    as a gap of exactly 0.000 s. silencedetect sees it. Word timings are used
    only to say WHICH words a silence fell between.
    """
    # align ASR words to script tokens by normalized text, in order
    import difflib
    a = [norm(w) for w, _, _, _ in words]
    b = [norm(t[0]) for t in toks]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    amap = {}
    for i, j, n in sm.get_matching_blocks():
        for k in range(n):
            amap[i + k] = j + k

    explained, unexplained, unplaced = [], [], []
    for s0, s1 in sil:
        gap = s1 - s0
        if gap < min_pause:
            continue
        # the last word that finished before this silence began
        i = None
        for k, (_, ws, we, _) in enumerate(words):
            if we <= s0 + 0.06:
                i = k
            else:
                break
        if i is None or i + 1 >= len(words):
            continue
        j = amap.get(i)
        if j is None:
            unplaced.append((s0, gap))     # blind here — counted, never silently dropped
            continue
        w, sent, clause, para, chap = toks[j]
        nxt = toks[j + 1][0] if j + 1 < len(toks) else ""
        after = toks[j + 2][0] if j + 2 < len(toks) else ""
        pair = (w.strip(".,;:").lower(), nxt.strip(".,;:").lower())

        # The master gives a bare date its own beat on purpose. That is a real
        # reason, so it is explained -- EXCEPT across a range, where the beat
        # splits one span in half and is exactly the defect this gate exists for.
        postdate = (_year(w) and not _year(nxt)
                    and not (nxt.strip(".,;:").lower() in RANGE_JOINERS
                             and _year(after)))

        why = ("sentence" if sent else "clause" if clause else
               "paragraph" if para else "chapter" if chap else
               "curated" if pair in curated else
               "post-date" if postdate else None)
        rec = (s0, gap, w, nxt, why)
        (explained if why else unexplained).append(rec)
    return explained, unexplained, unplaced


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--script", required=True, help="script_lines.txt from the run")
    ap.add_argument("--curated", help="the curated break file used for the master")
    ap.add_argument("--no-boundary-audit", action="store_true",
                    help="skip the script-level check for beats inside date ranges")
    ap.add_argument("--sections", help="sections.json from the run — the authority on "
                                       "which lines are chapter announcements. Without "
                                       "it chapters are guessed from line length, which "
                                       "over-counts.")
    ap.add_argument("--asr-model", default="distil-large-v3")
    ap.add_argument("--target-lufs", type=float, default=-14.0)
    ap.add_argument("--target-tp", type=float, default=-1.5)
    ap.add_argument("--lufs-tol", type=float, default=1.0)
    ap.add_argument("--json", help="write the full report here")
    a = ap.parse_args()

    fails, warns, report = [], [], {}

    dur = duration(a.audio)
    report["duration"] = dur
    log(f"{os.path.basename(a.audio)} — {int(dur//60)}:{dur%60:05.2f}")

    # ---- signal
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.audio, "-ac", "1",
                          "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    try:
        sys.path.insert(0, os.path.expanduser(
            "~/.claude/skills/explaintory-vo-master/scripts"))
        import humanize as H
        qc = H.qc_report(x, "delivered")
        report["qc"] = qc
        if qc:
            for f in qc:
                (fails if f.startswith("CLIP") else warns).append(f"QC: {f}")
        else:
            log("QC clean (re-run here, not read from a log)")
    except Exception as e:
        warns.append(f"QC could not run: {e}")

    # ---- loudness, measured
    lufs, tp, lra = loudness(a.audio)
    report["lufs"], report["true_peak"], report["lra"] = lufs, tp, lra
    log(f"measured {lufs} LUFS / {tp} dBTP true peak (LRA {lra})")
    if lufs is not None and abs(lufs - a.target_lufs) > a.lufs_tol:
        warns.append(f"loudness {lufs} LUFS is {abs(lufs-a.target_lufs):.1f} LU "
                     f"from the {a.target_lufs} target")
    if tp is not None and tp > a.target_tp:
        warns.append(f"true peak {tp} dBTP is above the {a.target_tp} ceiling")

    # ---- words
    log("transcribing (this is the slow part)")
    words = transcribe_words(a.audio, a.asr_model)
    toks = script_tokens(a.script)
    report["asr_words"], report["script_words"] = len(words), len(toks)

    import readcheck as rc
    heard = " ".join(w for w, _, _, _ in words)
    script_text = " ".join(t[0] for t in toks)
    wer, spans = rc.diff_words(script_text, heard)
    hard = rc.classify(spans)
    report["wer"] = round(wer, 4)
    log(f"{len(words)} words heard vs {len(toks)} in the script — WER {wer:.3f}")
    for kind, exp, got, ctx in hard[:12]:
        warns.append(f"{kind}: after “…{ctx}” expected “{exp}” heard “{got}”")

    # ---- rate
    sil = silences(a.audio)
    quiet = sum(b - s for s, b in sil)
    n = len(toks)
    overall = n / (dur / 60) if dur else 0
    artic = n / ((dur - quiet) / 60) if dur > quiet else 0
    report["overall_wpm"], report["articulation_wpm"] = round(overall, 1), round(artic, 1)
    log(f"{overall:.0f} wpm overall, {artic:.0f} articulation "
        f"(reference {REF_OVERALL:.0f}/{REF_ARTIC:.0f}); silence {quiet/dur*100:.1f}%")

    # ---- pauses: the check that would have caught 0:57
    curated = set()
    if a.curated and os.path.isfile(a.curated):
        for line in open(a.curated, encoding="utf-8"):
            if "|" in line:
                x1, x2 = line.strip().split("|", 1)
                curated.add((x1.strip().lower(), x2.strip().lower()))
    ok, bad, unplaced = explain_pauses(words, toks, curated, sil)
    report["pauses_explained"] = len(ok)
    report["pauses_unexplained"] = [
        {"at": round(t, 2), "gap": round(g, 3), "after": w, "before": nx}
        for t, g, w, nx, _ in bad]
    log(f"{len(ok)} pauses traced to the script, {len(bad)} unexplained, "
        f"{len(unplaced)} could not be placed")
    if unplaced:
        big = [(t, g) for t, g in unplaced if g >= 0.20]
        warns.append(f"{len(unplaced)} silence(s) could not be matched to the script "
                     f"and were NOT judged"
                     + (f"; {len(big)} of them over 200 ms, longest "
                        f"{max(g for _, g in big)*1000:.0f} ms" if big else ""))
    if not a.no_boundary_audit:
        bad_b = audit_boundaries(a.script, words, sil, toks)
        log(f"date ranges: {len(bad_b)} carrying a beat that splits them")
        for c in bad_b:
            fails.append(f"boundary: {c}")
    for t, g, w, nx, _ in bad[:20]:
        fails.append(f"unexplained {g*1000:.0f} ms pause at "
                     f"{int(t//60)}:{t%60:05.2f} — “{w} ‖ {nx}”")

    # ---- chapters
    if a.sections and os.path.isfile(a.sections):
        man = json.load(open(a.sections, encoding="utf-8"))
        chaps = [s["send_text"].strip() for s in man["sections"]
                 if s.get("is_heading") and not s.get("is_title")]
    else:
        chaps = [t[0] for t in toks if t[4]]
    heard_seq = [norm(w) for w, _, _, _ in words]
    found = 0
    for c in chaps:
        parts = [norm(x) for x in c.split() if norm(x)]
        if not parts:
            continue
        # a two-word chapter ("Forced March.") never matches a single ASR token
        import difflib
        want = "".join(parts)
        hit = False
        for k in range(len(heard_seq) - len(parts) + 1):
            got = "".join(heard_seq[k:k + len(parts)])
            # a chapter name is a proper noun; the transcriber routinely gets the
            # spelling slightly wrong ("philippon" for "Philopon") and that is not
            # a missing chapter
            if difflib.SequenceMatcher(a=want, b=got).ratio() >= 0.80:
                hit = True
                break
        found += 1 if hit else 0
    report["chapters"] = {"in_script": len(chaps), "found_in_audio": found}
    log(f"chapters: {found} of {len(chaps)} located in the audio")
    if found < len(chaps):
        fails.append(f"only {found} of {len(chaps)} chapter names found in the audio")

    # ---- verdict
    print()
    for f in fails:
        print(f"  FAIL  {f}")
    for w in warns:
        print(f"  warn  {w}")
    if a.json:
        json.dump(report, open(a.json, "w"), indent=1)
    print()
    if fails:
        log(f"NOT DELIVERABLE — {len(fails)} failure(s), {len(warns)} warning(s)")
        return 1
    log(f"verified — 0 failures, {len(warns)} warning(s)")
    log("what this cannot tell you: whether the read sounds right. "
        "Stretch artefacts, emphasis and tone need an ear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
