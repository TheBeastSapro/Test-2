"""Where do the mid-phrase pauses actually land?

Preserved as the record of how the PREFER_SITES / AVOID_SITES tables in
``v2_profile.py`` were derived. It reads the caption files this analysis ran
on, which lived in a working directory that did not survive the session — point
the paths in ``main()`` at fresh ones to re-run it.

The styleprint fingerprint says both reference narrators stop roughly once
every ten words at a position with no punctuation. That is the single
loudest difference from TTS, which only ever rests where the typesetting tells
it to. But "pause mid-phrase" is not yet a rule you can apply — this script
finds WHICH syntactic positions those pauses prefer.

Everything is reported as LIFT, not as a raw count: the share of pauses that
land at a position, divided by that position's share of all word boundaries.
Lift 2.0 means the narrator stops there twice as often as chance. Raw counts
alone would just rediscover which parts of speech are common.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/home/user/Test-2/vo-studio")
import spacy
from vostudio import styleprint as sp

NLP = spacy.load("en_core_web_sm")
MIN_PAUSE = 0.10          # a mid-phrase gap this short is still audible as a beat


def analyse(caption_path: str, label: str) -> dict:
    words = sp.load_json3(caption_path)

    # Index the pause following each word, rebuilt by walking pairs the same
    # way styleprint does rather than by matching timestamps back to it.
    pause_after = {}
    from vostudio.styleprint import _expected_duration_model
    model = _expected_duration_model(words)
    for i, (a, b) in enumerate(zip(words, words[1:])):
        gap = (b.t - a.t) - model(len(a.bare))
        if gap >= MIN_PAUSE:
            pause_after[i] = gap

    text = " ".join(w.text for w in words)
    doc = NLP(text)

    # align spacy tokens back onto caption words by consuming characters
    toks = [t for t in doc if not t.is_space]
    aligned = []
    ti = 0
    for w in words:
        need = w.text.strip()
        buf = ""
        start_ti = ti
        while ti < len(toks) and len(buf) < len(need):
            buf += toks[ti].text
            ti += 1
        aligned.append(toks[start_ti] if ti > start_ti else None)

    site_all = Counter()
    site_paused = Counter()
    site_durs = defaultdict(list)

    for i in range(len(words) - 1):
        cur, nxt = aligned[i], aligned[i + 1]
        if cur is None or nxt is None:
            continue
        if words[i].slot != "none":          # punctuated boundaries are a separate story
            continue

        feats = []
        feats.append(f"before:{nxt.pos_}")
        feats.append(f"after:{cur.pos_}")
        feats.append(f"pair:{cur.pos_}>{nxt.pos_}")
        if nxt.ent_type_:
            feats.append(f"before-entity:{nxt.ent_type_}")
        if nxt.pos_ in ("PROPN",):
            feats.append("before:PROPER-NOUN")
        if nxt.like_num or nxt.pos_ == "NUM":
            feats.append("before:NUMBER")
        if nxt.dep_ in ("nsubj", "nsubjpass"):
            feats.append("before:SUBJECT")
        if nxt.pos_ in ("VERB", "AUX"):
            feats.append("before:VERB")
        if nxt.text.lower() in ("and", "but", "or", "so", "because", "then",
                                "when", "while", "which", "that", "who", "as",
                                "before", "after", "until"):
            feats.append(f"before-connective:{nxt.text.lower()}")
        if cur.dep_ in ("nsubj", "nsubjpass"):
            feats.append("after:SUBJECT")
        if cur.pos_ == "ADP":
            feats.append("after:PREPOSITION")
        if nxt.pos_ == "ADP":
            feats.append("before:PREPOSITION")
        if nxt.pos_ == "ADJ":
            feats.append("before:ADJECTIVE")
        # is the next token starting a new clause? (its head is to the right)
        if nxt.dep_ in ("advcl", "relcl", "ccomp", "conj", "acl"):
            feats.append("before:NEW-CLAUSE")

        for f in feats:
            site_all[f] += 1
            if i in pause_after:
                site_paused[f] += 1
                site_durs[f].append(pause_after[i])

    total_slots = sum(1 for i in range(len(words) - 1) if words[i].slot == "none")
    total_paused = sum(1 for i in pause_after if words[i].slot == "none")
    base = total_paused / max(total_slots, 1)

    rows = []
    for f, n in site_all.items():
        if n < 40:
            continue
        k = site_paused[f]
        rate = k / n
        durs = sorted(site_durs[f])
        rows.append({
            "site": f, "boundaries": n, "paused": k,
            "rate": round(rate, 3), "lift": round(rate / base, 2),
            "median_pause": round(durs[len(durs) // 2], 3) if durs else None,
        })
    rows.sort(key=lambda r: -r["lift"])
    return {
        "label": label,
        "unpunctuated_boundaries": total_slots,
        "of_which_paused": total_paused,
        "base_rate": round(base, 3),
        "one_pause_every_n_words": round(len(words) / max(total_paused, 1), 1),
        "sites": rows,
    }


def main():
    out = {}
    for path, label in [("/home/user/Test-2/.work/ref/sNMDXA8Qcts.en.json3", "A_SeriousHistory"),
                        ("/home/user/Test-2/.work/ref/3GKC4kC3iQ0.en.json3", "B_AgentFlappy")]:
        out[label] = analyse(path, label)

    Path("/home/user/Test-2/.work/analysis/pause-sites.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")

    for label, r in out.items():
        print(f"\n=== {label} ===")
        print(f"unpunctuated boundaries: {r['unpunctuated_boundaries']}, "
              f"paused at {r['of_which_paused']} of them "
              f"(base rate {r['base_rate']:.1%}); "
              f"one mid-phrase pause every {r['one_pause_every_n_words']} words")
        print(f"{'site':<34}{'n':>6}{'paused':>8}{'rate':>8}{'lift':>7}{'med_s':>8}")
        for row in r["sites"][:18]:
            print(f"{row['site']:<34}{row['boundaries']:>6}{row['paused']:>8}"
                  f"{row['rate']:>8.2f}{row['lift']:>7.2f}{(row['median_pause'] or 0):>8.3f}")

    # agreement between the two narrators — a rule only counts if both do it
    a = {r["site"]: r["lift"] for r in out["A_SeriousHistory"]["sites"]}
    b = {r["site"]: r["lift"] for r in out["B_AgentFlappy"]["sites"]}
    shared = [(s, a[s], b[s]) for s in a if s in b]
    shared.sort(key=lambda x: -min(x[1], x[2]))
    print("\n=== sites BOTH narrators favour (sorted by weaker of the two lifts) ===")
    print(f"{'site':<34}{'lift A':>9}{'lift B':>9}")
    for s, la, lb in shared[:15]:
        print(f"{s:<34}{la:>9.2f}{lb:>9.2f}")
    print("\n=== sites BOTH narrators AVOID ===")
    shared.sort(key=lambda x: max(x[1], x[2]))
    for s, la, lb in shared[:8]:
        print(f"{s:<34}{la:>9.2f}{lb:>9.2f}")


if __name__ == "__main__":
    main()
