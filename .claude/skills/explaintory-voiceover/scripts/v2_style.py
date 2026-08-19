"""The V2 style layer: plan the rests, price them, or apply them.

Three ways out of the same plan, because the choice between them is a spend
decision and belongs to Sapro, not to this script:

  --emit-plan   a JSON plan for :mod:`v2_rest`, which opens the gaps in the
                rendered audio afterwards. Costs nothing.
  --review      the plan in readable form: every rest, where it goes, and the
                measured reason it was chosen there.
  --tags        ``<break>`` markup for the text itself, with the character cost
                stated. Only ``eleven_multilingual_v2`` and the Flash models
                honour break tags; v3 ignores them.

The post route is the default and the recommended one. At the measured rate of
one rest every ten words, break-tag markup adds 36-43% to the billed character
count of a script — around 9,000 characters on a 4,500-word video, bought
entirely to describe silence. The same silence costs nothing after the render,
and the standing rule here is already repair-first-generate-last.

The tag route is kept because it is not strictly worse: a break tag is present
while the model is reading, so it can shape the delivery either side of the
gap, which a post-production cut cannot do. If a passage needs the VOICE to
change around the pause rather than just the timing, that is what to spend on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import v2_prep
from v2_profile import REFERENCE, DEFAULT_TARGET

# A break tag is billed like any other text. Measured on the rendered form this
# module emits, rounded to the 3-decimal seconds the planner produces.
TAG_CHARS = 23


def build_plan(text: str, target: str = DEFAULT_TARGET,
               emphasise_numbers: bool = False) -> dict:
    """Plan the rests and package them with the tokens needed to place them.

    The tokens travel with the plan because :mod:`v2_rest` matches rests to the
    audio by the words either side, not by index — the ASR sequence and the
    script never line up exactly.
    """
    plans = v2_prep.plan_script(text, target=target,
                                emphasise_numbers=emphasise_numbers)
    nlp = v2_prep._nlp()
    out = []
    for p in plans:
        toks = [t.text for t in nlp(p.text) if not t.is_space]
        out.append({
            "text": p.text,
            "words": p.words,
            "tokens": toks,
            "rests": [{"index": r.index, "seconds": r.seconds,
                       "site": r.site, "score": r.score} for r in p.rests],
        })
    words = sum(p["words"] for p in out)
    rests = sum(len(p["rests"]) for p in out)
    return {
        "target": target,
        "target_label": REFERENCE[target]["label"],
        "emphasise_numbers": emphasise_numbers,
        "words": words,
        "rests": rests,
        "words_per_rest": round(words / rests, 1) if rests else None,
        "reference_words_per_rest": REFERENCE[target]["words_per_midphrase_pause"],
        "added_silence_s": round(sum(r["seconds"] for p in out for r in p["rests"]), 2),
        "sentences": out,
    }


def cost_report(plan: dict, script_chars: int) -> str:
    rests = plan["rests"]
    added = rests * TAG_CHARS
    return "\n".join([
        "## cost of the two routes",
        "",
        f"- {rests} rests planned, {plan['added_silence_s']}s of silence in total",
        f"- **post-production** (`v2_rest.py`): **0 characters**, 0 credits",
        f"- **break tags**: +{added:,} characters on {script_chars:,} "
        f"(+{added / script_chars:.0%}), billed at render",
        "",
        "Break tags are only worth their cost where the VOICE needs to change "
        "around the gap, not merely the timing — the model reads the tag, so it "
        "can shape delivery either side of it. For a rest that is purely a beat, "
        "the post route produces the same silence for nothing.",
    ])


def apply_to_sections(sections, target: str = DEFAULT_TARGET,
                      emphasise_numbers: bool = False) -> dict:
    """Write break tags into ``send_text`` only, and re-price each section.

    Mirrors ``pronounce.apply_to_sections``: ``text`` is left alone so the
    read-check and the mastering alignment still see the real script, and
    ``chars`` is updated because the tags are billed. Getting that second part
    wrong would make the approval gate under-report what a run costs, which is
    the one number that must never be optimistic.
    """
    total_added = 0
    touched = 0
    for sec in sections:
        if sec.get("is_heading"):
            continue          # a one-or-two-word chapter name has nothing to pace
        src = sec.get("send_text") or sec["text"]
        plans = v2_prep.plan_script(src, target=target,
                                    emphasise_numbers=emphasise_numbers)
        if not any(p.rests for p in plans):
            continue
        marked = v2_prep.render_break_tags(plans)
        added = len(marked) - len(src)
        sec["send_text"] = marked
        sec["chars"] = len(marked)      # tags are billed, so they are counted
        sec["v2_rests"] = sum(len(p.rests) for p in plans)
        total_added += added
        touched += 1
    return {"sections_touched": touched, "chars_added": total_added}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("script", help="the script to plan")
    ap.add_argument("--target", default=DEFAULT_TARGET, choices=sorted(REFERENCE),
                    help="which reference narrator to aim at")
    ap.add_argument("--emphasise-numbers", action="store_true",
                    help="also rest before numerals (Agent Flappy's strongest "
                         "single move, lift 4.31; Serious History does not do it)")
    ap.add_argument("--emit-plan", help="write the JSON plan for v2_rest.py here")
    ap.add_argument("--review", action="store_true",
                    help="print every rest with the reason it was chosen")
    ap.add_argument("--tags", help="write break-tag markup here (billed — see cost)")
    a = ap.parse_args(argv)

    text = Path(a.script).read_text(encoding="utf-8")
    plan = build_plan(text, a.target, a.emphasise_numbers)

    print(f"target: {plan['target_label']}")
    print(f"{plan['words']} words, {plan['rests']} rests — one every "
          f"{plan['words_per_rest']} words "
          f"(reference: {plan['reference_words_per_rest']})")
    print(f"{plan['added_silence_s']}s of silence added in total")
    print()
    print(cost_report(plan, len(text)))

    if a.review:
        print()
        plans = v2_prep.plan_script(text, target=a.target,
                                    emphasise_numbers=a.emphasise_numbers)
        print(v2_prep.render_review(plans))

    if a.emit_plan:
        Path(a.emit_plan).write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"\nplan written to {a.emit_plan}")
    if a.tags:
        plans = v2_prep.plan_script(text, target=a.target,
                                    emphasise_numbers=a.emphasise_numbers)
        Path(a.tags).write_text(v2_prep.render_break_tags(plans), encoding="utf-8")
        print(f"break-tag markup written to {a.tags} — this route is billed")
    if not (a.emit_plan or a.tags or a.review):
        print("\n(nothing written — pass --emit-plan, --tags or --review)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
