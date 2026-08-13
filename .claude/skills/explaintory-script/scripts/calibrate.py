#!/usr/bin/env python3
"""
Derive the script profile from real published scripts, instead of guessing it.

Point this at a folder of finished ExplainTory scripts and it measures them,
then writes the numbers into script_profile.json. Every value it sets is a
measurement of work that already went out; nothing is invented.

It also answers a question that is otherwise pure speculation: WHICH decisions
actually change between videos. For each measured quantity it reports the
coefficient of variation across the corpus and calls it:

    CONSTANT   cv < 0.10   -- lock it in the profile, never ask again
    VARIES     cv > 0.25   -- this belongs in the per-video spec gate
    (between)  drifting    -- lock it, but show it at the gate so it can be
                              overridden when a title needs it

That classification is the useful output. A writer generally cannot say from
memory whether their videos are all the same length; the files know.

Usage:

    calibrate.py scripts/                     # report only, changes nothing
    calibrate.py scripts/ --write             # update script_profile.json
    calibrate.py scripts/ --write --out p.json

Only fields that measurement can actually support are written. Taste --
banned phrases, hook rules, voice -- is left exactly as it is, because a
corpus of good scripts cannot tell you what a bad one would have contained.
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import (  # noqa: E402
    CHARS_PER_SEC, WPM, load_profile, parse_draft, proper_nouns, sentences, wc)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE = os.path.join(HERE, "..", "script_profile.json")

SCRIPT_GLOBS = ("*.txt", "*.md", "*.markdown")


def collect(paths):
    files = []
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for g in SCRIPT_GLOBS:
                files.extend(sorted(glob.glob(os.path.join(p, "**", g), recursive=True)))
        elif os.path.isfile(p):
            files.append(p)
    # A research file or a README sitting in the same folder is not a script and
    # would drag every median toward nonsense. Anything too short to be a video
    # is dropped, and the drop is reported rather than done quietly.
    return sorted(set(files))


def measure_one(path, profile):
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    p = parse_draft(raw, profile)
    narration = p["narration"]
    total_words = wc(narration)
    if total_words < 300:
        return None

    sents = sentences(narration)
    slens = [wc(s) for s in sents] or [0]
    ch_words = [c["words"] for c in p["chapters"]] or [0]
    n_num = len(re.findall(r"\b\d[\d,.]*\b", narration))
    n_prop = len(proper_nouns(narration))

    return {
        "file": os.path.basename(path),
        "words": total_words,
        "chars": len(narration),
        "runtime_min": round(total_words / profile["length"].get("wpm", WPM), 2),
        # Observation only, never a length target. Recorded so that if real
        # published runtimes are supplied later, the true wpm and the true
        # chars-per-second can both be solved for instead of assumed.
        "chars_per_word": len(narration) / max(total_words, 1),
        "chapters": len(p["chapters"]),
        "chapter_title_words": (statistics.mean(len(c["title"].split())
                                                for c in p["chapters"])
                                if p["chapters"] else 0),
        "chapter_title_max": (max(len(c["title"].split()) for c in p["chapters"])
                              if p["chapters"] else 0),
        "chapter_words_mean": statistics.mean(ch_words),
        "chapter_spread_pct": ((max(ch_words) - min(ch_words)) / statistics.mean(ch_words) * 100
                               if len(ch_words) > 1 and statistics.mean(ch_words) else 0),
        "hook_words": wc(p["hook"]),
        "sentence_stdev": statistics.pstdev(slens) if len(slens) > 1 else 0,
        "sentence_mean": statistics.mean(slens),
        "sentence_max": max(slens),
        "fact_density": (n_num + n_prop) / max(total_words, 1) * 100,
        "guide_entries": len(p["guide"] or {}),
        "has_title": bool(p["title"]),
    }


def cv(values):
    """Coefficient of variation. The one number that says 'this varies'."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    m = statistics.mean(vals)
    return (statistics.pstdev(vals) / m) if m else None


def classify(c):
    if c is None:
        return "single-sample"
    if c < 0.10:
        return "CONSTANT"
    if c > 0.25:
        return "VARIES"
    return "drifting"


# Percentile floors, not means. A floor set at the corpus mean fails half of
# the writer's own published work, which teaches them to ignore the gate. p20
# says "at least as good as your weaker fifth", which is a bar a real script
# clears while still catching prose that fell off a cliff.
def p20(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    return vals[max(0, int(len(vals) * 0.20) - (1 if len(vals) > 4 else 0))]


FIELDS = [
    ("runtime_min", "runtime (min)", "{:.1f}"),
    ("words", "words", "{:.0f}"),
    ("chapters", "chapters", "{:.1f}"),
    ("chapter_title_words", "chapter title words", "{:.1f}"),
    ("chapter_words_mean", "words per chapter", "{:.0f}"),
    ("chapter_spread_pct", "chapter spread %", "{:.0f}"),
    ("hook_words", "hook words", "{:.0f}"),
    ("sentence_stdev", "sentence len stdev", "{:.1f}"),
    ("sentence_mean", "sentence len mean", "{:.1f}"),
    ("fact_density", "facts / 100 words", "{:.1f}"),
    ("guide_entries", "pronunciation entries", "{:.0f}"),
    ("chars_per_word", "chars per word", "{:.2f}"),
]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="script files or folders")
    ap.add_argument("--write", action="store_true", help="update the profile")
    ap.add_argument("--out", help="profile to write (default: the skill's own)")
    ap.add_argument("--profile", help="profile to read defaults from")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    profile = load_profile(a.profile)
    files = collect(a.paths)
    if not files:
        raise SystemExit("No .txt/.md files found in those paths.")

    rows, skipped = [], []
    for f in files:
        try:
            r = measure_one(f, profile)
        except Exception as e:
            skipped.append((os.path.basename(f), f"error: {e}"))
            continue
        (rows.append(r) if r else skipped.append((os.path.basename(f), "under 300 words")))

    if not rows:
        raise SystemExit(f"Nothing measurable. Skipped {len(skipped)}: {skipped[:5]}")

    stats = {}
    for key, _, _ in FIELDS:
        vals = [r[key] for r in rows]
        stats[key] = {"median": statistics.median(vals), "min": min(vals),
                      "max": max(vals), "cv": cv(vals), "p20": p20(vals)}

    if a.json:
        print(json.dumps({"rows": rows, "stats": stats, "skipped": skipped}, indent=2))
    else:
        print(f"\n  CALIBRATION · {len(rows)} scripts"
              + (f" · {len(skipped)} skipped" if skipped else "") + "\n")
        print(f"  {'quantity':22} {'median':>9} {'min':>8} {'max':>8}   verdict")
        print("  " + "-" * 62)
        for key, label, fmt in FIELDS:
            s = stats[key]
            print(f"  {label:22} {fmt.format(s['median']):>9} {fmt.format(s['min']):>8} "
                  f"{fmt.format(s['max']):>8}   {classify(s['cv'])}")
        if skipped:
            print("\n  skipped:")
            for name, why in skipped[:10]:
                print(f"    {name} — {why}")

        varies = [label for key, label, _ in FIELDS if classify(stats[key]["cv"]) == "VARIES"]
        print("\n  ASK PER VIDEO: " + (", ".join(varies) if varies else
                                       "nothing — every measured quantity is stable"))
        print("  LOCK IN PROFILE: everything else\n")

    if not a.write:
        print("  (report only — pass --write to update the profile)\n")
        return 0

    # Only measurement-supported fields. Taste is left alone: a corpus of good
    # scripts cannot tell you what a bad one would have contained, so the banned
    # phrases and the hook rules are not touched here.
    profile["length"]["default_runtime_min"] = round(stats["runtime_min"]["median"], 1)
    profile["structure"]["default_chapters"] = int(round(stats["chapters"]["median"]))
    profile["structure"]["chapter_title_words"] = round(stats["chapter_title_words"]["median"], 1)
    profile["structure"]["chapter_title_max_words"] = max(
        3, int(max(r["chapter_title_max"] for r in rows)))
    profile["structure"]["chapter_spread_pct"] = int(round(
        max(20, stats["chapter_spread_pct"]["median"])))
    profile["hook"]["target_words"] = int(round(stats["hook_words"]["median"]))
    profile["hook"]["max_words"] = int(round(max(stats["hook_words"]["max"],
                                                 stats["hook_words"]["median"] * 1.2)))
    profile["rhythm"]["sentence_len_stdev_min"] = round(stats["sentence_stdev"]["p20"], 1)
    profile["rhythm"]["max_sentence_words"] = int(max(
        30, max(r["sentence_max"] for r in rows)))
    profile["substance"]["facts_per_100_words_min"] = round(stats["fact_density"]["p20"], 1)

    for k in ("length.default_runtime_min", "structure.default_chapters",
              "rhythm.sentence_len_stdev_min", "substance.facts_per_100_words_min"):
        profile["_provenance"][k] = f"measured — {len(rows)} scripts, {os.path.basename(a.paths[0])}"
    profile["_provenance"]["_calibrated_from"] = [r["file"] for r in rows]
    profile["_provenance"]["_varies_per_video"] = [
        label for key, label, _ in FIELDS if classify(stats[key]["cv"]) == "VARIES"]

    out = os.path.abspath(os.path.expanduser(a.out or DEFAULT_PROFILE))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  wrote {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
