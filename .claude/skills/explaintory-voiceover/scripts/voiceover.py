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
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as gen  # noqa: E402
import readcheck as rc  # noqa: E402
from script_prep import (_META_LABELS, build_sections, detect_structure,  # noqa: E402
                         guide_preflight, master_script_lines, note_wants_runon,
                         split_pronunciation_guide, split_read_note)

CHARS_PER_SEC = 14      # the studio's narration-pace constant, for the estimate

STAGES = ["generate", "check", "master"]

HERE = os.path.dirname(os.path.abspath(__file__))

# Where explaintory-vo-master keeps humanize.py. It is a separate skill; this one
# drives it rather than duplicating its 560 lines of measured settings.
#
# Everything here resolves against THIS FILE, never the cwd. An earlier list ended
# in "./.claude/skills/..." which only works when the pipeline is run from the
# repository root — while the pipeline's own design (--out-dir, --work) pushes the
# run into a scratch directory, where that entry resolves to nothing. The failure
# then landed at the very end of the run, after generation had been paid for and
# the read-check had spent ten minutes.
HUMANIZE_REL = os.path.join("explaintory-vo-master", "scripts", "humanize.py")

# The installed copy is not always where the skill name suggests: on this machine it
# sits under .../skills/synced/explaintory-vo-master/..., which no fixed path
# anticipated. So the skills roots are globbed rather than guessed.

# torchaudio's MMS_FA alignment checkpoint, downloaded by humanize.py on its first
# run. Named here so a poisoned cache can be verified and cleared from the error
# path — see readcheck.purge_cached_model for why that is not optional.
MMS_FA_CHECKPOINT = os.path.expanduser("~/.cache/torch/hub/checkpoints/model.pt")
MMS_FA_BYTES = 1_262_047_414          # measured against the upstream content-length


def log(m):
    print(f"[voiceover] {m}", flush=True)


def _skills_roots():
    """Every plausible skills directory, resolved from this script and from $HOME.

    The parent walk is what makes a checkout work from any cwd: this file lives at
    <root>/.claude/skills/explaintory-voiceover/scripts/, so its sibling skill is
    somewhere above it no matter where the run was launched from.
    """
    roots, d = [], HERE
    while True:
        if os.path.basename(d) == "skills":
            roots.append(d)                       # this script's own skills root
        parent = os.path.dirname(d)
        if parent == d:
            break
        roots.append(os.path.join(d, ".claude", "skills"))
        d = parent
    roots += [os.path.expanduser("~/.claude/skills"), "/root/.claude/skills"]
    seen, out = set(), []
    for r in roots:
        r = os.path.abspath(os.path.expanduser(r))
        if r not in seen and os.path.isdir(r):
            seen.add(r)
            out.append(r)
    return out


def find_humanize(override=None, quiet=False):
    """-> path to explaintory-vo-master's humanize.py. Raises if it cannot be found."""
    if override:
        p = os.path.abspath(os.path.expanduser(override))
        if os.path.isfile(p):
            return p
        raise SystemExit(f"--humanize {override} is not a file")

    roots = _skills_roots()
    for root in roots:                       # the common, shallow layout first
        p = os.path.join(root, HUMANIZE_REL)
        if os.path.isfile(p):
            return p
    for root in roots:                       # then anything nested (synced/, vendor/…)
        hits = sorted(glob.glob(os.path.join(root, "**", HUMANIZE_REL), recursive=True))
        if hits:
            if len(hits) > 1 and not quiet:
                log(f"note: {len(hits)} copies of humanize.py found; using {hits[0]}")
            return hits[0]

    raise SystemExit(
        "Could not find humanize.py from the explaintory-vo-master skill.\n"
        "Looked for */" + HUMANIZE_REL + " under:\n  "
        + "\n  ".join(roots or ["(no skills directory found at all)"])
        + "\nPass --humanize /path/to/humanize.py, or install that skill.")


def safe_filename(s):
    s = re.sub(r"[^\w\-. ]+", "", (s or "").strip())
    return re.sub(r"\s+", " ", s)[:80] or "Voiceover"


def derive_title(script_path, raw, explicit=None, read_title=True):
    """-> (title, script for narration).

    The H1 names the file either way. Whether it is also SPOKEN is the profile's
    `readTitle`, not this tool's opinion.

    This docstring used to add "the studio reads it by default and that is the
    read Sapro has been publishing". That was false, and it was written by the
    agent rather than by him. 2026-08-18: "remove the video title from the
    voiceover that's not allowed in the voiceover."

    Note how it survived. `readTitle` was never chosen by anyone — it was an
    inherited default, and the --plan gate said so on EVERY run, in its own
    dedicated line: "1 value(s) nobody chose — inherited defaults, not settings:
    read_title". The gate worked. It was read past, because this docstring
    asserted the default was already correct and the assertion was taken as
    evidence. A comment is not a measurement, and provenance marks exist to be
    acted on, not skimmed.

    `readTitle` is false in voice-calibration.json now, so the narration opens on
    the first chapter name.
    """
    def clean(t):
        # "EVERY DRUG USED IN WAR EXPLAINED — VOICEOVER SCRIPT" names the document,
        # not the video. The suffix would be read aloud and would name the file.
        t = re.sub(r"\s*[—–\-|:]\s*(voice\s*over|voiceover|vo)\s*script\s*$", "", t, flags=re.I)
        t = re.sub(r"\s*[—–\-|:]\s*(script|draft|final|v\d+(\.\d+)?)\s*$", "", t, flags=re.I)
        return t.strip()

    lines = raw.split("\n")
    for i, line in enumerate(lines[:12]):
        s = line.strip()
        m = (re.match(r"^#\s+(.{2,80})$", s)
             or re.match(r"^title\s*[:\-]\s*(.{2,80})$", s, re.I))
        if m and re.fullmatch(r"[\s*_#]*" + _META_LABELS + r"[\s*_:.]*", s, re.I):
            # '# Script' labels the document; it is not the video's title and there
            # is nothing here to narrate. The title then comes from --title or the
            # filename, and names the file only.
            continue
        if m:
            found = clean(m.group(1).strip())
            shown = (explicit.strip() if explicit else found)
            if read_title:
                out = list(lines)
                out[i] = "# " + shown       # narrate the title, not the document name
                body = "\n".join(out)
            else:
                body = "\n".join(lines[:i] + lines[i + 1:])
            return shown, body
    if explicit:
        return explicit.strip(), raw
    stem = os.path.splitext(os.path.basename(script_path))[0]
    return clean(re.sub(r"[_\-]+", " ", stem).strip().title()), raw


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
                # Walk the LEFT edge back off its own punctuation before testing it.
                #
                # When a fronted modifier's subtree ends on its comma — "The better a
                # submariner aimed, ‖ the more likely…" — last.text is "," and nxt is
                # an ordinary word, so the "already punctuated" guard below passed and
                # a ",|the" pair was emitted for a clause that is already punctuated.
                # It cannot match anything downstream, and it is noise in a list whose
                # whole purpose is to be short enough to read by hand. Both edges of a
                # boundary have to be tested, not just the one the bug showed up on.
                while last.is_punct and last.i > sub[0].i:
                    last = doc[last.i - 1]
                if last.is_punct:
                    continue                        # the whole subtree was punctuation
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


def _pack(pairs, width=76, indent="  "):
    """Lay 'name value (source)' fragments out over as few lines as fit."""
    lines, cur = [], ""
    for frag in pairs:
        cand = frag if not cur else cur + " · " + frag
        if len(cand) > width - len(indent) and cur:
            lines.append(indent + cur)
            cur = frag
        else:
            cur = cand
    if cur:
        lines.append(indent + cur)
    return lines


def show_plan(title, raw, guide, sections, prof, skip_headings, api_key=None,
              note=None, runon=False, overrides=None, warnings=None,
              max_redos=0, auto_redo=False, humanize=None):
    """What the studio's structure panel and estimator show, before a credit is spent.

    Generation is the irreversible part of this pipeline — the read-check and the
    master can be re-run for free, but characters sent are characters billed. So
    the same numbers Sapro checks in the browser get printed here, and the run
    stops until he has seen them.

    It prints EVERY value it is about to commit, each marked with where it came
    from. It used to print voice · model · stability · style · speed, which left
    out similarity_boost and use_speaker_boost — precisely the two values
    load_profile fills in from DEFAULT_SETTINGS when the profile omits them. So the
    one setting that was wrong (0.75 inherited, 0.80 locked in) was the one setting
    the gate could not show, and it was caught only because Sapro knows his own
    numbers and said "you missed similarity 80%". A gate that shows a subset of the
    state cannot be trusted with the rest of it, and the omitted values are the
    highest-risk ones by construction: an explicit value has been thought about at
    least once, an inherited default never has.
    """
    st = detect_structure(raw)
    chars = sum(s["chars"] for s in sections)
    # in run-on mode the name is merged into its section, so it is no longer a
    # heading section — the chapter list has to come from the structure, not the
    # sections, or the confirmation screen would show none at all
    want = title.strip().rstrip(".").lower()
    st_chapters = [h for h in st["headings"]
                   if h.strip().rstrip(".").lower() != want]
    mins, secs_ = divmod(int(chars / CHARS_PER_SEC), 60)
    heads = [s for s in sections if s["is_heading"]]
    titled = (any(s.get("is_title") for s in sections)
              or any(want == s["send_text"].strip().rstrip(".").lower()
                     for s in sections if s["is_heading"])
              or (not skip_headings and len(st["headings"]) > len(st_chapters)))
    chapters = chapter_names(sections) or st_chapters

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
    if note:
        print(f"  READ NOTE: {len(note)} lines held out of the narration")
        print(f"  chapter style: {'RUN-ON — name leads the first sentence, no beat' if runon else 'announce — a beat around the name'}")
    elif runon:
        print("  chapter style: RUN-ON — name leads the first sentence, no beat")

    # Everything the script's own answer key says is wrong with the script. Free,
    # and the only place an export artifact that leaves the text well-formed can be
    # caught — every downstream check compares against the same corrupted source.
    if warnings:
        print(f"\n  PRE-FLIGHT — {len(warnings)} thing(s) to look at before spending:")
        for w in warnings:
            print(f"    ! {w}")

    spoken_heads = len(chapters)
    print(f"\n  {len(sections)} sections ({spoken_heads} chapter announcements"
          f"{' + the title' if titled else ''})"
          f" · {chars:,} chars · ~{mins}:{secs_:02d} audio")

    # ---- the full effective calibration, every value marked with its provenance
    src = dict(prof.get("source") or {})
    src.update(overrides or {})

    def p(key, label, value):
        where = src.get(key, "default")
        return f"{label} {value} ({where})"

    s = prof["settings"]
    print("\n  CALIBRATION — every value that will be sent, and who chose it:")
    for line in _pack([p("voice_id", "voice", prof["voice_id"] or "MISSING"),
                       p("model", "model", prof["model"])]):
        print(line)
    for line in _pack([p("stability", "stability", s["stability"]),
                       p("similarity_boost", "similarity_boost", s["similarity_boost"]),
                       p("style", "style", s["style"]),
                       p("speed", "speed", s["speed"]),
                       p("use_speaker_boost", "use_speaker_boost", s["use_speaker_boost"])]):
        print(line)
    for line in _pack([p("chunk_size", "chunkSize", prof["chunk_size"] or 450),
                       p("chapter_pause", "chapterPause", prof["chapter_pause"]),
                       p("collapse_breaks", "collapseBreaks", prof["collapse_breaks"]),
                       p("read_title", "readTitle", prof["read_title"]),
                       p("skip_headings", "skipHeadings", skip_headings)]):
        print(line)
    inherited = [k for k in ("stability", "similarity_boost", "style", "speed",
                             "use_speaker_boost", "chunk_size", "chapter_pause",
                             "collapse_breaks", "read_title", "skip_headings")
                 if src.get(k, "default") == "default"]
    if inherited:
        print(f"  ^ {len(inherited)} value(s) nobody chose — inherited defaults, not "
              f"settings: {', '.join(inherited)}")

    # ---- cost, first pass AND worst case. The number at the gate has to be the
    # ceiling for the whole run, not the cost of the first of several calls.
    print(f"\n  COST: ~{chars:,} credits (first pass)", end="")
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
    rounds = max_redos if auto_redo else 0
    worst = chars * (1 + rounds)
    if rounds:
        print(f"  redo rounds: up to {rounds}, AUTOMATIC (--auto-redo)")
        print(f"  WORST CASE this run: ~{worst:,} credits "
              f"({1 + rounds} x every section). --approve-spend is spent down across "
              f"every render, so this is a ceiling, not a per-call allowance.")
    else:
        print(f"  redo rounds: off (--max-redos {max_redos}"
              + ("; --auto-redo not given" if max_redos else "")
              + ") — flagged sections are reported, not re-rendered")
        print(f"  WORST CASE this run: ~{worst:,} credits")
    if humanize:
        print(f"  master: {humanize}")
    print()


def run_stage(cmd, ok=(0,)):
    """Run a stage and hold it to its exit code.

    `ok` used to include 1, which is the exit code humanize.py and generate.py both
    use to ABORT — a corrupt alignment checkpoint, a budget stop. Treating that as
    success is how a run that produced nothing carried on and then reported itself
    finished. A stage that means "done, with findings" has to say so by being passed
    an explicit `ok`; the default is that only zero is success.
    """
    log("$ " + " ".join(str(c) for c in cmd))
    p = subprocess.run(cmd)
    if p.returncode not in ok:
        raise SystemExit(f"stage failed with exit {p.returncode}: "
                         f"{os.path.basename(str(cmd[1]) if len(cmd) > 1 else cmd[0])}")
    return p.returncode


def assert_artifact(path, what, min_seconds=1.0):
    """Prove a stage's output exists before anything reports success.

    The diagnosis in the log is for humans; the exit code is for everything else —
    the shell, the background-task harness, CI. A stage that detects its own failure
    and still exits 0 converts a loud failure into a silent one, and it is worse than
    an uncaught crash, because a crash is at least self-reporting. So: the file
    exists, it is not empty, and it is long enough to be the thing that was asked for.
    """
    if not os.path.isfile(path):
        raise SystemExit(f"{what} produced no file — expected {path}")
    size = os.path.getsize(path)
    if size == 0:
        raise SystemExit(f"{what} produced an EMPTY file at {path}")
    try:
        dur = rc.probe_duration(path)
    except Exception as e:
        log(f"WARNING: could not probe {path} ({e}) — duration unverified")
        return None
    if dur <= 0:
        raise SystemExit(
            f"{what} wrote {path} ({size:,} bytes) but it has no readable duration — "
            f"it is not decodable audio")
    if dur < min_seconds:
        raise SystemExit(
            f"{what} wrote {path} but it is only {dur:.2f}s long — truncated")
    return dur


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
    ap.add_argument("--chapter-style", choices=["announce", "run-on"],
                    help="announce = a beat around the chapter name (profile default); "
                         "run-on = the name leads the first sentence in the same "
                         "request, no inserted silence. Auto-read from the script's "
                         "READ NOTE when not given.")
    ap.add_argument("--asr-model", default=rc.DEFAULT_ASR)
    ap.add_argument("--approval", default="",
                    help="Sapro's own words approving this send. Required for any "
                         "generation; an earlier approval does not carry forward.")
    ap.add_argument("--approve-spend", type=int, default=0,
                    help="characters this RUN is allowed to send, across every "
                         "render including redos. Default ceiling is 2000; a full "
                         "render needs this set to the plan's worst-case cost.")
    ap.add_argument("--max-redos", type=int, default=None,
                    help="rounds of re-rendering flagged sections before giving up. "
                         "Default 0: flagged sections are reported with their ASR "
                         "evidence and the cost of re-rendering them, and nothing is "
                         "spent. --auto-redo raises the default to 2.")
    ap.add_argument("--auto-redo", action="store_true",
                    help="re-render flagged sections without asking. OFF by default: "
                         "the gate before generation is consent for one quantity of "
                         "characters, not for every later render the pipeline decides "
                         "to do. Spends from the same --approve-spend ceiling.")
    ap.add_argument("--from", dest="start", choices=STAGES, default="generate")
    ap.add_argument("--humanize", help="path to humanize.py")
    ap.add_argument("--max-wpm", type=float, default=0.0,
                    help="slow only sentences faster than this, in the master. 290 = "
                         "faster than the human reference ever goes, so it catches only "
                         "broken sentences; 250 is the human's p90 and will also slow "
                         "real punchlines. 0 (default) = off, the approved sound.")
    ap.add_argument("--no-master", action="store_true", help="stop after the read-check")
    ap.add_argument("--keep-glitches", action="store_true",
                    help="pass through to humanize.py: skip splice-fragment "
                         "removal. Use when the delivery gate reports the master "
                         "ate a word — a short word fenced by pauses looks exactly "
                         "like a fragment to a detector with no level guard.")
    ap.add_argument("--no-gate", action="store_true",
                    help="skip the post-master word-loss gate. Do not use for a "
                         "real delivery; it exists for pipeline debugging only.")
    ap.add_argument("--suggest-breaks", action="store_true",
                    help="print candidate clause breaks and exit — read them, keep the real ones")
    ap.add_argument("--plan", action="store_true",
                    help="show the structure and the credit cost, then stop. Run this "
                         "first and let Sapro confirm before spending anything.")
    a = ap.parse_args()

    # Approval is granted for a quantity, not for a category: the redo loop can
    # invoke the generator again, so it does not get to do that unasked.
    #
    # --max-redos is how many rounds are ALLOWED; --auto-redo is permission to use
    # them without asking. Without that permission the count is zero whatever was
    # passed, because the confirmation collected before generation was consent for
    # one quantity of characters, not for every later render the pipeline chooses.
    auto_redo = a.auto_redo
    max_redos = a.max_redos if a.max_redos is not None else (2 if auto_redo else 0)
    redo_rounds = max_redos if auto_redo else 0

    # the studio's locked-in calibration supplies the defaults; explicit flags win
    prof = gen.load_profile(a.profile)
    overrides = {}                      # key -> "flag", for the plan's provenance
    if a.skip_headings is None:
        a.skip_headings = prof["skip_headings"]
    else:
        overrides["skip_headings"] = "flag"
    if a.max_chunk is None:
        a.max_chunk = prof["chunk_size"] or 450
    else:
        overrides["chunk_size"] = "flag"
    if a.chapter_pause:
        overrides["chapter_pause"] = "flag"

    title, raw = derive_title(a.script, open(a.script, encoding="utf-8").read(),
                              a.title, prof["read_title"])
    # the guide at the foot of the script is a note to the reader, never a line to
    # read — and it is this video's answer key for how each name should sound
    raw, guide = split_pronunciation_guide(raw)
    raw, note = split_read_note(raw)
    # The profile decides the chapter style. A note inside a script is writing
    # direction, not configuration, and reading it as configuration is how a
    # screenshot shown for an opinion turned into a silent override of
    # chapterPause: natural — the sound that was already signed off. If a note
    # asks for something else, say so and let Sapro choose; never switch quietly.
    runon = a.chapter_style == "run-on"
    if not a.chapter_style and note_wants_runon(note):
        log("NOTE: this script's read note asks for no pause after the chapter "
            "name. Following the profile (announce) anyway — pass "
            "--chapter-style run-on if you want the note's version.")
    lines = master_script_lines(raw, a.skip_headings, runon)

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
    sections = mark_title_section(
        build_sections(raw, a.skip_headings, a.max_chunk, runon), title)
    log(f"“{title}” · {len(sections)} sections · "
        f"{sum(s['chars'] for s in sections)} chars")
    if guide:
        guide_path = os.path.join(work, "pronunciation_guide.json")
        json.dump({"words": guide}, open(guide_path, "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
        log(f"pronunciation guide: {len(guide)} names, held out of the narration "
            f"({', '.join(list(guide)[:5])}{'…' if len(guide) > 5 else ''})")

    # Check the script against its own answer key before anything is spent. A
    # ". 303" that the Docs export made out of ".303" is well-formed text, so it is
    # invisible to the read-check — which diffs the ASR against this same script and
    # finds agreement — and it changes what the voice says.
    warnings = guide_preflight(raw, guide)

    # Every prerequisite of a multi-stage run, validated UP FRONT. The master stage
    # used to look for humanize.py only when it got there, which is after generation
    # has been paid for and the read-check has spent ten minutes.
    hum = None
    if not a.no_master:
        try:
            hum = find_humanize(a.humanize, quiet=a.plan)
        except SystemExit as e:
            if not a.plan:
                raise
            warnings.append(str(e).replace("\n", " "))
        if hum:
            ok, why = rc.verify_torch_checkpoint(MMS_FA_CHECKPOINT, MMS_FA_BYTES)
            if not ok:
                # A cache with no integrity check turns one bad transfer into a
                # permanent failure, and the retry provably cannot succeed while the
                # poisoned file is still there. Clear it now, before the run.
                log(f"cached MMS_FA alignment checkpoint is damaged: {why}")
                log(rc.purge_cached_model(MMS_FA_CHECKPOINT, why))

    if a.plan:
        show_plan(title, raw, guide, sections, prof, a.skip_headings,
                  prof["api_key"], note, runon, overrides=overrides,
                  warnings=warnings, max_redos=max_redos, auto_redo=auto_redo,
                  humanize=hum)
        return 0

    for w in warnings:
        log("PRE-FLIGHT ! " + w)

    start = STAGES.index(a.start)
    here = HERE

    # ---------------------------------------------------------- 1. generate
    # The ledger is the run's budget, not this call's. Every generate.py invocation
    # in this work dir — the first pass and every redo round — debits the same file,
    # so --approve-spend is a ceiling for the run instead of a fresh allowance handed
    # out again on each round.
    spend_log = os.path.join(work, "spend.json")
    gen_cmd = [sys.executable, os.path.join(here, "generate.py"),
               "--script", source_txt, "--out", raw_vo, "--parts-dir", parts_dir,
               "--sections-json", sections_json, "--max-chunk", str(a.max_chunk),
               "--spend-log", spend_log]
    if a.profile:
        gen_cmd += ["--profile", a.profile]
    if a.skip_headings:
        gen_cmd += ["--skip-headings"]
    if a.chapter_pause:
        gen_cmd += ["--chapter-pause", a.chapter_pause]
    if a.lexicon:
        gen_cmd += ["--lexicon", a.lexicon]
    if a.approve_spend:
        gen_cmd += ["--approve-spend", str(a.approve_spend)]
    # Sapro's approval has to reach generate.py, which is where the gate lives.
    # Without this passthrough the pipeline cannot send anything at all — which is
    # the safe direction to fail, but it also means the gate was unreachable from
    # the top-level tool until now.
    if a.approval:
        gen_cmd += ["--approval", a.approval]
    if runon:
        gen_cmd += ["--run-on"]

    def spent():
        return max(0, gen.spend_so_far(spend_log))

    if start <= STAGES.index("generate"):
        run_stage(gen_cmd)
        # The stitch is an artifact, so its existence is asserted rather than assumed.
        assert_artifact(raw_vo, "generate (stitch)")
    elif not os.path.isfile(sections_json):
        raise SystemExit(f"--from {a.start} needs an earlier run's {sections_json}")

    # ---------------------------------------------------------- 2. read-check
    if start <= STAGES.index("check"):
        man = json.load(open(sections_json, encoding="utf-8"))
        by_index = {s["index"]: s for s in man["sections"]}
        seen_subs, settled = {}, {}
        for rnd in range(redo_rounds + 1):
            results = rc.check_sections(man["sections"], parts_dir, a.asr_model, guide)
            for r in rc.settle_repeats(results, seen_subs):
                settled[r["index"]] = r["settled"]
            bad = rc.report(results)
            json.dump({"results": results, "asr_model": a.asr_model, "round": rnd},
                      open(check_json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            if not bad:
                log(f"read-check clean after {rnd} redo round(s)")
                break

            cost = sum(by_index.get(r["index"], {}).get("chars", 0) for r in bad)
            names = ", ".join(str(r["index"] + 1) for r in bad)
            if rnd == redo_rounds:
                if redo_rounds:
                    log(f"{len(bad)} section(s) still flagged after {redo_rounds} redo "
                        f"rounds — listen to these before publishing: {names}")
                else:
                    # Re-rendering spends money AFTER the gate, so it gets its own
                    # gate. The evidence and the price are printed, and the command
                    # that would do it is handed over rather than run.
                    log(f"{len(bad)} section(s) flagged: {names}")
                    log(f"NOT re-rendering — that would send ~{cost:,} more characters "
                        f"and this run has spent {spent():,} so far. The read-check "
                        f"evidence for each is above and in {check_json}."
                        + (f" (--max-redos {max_redos} was given, but --auto-redo "
                           f"was not.)" if max_redos else ""))
                    log("To re-render them, approve the spend explicitly:\n"
                        f"    python3 {os.path.join(here, 'voiceover.py')} "
                        f"--script {a.script} --work {work} --from check "
                        f"--auto-redo --max-redos 1 "
                        f"--approve-spend {spent() + cost}")
                break

            # A plain re-roll fixes a one-off misread. Hesitation is systematic, and
            # the studio's lever for it is a small stability rise — so later rounds
            # nudge rather than rolling the same dice again.
            redo = gen_cmd + ["--regen", ",".join(str(r["index"] + 1) for r in bad)]
            if rnd >= 1:
                nudged = min(1.0, prof["settings"]["stability"] + 0.05 * rnd)
                log(f"round {rnd+1}: nudging stability to {nudged:.2f}")
                redo += ["--stability", f"{nudged:.3f}"]
            else:
                log(f"re-rendering {len(bad)} flagged section(s) (~{cost:,} chars), "
                    f"round {rnd+1}; {spent():,} chars spent so far this run")
            run_stage(redo)
            # a redo re-stitches, so the artifact has to hold up again
            assert_artifact(raw_vo, "generate (re-stitch)")

        # sections that stopped being re-rendered because the render is consistent
        # still need an ear, so they are named rather than quietly passing
        if settled:
            log("consistent across takes, worth a listen: " + "; ".join(
                f"section {i+1} " + ", ".join(f"“{e}”→“{g}”" for e, g in pairs)
                for i, pairs in sorted(settled.items())))
            log(f"if any of those are real mispronunciations, seed the lexicon:\n"
                f"    python3 {os.path.join(here, 'pronounce.py')} "
                f"--from-check {check_json}")

    if a.no_master:
        log(f"stopping before master; raw stitch at {raw_vo}")
        return 0

    # ---------------------------------------------------------- 3. master
    hum = hum or find_humanize(a.humanize)     # resolved at startup; re-checked here
    assert_artifact(raw_vo, "the stitch this run is about to master")
    mcmd = [sys.executable, hum, "--audio", raw_vo, "--script", script_txt,
            "--out", final, "--report", report,
            "--align-cache", os.path.join(work, "align.json")]
    if a.curated:
        mcmd += ["--curated", a.curated]
    if a.keep_glitches:
        mcmd += ["--keep-glitches"]
    if a.max_wpm:
        mcmd += ["--max-wpm", str(a.max_wpm)]
        log(f"levelling sentences above {a.max_wpm:.0f} wpm "
            "(off by default — this changes the approved sound)")
    try:
        run_stage(mcmd)
    except SystemExit:
        # humanize.py's first failure here was a truncated MMS_FA checkpoint, whose
        # error message ("your checkpoint file is corrupted") points at the server
        # rather than at the transfer. Leaving the bad file cached makes the obvious
        # recovery — run it again — provably useless, so it goes now.
        ok, why = rc.verify_torch_checkpoint(MMS_FA_CHECKPOINT, MMS_FA_BYTES)
        if not ok:
            log(f"the cached MMS_FA alignment checkpoint is damaged: {why}")
            log(rc.purge_cached_model(MMS_FA_CHECKPOINT, why))
            log("re-run with --from master; the checkpoint will be fetched again")
        raise

    # The master's artifact is the deliverable, so nothing reports success until it
    # is on disk and is real audio. A stage that diagnoses its own failure in prose
    # and still exits 0 turns a loud failure into a silent one — every layer above
    # (the shell, the background-task harness, CI) reads the exit code, not the log.
    dur = assert_artifact(final, "mastering", min_seconds=5.0)

    # THE LAST GATE. The master is a DESTRUCTIVE edit — it declips, it removes
    # what it judges to be splice fragments, it stretches and it inserts pauses —
    # and it was the only destructive edit in this pipeline exempt from rule 7
    # ("transcribe after every destructive edit and confirm no words were lost").
    # The read-check runs on the section takes BEFORE mastering, and the QC pass
    # measures levels rather than words, so a file could pass every gate here with
    # a word cut out of the middle of a sentence. One was: `fix_glitches()` took
    # 165 ms at -8.2 dB out of "pack them tight" and delivered "pick them tight".
    # Sapro caught it by ear, which is exactly what this pipeline exists to stop.
    # So the gate runs on every delivery, and a failure is fatal rather than a
    # warning — a warning is a thing that gets read after the file has been sent.
    if not a.no_gate:
        log("verifying the master changed no words (delivery gate)")
        rc_gate = subprocess.call([sys.executable,
                                   os.path.join(HERE, "delivery_gate.py"),
                                   "--raw", raw_vo, "--delivered", final,
                                   "--script", os.path.join(work, "script_lines.txt"),
                                   "--asr-model", a.asr_model])
        if rc_gate != 0:
            log("DELIVERY BLOCKED — mastering altered the read. "
                "Re-master with --keep-glitches and run again.")
            return rc_gate

    log(f"delivered {final} ({os.path.getsize(final)/1e6:.1f} MB"
        + (f", {int(dur)//60}:{int(dur)%60:02d}" if dur else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
