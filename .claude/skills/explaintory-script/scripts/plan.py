#!/usr/bin/env python3
"""
Stage 3 tier budget — allocate it, and verify it in the shell.

This exists because of a failure the SOP names in its own words:

    "In one session every runtime estimate was given at 168 WPM and every
     entry-weight sum was wrong by 600 words, both stated with confidence.
     Recompute in the shell, never in the head, and print the number."
                                        -- Scripting SOP v1.6, Stage 5B rule 4

So this is the shell. Nothing here is computed in the head, and every number
it prints carries the arithmetic that produced it.

Two modes:

    --entries 9 --words 1800       allocate:  a tier per entry, summed and
                                              checked against the band
    --verify script.md             audit:     measured section words against
                                              tiers, adjacency, rehook slot

The allocator is not a suggestion engine. The tier system exists to stop
uniform entry lengths, which the channel skill calls the measurable tell of
generated writing and a way to teach viewers where the exits are. So the
allocation enforces the shape rather than averaging toward the middle:

  - opener, rehook and closer are HEAVY by rule, not by preference
  - at most five HEAVY entries in a script
  - never two HEAVY back to back
  - the rehook lands at 40-55% of the way through

Constants, all from the SOP appendix and channel skill v6.5 — none chosen here:

    VO rate        185 WPM measured   (2,291 words -> 12:21; 78 words = 0:25)
    Listicle       1,600-2,000 words, 8-12 entries
    HEAVY          250-320 words
    MEDIUM         170-220 words
    LIGHT          110-160 words
    ENTIRE History 3,300-4,000 words
"""
import argparse
import json
import os
import re
import sys

WPM = 185.0                      # measured, channel skill v6.5 §VO pace
KILL_LINE_WORDS = 78             # 25 s at 185 WPM, Fix 1

FORMAT_BANDS = {
    "listicle":  (1600, 2000),
    "every-era": (1600, 2000),
    "history":   (3300, 4000),
}

TIERS = {
    "HEAVY":  (250, 320),
    "MEDIUM": (170, 220),
    "LIGHT":  (110, 160),
}
TIER_ORDER = ["HEAVY", "MEDIUM", "LIGHT"]
MAX_HEAVY = 5                    # opener + rehook + closer, plus at most 2 more


def fmt_time(seconds):
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def secs(words):
    return words / WPM * 60.0


def rehook_index(n):
    """
    The rehook sits at 40-55% of the way through. Mid-point of that band,
    rounded to an entry, and never the opener or the closer -- on a short
    script the arithmetic can otherwise land on entry 1.
    """
    idx = int(round(n * 0.475))
    return max(1, min(idx, n - 2))


def _reachable_counts(target_words, lo=4, hi=30):
    """Which entry counts can carry this word target inside the tier bands."""
    ok = []
    for n in range(lo, hi + 1):
        n_heavy = min(MAX_HEAVY, max(3, n // 3))
        rest = n - n_heavy
        med, light = (rest + 1) // 2, rest // 2
        span_lo = (n_heavy * TIERS["HEAVY"][0] + med * TIERS["MEDIUM"][0]
                   + light * TIERS["LIGHT"][0])
        span_hi = (n_heavy * TIERS["HEAVY"][1] + med * TIERS["MEDIUM"][1]
                   + light * TIERS["LIGHT"][1])
        if span_lo <= target_words <= span_hi:
            ok.append(n)
    return ", ".join(map(str, ok)) if ok else "none between 4 and 30"


def allocate(n_entries, target_words, band):
    """
    Assign a tier per entry, then size each entry inside its tier band so the
    total lands on target.

    Tiers are assigned first and sizes fitted afterwards, never the other way
    round. Fitting sizes first and labelling them afterwards is how every entry
    drifts to the middle of its band and the script comes out uniform -- which
    is the exact failure the tier system exists to prevent.
    """
    lo, hi = band
    if not (lo <= target_words <= hi):
        print(f"  ! target {target_words} is outside the {lo}-{hi} band for "
              f"this format", file=sys.stderr)

    opener, closer, rehook = 0, n_entries - 1, rehook_index(n_entries)

    # THREE fixed HEAVY entries, not five. The SOP allows "max 2 more" but its
    # own worked example is 9 entries / 1,800 words as 3 HEAVY + 3-4 MEDIUM +
    # 2-3 LIGHT. Taking the maximum as the default overshoots: five HEAVY at
    # tier minimum already totals 1,810 words across 9 entries, over the whole
    # target, before a single MEDIUM entry is written. So the extra HEAVY slots
    # are spent only when the word budget cannot be met without them.
    tiers = [None] * n_entries
    for i in (opener, closer, rehook):
        tiers[i] = "HEAVY"

    # Everything else alternates MEDIUM/LIGHT, starting MEDIUM, so no two LIGHT
    # entries sit together and create a flat stretch.
    flip = True
    for i in range(n_entries):
        if tiers[i] is None:
            tiers[i] = "MEDIUM" if flip else "LIGHT"
            flip = not flip

    def band_span(ts):
        return (sum(TIERS[t][0] for t in ts), sum(TIERS[t][1] for t in ts))

    # Promote toward HEAVY only while the target is out of reach at the top of
    # the current bands, and demote only while it is out of reach at the bottom.
    # Both walk outward from the middle and both refuse to create an adjacent
    # HEAVY pair.
    order = sorted(range(n_entries), key=lambda i: abs(i - n_entries / 2))
    while band_span(tiers)[1] < target_words:
        for i in order:
            if tiers[i] == "HEAVY" or sum(t == "HEAVY" for t in tiers) >= MAX_HEAVY:
                continue
            if (i > 0 and tiers[i - 1] == "HEAVY") or \
               (i < n_entries - 1 and tiers[i + 1] == "HEAVY"):
                continue
            tiers[i] = "HEAVY" if tiers[i] == "MEDIUM" else "MEDIUM"
            break
        else:
            break
    while band_span(tiers)[0] > target_words:
        for i in reversed(order):
            if tiers[i] == "LIGHT" or i in (opener, closer, rehook):
                continue
            tiers[i] = "LIGHT" if tiers[i] == "MEDIUM" else "MEDIUM"
            break
        else:
            break

    # Size within band. Start every entry at its band minimum, then distribute
    # the remaining words proportionally to each entry's headroom, so the
    # HEAVY entries absorb most of the surplus and the LIGHT ones stay light.
    sizes = [TIERS[t][0] for t in tiers]
    headroom = [TIERS[t][1] - TIERS[t][0] for t in tiers]
    remaining = target_words - sum(sizes)
    total_head = sum(headroom)

    # Report the reachable range rather than a guess at the fix. The tier bands
    # in the SOP appendix are documented for the Listicle format; ENTIRE History
    # runs 3,300-4,000 words in era blocks and has no published tier table, so
    # a target it cannot reach is a signal that the wrong structure is being
    # planned, not that the entry count needs nudging.
    if remaining < 0 or remaining > total_head:
        reach_lo, reach_hi = sum(sizes), sum(sizes) + total_head
        raise SystemExit(
            f"  {n_entries} entries can carry {reach_lo}-{reach_hi} words at these "
            f"tier bands.\n  Target {target_words} is "
            f"{'below' if remaining < 0 else 'above'} that range.\n\n"
            f"  Reachable entry counts for {target_words} words: "
            f"{_reachable_counts(target_words)}\n"
            f"  (HEAVY {TIERS['HEAVY'][0]}-{TIERS['HEAVY'][1]}, "
            f"MEDIUM {TIERS['MEDIUM'][0]}-{TIERS['MEDIUM'][1]}, "
            f"LIGHT {TIERS['LIGHT'][0]}-{TIERS['LIGHT'][1]} — SOP appendix, "
            f"documented for Listicle. ENTIRE History uses era blocks and has "
            f"no published tier table; do not force it through this allocator.)")

    for i in range(n_entries):
        share = int(round(remaining * (headroom[i] / total_head))) if total_head else 0
        sizes[i] += min(share, headroom[i])

    # Rounding leaves a few words either way. Push them into the HEAVY entries
    # that still have headroom -- they are the ones with room to absorb it
    # without leaving their band.
    drift = target_words - sum(sizes)
    order = sorted(range(n_entries),
                   key=lambda i: (TIER_ORDER.index(tiers[i]), -headroom[i]))
    while drift != 0:
        moved = False
        for i in order:
            room_up = TIERS[tiers[i]][1] - sizes[i]
            room_dn = sizes[i] - TIERS[tiers[i]][0]
            if drift > 0 and room_up > 0:
                sizes[i] += 1
                drift -= 1
                moved = True
            elif drift < 0 and room_dn > 0:
                sizes[i] -= 1
                drift += 1
                moved = True
            if drift == 0:
                break
        if not moved:
            break          # every band is saturated; report the gap honestly

    return [{"index": i + 1, "tier": tiers[i], "words": sizes[i],
             "role": ("OPENER" if i == opener else "CLOSER" if i == closer
                      else "REHOOK" if i == rehook else ""),
             "seconds": secs(sizes[i])}
            for i in range(n_entries)], drift


def check_shape(entries):
    """Adjacency and distribution problems, as a list of strings."""
    problems = []
    for a, b in zip(entries, entries[1:]):
        if a["tier"] == "HEAVY" and b["tier"] == "HEAVY":
            problems.append(f"entries {a['index']} and {b['index']} are both HEAVY "
                            f"— back-to-back HEAVY flattens the tier variation")
    n_heavy = sum(1 for e in entries if e["tier"] == "HEAVY")
    if n_heavy > MAX_HEAVY:
        problems.append(f"{n_heavy} HEAVY entries, max is {MAX_HEAVY}")
    if len({e["tier"] for e in entries}) < 3:
        problems.append("only " + "/".join(sorted({e["tier"] for e in entries}))
                        + " used — uniform structures teach viewers where the exits are")
    return problems


# --- verify mode -------------------------------------------------------------

# Section headers are markdown H2 in a finished script, and carry no numbers.
_H2 = re.compile(r"^##\s+(?!.*(pronunciation|audit|appendix|source))(.+?)\s*$", re.I)
_BACK_MATTER = re.compile(r"^#{1,6}\s*(pronunciation|audit|appendix|source|"
                          r"animator|production|research)", re.I)


def read_sections(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    sections, cur = [], None
    for ln in lines:
        if _BACK_MATTER.match(ln):
            break
        m = _H2.match(ln)
        if m:
            cur = {"title": m.group(2).strip(" *#"), "words": 0}
            sections.append(cur)
        elif cur is not None and ln.strip() and not ln.startswith("#"):
            cur["words"] += len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", ln))
    return sections


def classify(words):
    for tier, (lo, hi) in TIERS.items():
        if lo <= words <= hi:
            return tier
    return "OVER-HEAVY" if words > TIERS["HEAVY"][1] else "UNDER-LIGHT"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entries", type=int, help="entry count to allocate")
    ap.add_argument("--words", type=int, help="target total words")
    ap.add_argument("--format", default="listicle", choices=list(FORMAT_BANDS))
    ap.add_argument("--verify", help="measure a drafted script instead")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    band = FORMAT_BANDS[a.format]

    if a.verify:
        sections = read_sections(a.verify)
        if not sections:
            raise SystemExit(
                f"No '## ' section headers found in {a.verify}. Headers are H2 "
                f"and carry no numbers (SOP Stage 4).")
        entries = [{"index": i + 1, "tier": classify(s["words"]), "words": s["words"],
                    "role": "", "seconds": secs(s["words"]), "title": s["title"]}
                   for i, s in enumerate(sections)]
        rh = rehook_index(len(entries))
        entries[0]["role"] = "OPENER"
        entries[-1]["role"] = "CLOSER"
        entries[rh]["role"] = "REHOOK?"
        total = sum(e["words"] for e in entries)
        problems = check_shape(entries)
        if not (band[0] <= total <= band[1]):
            problems.append(f"total {total} outside the {band[0]}-{band[1]} band "
                            f"({total - band[0] if total < band[0] else total - band[1]:+d})")
        for e in entries:
            if e["tier"] in ("OVER-HEAVY", "UNDER-LIGHT"):
                problems.append(f"entry {e['index']} '{e.get('title','')}' is "
                                f"{e['words']}w — {e['tier']}, outside every tier band")
        drift = 0
    else:
        if not (a.entries and a.words):
            ap.error("give --entries and --words, or --verify a script")
        entries, drift = allocate(a.entries, a.words, band)
        problems = check_shape(entries)
        total = sum(e["words"] for e in entries)

    if a.json:
        print(json.dumps({"entries": entries, "total": total, "drift": drift,
                          "problems": problems, "band": band,
                          "runtime": fmt_time(secs(total))}, indent=2))
        return 0 if not problems else 1

    print(f"\n  {'VERIFY' if a.verify else 'TIER BUDGET'} · {a.format} · "
          f"{len(entries)} entries · band {band[0]}-{band[1]}\n")
    print(f"  {'#':>2}  {'tier':<7} {'words':>6} {'time':>7}  role")
    print("  " + "-" * 46)
    for e in entries:
        print(f"  {e['index']:>2}  {e['tier']:<7} {e['words']:>6} "
              f"{fmt_time(e['seconds']):>7}  {e['role']}"
              + (f"  {e.get('title','')[:28]}" if a.verify else ""))
    print("  " + "-" * 46)
    print(f"      {'TOTAL':<7} {total:>6} {fmt_time(secs(total)):>7}"
          f"   at {WPM:g} WPM")

    if drift:
        print(f"\n  ! {abs(drift)} words could not be placed inside the tier bands "
              f"({'short' if drift > 0 else 'over'}). Change the entry count.")
    if problems:
        print("\n  PROBLEMS:")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  shape ok — no back-to-back HEAVY, all three tiers used")

    print(f"\n  kill-line must land inside the first {KILL_LINE_WORDS} words "
          f"(0:25) of entry 1.")
    print(f"  no extracted hook section, no outro — the closer's last sentence "
          f"ends the script.\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
