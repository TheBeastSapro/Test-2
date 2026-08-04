"""Keeping the same person the same person from shot four to shot sixty.

## The failure

A script says "a 70-year-old grandmother in a beige cardigan" in scene two, "the
grandmother" in scene seven, and "she" in scene eleven. The shot planner writes each
visual prompt independently, so scene seven's generated person is a different
seventy-year-old and scene eleven's is a third.

It is the single most obvious tell that a machine made a narrative video, and it is
obvious in a way the other tells are not. A viewer who cannot say why a grade looks wrong
will say immediately that the woman in the kitchen is not the woman at the window. Faces
are the thing people track; they have been doing it since before they could read.

## Why a locked description and not a locked seed

The obvious fix is to fix the seed, and it does not work.

A seed locks a model's *noise*, not a person. Two prompts with the same seed and different
words produce two different people, and the words necessarily differ between shots —
that is what makes them different shots. Seeds hold a face still only when everything else
is already identical, which is the case where you did not have a problem.

A seed is also per-model, and this app now routes per shot: the opening runs on the hero
model and the batch on the cheap one, so a seed lock is lost at exactly the cut where
identity matters most. A written description survives a model change, a vendor change, and
a re-render six months later.

So a character is a **string that is reused verbatim**. Verbatim is the operative word:
paraphrase is how the drift happens, and a planner asked to "describe her consistently"
will produce eleven consistent-sounding descriptions of eleven different women.

## Why only some subjects get locked

Not every noun. A city street does not need to be the same city street — nobody is
tracking it, and locking it spends prompt budget on something invisible. Faces are what
viewers track, so the cast is people and animals.

And a subject appearing in one scene only cannot be inconsistent with itself, so it is not
locked either. That is not a saving for its own sake: every locked character costs words
in every prompt that includes them, and a prompt carrying twelve descriptions has pushed
the actual shot out of the model's attention.

## What this does not do

It does not generate reference images, and it does not call a vendor. `providers/
higgsfield.py` exists for identity as a *service*, and `fal-ai/veo3.1/reference-to-video`
takes up to three reference images — both are strictly better than words when they are
available and configured. This is the floor that works on every model, with no key and no
extra call, and it is what the other two build on rather than a competitor to them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A description shorter than this is a label, not a likeness — "an old woman" produces a
# different old woman every time, which is the whole failure. The i2v skill says specific
# prompts land on the first try about 85% of the time against roughly 30% for vague ones;
# for a recurring face that difference compounds across every shot they appear in.
MIN_DESCRIPTION_WORDS = 6

# Past this a description stops being a likeness and starts being a biography, and it
# crowds the shot out of its own prompt. Twelve to thirty words is a face.
MAX_DESCRIPTION_WORDS = 40

# Below this many appearances there is nothing to be inconsistent with.
LOCKS_FROM_APPEARANCES = 2

# More faces than this in one video is not a cast, it is a crowd — and it is a sign the
# script is naming people it does not return to. Locking all of them would put a hundred
# words of cast into every prompt.
MAX_CAST = 6

# The traits a likeness needs to hold still. Not a schema the model must fill — a
# checklist for `thin_description`, which warns rather than rejects, because a character
# who is genuinely just "a silhouette in a doorway" is legitimately described in four
# words and should not be blocked by a rule written for faces.
LIKENESS_TRAITS = (
    "age", "hair", "clothing", "build", "face", "skin", "eyes", "beard",
    "glasses", "uniform", "coat", "jacket", "dress", "shirt", "hat", "scarf",
    "cardigan", "suit", "years old", "young", "elderly", "middle-aged",
)

# Letters and digits in any script, not `[a-z]+`.
#
# `[a-z]+` was the first version and it dropped two whole classes of name silently. Digits
# went first — "Agent 47" and "Flight 191" keyed as "agent" and "flight", so two of them
# in one script merged into one character. Then the serious one: every name written in a
# non-Latin script produced *no words at all*, so it keyed to empty and was discarded
# before it could be locked. This app carries a `language` per channel, so an Arabic,
# Hindi, Russian or Japanese channel would have had no character consistency whatsoever
# and nothing anywhere would have said so.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# Words that identify nobody, so a name reduced to only these matches nothing rather than
# matching everything. Honorifics are here for a specific reason: "Dr" left in would make
# every doctor in a script the same doctor, which is the failure this module is for,
# inverted.
_NOT_DISTINCTIVE = frozenset({
    "the", "a", "an", "of", "and", "her", "his", "their", "our", "its",
    "dr", "doctor", "mr", "mrs", "ms", "miss", "sir", "lord", "lady",
    "prof", "professor", "captain", "officer", "president", "young", "old",
})


@dataclass(frozen=True)
class Character:
    """One recurring subject, and the words that keep them the same person."""

    key: str
    #: What the script calls them — "the grandmother", "Dr Reyes".
    name: str
    #: The locked likeness. Reused verbatim in every prompt they appear in.
    description: str
    #: Scene indexes they appear in. Ordered, and the reason they are locked at all.
    scenes: tuple[int, ...] = ()

    @property
    def appearances(self) -> int:
        return len(self.scenes)

    def as_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "description": self.description,
                "scenes": list(self.scenes), "appearances": self.appearances}


@dataclass
class Cast:
    """Everyone a video has to keep consistent, and nobody else."""

    characters: list[Character] = field(default_factory=list)
    #: Named subjects that appear once and are therefore deliberately not locked. Kept
    #: so the decision is visible: an operator asking why the man in scene nine drifted
    #: should find "he appears once" rather than nothing at all.
    walk_ons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.characters)

    def by_key(self, key: str) -> Character | None:
        return next((one for one in self.characters if one.key == key), None)

    def in_scene(self, index: int) -> list[Character]:
        return [one for one in self.characters if index in one.scenes]

    def as_dict(self) -> dict:
        return {"characters": [one.as_dict() for one in self.characters],
                "walk_ons": list(self.walk_ons)}


def _key(name: str) -> str:
    """A stable handle for a name the script may write several ways.

    Lowercased words only, so "The Grandmother", "the grandmother," and "Grandmother"
    are one character rather than three — which is the same drift this module exists to
    stop, occurring in the bookkeeping instead of in the pictures.
    """
    words = _WORD.findall(str(name or "").lower())
    return "_".join(word for word in words if word not in {"the", "a", "an"})[:48]


def thin_description(description: str) -> str:
    """Why this description will not hold a face still, or empty if it will.

    A warning rather than a refusal. A character who really is "a silhouette in a
    doorway" is correctly described in four words, and a rule written for faces should
    not block one — but the operator should be told, because the far more common cause of
    a four-word description is a planner that did not try.
    """
    words = str(description or "").split()
    if not words:
        return "no description at all, so every shot will invent one"
    if len(words) < MIN_DESCRIPTION_WORDS:
        return (f"only {len(words)} words — a label rather than a likeness, so each shot "
                f"will render a different person")
    if len(words) > MAX_DESCRIPTION_WORDS:
        return (f"{len(words)} words — a biography rather than a likeness, and it will "
                f"crowd the shot out of its own prompt")

    lowered = description.lower()
    if not any(trait in lowered for trait in LIKENESS_TRAITS):
        return ("names no physical trait — age, hair, build or clothing — so there is "
                "nothing in it for the model to hold still")
    return ""


def build(raw: object, scenes: list[dict] | None = None) -> Cast:
    """The cast, from whatever the script stage produced.

    Tolerant of shape on purpose. This reads a language model's output, and a planner
    that returns a list of strings, a dict keyed by name, or a list of objects with
    slightly different field names is not a bug worth failing a paid run over — the
    script itself is already written and approved by the time this runs.
    """
    entries: list[dict] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, dict):
                entries.append({"name": name, **value})
            else:
                entries.append({"name": name, "description": str(value)})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                entries.append(item)

    seen: dict[str, dict] = {}
    for entry in entries:
        name = str(entry.get("name") or entry.get("who") or entry.get("character") or "")
        key = _key(name)
        if not key:
            continue
        description = str(entry.get("description") or entry.get("appearance")
                          or entry.get("look") or "").strip()
        found = _scenes_for(entry, name, scenes)
        if key in seen:
            # The same character named twice. Keep the fuller description and merge the
            # scene lists rather than letting the second entry win: a model that lists
            # someone twice usually describes them well once.
            previous = seen[key]
            if len(description.split()) > len(previous["description"].split()):
                previous["description"] = description
            previous["scenes"] = sorted(set(previous["scenes"]) | set(found))
            continue
        seen[key] = {"key": key, "name": name.strip(), "description": description,
                     "scenes": sorted(found)}

    locked: list[Character] = []
    walk_ons: list[str] = []
    for row in seen.values():
        if len(row["scenes"]) < LOCKS_FROM_APPEARANCES:
            walk_ons.append(row["name"])
            continue
        locked.append(Character(key=row["key"], name=row["name"],
                                description=row["description"],
                                scenes=tuple(row["scenes"])))

    # The most-seen faces first, so the cap keeps the people a viewer will actually
    # track rather than whoever the model happened to list first.
    locked.sort(key=lambda one: (-one.appearances, one.key))
    if len(locked) > MAX_CAST:
        walk_ons.extend(one.name for one in locked[MAX_CAST:])
        locked = locked[:MAX_CAST]
    return Cast(characters=locked, walk_ons=walk_ons)


def _scenes_for(entry: dict, name: str, scenes: list[dict] | None) -> list[int]:
    """Which scenes a character is in — from the entry if it said, else from the script.

    Read from the narration as a fallback because a model asked for a cast list will
    often give names and descriptions and no scene numbers. Matching on the name's
    distinctive word rather than the whole phrase: a script that introduces "Dr Elena
    Reyes" and thereafter writes "Reyes" would otherwise show one appearance and be
    dropped as a walk-on — which is the exact character most worth locking.
    """
    stated = entry.get("scenes") or entry.get("scene_indexes") or entry.get("appears_in")
    if isinstance(stated, list) and stated:
        out: list[int] = []
        for value in stated:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
        if out:
            return out

    if not scenes:
        return []

    words = [word for word in _WORD.findall(name.lower())
             if word not in _NOT_DISTINCTIVE and len(word) > 2]
    if not words:
        # Nothing distinctive enough to search for. Common with names written in scripts
        # where a word is one or two characters — plenty of Chinese and Japanese names
        # are two — so falling back to the whole cleaned name is what keeps them findable
        # rather than dropped. The length rule exists to stop "the" and "dr" matching
        # everything, and a two-character name is not that problem.
        whole = " ".join(_WORD.findall(name.lower()))
        if not whole:
            return []
        words = [whole]

    # *Any* distinctive word, not the longest one. Taking the longest looked right and
    # was wrong on the case this fallback exists for: a script that introduces "Dr Elena
    # Reyes" and thereafter writes "Reyes" matched on "elena", found her once, and
    # dropped her as a walk-on — the exact character most worth locking, discarded by the
    # code meant to catch her.
    #
    # On word boundaries, because a substring match makes "reyes" hit "reyeswood" and,
    # worse, makes a two-letter honorific that slipped the filter match half the script.
    pattern = re.compile(r"\b(" + "|".join(re.escape(word) for word in words) + r")\b")
    found: list[int] = []
    for position, scene in enumerate(scenes):
        haystack = (f"{scene.get('narration', '')} "
                    f"{scene.get('visual_prompt', '')}").lower()
        if pattern.search(haystack):
            found.append(int(scene.get("index", position)))
    return found


def stamp(prompt: str, characters: list[Character]) -> str:
    """Put the locked likenesses into one shot's prompt.

    Appended rather than substituted into the sentence. Rewriting the planner's prose to
    splice a description in is a second generation of paraphrase — the thing this module
    exists to prevent — and it also breaks the prompt skeleton the i2v skill specifies,
    where subject, action, camera, lighting and mood each occupy their own clause.

    Only the characters in this shot, and that is not an optimisation. Every locked face
    costs words in every prompt carrying it, and a prompt holding six descriptions has
    pushed its own subject out of the model's attention.
    """
    text = str(prompt or "").strip()
    usable = [one for one in characters if one.description.strip()]
    if not usable:
        return text
    block = " ".join(f"{one.name.strip().rstrip('.')}: {one.description.strip().rstrip('.')}."
                     for one in usable)
    if not text:
        return block
    return f"{text.rstrip('.')}. {block}"


def planner_block(cast: Cast) -> str:
    """The cast handed to the shot planner, so it writes to the locked descriptions.

    Given to the planner as well as stamped onto the prompt afterwards, which reads like
    belt and braces and is not. Stamping alone leaves the planner free to write "an older
    woman looks up" for a character locked as a seventy-year-old — the prompt then carries
    two descriptions of one person and the model resolves the contradiction however it
    likes. Telling the planner up front is what stops the contradiction being written.
    """
    if not cast:
        return ""
    lines = ["RECURRING CHARACTERS. These people appear in more than one shot and must "
             "look identical in all of them. Use each description exactly as written — "
             "do not paraphrase it, shorten it, or 'improve' it. Naming a character in a "
             "shot means their whole description goes in that shot's prompt.", ""]
    for one in cast.characters:
        where = ", ".join(str(index) for index in one.scenes)
        lines.append(f"  {one.name} — {one.description}")
        lines.append(f"    appears in scenes: {where}")
    if cast.walk_ons:
        lines += ["", "Everyone else appears once and needs no consistency: "
                  + ", ".join(cast.walk_ons)]
    return "\n".join(lines)


#: Appended to the script stage's instructions, so the cast comes out of the call that
#: already has the whole script in front of it rather than a second paid LLM round trip.
SCRIPT_INSTRUCTION = """
Also return a "cast" array: every person or animal that appears in MORE THAN ONE scene.

For each one give:
  - "name": what the narration calls them ("the grandmother", "Dr Reyes")
  - "description": a physical likeness of 12-30 words, specific enough that two different
    illustrators would draw the same person. Age, hair, build, clothing. Not their role,
    not their mood, not what they are doing — those change from shot to shot and the
    likeness must not.
  - "scenes": the scene indexes they appear in

Leave the array empty if nobody recurs. Do not list places, objects or crowds — only
subjects with a face, because those are the ones a viewer notices changing.
""".strip()
