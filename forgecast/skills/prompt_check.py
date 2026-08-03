"""Reads an image-to-video prompt and reports what will melt before it is submitted.

`data/i2v-prompt-cookbook.md` carries a verb bank in three tiers and six anti-pattern
diagnoses. The forbidden tier "almost always melts", which in this app means a provider
submission that is billed in full and thrown away — image-to-video is the most expensive
operation in the pipeline, so a prompt that was going to fail is money already gone. The
document can only help when it was loaded; this runs whether it was or not.

## What comes back, and why it is never a boolean

Every check returns a `Finding` naming the words that triggered it and what to do instead.
A checker that answers False teaches the caller to strip words until it answers True, and
what gets stripped is whichever half of the prompt was load-bearing. "Two focal verbs —
'walks' and 'opens'; split into two clips" can be acted on. `False` cannot.

## The one-verb rule, which is the hard one

The cookbook says one verb per prompt, and its own strongest examples contain three:
"slowly closes a manila folder, pauses, looks just past the camera". Counting verbs flags
every good example in the document and the rule becomes noise.

Reading the examples against the anti-patterns, what separates them is grammatical rather
than numeric. The anti-patterns chain *finite* verbs into a sequence the model has to pick
one of — "walks to the door, opens it, steps outside, and waves", "reaches for the phone,
picks it up, dials". The good examples use one finite action and put everything else in
participles, which describe one continuous motion rather than a next step: "sliding open,
revealing rows of folders, pulling out one, laying it flat". The cookbook's own shot
template says as much — "[single action]; [secondary micro-expression]" — so the grammar
the templates already use is the rule this implements:

* one finite action verb is fine, and micro-expressions (`pauses`, `looks`, `nods`) and
  postures (`sits`, `stands`) do not count against it, because the shot templates ask for
  them alongside the action;
* participles are one motion, not a chain;
* environmental motion is free, exactly as the document says — leaves drifting and a flag
  swaying are handled by the model separately from the subject's action;
* camera moves are not actions, so they are removed before counting.

This is a heuristic over English, and it will be wrong sometimes. It is wrong in the
cheap direction: a warning on a good prompt costs a glance, and a missed forbidden verb
costs a render.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ------------------------------------------------------------------------- the banks

# Word forms rather than stems, because a stem match here is how "fallen leaves drifting"
# — from the document's own establishing-shot example — reads as the risky verb "falls".
_words = lambda *forms: r"\b(?:" + "|".join(forms) + r")\b"  # noqa: E731

# The cookbook's forbidden tier, plus the verbs `image-to-video.md` lists under "verbs
# that fail" that the cookbook does not tier at all. Merged deliberately: both documents
# describe the same outcome — output that cannot be used — and a checker that only knew
# one list would pass `transforms` and `speaks` at full price. Lip sync is the reason
# `speaks` is here: the skill's instruction is a lip-closed shot with the audio overlaid.
FORBIDDEN: tuple[tuple[str, str, str], ...] = (
    (_words("fight", "fights", "fighting", "fought"), "fights",
     "multi-limb contact between subjects melts limbs on every model"),
    (_words("kiss", "kisses", "kissing"), "kisses", "two faces in contact deform both"),
    (_words("hug", "hugs", "hugging", "hugged"), "hugs", "overlapping bodies merge"),
    (_words("climb", "climbs", "climbing"), "climbs",
     "hands and feet leaving surfaces produce extra limbs"),
    (_words("swim", "swims", "swimming"), "swims", "water plus body is unpredictable"),
    (_words("jump", "jumps", "jumping", "leap", "leaps", "leaping"), "jumps",
     "push-off plus gravity plus body melts, where 'falls' alone survives"),
    (_words("shave", "shaves", "shaving"), "shaves", "tool against a face deforms it"),
    (_words("speak", "speaks", "speaking", "says"), "speaks",
     "lip sync is unreliable — use a lip-closed shot and overlay the audio"),
    (r"\btalk(?:s|ing)?\b(?!\s*-?\s*head)", "talks",
     "lip sync is unreliable — use a lip-closed shot and overlay the audio"),
    (_words("disappear", "disappears", "disappearing", "vanish", "vanishes", "vanishing"),
     "disappears", "the model has no way to render an absence"),
    (_words("transform", "transforms", "transforming", "morph", "morphs", "morphing"),
     "transforms", "identity is not preserved across a transformation"),
    (_words("multiply", "multiplies", "multiplying", "replicate", "replicates",
            "replicating"), "multiplies", "duplicated subjects come back malformed"),
    (r"\b(?:plays?|playing)\s+(?:\w+\s+){0,2}?"
     r"(?:sports?|football|soccer|basketball|tennis|golf)\b", "plays sports",
     "whole-body athletic motion is the worst case for every model"),
    (r"\b(?:performs?|performing)\s+surgery\b", "performs surgery",
     "fine hand work on a body deforms both"),
    (r"\b(?:operates?|operating)\s+(?:a\s+|the\s+)?machin\w*", "operates machinery",
     "hands plus moving mechanism produces neither correctly"),
    (r"\b(?:writes?|writing)\s+(?:out\s+)?(?:a\s+|the\s+)?"
     r"(?:paragraph|paragraphs|sentence|sentences|essay|note|notes)\b",
     "writes paragraphs", "rendered handwriting warps; add text in post"),
    (r"\b(?:cuts?|cutting)\s+(?:\w+\s+){0,2}?hair\b", "cuts hair",
     "tool against a head deforms the head"),
    (_words("choreography", "choreographed"), "complex choreography",
     "multi-beat body motion desynchronises"),
)

# The risky tier. Allowed, and warned about, because the document permits them under
# conditions a regex cannot check — "single subject, single direction, clear duration".
RISKY: tuple[tuple[str, str, str], ...] = (
    (_words("run", "runs", "running"), "runs", "lock the direction"),
    (_words("throw", "throws", "throwing"), "throws", "one object only"),
    (_words("drive", "drives", "driving"), "drives",
     "static car with a motion-blurred background"),
    (_words("fall", "falls", "falling"), "falls",
     "one object on a linear trajectory"),
    (_words("crash", "crashes", "crashing"), "crashes",
     "into stationary objects only"),
    (_words("smile", "smiles", "smiling"), "smiles", "slight only"),
    (_words("cry", "cries", "crying"), "cries", "a single tear"),
    (_words("argue", "argues", "arguing", "yell", "yells", "yelling"), "argues",
     "one person only"),
    (_words("dance", "dances", "dancing"), "dances",
     "slow, and name the move — 'ballet pirouette' beats 'dance'"),
    (_words("fly", "flies", "flying"), "flies", "objects, not people"),
    (_words("cook", "cooks", "cooking"), "cooks", "one steady action"),
)

# Finite third-person forms that count as the shot's action. Kept as a list of forms
# rather than derived, so that adding one is a decision somebody made rather than a
# side effect of a suffix rule.
PRIMARY_FINITE = frozenset({
    "walks", "opens", "closes", "sets", "picks", "reads", "writes", "signs", "pours",
    "reaches", "grabs", "steps", "waves", "dials", "lifts", "lowers", "drops", "slides",
    "types", "points", "hands", "places", "carries", "knocks", "slams", "enters",
    "exits", "throws", "runs", "drives", "falls", "crashes", "cries",
    "argues", "yells", "dances", "flies", "cooks", "fights", "kisses", "hugs",
    "climbs", "swims", "jumps", "shaves", "speaks", "talks", "unfolds",
})
# "leaves" is absent deliberately. It is a verb, and in these prompts it is almost always
# the noun — the establishing-shot template's own example has leaves drifting across a
# lawn — so counting it as an action flagged the document's good example as multi-action.
# The clean tier spells the departure as "walks slowly away from" anyway.

# Micro-expressions. The cookbook's hook-close-up template asks for one of these
# *alongside* the action ("[single action]; [secondary micro-expression]"), so counting
# them as competing verbs would flag the document's own best example.
MICRO_FINITE = frozenset({
    "looks", "glances", "pauses", "hesitates", "nods", "shakes", "furrows", "raises",
    "blinks", "widens", "tightens", "narrows", "breathes", "sighs", "frowns", "smiles",
    "shifts", "waits",
})

# Postures, which belong to the SUBJECT field: they say where the subject is, not what
# happens next. "sits at a kitchen table reading a letter" is one action, not two.
POSTURE_FINITE = frozenset({
    "sits", "stands", "lies", "leans", "kneels", "rests", "holds", "wears", "remains",
    "sitting", "standing",
})

# Camera language, stripped before any verb counting: a push-in is not something the
# subject does. Also the vocabulary the camera-contradiction check reads.
CAMERA_MOVE = (
    r"push(?:es|ing)?[-\s]?in|pull(?:s|ing)?[-\s]?(?:back|out)|truck(?:s|ing)?[-\s]"
    r"(?:left|right)|pan(?:s|ning)?[-\s](?:left|right)|whip[-\s]?pan|pan(?:s|ning)?\b|"
    r"tilt(?:s|ing)?[-\s](?:up|down)|dolly|dollies|crane|orbit(?:s|ing)?|arc(?:s|ing)?|"
    r"tracking shot|track(?:s|ing)\s+(?:left|right|with)|handheld|zoom(?:s|ing)?[-\s]"
    r"?(?:in|out)?|steadicam|gimbal"
)
_CAMERA_CLAUSE = re.compile(
    rf"(?:(?:slow|slowly|fast|smooth|gentle|very slow)\s+)?(?:{CAMERA_MOVE})", re.I)

# Moves that distort a face. Push-in is absent on purpose: the cookbook's authority-intro
# template calls for "static or very slow push-in", so blocking it would contradict the
# document it enforces.
FACE_HOSTILE_MOVE = re.compile(
    r"orbit(?:s|ing)?|whip[-\s]?pan|arc(?:s|ing)?|handheld|pan(?:s|ning)?[-\s]"
    r"(?:left|right)|zoom(?:s|ing)?", re.I)
FACE_SHOT = re.compile(
    r"close[-\s]?up|\bcu\b|\bxcu\b|\bmcu\b|portrait|\bface\b|head and shoulders", re.I)
LOCKED_CAMERA = re.compile(r"\bstatic\b|\blocked\b|\bno camera (?:motion|movement)\b|"
                           r"\btripod\b|\bminimal camera motion\b", re.I)

# Mutually exclusive environmental conditions. The model cannot hold both, so it
# alternates and the light flickers across the clip — a re-render, not a grade fix.
CONDITION_CONFLICTS: tuple[tuple[str, str, str], ...] = (
    (r"overcast|cloudy|grey sky|gray sky|heavy cloud",
     r"shafts? of (?:bright )?(?:sun|sunlight)|bright sunlight|direct sunlight|sunbeam|"
     r"harsh sun|golden hour|sunlit",
     "overcast light and direct sun"),
    (r"\bnight\b|night-?time|after dark|moonlit|midnight",
     r"midday|high noon|broad daylight|bright sunlight|golden hour|sunrise|sunset",
     "night and daylight"),
    (r"\brain(?:y|ing)?\b|downpour|thunderstorm|\bstorm\b|\bwet\b",
     r"dry dust|dusty|cloudless|clear blue sky|parched|arid",
     "rain and dry weather"),
    (r"\bsnow(?:y|ing)?\b|blizzard|deep winter",
     r"\bsummer\b|heatwave|humid heat", "snow and summer"),
    (r"\bfog(?:gy)?\b|\bmist(?:y)?\b|thick haze",
     r"crystal clear|perfect visibility|razor sharp horizon", "fog and clear visibility"),
)

# Asking for legible type in frame. The threshold is two words inside the quotes, and it
# is there because the cookbook's own mechanism-shot example animates a folder tab
# `labelled "1997"` — a short label on a prop is what the document does, a sentence
# across the frame is what it warns about.
TEXT_REQUESTS: tuple[tuple[str, str], ...] = (
    (r"\bthe words?\s+[\"'“‘]", "the words … in frame"),
    (r"\b(?:text|sign|banner|headline|screen|letter)\s+(?:that\s+)?"
     r"(?:reads|says|showing|displaying)\b", "text that reads …"),
    (r"\blabel(?:l)?ed\s+[\"'“][^\"'”’]*\s[^\"'”’]*[\"'”’]",
     "a multi-word label"),
    (r"[\"'“][A-Z0-9][A-Z0-9 ,'’-]{6,}[\"'”]", "an all-caps phrase in quotes"),
    (r"\bon-?screen text|\bsubtitle|\bcaption\b|\btitle card\b|\blower third\b",
     "an on-screen text element"),
    (r"\bthe (?:number|figure|amount|total|price|date)\s+[\"'“]?[\$\d]",
     "a rendered numeral"),
    (r"\bwritten\s+(?:on|across)\b", "writing across the frame"),
)

# The four fields of the skeleton, detected loosely. Their absence is what makes a prompt
# read as a stock image: "every field generic, so the output feels like stock".
SKELETON = {
    "camera": re.compile(
        r"close[-\s]?up|wide shot|medium|establishing|aerial|drone|\bpov\b|eye level|"
        r"over[-\s]the[-\s]shoulder|insert|static|" + CAMERA_MOVE, re.I),
    "lighting": re.compile(
        r"light|lighting|\bkey\b|\bfill\b|\brim\b|golden hour|low[-\s]key|high[-\s]key|"
        r"backlit|silhouette|lamp|window|shadow|overcast|practical", re.I),
    "mood": re.compile(
        r"mood is|\bmood\b|ominous|intimate|melancholy|urgent|tense|calm|defiant|"
        r"triumphant|frenetic|reverent|dread|weighted|methodical|nostalgic|"
        r"aspirational|mournful", re.I),
    "technical": re.compile(
        r"\d+\s*:\s*\d+|\b\d+(?:\.\d+)?\s*seconds?\b|no cuts|\bfps\b|vertical|"
        r"\b(?:minimal|moderate|smooth|fast) camera motion\b", re.I),
}
PLACEHOLDER = re.compile(
    r"\bstuff\b|\bthings\b|\bsomething\b|\bsome kind of\b|\bgeneric\b|\bvarious\b|"
    r"\bdoing\s+\w+\s+stuff\b|\betc\b", re.I)

# Models the fingerprint table calls realism specialists. Their "realism gravity" pulls a
# stylized prompt halfway and returns half-real confusion — the sixth anti-pattern.
REALISM_MODELS = re.compile(r"veo|sora", re.I)
STYLIZED = re.compile(
    r"\banime\b|\bcartoon\b|cel[-\s]?shaded|illustrat|painterly|watercolou?r|comic book|"
    r"graphic novel|hand[-\s]drawn|low[-\s]poly|pixel art|styli[sz]ed|\bmanga\b", re.I)


# ------------------------------------------------------------------------- the report


@dataclass(frozen=True)
class Finding:
    """One thing wrong, the words that say so, and what to do instead."""

    code: str
    level: str          # "block" — a submission that wastes money; "warn" — check it
    message: str
    evidence: str = ""

    def as_dict(self) -> dict:
        return {"code": self.code, "level": self.level, "message": self.message,
                "evidence": self.evidence}


@dataclass(frozen=True)
class Review:
    prompt: str
    model: str
    findings: tuple[Finding, ...]

    @property
    def blocked(self) -> bool:
        """Whether submitting this as it stands is expected to waste the charge."""
        return any(finding.level == "block" for finding in self.findings)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def summary(self) -> str:
        if not self.findings:
            return "no issues found against the i2v prompt cookbook"
        return "; ".join(f"{finding.message}" for finding in self.findings)

    def as_dict(self) -> dict:
        return {"prompt": self.prompt, "model": self.model, "blocked": self.blocked,
                "findings": [finding.as_dict() for finding in self.findings],
                "summary": self.summary()}


# ------------------------------------------------------------------------- the checks


def _found(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I)
    return match.group(0) if match else ""


def _strip_camera(text: str) -> str:
    """Remove camera language before counting actions.

    "the camera pushes in" is not the subject doing something, and "pulls back" shares a
    verb with "pulls out a folder". Counting them as actions would flag every prompt that
    described its camera, which is every good prompt.
    """
    cleaned = _CAMERA_CLAUSE.sub(" ", text)
    return re.sub(r"\bcamera\b[^,;.]*", " ", cleaned, flags=re.I)


# Background motion is explicitly free: the cookbook's example is "a man reads a letter
# while leaves drift past the window", where `reads` is focal and `drift` is environmental
# motion the model handles separately. So a subordinate clause is not a second action.
_BACKGROUND_CLAUSE = re.compile(
    r"\b(?:while|as|behind (?:him|her|them)|in the background|beyond)\b[^,;]*", re.I)


def _focal_verbs(text: str) -> list[str]:
    """The finite action verbs in the subject's clause, in order of appearance."""
    stripped = _strip_camera(_BACKGROUND_CLAUSE.sub(" ", text.lower()))
    return [token for token in re.findall(r"[a-z]+", stripped)
            if token in PRIMARY_FINITE
            and token not in MICRO_FINITE and token not in POSTURE_FINITE]


def _check_verb_tiers(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for pattern, label, reason in FORBIDDEN:
        hit = _found(pattern, text)
        if hit:
            findings.append(Finding(
                "forbidden_verb", "block",
                f"'{label}' is in the forbidden tier — {reason}. Recut the shot around "
                f"it or split it so the action happens off-frame.", hit))
    for pattern, label, condition in RISKY:
        hit = _found(pattern, text)
        if hit:
            findings.append(Finding(
                "risky_verb", "warn",
                f"'{label}' is in the risky tier: usable with {condition}. Expect to "
                f"re-render if it comes back wrong.", hit))
    return findings


def _check_one_verb(text: str) -> list[Finding]:
    verbs = _focal_verbs(text)
    chained = re.search(r"\b(?:and\s+then|,\s*then|\bthen\b)\s+[a-z]+s\b", text, re.I)

    if len(verbs) > 1:
        return [Finding(
            "multi_action", "block",
            f"{len(verbs)} focal actions in one prompt ({', '.join(verbs)}) — the model "
            f"picks one and melts the rest. Split into {len(verbs)} clips, or keep one "
            f"action and let the others happen off-frame.", ", ".join(verbs))]
    if chained:
        return [Finding(
            "multi_action", "block",
            "the actions are chained with 'then', which is two shots rather than one — "
            "chaining rarely helps; split into two clips.", chained.group(0))]
    return []


def _check_conditions(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for first, second, label in CONDITION_CONFLICTS:
        left, right = _found(first, text), _found(second, text)
        if left and right:
            findings.append(Finding(
                "condition_conflict", "block",
                f"{label} are mutually exclusive, so the model alternates and the light "
                f"flickers across the clip. Pick one.", f"{left} / {right}"))

    locked = LOCKED_CAMERA.search(text)
    move = _CAMERA_CLAUSE.search(text)
    # "minimal camera motion" is a technical note, not a move: the document's own worked
    # example carries both it and "static", and flagging that pair would flag the
    # skeleton itself.
    if locked and move and move.group(0).strip().lower() not in {"static", "locked"}:
        findings.append(Finding(
            "camera_conflict", "block",
            f"the camera is described as {locked.group(0)!r} and as "
            f"{move.group(0).strip()!r} in the same prompt. Conflicting instructions "
            f"produce jerky motion — decide which one the shot is.",
            f"{locked.group(0)} / {move.group(0).strip()}"))

    if FACE_SHOT.search(text) and (hostile := FACE_HOSTILE_MOVE.search(text)):
        findings.append(Finding(
            "face_camera_move", "block",
            f"moving the camera ({hostile.group(0)}) across a face shot distorts the "
            f"face — the single most common error on a hook close-up. Lock the camera, "
            f"or move across the environment and end on the subject.", hostile.group(0)))
    return findings


def _check_text_request(text: str) -> list[Finding]:
    for pattern, label in TEXT_REQUESTS:
        hit = _found(pattern, text)
        if hit:
            return [Finding(
                "onscreen_text", "block",
                f"the prompt asks for legible type in frame ({label}) — letters warp and "
                f"kerning collapses. Generate the blank surface and add the text in "
                f"code.", hit)]
    return []


def _check_specificity(text: str) -> list[Finding]:
    present = [field for field, pattern in SKELETON.items() if pattern.search(text)]
    placeholder = PLACEHOLDER.search(text)
    if len(present) >= 2 and not placeholder:
        return []

    missing = [field for field in SKELETON if field not in present]
    detail = (f"{placeholder.group(0)!r} is a placeholder, not a subject; "
              if placeholder else "")
    return [Finding(
        "generic", "warn",
        f"{detail}no {' or '.join(missing)} in the prompt, so the output will read as a "
        f"stock image. Anchor every field of the skeleton — a specific prompt lands on "
        f"the first try about 85% of the time against roughly 30% for a vague one.",
        placeholder.group(0) if placeholder else ", ".join(missing))]


def _check_model_register(text: str, model: str) -> list[Finding]:
    if not model or not REALISM_MODELS.search(model):
        return []
    hit = STYLIZED.search(text)
    if not hit:
        return []
    return [Finding(
        "register_mismatch", "warn",
        f"{model} is a realism specialist and its realism gravity pulls a stylized "
        f"prompt ({hit.group(0)}) halfway, producing half-real confusion. Send stylized "
        f"work to a stylized model instead.", hit.group(0))]


def review(prompt: str, *, model: str = "") -> Review:
    """Score one i2v prompt. Order of findings is the order they should be fixed in."""
    text = " ".join(str(prompt).split())
    findings: list[Finding] = []
    findings += _check_verb_tiers(text)
    findings += _check_one_verb(text)
    findings += _check_conditions(text)
    findings += _check_text_request(text)
    findings += _check_specificity(text)
    findings += _check_model_register(text, model)
    # Blocking findings first: a caller that shows one line shows the one that stops the
    # submission, not the advisory note that happened to be checked earlier.
    findings.sort(key=lambda finding: 0 if finding.level == "block" else 1)
    return Review(prompt=text, model=str(model), findings=tuple(findings))
