#!/usr/bin/env python3
"""
The pronunciation lexicon — names the voice gets wrong, and how to spell them
so it gets them right.

Why respelling and not phonemes. ElevenLabs' pronunciation dictionaries take two
kinds of rule, and the docs are explicit about the split:

    "Pronunciation dictionary phoneme tags only work with eleven_flash_v2 and
     eleven_v3 models. Other models skip dictionary phoneme tags and use the
     default pronunciation. For other models, use alias tags instead to
     substitute spellings or phrases that produce the pronunciation you need."

The channel runs on eleven_multilingual_v2 — chosen for accuracy, and the one
model where a phoneme rule does nothing. It is not rejected, it is *skipped*: a
carefully written IPA string produces the same wrong reading as before, with no
error to tell you. So this works by alias, which every model honours.

Substitution happens on the way to the API only. The script text used for the
read-check and for the mastering alignment keeps the real spelling, so the
transcript is still compared against the word Sapro actually wrote.
"""
import json
import os
import re
import sys

# Models that honour phoneme rules. Anything else silently ignores them.
PHONEME_MODELS = {"eleven_flash_v2", "eleven_v3"}

# An entry that looks like IPA or CMU rather than a respelling.
_IPA_HINT = re.compile(r"[ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶʘɹɺɾɻʀʁ"
                       r"ɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑ]|^[A-Z]{1,3}\d\b")


def log(m):
    print(f"[pronounce] {m}", flush=True)


def load_lexicon(path):
    """-> {word: respelling}. Missing file is fine — most scripts need nothing."""
    if not path or not os.path.isfile(path):
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    entries = raw.get("words", raw) if isinstance(raw, dict) else {}
    return {k: str(v) for k, v in entries.items() if not k.startswith("_")}


def check_lexicon(lex, model):
    """Warn about entries that will be silently ignored on this model."""
    if model in PHONEME_MODELS:
        return []
    bad = [w for w, a in lex.items() if _IPA_HINT.search(a)]
    for w in bad:
        log(f"WARNING: “{w}” → “{lex[w]}” looks like a phoneme string, and {model} "
            f"skips phoneme rules silently. Respell it instead "
            f"(e.g. “Angolpo” → “An-gol-poh”).")
    return bad


def apply(text, lex):
    """-> (text with aliases substituted, {word: count}).

    Whole words only, so a lexicon entry for 'Hiero' cannot corrupt 'hierarchy'.
    """
    used = {}
    if not lex:
        return text, used
    # longest first, so a multi-word entry wins over its own first word
    for word in sorted(lex, key=len, reverse=True):
        pat = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.I)
        text, n = pat.subn(lex[word], text)
        if n:
            used[word] = used.get(word, 0) + n
    return text, used


def apply_to_sections(sections, lex):
    """Rewrite send_text in place; leave `text` alone so everything downstream
    still sees the real script. Returns {word: total count}."""
    total = {}
    for sec in sections:
        new, used = apply(sec["send_text"], lex)
        if used:
            sec["send_text"] = new
            sec["chars"] = len(new)     # a respelling is longer, and it is billed
            sec["spoken_as"] = used
            for w, n in used.items():
                total[w] = total.get(w, 0) + n
    return total


def candidates_from_check(check_json):
    """Turn the read-check's settled mismatches into lexicon starter entries.

    A word the voice renders identically on two separate takes is exactly the
    thing a lexicon is for — the transcriber is not going to change its mind, and
    neither is the voice.
    """
    d = json.load(open(check_json, encoding="utf-8"))
    out = {}
    for r in d.get("results", []):
        for exp, heard in r.get("settled", []):
            out.setdefault(exp, heard)
    return out


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Inspect or seed the pronunciation lexicon.")
    ap.add_argument("--lexicon")
    ap.add_argument("--model", default="eleven_multilingual_v2")
    ap.add_argument("--text", help="show what would be sent for this text")
    ap.add_argument("--from-check", help="readcheck.json — print lexicon candidates")
    a = ap.parse_args()

    if a.from_check:
        cand = candidates_from_check(a.from_check)
        if not cand:
            print("no consistently-misread words in that run")
            return 0
        print("Words the voice rendered the same way on two takes. Decide which are\n"
              "real mispronunciations, then set a respelling for each:\n")
        print(json.dumps({"words": {w: f"<respell — transcriber heard “{h}”>"
                                    for w, h in cand.items()}}, indent=2, ensure_ascii=False))
        return 0

    lex = load_lexicon(a.lexicon)
    print(f"{len(lex)} entries; model {a.model} "
          f"({'honours' if a.model in PHONEME_MODELS else 'SKIPS'} phoneme rules)")
    check_lexicon(lex, a.model)
    for w, v in sorted(lex.items()):
        print(f"  {w!r} -> {v!r}")
    if a.text:
        out, used = apply(a.text, lex)
        print(f"\nsent to the API:\n  {out}")
        print(f"substituted: {used or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
