"""The V2 delivery target, and the comparison that says how far off a take is.

``REFERENCE`` holds what was measured from two faceless-narration channels that
Sapro pointed at as the sound to hit. The numbers are the useful part of this
module: they turn "make it more human" into a target a take can be scored
against.

Both references were measured with :mod:`vostudio.styleprint` from ASR word
onsets. Where the two channels disagree, both values are kept rather than
averaged — they are two different ways of sounding human, not two estimates of
one truth, and a take should be aimed at ONE of them.

What the two agree on, and what V2 is therefore built from:

  * roughly a fifth of the runtime is silence (19.5% / 21.3%)
  * a full stop rests about twice as long as a comma (0.50/0.21, 0.53/0.29)
  * they stop mid-phrase, where no punctuation invites it, once every ten
    words — at 11% of all unpunctuated word boundaries in both
  * tempo holds flat for the whole video (trend r = -0.09 / +0.09) while
    swinging about 10% from one 30-second stretch to the next

The last two are the ones a TTS pipeline gets wrong by default: it pauses only
where the punctuation tells it to, and it holds one rate forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# measured reference profiles
# --------------------------------------------------------------------------

REFERENCE = {
    "serious_history": {
        "label": "Serious History — fast, even, silence saved and spent in lumps",
        "source_video": "sNMDXA8Qcts",
        "measured_words": 4152,
        "measured_seconds": 1321.1,
        "speech_wpm": 188.6,
        "articulation_wpm": 234.3,
        "silence_ratio": 0.195,
        "pause_rate_per_min": 26.3,
        "pause_s": {
            # median, and the p25-p75 band a take should mostly sit inside
            "sentence": {"median": 0.498, "p25": 0.395, "p75": 0.642, "p90": 0.772},
            "clause":   {"median": 0.212, "p25": 0.146, "p75": 0.290, "p90": 0.458},
            "midphrase": {"median": 0.138, "p25": 0.105, "p75": 0.200, "p90": 0.313},
        },
        "midphrase_rate": 0.109,        # share of unpunctuated boundaries paused at
        "words_per_midphrase_pause": 10.2,
        "holds_ge_700ms_per_10min": 20.4,
        "section_gaps_ge_2s": 3,
        "sentence_words": {"median": 17.0, "p10": 9.0, "p90": 29.0},
        "sentence_hist": {"1-3": 7, "4-7": 8, "8-12": 35, "13-20": 95,
                          "21-30": 58, "31+": 20},
        "pct_sentences_le5": 4.9,
        "pct_sentences_ge20": 39.0,
        "tempo_sd_pct_of_mean": 9.6,
        "tempo_trend_r": -0.09,
    },
    "agent_flappy": {
        "label": "Agent Flappy — slower, short sentences, silence spent constantly",
        "source_video": "3GKC4kC3iQ0",
        "measured_words": 4292,
        "measured_seconds": 1874.4,
        "speech_wpm": 137.4,
        "articulation_wpm": 175.3,
        "silence_ratio": 0.213,
        "pause_rate_per_min": 25.9,
        "pause_s": {
            "sentence": {"median": 0.532, "p25": 0.422, "p75": 0.662, "p90": 0.770},
            "clause":   {"median": 0.292, "p25": 0.207, "p75": 0.452, "p90": 0.686},
            "midphrase": {"median": 0.133, "p25": 0.102, "p75": 0.220, "p90": 0.367},
        },
        "midphrase_rate": 0.113,
        "words_per_midphrase_pause": 10.4,
        "holds_ge_700ms_per_10min": 19.2,
        "section_gaps_ge_2s": 2,
        "sentence_words": {"median": 11.0, "p10": 4.0, "p90": 22.0},
        "sentence_hist": {"1-3": 23, "4-7": 92, "8-12": 92, "13-20": 91,
                          "21-30": 40, "31+": 11},
        "pct_sentences_le5": 18.1,
        "pct_sentences_ge20": 18.1,
        "tempo_sd_pct_of_mean": 9.5,
        "tempo_trend_r": 0.09,
    },
}

DEFAULT_TARGET = "agent_flappy"

# --------------------------------------------------------------------------
# where a mid-phrase pause is allowed to go
# --------------------------------------------------------------------------

# Lift = how much more often the narrator stopped at this position than its
# share of available boundaries would predict. 1.0 is chance. These are the
# positions BOTH references favour, sorted by the weaker of the two lifts, so
# nothing here rests on a single channel's habit.
#
# The avoid list matters as much as the prefer list. A pause dropped between a
# determiner and its noun, or after a preposition, is the specific thing that
# makes inserted breaks sound mechanical instead of thoughtful — and both
# narrators steer around those positions well below chance.

PREFER_SITES = [
    # (site, lift in Serious History, lift in Agent Flappy)
    ("before a coordinating conjunction (and / but / or / so)", 1.78, 3.55),
    ("before the word 'and' specifically",                       1.84, 3.48),
    ("between a noun and the verb it governs",                   1.50, 2.23),
    ("after an adverb",                                          1.46, 1.30),
    ("after a noun",                                             1.29, 1.59),
    ("after a proper noun",                                      1.28, 2.68),
    ("before an auxiliary verb",                                 1.16, 1.16),
    ("before a date",                                            1.11, 1.38),
    ("before a verb",                                            1.11, 1.08),
    ("before a new subordinate clause",                          1.00, 1.17),
]

AVOID_SITES = [
    ("after the infinitive 'to' or another particle", 0.53, 0.14),
    ("between a pronoun and its verb",                0.62, 0.29),
    ("between a determiner and its noun",             0.67, 0.23),
    ("after a preposition",                           0.72, 0.31),
    ("between a preposition and a determiner",        0.72, 0.00),
    ("between a preposition and its noun",            0.74, 0.10),
    ("between a verb and a following determiner",     0.75, 0.37),
]

# Agent Flappy pauses before numerals at more than four times chance (lift
# 4.31, the strongest single effect measured anywhere in either channel) and
# before cardinal entities at 3.64. Serious History does not do this. It is
# kept out of PREFER_SITES because the two disagree, and offered separately:
# it is the move to use on a script whose weight sits in casualty figures,
# dates and totals.
NUMBER_EMPHASIS = {
    "site": "before a numeral",
    "lift_serious_history": None,      # not among its favoured positions
    "lift_agent_flappy": 4.31,
    "median_pause_s": 0.163,
    "note": "pair with the deceleration described in the qualitative pass: "
            "both narrators take figures LOWER and SLOWER rather than louder.",
}


@dataclass
class Deviation:
    metric: str
    take: float
    target: float
    band: tuple | None
    verdict: str        # "ok" | "high" | "low"
    advice: str = ""


def compare(fp, target: str = DEFAULT_TARGET) -> list[Deviation]:
    """Score a styleprint fingerprint against a reference profile.

    ``fp`` is a :class:`vostudio.styleprint.Fingerprint` or the dict form of
    one. Returns one :class:`Deviation` per metric, in the order worth fixing:
    the mid-phrase pause rate first, because it is the metric a TTS pipeline
    misses entirely, then the slot ratios, then rate.
    """
    if not isinstance(fp, dict):
        from dataclasses import asdict
        fp = asdict(fp)
    ref = REFERENCE[target]
    out: list[Deviation] = []

    def check(metric, take, tgt, band, advice_low, advice_high, tol=0.0):
        if take is None:
            return
        lo, hi = band if band else (tgt * (1 - tol), tgt * (1 + tol))
        verdict = "ok" if lo <= take <= hi else ("low" if take < lo else "high")
        out.append(Deviation(metric, round(take, 3), tgt, (round(lo, 3), round(hi, 3)),
                             verdict, "" if verdict == "ok"
                             else (advice_low if verdict == "low" else advice_high)))

    slots = fp.get("slots", {})
    words = fp.get("n_words", 0)
    mid_n = slots.get("none", {}).get("n", 0)
    per = words / mid_n if mid_n else float("inf")
    check("words per mid-phrase pause", per, ref["words_per_midphrase_pause"],
          (6.0, 16.0),
          "pausing mid-phrase too often — it will sound hesitant, not thoughtful",
          "barely pausing except at punctuation: this is the main thing that "
          "reads as TTS. Insert breaks at the PREFER_SITES positions.")

    for slot, key in (("sentence", "sentence"), ("clause", "clause"), ("none", "midphrase")):
        s = slots.get(slot, {})
        if not s.get("n"):
            continue
        t = ref["pause_s"][key]
        check(f"{key} pause median (s)", s.get("median"), t["median"],
              (t["p25"], t["p75"]),
              f"{key} rests are short — the read will feel rushed and even",
              f"{key} rests are long — the read will drag")

    ratio = (slots.get("sentence", {}).get("median") or 0) / (slots.get("clause", {}).get("median") or 1)
    tgt_ratio = ref["pause_s"]["sentence"]["median"] / ref["pause_s"]["clause"]["median"]
    check("sentence:clause pause ratio", ratio, round(tgt_ratio, 2), (1.5, 2.8),
          "commas rest nearly as long as full stops — the flat-TTS signature",
          "commas are being skated over relative to full stops")

    check("silence ratio", fp.get("silence_ratio"), ref["silence_ratio"], (0.16, 0.25),
          "not enough air in the read", "too much dead space")
    check("speech wpm", fp.get("speech_wpm"), ref["speech_wpm"],
          (ref["speech_wpm"] * 0.90, ref["speech_wpm"] * 1.10),
          "slower than the reference", "faster than the reference")

    order = {"high": 0, "low": 0, "ok": 1}
    out.sort(key=lambda d: order[d.verdict])
    return out


def report(fp, target: str = DEFAULT_TARGET) -> str:
    devs = compare(fp, target)
    ref = REFERENCE[target]
    lines = [f"# take vs {ref['label']}", "",
             "| metric | take | target | acceptable band | |",
             "|---|---|---|---|---|"]
    for d in devs:
        mark = {"ok": "ok", "high": "HIGH", "low": "LOW"}[d.verdict]
        band = f"{d.band[0]}–{d.band[1]}" if d.band else ""
        lines.append(f"| {d.metric} | {d.take} | {d.target} | {band} | {mark} |")
    bad = [d for d in devs if d.verdict != "ok"]
    if bad:
        lines += ["", "## what to change"]
        lines += [f"- **{d.metric}** ({d.verdict}): {d.advice}" for d in bad]
    else:
        lines += ["", "Every metric is inside the reference band."]
    return "\n".join(lines)
