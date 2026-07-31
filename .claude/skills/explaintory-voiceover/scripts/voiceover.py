#!/usr/bin/env python3
"""
Script in, mastered voiceover out. One command.

    generate  -> read-check -> redo bad sections -> master -> "<Title> (final).mp3"

The mastering stage is the existing `explaintory-vo-master` pipeline (humanize.py)
with its approved settings; nothing here re-tunes them. What this adds in front of
it is the generation and the automatic read-check, so a misread section is caught
and re-rendered before mastering instead of after a human has listened to twelve
minutes of audio.

Every stage writes into --work, so a run can be resumed with --from.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as gen  # noqa: E402
import readcheck as rc  # noqa: E402
from script_prep import (build_sections, detect_structure,  # noqa: E402
                         master_script_lines, split_pronunciation_guide)

CHARS_PER_SEC = 14      # the studio's narration-pace constant, for the estimate

STAGES = ["generate", "check", "master"]

# Where explaintory-vo-master keeps humanize.py. It is a separate skill; this one
# drives it rather than duplicating its 560 lines of measured settings.
HUMANIZE_CANDIDATES = [
    "~/.claude/skills/explaintory-vo-master/scripts/humanize.py",
    "/root/.claude/skills/explaintory-vo-master/scripts/humanize.py",
    "./.claude/skills/explaintory-vo-master/scripts/humanize.py",
]


def log(m):
    print(f"[voiceover] {m}", flush=True)


def find_humanize(override=None):
    for c in ([override] if override else []) + HUMANIZE_CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.isfile(p):
            return p
    raise SystemExit(
        "Could not find humanize.py from the explaintory-vo-master skill.\n"
        "Pass --humanize /path/to/humanize.py, or install that skill.")


def safe_filename(s):
    s = re.sub(r"[^\w\-. ]+", "", (s or "").strip())
    return re.sub(r"\s+", " ", s)[:80] or "Voiceover"


def derive_title(script_path, raw, explicit=None, read_title=True):
    """-> (title, script for narration).

    The H1 names the file either way. Whether it is also SPOKEN is the profile's
    `readTitle`, not this tool's opinion — the studio reads it by default and that
    is the read Sapro has been publishing.
    """
    lines = raw.split("\n")
    for i, line in enumerate(lines[:12]):
        s = line.strip()
        m = (re.match(r"^#\s+(.{2,80})$", s)
             or re.match(r"^title\s*[:\-]\s*(.{2,80})$", s, re.I))
        if m:
            found = m.group(1).strip()
            body = raw if read_title else "\n".join(lines[:i] + lines[i + 1:])
            return (explicit.strip() if explicit else found), body
    if explicit:
        return explicit.strip(), raw
    stem = os.path.splitext(os.path.basename(script_path))[0]
    return re.sub(r"[_\-]+", " ", stem).strip().title(), raw


def suggest_breaks(script_lines):
    """Candidate clause breaks the script forgot to punctuate.

    A fronted adverbial — "At Angolpo ‖ the Japanese lost…", "Below the garden ‖
    sat a temple" — wants a beat where the writer put no comma. Finding it means
    knowing where the phrase ENDS, which is a parse, not a pattern: a regex
    counting words lands on "lost forty ‖ ships". So this uses spaCy and takes
    the last token of the modifier's own subtree.

    Candidates only. The vo-master skill is explicit that automatic guesses are
    wrong about a third of the time — it wants a pause inside "growing on a deck ‖
    that also mounted a catapult". Read them, keep the real ones. Dates are
    already handled inside humanize.py, so they are not repeated here.
    """
    try:
        import spacy
    except ImportError:
        raise SystemExit("--suggest-breaks needs spaCy: "
                         "pip install spacy && python3 -m spacy download en_core_web_sm")
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing: python3 -m spacy download en_core_web_sm")

    out = []
    for doc in nlp.pipe(script_lines):
        for sent in doc.sents:
            head = sent.root
            for child in head.children:
                if child.dep_ not in ("prep", "advmod", "advcl", "npadvmod"):
                    continue
                sub = list(child.subtree)
                if sub[0].i != sent.start:          # only FRONTED phrases
                    continue
                last = sub[-1]
                nxt = doc[last.i + 1] if last.i + 1 < len(doc) else None
                if nxt is None or nxt.is_punct or nxt.i >= sent.end:
                    continue                        # already punctuated — nothing to add
                if len(sub) < 2:                    # a bare "Then," needs no beat
                    continue
                if re.fullmatch(r"\d+|BCE?|AD", last.text, re.I):
                    continue                        # post-date beats are automatic already
                out.append((last.text, nxt.text, sent.text.strip()))
    return out


def mark_title_section(sections, title):
    """Flag the section that is the video's TITLE rather than a chapter.

    With readTitle on, the H1 is spoken, so it becomes a heading section like any
    other — but it is not a chapter, and counting it as one overstates the chapter
    count and misreads the script's shape back to Sapro.

    It stays in the heading rate levelling on purpose: the title is the section with
    no conditioning behind it at all, so it is the one that rushes, and the chapters
    are what it should be levelled against.
    """
    want = title.strip().rstrip(".").lower()
    for sec in sections:
        if not sec["is_heading"]:
            continue
        if sec["send_text"].strip().rstrip(".").lower() == want:
            sec["is_title"] = True
        break                                    # only the first heading can be it
    return sections


def chapter_names(sections):
    return [s["send_text"].strip().rstrip(".") for s in sections
            if s["is_heading"] and not s.get("is_title")]


def show_plan(title, raw, guide, sections, prof, skip_headings, api_key=None):
    """What the studio's structure panel and estimator show, before a credit is spent.

    Generation is the irreversible part of this pipeline — the read-check and the
    master can be re-run for free, but characters sent are characters billed. So
    the same numbers Sapro checks in the browser get printed here, and the run
    stops until he has seen them.
    """
    st = detect_structure(raw)
    chars = sum(s["chars"] for s in sections)
    mins, secs_ = divmod(int(chars / CHARS_PER_SEC), 60)
    heads = [s for s in sections if s["is_heading"]]
    titled = any(s.get("is_title") for s in sections)
    chapters = chapter_names(sections)

    print(f"\n  TITLE: “{title}”"
          + ("  (read aloud — readTitle is on)" if titled
             else "  (not narrated)"))
    bits = []
    if chapters:
        bits.append(f"{len(chapters)} chapter" + ("s" if len(chapters) > 1 else ""))
    if st["directions"]:
        bits.append(f"{st['directions']} stage direction"
                    + ("s" if st["directions"] > 1 else ""))
    if st.get("dividers"):
        bits.append(f"{st['dividers']} divider" + ("s" if st["dividers"] > 1 else ""))
    if st["ctas"]:
        bits.append(f"{st['ctas']} CTA" + ("s" if st["ctas"] > 1 else ""))
    print(f"  detected {' · '.join(bits) if bits else 'no chapters or directions'}"
          f" — chapter names {'NOT read aloud' if skip_headings else 'read aloud as intros'}")

    for n, name in enumerate(chapters, 1):
        print(f"    {n}. {name}")
    for pv in st["cta_previews"][:3]:
        print(f"  CTA: “{pv}”")
    if guide:
        print(f"  pronunciation guide: {len(guide)} names held out of the narration")

    spoken_heads = len(heads) - (1 if titled else 0)
    print(f"\n  {len(sections)} sections ({spoken_heads} chapter announcements"
          f"{' + the title' if titled else ''})"
          f" · {chars:,} chars · ~{mins}:{secs_:02d} audio")
    print(f"  voice {prof['voice_id']} · {prof['model']} · stability "
          f"{prof['settings']['stability']} · style {prof['settings']['style']} · "
          f"speed {prof['settings']['speed']}")
    print(f"  COST: ~{chars:,} credits", end="")

    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            sub = ElevenLabs(api_key=api_key).user.subscription.get()
            left = sub.character_limit - sub.character_count
            print(f" of {left:,} remaining"
                  + ("   ** NOT ENOUGH **" if chars > left else ""))
        except Exception:
            print("")
    else:
        print("")
    print()


def run_stage(cmd):
    log("$ " + " ".join(str(c) for c in cmd))
    p = subprocess.run(cmd)
    if p.returncode not in (0, 1):
        raise SystemExit(f"stage failed with exit {p.returncode}")
    return p.returncode


def main():
    ap = argparse.ArgumentParser(description="Script -> mastered ExplainTory voiceover.")
    ap.add_argument("--script", required=True)
    ap.add_argument("--title", help="video title; defaults to the script's H1 or filename")
    ap.add_argument("--out-dir", default=".", help="where the delivered MP3 lands")
    ap.add_argument("--work", help="working directory (default: <out-dir>/.vo_<title>)")
    ap.add_argument("--profile", help="voiceover_profile.json from Voiceover Studio")
    ap.add_argument("--curated", help="clause-break file for the mastering pass "
                                      "(one 'wordA|wordB' pair per line)")
    ap.add_argument("--lexicon", help="pronunciation lexicon JSON — names respelled so "
                                      "the voice reads them right")
    ap.add_argument("--skip-headings", action="store_true", default=None,
                    help="do not read chapter names aloud (default: whatever the profile locked in)")
    ap.add_argument("--max-chunk", type=int, default=None)
    ap.add_argument("--chapter-pause", choices=["tight", "natural", "wide"])
    ap.add_argument("--asr-model", default=rc.DEFAULT_ASR)
    ap.add_argument("--max-redos", type=int, default=2,
                    help="rounds of re-rendering flagged sections before giving up")
    ap.add_argument("--from", dest="start", choices=STAGES, default="generate")
    ap.add_argument("--humanize", help="path to humanize.py")
    ap.add_argument("--max-wpm", type=float, default=0.0,
                    help="slow only sentences faster than this, in the master. 290 = "
                         "faster than the human reference ever goes, so it catches only "
                         "broken sentences; 250 is the human's p90 and will also slow "
                         "real punchlines. 0 (default) = off, the approved sound.")
    ap.add_argument("--no-master", action="store_true", help="stop after the read-check")
    ap.add_argument("--suggest-breaks", action="store_true",
                    help="print candidate clause breaks and exit — read them, keep the real ones")
    ap.add_argument("--plan", action="store_true",
                    help="show the structure and the credit cost, then stop. Run this "
                         "first and let Sapro confirm before spending anything.")
    a = ap.parse_args()

    # the studio's locked-in calibration supplies the defaults; explicit flags win
    prof = gen.load_profile(a.profile)
    if a.skip_headings is None:
        a.skip_headings = prof["skip_headings"]
    if a.max_chunk is None:
        a.max_chunk = prof["chunk_size"] or 450

    title, raw = derive_title(a.script, open(a.script, encoding="utf-8").read(),
                              a.title, prof["read_title"])
    # the guide at the foot of the script is a note to the reader, never a line to
    # read — and it is this video's answer key for how each name should sound
    raw, guide = split_pronunciation_guide(raw)
    lines = master_script_lines(raw, a.skip_headings)

    if a.suggest_breaks:
        for w1, w2, ctx in suggest_breaks(lines):
            print(f"{w1}|{w2}\t\t… {ctx.strip()} …")
        return 0

    work = a.work or os.path.join(a.out_dir, ".vo_" + safe_filename(title).replace(" ", "_"))
    os.makedirs(work, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)

    parts_dir = os.path.join(work, "parts")
    raw_vo = os.path.join(work, "raw_stitched.wav")
    sections_json = os.path.join(work, "sections.json")
    script_txt = os.path.join(work, "script_lines.txt")
    source_txt = os.path.join(work, "narration_source.txt")
    check_json = os.path.join(work, "readcheck.json")
    final = os.path.join(a.out_dir, f"{safe_filename(title)} (final).mp3")
    report = os.path.join(work, "pauses.csv")

    # the title-stripped script every stage works from, so generation and the
    # alignment used for mastering can never disagree about what was spoken
    open(source_txt, "w", encoding="utf-8").write(raw)
    open(script_txt, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    sections = mark_title_section(build_sections(raw, a.skip_headings, a.max_chunk), title)
    log(f"“{title}” · {len(sections)} sections · "
        f"{sum(s['chars'] for s in sections)} chars")
    if guide:
        guide_path = os.path.join(work, "pronunciation_guide.json")
        json.dump({"words": guide}, open(guide_path, "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
        log(f"pronunciation guide: {len(guide)} names, held out of the narration "
            f"({', '.join(list(guide)[:5])}{'…' if len(guide) > 5 else ''})")

    if a.plan:
        show_plan(title, raw, guide, sections, prof, a.skip_headings, prof["api_key"])
        return 0

    start = STAGES.index(a.start)
    here = os.path.dirname(os.path.abspath(__file__))

    # ---------------------------------------------------------- 1. generate
    gen_cmd = [sys.executable, os.path.join(here, "generate.py"),
               "--script", source_txt, "--out", raw_vo, "--parts-dir", parts_dir,
               "--sections-json", sections_json, "--max-chunk", str(a.max_chunk)]
    if a.profile:
        gen_cmd += ["--profile", a.profile]
    if a.skip_headings:
        gen_cmd += ["--skip-headings"]
    if a.chapter_pause:
        gen_cmd += ["--chapter-pause", a.chapter_pause]
    if a.lexicon:
        gen_cmd += ["--lexicon", a.lexicon]

    if start <= STAGES.index("generate"):
        run_stage(gen_cmd)
    elif not os.path.isfile(sections_json):
        raise SystemExit(f"--from {a.start} needs an earlier run's {sections_json}")

    # ---------------------------------------------------------- 2. read-check
    if start <= STAGES.index("check"):
        man = json.load(open(sections_json, encoding="utf-8"))
        seen_subs, settled = {}, {}
        for rnd in range(a.max_redos + 1):
            results = rc.check_sections(man["sections"], parts_dir, a.asr_model)
            for r in rc.settle_repeats(results, seen_subs):
                settled[r["index"]] = r["settled"]
            bad = rc.report(results)
            json.dump({"results": results, "asr_model": a.asr_model, "round": rnd},
                      open(check_json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            if not bad:
                log(f"read-check clean after {rnd} redo round(s)")
                break
            if rnd == a.max_redos:
                log(f"{len(bad)} section(s) still flagged after {a.max_redos} redo rounds — "
                    "listen to these before publishing: " +
                    ", ".join(str(r['index'] + 1) for r in bad))
                break

        # sections that stopped being re-rendered because the render is consistent
        # still need an ear, so they are named rather than quietly passing
        if settled:
            log("consistent across takes, worth a listen: " + "; ".join(
                f"section {i+1} " + ", ".join(f"“{e}”→“{g}”" for e, g in pairs)
                for i, pairs in sorted(settled.items())))
            log(f"if any of those are real mispronunciations, seed the lexicon:\n"
                f"    python3 {os.path.join(here, 'pronounce.py')} "
                f"--from-check {check_json}")
            # A plain re-roll fixes a one-off misread. Hesitation is systematic, and
            # the studio's lever for it is a small stability rise — so later rounds
            # nudge rather than rolling the same dice again.
            redo = gen_cmd + ["--regen", ",".join(str(r["index"] + 1) for r in bad)]
            if rnd >= 1:
                nudged = min(1.0, prof["settings"]["stability"] + 0.05 * rnd)
                log(f"round {rnd+1}: nudging stability to {nudged:.2f}")
                redo += ["--stability", f"{nudged:.3f}"]
            else:
                log(f"re-rendering {len(bad)} flagged section(s), round {rnd+1}")
            run_stage(redo)

    if a.no_master:
        log(f"stopping before master; raw stitch at {raw_vo}")
        return 0

    # ---------------------------------------------------------- 3. master
    hum = find_humanize(a.humanize)
    mcmd = [sys.executable, hum, "--audio", raw_vo, "--script", script_txt,
            "--out", final, "--report", report,
            "--align-cache", os.path.join(work, "align.json")]
    if a.curated:
        mcmd += ["--curated", a.curated]
    if a.max_wpm:
        mcmd += ["--max-wpm", str(a.max_wpm)]
        log(f"levelling sentences above {a.max_wpm:.0f} wpm "
            "(off by default — this changes the approved sound)")
    run_stage(mcmd)

    if not os.path.isfile(final):
        raise SystemExit("mastering produced no file")
    log(f"delivered {final} ({os.path.getsize(final)/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
