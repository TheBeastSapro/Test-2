#!/usr/bin/env python3
"""
One conformance score for a draft — and a refusal to let it hide a hard failure.

A score is the right tool for exactly two jobs and the wrong tool for a third.

RIGHT: comparing two drafts of the SAME title (two models, two passes, two
writers) and tracking profile drift across scripts over time. Both need one
comparable number, and "which of these two is closer to the channel's measured
profile" is a real question that per-gate output answers badly.

WRONG: deciding whether a script may be presented. That decision is already
made by the battery, and a composite number would smother it. A draft can sit
at 88/100 while addressing the viewer as "you", running two consecutive
deadzones, and asserting a lineage no source supports -- each of which is a
hard fail on its own and none of which averages away.

So this tool separates them and refuses to blend:

    BLOCKING   every hard failure, listed. Not scored, not weighted, not
               averaged. Any one of these means the draft is not presentable
               regardless of what the number says.

    SCORE      0-100 across the CONTINUOUS profile metrics only -- the ones
               that are legitimately a matter of degree.

A draft with blocking failures still gets its score printed, because the score
is diagnostic and you want it while you fix them. It is printed with BLOCKED
next to it, and the exit code follows the blocking list, never the score.

    score.py draft.md                            one draft
    score.py --compare a.md b.md                 A/B, per-dimension deltas

The A/B mode is the honest way to settle "which model writes this better".
Same title, same outline, two drafts, one table. The channel's own measured
profile is the referee rather than anybody's taste -- including mine.

WHAT THE NUMBER CANNOT SEE. Whether a fact is true. Whether a joke is funny.
Whether the betrayal lands. Whether the payoff breathes. Whether the subject
should have been written at all. Those are Stage 5A, the judgment battery, and
Gate 0, and a script that scores 100 can fail all of them. The score measures
CONFORMANCE TO A PROFILE, which is a floor and never a ceiling.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clarity as cl            # noqa: E402
import overlay as ov            # noqa: E402
import plan as pl               # noqa: E402

LINT = os.path.join(HERE, "lint-v3_2.py")

# Weights. Rhythm carries the most because it is the profile's densest signal
# and the one a drafting pass most often drifts on; length and tier shape are
# structural and near-binary in practice, so they carry less than their
# importance suggests -- they are usually either right or obviously wrong.
WEIGHTS = {
    "length":     0.12,
    "tier_shape": 0.12,
    "rhythm":     0.22,
    "substance":  0.16,
    "deadzone":   0.08,
    "clarity":    0.15,     # can a viewer follow it
    "drawable":   0.15,     # can the animator draw it
    "humor":      0.10,     # dramatic mode only; redistributed when off
}


def band_conformance(value, lo, hi):
    """
    1.0 inside the band, decaying to 0 at one band-width outside it.

    Linear rather than cliff-edged: a draft 5 words over target and one 500
    words over are not the same problem, and a step function would score them
    identically and teach the writer nothing.
    """
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1e-9)
    dist = (lo - value) if value < lo else (value - hi)
    return max(0.0, 1.0 - dist / width)


def run_lint(path, fmt, overlay_on):
    cmd = [sys.executable, LINT, path, "--format", fmt]
    if overlay_on:
        cmd.append("--overlay")
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout + p.stderr

    fails = []
    m = re.search(r"--- FAILURES \(\d+\) ---\n(.*?)(?:\nVERDICT|\Z)", out, re.S)
    if m:
        fails = [ln.strip()[2:].strip() for ln in m.group(1).split("\n")
                 if ln.strip().startswith("X ")]

    dz = re.search(r"deadzones:\s*(\d+)\s*sentence\(s\),\s*(\d+)\s*consecutive", out)
    deadzones = int(dz.group(1)) if dz else 0
    dz_runs = int(dz.group(2)) if dz else 0

    wc = re.search(r"Word count \(body\):\s*(\d+)", out)
    words = int(wc.group(1)) if wc else 0

    dens = re.search(r"fact-density floor:\s*(\d+)/(\d+) sections clear", out)
    dens_ok, dens_tot = (int(dens.group(1)), int(dens.group(2))) if dens else (0, 0)

    return {"exit": p.returncode, "fails": fails, "deadzones": deadzones,
            "deadzone_runs": dz_runs, "words": words,
            "density_clear": dens_ok, "density_total": dens_tot, "raw": out}


def score_draft(path, fmt="listicle", mode="explaintory", dramatic=False):
    body, beats = ov.read_body(path)
    ov_res = ov.analyse(body, beats, mode)
    lint = run_lint(path, fmt, overlay_on=True)
    lint_mod = cl.load_lint()

    sents = ov.sentences(body)
    slens = [len(ov.words(s)) for s in sents] or [0]
    total_w = sum(slens)
    band = pl.FORMAT_BANDS[fmt]

    dims, detail = {}, {}

    # --- length ---
    dims["length"] = band_conformance(total_w, *band)
    detail["length"] = f"{total_w}w vs {band[0]}-{band[1]}"

    # --- tier shape ---
    secs = pl.read_sections(path)
    if secs:
        tiers = [pl.classify(s["words"]) for s in secs]
        in_band = sum(1 for t in tiers if t in pl.TIERS) / len(tiers)
        adj = sum(1 for a, b in zip(tiers, tiers[1:]) if a == b == "HEAVY")
        variety = len({t for t in tiers if t in pl.TIERS}) / 3.0
        dims["tier_shape"] = max(0.0, in_band * 0.5 + variety * 0.5
                                 - 0.15 * adj)
        detail["tier_shape"] = (f"{sum(1 for t in tiers if t in pl.TIERS)}/{len(tiers)} "
                                f"in band, {len({t for t in tiers if t in pl.TIERS})}/3 "
                                f"tiers used, {adj} back-to-back HEAVY")
    else:
        dims["tier_shape"] = 0.0
        detail["tier_shape"] = "no '## ' sections found"

    # --- rhythm ---
    r = {"avg_words": statistics.mean(slens),
         "frag_pct": sum(1 for x in slens if x <= 4) / len(slens) * 100,
         "short_pct": sum(1 for x in slens if x <= 8) / len(slens) * 100,
         "long_pct": sum(1 for x in slens if x >= 20) / len(slens) * 100}
    subs = [band_conformance(r[k], *ov.RHYTHM[k]) for k in ov.RHYTHM]
    dims["rhythm"] = statistics.mean(subs)
    detail["rhythm"] = (f"avg {r['avg_words']:.1f} · frag {r['frag_pct']:.0f}% · "
                        f"short {r['short_pct']:.0f}% · long {r['long_pct']:.0f}%")

    # --- substance ---
    # The linter's own per-section date/name/number floor is the measure here,
    # rather than a second density heuristic invented alongside it.
    dims["substance"] = (lint["density_clear"] / lint["density_total"]
                         if lint["density_total"] else 0.0)
    detail["substance"] = (f"{lint['density_clear']}/{lint['density_total']} sections "
                           f"carry a date, a name and a number")

    # --- deadzone burden ---
    # Per 1,000 words so long and short scripts compare. 20+ per 1,000 scores
    # zero; that is roughly one dead sentence every two, at which point the
    # animator has nothing to cut to for stretches at a time.
    per_k = lint["deadzones"] / max(total_w, 1) * 1000
    dims["deadzone"] = max(0.0, 1.0 - per_k / 20.0)
    detail["deadzone"] = (f"{lint['deadzones']} ({per_k:.1f}/1k words), "
                          f"{lint['deadzone_runs']} consecutive runs")

    # --- clarity and drawability ---
    # Weighted alongside the rest rather than bolted on, because "a viewer can
    # follow it" and "the animator can draw it" are the two things that decide
    # whether the video works at all. A script can be accurate, on-profile and
    # unwatchable.
    g_clean, _, _, _ = cl.flesch(body, strip_names=True)
    dims["clarity"] = cl.band_grade_conformance(g_clean)
    detail["clarity"] = f"grade {g_clean:.1f} without names (target ≤{cl.GRADE_MAX:g})"

    draw, _ = cl.drawability(body, lint_mod.CONCRETE_RE, lint_mod.UNIT_RE)
    dims["drawable"] = min(1.0, draw / cl.DRAWABLE_MIN)
    detail["drawable"] = f"{draw * 100:.0f}% of sentences name something physical"

    # --- humor, dramatic only ---
    if dramatic:
        hum = {c["check"]: c for c in ov_res["checks"]}
        got = lambda k: 1.0 if hum.get(k, {}).get("ok") else 0.4  # noqa: E731
        dims["humor"] = statistics.mean([got("humor:floor"),
                                         got("humor:reacting_narrator"),
                                         got("humor:anachronism")])
        detail["humor"] = "; ".join(hum[k]["detail"][:38] for k in
                                    ("humor:floor", "humor:reacting_narrator",
                                     "humor:anachronism") if k in hum)

    weights = {k: v for k, v in WEIGHTS.items() if k in dims}
    tot_w = sum(weights.values())
    total = sum(dims[k] * weights[k] for k in dims) / tot_w * 100

    # --- blocking ---
    blocking = list(lint["fails"])
    if lint["deadzone_runs"] > 0:
        blocking.append(f"DEADZONE RUNS: {lint['deadzone_runs']} consecutive — "
                        f"hard fail, seconds with nothing on screen")
    for c in ov_res["checks"]:
        if not c["ok"] and c["severity"] == "fail" and c["check"] in (
                "pov:second_person", "engine:no_telegraph", "banned_phrases",
                "sourcing:attribution"):
            blocking.append(f"{c['check'].upper()}: {c['detail']}")

    return {"file": os.path.basename(path), "score": round(total, 1),
            "dimensions": {k: round(v * 100, 1) for k, v in dims.items()},
            "detail": detail, "blocking": blocking,
            "words": total_w, "sections": len(secs)}


def render(r):
    out = [f"\n  {r['file']}",
           f"  {'BLOCKED · ' if r['blocking'] else ''}SCORE {r['score']:.1f} / 100"
           f"   ({r['words']} words, {r['sections']} sections)\n"]
    for k in WEIGHTS:
        if k in r["dimensions"]:
            v = r["dimensions"][k]
            bar = "█" * int(v / 5) + "·" * (20 - int(v / 5))
            out.append(f"  {k:11} {v:5.1f}  {bar}  {r['detail'].get(k,'')}")
    if r["blocking"]:
        out.append(f"\n  BLOCKING ({len(r['blocking'])}) — not scored, not averaged:")
        for b in r["blocking"][:14]:
            out.append(f"    X {b[:100]}")
        if len(r["blocking"]) > 14:
            out.append(f"    … and {len(r['blocking']) - 14} more")
        out.append("\n  The score above is diagnostic only. Any blocking line means")
        out.append("  the draft is not presentable, whatever the number says.")
    else:
        out.append("\n  No blocking failures. The score is profile CONFORMANCE —")
        out.append("  it cannot see whether a fact is true, a joke is funny, or the")
        out.append("  betrayal lands. Stage 5A and the judgment battery still owe.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    ap.add_argument("--format", default="listicle", choices=list(pl.FORMAT_BANDS))
    ap.add_argument("--mode", default="explaintory",
                    choices=["explaintory", "sticktory"])
    ap.add_argument("--dramatic", action="store_true",
                    help="score the humor dimension (dramatic voice state)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.compare:
        ra, rb = (score_draft(p, a.format, a.mode, a.dramatic) for p in a.compare)
        if a.json:
            print(json.dumps({"a": ra, "b": rb}, indent=2))
            return 0
        print(f"\n  A/B · {ra['file']}  vs  {rb['file']}\n")
        print(f"  {'dimension':12} {'A':>7} {'B':>7} {'Δ':>7}")
        print("  " + "-" * 36)
        for k in WEIGHTS:
            if k in ra["dimensions"] and k in rb["dimensions"]:
                x, y = ra["dimensions"][k], rb["dimensions"][k]
                print(f"  {k:12} {x:7.1f} {y:7.1f} {y - x:+7.1f}")
        print("  " + "-" * 36)
        print(f"  {'TOTAL':12} {ra['score']:7.1f} {rb['score']:7.1f} "
              f"{rb['score'] - ra['score']:+7.1f}")
        print(f"  {'blocking':12} {len(ra['blocking']):7} {len(rb['blocking']):7}")
        # Blocking decides first, and the verdict has to actually obey that.
        # Ranking on score and then printing "but blocking decides first"
        # underneath is a verdict arguing with its own caveat, and the reader
        # takes the headline.
        na, nb = len(ra["blocking"]), len(rb["blocking"])
        if na != nb:
            win = "A" if na < nb else "B"
            why = f"fewer blocking failures ({min(na, nb)} vs {max(na, nb)})"
        elif ra["score"] != rb["score"]:
            win = "B" if rb["score"] > ra["score"] else "A"
            why = f"equal blocking, closer to profile by {abs(rb['score'] - ra['score']):.1f}"
        else:
            win, why = "tie", "identical on both"
        print(f"\n  BETTER DRAFT: {win} — {why}")
        if na or nb:
            print("  Both still carry blocking failures; neither is presentable yet.")
        print("  A higher score with more blocking failures is the worse draft.\n")
        return 0

    if not a.script:
        ap.error("give a script, or --compare A B")
    r = score_draft(a.script, a.format, a.mode, a.dramatic)
    print(json.dumps(r, indent=2) if a.json else render(r) + "\n")
    return 1 if r["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
