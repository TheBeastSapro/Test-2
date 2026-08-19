"""Author the pauses into a script before it is ever sent to the voice.

A TTS engine rests where the typesetting tells it to and nowhere else. The two
reference narrators rest once every ten words at positions with no punctuation
at all — and, just as consistently, refuse to rest at certain other positions
even though nothing in the text stops them. That difference is most of what
"sounds human" turns out to mean, and none of it is a voice-quality problem, so
none of it is fixable by re-rolling a take.

This module decides WHERE those rests go and HOW LONG they are, from the
measured site preferences in :mod:`vostudio.v2_profile`. It is deliberately
separate from rendering: placement is a fact about English and about the two
narrators, while the markup that expresses it is a fact about whichever engine
is being driven this month.

Determinism matters more than it looks. Every rest is drawn from a hash of the
sentence text and the token index, never from a global RNG, so the same script
always produces the same markup. A prep step that drifted between runs would
mean a re-render of one sentence no longer matches its neighbours — and under
the standing rule that every character sent has to be approved first, silently
changing the input is the expensive kind of bug.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from v2_profile import REFERENCE, DEFAULT_TARGET

_NLP = None


def _nlp():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


# Weights are the lifts measured across both reference channels, taking the
# WEAKER of the two so nothing here rests on a single narrator's habit. A site
# in VETO was below chance in both and is never used, however well it scores
# elsewhere: those are the positions where an inserted break stops sounding
# like thought and starts sounding like a dropped packet.
# Only ever consulted together with a part-of-speech test. Matching these as
# bare strings is wrong and was caught in testing: "for" is a conjunction in
# "for he had no choice" and a preposition in "stretched for 1,600 km", and the
# preposition reading is a position both narrators actively avoid resting at.
_CONNECTIVES = {"and", "but", "or", "so", "because", "then", "yet", "for"}


def _vetoed(prev, nxt) -> bool:
    """Positions both narrators steered around, each well below chance.

    Kept separate from scoring because a veto has to outrank every bonus,
    including the opt-in number emphasis — otherwise a numeral sitting just
    after a preposition drags a rest into the one place it must not go.
    """
    if prev.pos_ == "PART" or prev.text.lower() == "to":
        return True                                   # lift 0.53 / 0.14
    if prev.pos_ == "ADP":
        return True                                   # lift 0.72 / 0.31
    if prev.pos_ == "DET" and nxt.pos_ in ("NOUN", "PROPN"):
        return True                                   # lift 0.67 / 0.23
    if prev.pos_ == "PRON" and nxt.pos_ in ("VERB", "AUX"):
        return True                                   # lift 0.62 / 0.29
    if prev.pos_ == "VERB" and nxt.pos_ == "DET":
        return True                                   # lift 0.75 / 0.37
    if prev.pos_ == "AUX" and nxt.pos_ == "VERB":
        return True                                   # splits the verb group
    if nxt.pos_ == "ADP":
        return True                                   # strands the preposition
    if nxt.pos_ == "PART":
        return True                                   # splits infinitival "to work"
    # A degree modifier is glued to what it modifies: "too | heavy" and
    # "almost | certain" read as a stutter, not a beat. The measured
    # after-an-adverb preference (lift 1.46 / 1.30) is about adverbs that end a
    # phrase, not ones still reaching forward for their head.
    if prev.pos_ == "ADV" and nxt.pos_ in ("ADJ", "ADV") and prev.head == nxt:
        return True
    if nxt.pos_ == "PUNCT" or prev.pos_ == "PUNCT":
        return True
    return False


def _site_score(prev, nxt) -> float:
    """How much this boundary looks like one the references would rest at.

    A score above 1.0 built from the measured lifts; 0.0 means no measured
    preference. Not a probability — only the ordering is used. Vetoes are
    applied by the caller, not here.
    """
    score = 0.0
    if nxt.pos_ == "CCONJ":
        score = max(score, 1.78)                      # 1.78 / 3.55
    if nxt.pos_ in ("CCONJ", "SCONJ") and nxt.text.lower() in _CONNECTIVES:
        score = max(score, 1.84)                      # 1.84 / 3.48
    if prev.pos_ in ("NOUN", "PROPN") and nxt.pos_ in ("VERB", "AUX"):
        score = max(score, 1.50)                      # 1.50 / 2.23
    if prev.pos_ == "PROPN":
        score = max(score, 1.28)                      # 1.28 / 2.68
    if prev.pos_ == "ADV":
        score = max(score, 1.46)                      # 1.46 / 1.30
    if prev.pos_ == "NOUN":
        score = max(score, 1.29)                      # 1.29 / 1.59
    if nxt.pos_ == "AUX":
        score = max(score, 1.16)
    if nxt.ent_type_ == "DATE":
        score = max(score, 1.11)                      # 1.11 / 1.38
    if nxt.dep_ in ("advcl", "relcl", "ccomp", "conj", "acl"):
        score = max(score, 1.10)
    return score


def _number_bonus(nxt) -> float:
    """Agent Flappy's strongest single move, offered only when asked for.

    Pausing before a numeral scored a lift of 4.31 there — the largest effect
    measured in either channel — and did not appear at all in Serious History.
    Because the two disagree it is opt-in, and it is the right switch to throw
    on a script whose weight sits in figures, dates and totals.
    """
    return 4.31 if (nxt.like_num or nxt.pos_ == "NUM" or nxt.ent_type_ == "CARDINAL") else 0.0


def _jitter(key: str, lo: float, hi: float) -> float:
    """A stable value in [lo, hi], drawn from the text rather than from chance."""
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return round(lo + (hi - lo) * (h / 0xFFFFFFFF), 3)


@dataclass
class Rest:
    index: int          # insert AFTER the token at this index in the sentence
    seconds: float
    site: str           # why it was chosen — carried through for review
    score: float


@dataclass
class PreparedSentence:
    text: str
    rests: list = field(default_factory=list)
    words: int = 0


def _candidates(sent_text: str, emphasise_numbers: bool) -> list[tuple[float, int, str]]:
    """Every non-vetoed boundary in one sentence, with its measured score."""
    toks = [t for t in _nlp()(sent_text) if not t.is_space]
    out = []
    for i in range(len(toks) - 1):
        prev, nxt = toks[i], toks[i + 1]
        if prev.is_punct or nxt.is_punct:
            continue                     # punctuation has its own rest already
        if _vetoed(prev, nxt):
            continue                     # a veto outranks every bonus below
        s = _site_score(prev, nxt)
        if emphasise_numbers:
            s = max(s, _number_bonus(nxt))
        if s <= 0:
            continue
        site = f"{prev.pos_}>{nxt.pos_}"
        if nxt.pos_ in ("CCONJ", "SCONJ"):
            site += f" [{nxt.text.lower()}]"
        elif emphasise_numbers and _number_bonus(nxt):
            site += " [numeral]"
        out.append((s, i, site))
    out.sort(key=lambda c: (-c[0], c[1]))
    return out


def plan_sentence(sent_text: str, target: str = DEFAULT_TARGET,
                  emphasise_numbers: bool = False,
                  quota: int | None = None,
                  min_gap_words: int = 4) -> PreparedSentence:
    """Choose the mid-phrase rests for one sentence.

    Sites are taken in order of measured preference, subject to a minimum
    spacing so two rests never crowd each other.
    """
    ref = REFERENCE[target]
    band = ref["pause_s"]["midphrase"]
    toks = [t for t in _nlp()(sent_text) if not t.is_space]
    real = [t for t in toks if not t.is_punct]
    prepared = PreparedSentence(text=sent_text, words=len(real))

    if quota is None:
        quota = max(int(round(len(real) / ref["words_per_midphrase_pause"])), 0)
    if quota < 1:
        return prepared

    chosen: list[Rest] = []
    for s, i, site in _candidates(sent_text, emphasise_numbers):
        if len(chosen) >= quota:
            break
        if any(abs(i - r.index) < min_gap_words for r in chosen):
            continue
        chosen.append(Rest(index=i, seconds=_jitter(f"{sent_text}|{i}", band["p25"], band["p75"]),
                           site=site, score=round(s, 2)))
    chosen.sort(key=lambda r: r.index)
    prepared.rests = chosen
    return prepared


def plan_script(text: str, target: str = DEFAULT_TARGET,
                emphasise_numbers: bool = False,
                min_gap_words: int = 4) -> list[PreparedSentence]:
    """Plan a whole script, spending the rest budget across it as one pool.

    Allocating per sentence and rounding each one independently is what made
    the first version land at 15.6 words per rest against a target of 10.4:
    every sentence shorter than the rate silently rounded down to nothing, and
    the shortfall had nowhere to go. The budget is therefore computed once for
    the whole script and spent on the best-scoring sites wherever they are,
    which also matches the references — neither narrator distributes rests
    evenly by sentence.
    """
    ref = REFERENCE[target]
    sents = [s.text.strip() for s in _nlp()(text).sents if s.text.strip()]
    plans = [PreparedSentence(text=s, words=len([t for t in _nlp()(s) if not t.is_punct
                                                 and not t.is_space]))
             for s in sents]
    budget = int(round(sum(p.words for p in plans) / ref["words_per_midphrase_pause"]))
    if budget < 1:
        return plans

    pool = []
    for si, s in enumerate(sents):
        for score, i, site in _candidates(s, emphasise_numbers):
            pool.append((score, si, i, site))
    pool.sort(key=lambda c: (-c[0], c[1], c[2]))

    band = ref["pause_s"]["midphrase"]
    taken = 0
    for score, si, i, site in pool:
        if taken >= budget:
            break
        rests = plans[si].rests
        if any(abs(i - r.index) < min_gap_words for r in rests):
            continue
        rests.append(Rest(index=i, seconds=_jitter(f"{sents[si]}|{i}", band["p25"], band["p75"]),
                          site=site, score=round(score, 2)))
        taken += 1
    for p in plans:
        p.rests.sort(key=lambda r: r.index)
    return plans


# --------------------------------------------------------------------------
# rendering — the only part that knows what engine is on the other end
# --------------------------------------------------------------------------

def render_break_tags(plans: list[PreparedSentence]) -> str:
    """Express the plan as ``<break time="…s" />`` markup."""
    out = []
    for p in plans:
        toks = [t.text_with_ws for t in _nlp()(p.text)]
        by_index = {r.index: r for r in p.rests}
        buf = ""
        for i, tok in enumerate(toks):
            buf += tok
            if i in by_index:
                buf = buf.rstrip() + f' <break time="{by_index[i].seconds}s" /> '
        out.append(buf.strip())
    return "\n\n".join(out)


def render_review(plans: list[PreparedSentence]) -> str:
    """A human-readable plan: what was chosen, where, and why."""
    lines = []
    total_rests = sum(len(p.rests) for p in plans)
    total_words = sum(p.words for p in plans)
    lines.append(f"{len(plans)} sentences, {total_words} words, {total_rests} "
                 f"mid-phrase rests — one every "
                 f"{total_words / total_rests:.1f} words"
                 if total_rests else
                 f"{len(plans)} sentences, {total_words} words, no rests placed")
    lines.append("")
    for p in plans:
        if not p.rests:
            continue
        toks = [t.text for t in _nlp()(p.text) if not t.is_space]
        for r in p.rests:
            left = " ".join(toks[max(0, r.index - 4): r.index + 1])
            right = " ".join(toks[r.index + 1: r.index + 4])
            lines.append(f"  {r.seconds:.3f}s  …{left} ⟨rest⟩ {right}…   "
                         f"[{r.site}, lift {r.score}]")
    return "\n".join(lines)
