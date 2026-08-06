"""Skills: named instruction documents the agent loads when they apply.

## What a skill is, and what it is not

A *style* — `forgecast/style/editing.py` — is measured. It is what a creator's edit
demonstrably does: cuts per minute, saturation, caption position. Nobody writes one by
hand and nobody argues with it, because it came off a video.

A *skill* is the opposite kind of knowledge. It is craft an operator holds in their head
and would otherwise retype into the chat every week: how to open a video, where the turn
in a documentary belongs, what a caption card is allowed to do. It is prose, it is
argued with, and it is edited by a person. So it is stored as markdown rather than as
fields, and it carries the one piece of metadata that decides whether the agent should
be reading it at all — `when_to_use`.

## Why markdown files rather than rows

Two reasons, both practical. A skill is something you want to paste into a chat, mail to
someone, or keep in a git repo beside the scripts it governs; a database row is none of
those. And the agent is already sandboxed to a folder it can Read — a file it can open
itself costs no tool and no round trip.

## Why the front matter is parsed by hand

Adding PyYAML for two keys is a dependency, an install-time failure mode, and a parser
with an arbitrary-object surface, all bought for `name:` and `when_to_use:`. What is
supported instead is exactly what is written: `key: value` lines above a `---` fence.
Anything else in the block is kept in `extra` rather than dropped, so a file hand-edited
with a third key does not lose it on the next save.

## Why this is a package with a `data/` directory

The three original starters are Python strings a few hundred words each. The four visual
documents are ten to thirteen kilobytes of operational craft apiece, and they are edited
as prose — reordered, re-argued, re-costed. Pasted into a `\"\"\"` literal they become a
file nobody reviews and every edit a diff nobody can read, so they live as markdown in
`data/` beside this module and are read at seed time.

The cost of that choice is a packaging obligation: a wheel built without
`[tool.setuptools.package-data]` naming `data/*.md` installs the seeding code and none of
the documents. That failure is invisible — the library simply comes up with three skills
instead of seven — so a document that cannot be read is logged by name rather than
skipped in silence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("forgecast.skills")

FOLDER_NAME = "skills"

# Long enough for a real title, short enough that the filename stays a filename on every
# platform this runs on — Windows still counts a whole path against 260 characters, and
# the storage directory is already deep.
MAX_SLUG_CHARS = 60

_KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_FENCE = "---"

# Windows resolves these as devices in every directory and whatever the extension, so
# `nul.md` there is not a file: the write is swallowed and every later read hands back an
# empty document, which for a skill means its prose is gone and the page still lists it.
# A whitelist on the characters cannot catch this, because every character is legal.
_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in "0123456789"}
    | {f"lpt{digit}" for digit in "0123456789"}
)
_DEVICE_SUFFIX = "-skill"


def slugify(name: str) -> str:
    """A filesystem-safe key from a human name, or "" when nothing survives.

    This is the boundary where user input becomes a path, so it is a whitelist rather
    than a blacklist: everything that is not a letter or a digit becomes a hyphen. That
    disposes of separators, `..`, leading dots, colons, and the reserved characters on
    Windows in one rule instead of five that each have to be remembered.

    A name that lands on a Windows device name is suffixed rather than refused, because
    "Aux" and "Con" are legitimate titles and nobody should have to learn which two dozen
    words their filesystem has taken. The suffix is idempotent — `nul-skill` is not
    itself reserved — which matters because every read and delete slugifies again, and a
    rule that grew a suffix per pass would stop finding the file it wrote.

    Empty is returned rather than a default like "skill", because a caller that has no
    name should be told so — silently filing an unnamed skill under a generic slug is
    how the second unnamed skill overwrites the first.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    cleaned = cleaned[:MAX_SLUG_CHARS].strip("-")
    return f"{cleaned}{_DEVICE_SUFFIX}" if cleaned in _DEVICE_NAMES else cleaned


@dataclass
class Skill:
    """One instruction document, as it exists on disk."""

    slug: str
    name: str
    when_to_use: str = ""
    body: str = ""
    # Keys a person added to the front matter by hand. Preserved through a save so the
    # page's editor is not a way to quietly delete them.
    extra: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def document(self) -> str:
        """The exact file text, front matter and all.

        Values are flattened to one line on the way out. A newline inside `name` would
        put a bare word where the parser expects `key: value`, and the next read would
        see a truncated name and a body that has silently absorbed the rest.
        """
        lines = [_FENCE, f"name: {_one_line(self.name)}"]
        if self.when_to_use:
            lines.append(f"when_to_use: {_one_line(self.when_to_use)}")
        for key, value in self.extra.items():
            lines.append(f"{key}: {_one_line(value)}")
        lines.append(_FENCE)
        return "\n".join(lines) + "\n\n" + self.body.strip() + "\n"

    def summary(self, limit: int = 150) -> str:
        """The line the list view shows under the name."""
        text = _one_line(self.when_to_use) or _first_prose(self.body)
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def as_prompt(self) -> str:
        """How the skill is announced when it is loaded into a turn.

        The header is what makes a loaded skill visible in the transcript rather than
        invisible context — the difference between an agent that says which document it
        is following and one whose reasoning cannot be checked against anything.
        """
        return (f"SKILL / {self.name} / {self.slug}\n"
                f"Use when: {self.when_to_use or 'unspecified'}\n\n{self.body.strip()}")


# ------------------------------------------------------------------------ parsing


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def _first_prose(body: str) -> str:
    """The first line that is neither blank nor a heading."""
    for line in body.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not line.strip().startswith(("#", "-", "*", ">")):
            return stripped
    return ""


def parse(text: str, *, slug: str = "") -> Skill:
    """Read a skill document. Never raises on a malformed one.

    A file someone hand-edited into an unparseable state has to come back as a skill
    with a body, not as an exception: the page that would have let them fix it is the
    page that failed to load. So a missing front matter block means the whole file is
    the body and the slug stands in for the name.
    """
    lines = text.lstrip("﻿").splitlines()
    start = 1 if lines and lines[0].strip() == _FENCE else 0

    meta: dict[str, str] = {}
    body_at = None
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if stripped == _FENCE:
            body_at = index + 1
            break
        if not stripped:
            continue
        match = _KEY_LINE.match(stripped)
        if match is None:
            # A non-`key: value` line before any fence means this file has no front
            # matter at all. Guessing otherwise would eat the first paragraph.
            break
        meta[match.group(1).lower()] = match.group(2).strip()

    if body_at is None:
        meta, body_at = {}, 0

    body = "\n".join(lines[body_at:]).strip()
    known = {"name", "when_to_use"}
    return Skill(
        slug=slug,
        name=meta.get("name") or slug or "Untitled skill",
        when_to_use=meta.get("when_to_use", ""),
        body=body,
        extra={k: v for k, v in meta.items() if k not in known},
    )


# ------------------------------------------------------------------------ storage


def directory(base: Path | str | None = None) -> Path:
    """Where skills live. Created on demand.

    `base` exists so tests and the CLI can point at a folder of their own; the default
    is the one place the rest of the app already knows about.
    """
    root = Path(base) if base is not None else get_settings().storage_dir
    folder = root / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _path(slug: str, base: Path | str | None = None) -> Path:
    """The file a slug names, checked to be inside the skills folder.

    `slugify` already makes traversal impossible, so this check should be dead code —
    which is the point of it. It is the assertion that survives someone later relaxing
    the slug rules to allow a dot or a slash "just for namespacing", and it turns that
    change into a refused write instead of a file written over `~/.ssh/config`.
    """
    folder = directory(base).resolve()
    safe = slugify(slug)
    if not safe:
        raise ValueError("a skill needs a name with at least one letter or digit")
    path = (folder / f"{safe}.md").resolve()
    if path.parent != folder:
        raise ValueError(f"{slug!r} does not name a skill inside {folder}")
    return path


def available(base: Path | str | None = None) -> list[dict]:
    """Every skill, alphabetically, as rows for a list view."""
    folder = directory(base)
    _ensure_starters(folder)

    rows: list[dict] = []
    for path in sorted(folder.glob("*.md")):
        try:
            skill = _load(path)
        except OSError:
            continue
        rows.append({
            "slug": skill.slug,
            "name": skill.name,
            "when_to_use": skill.when_to_use,
            "summary": skill.summary(),
            "words": len(skill.body.split()),
            "updated_at": skill.updated_at,
        })
    rows.sort(key=lambda row: row["name"].lower())
    return rows


def exists(slug: str, base: Path | str | None = None) -> bool:
    """Whether a slug already names a stored skill.

    Separate from `get` so a caller deciding whether it is about to overwrite someone
    else's document does not have to read and parse it, and so a name that cannot be a
    slug at all answers False instead of raising — there is nothing there to protect.
    """
    try:
        return _path(slug, base).exists()
    except ValueError:
        return False


def get(slug: str, base: Path | str | None = None) -> Skill:
    """One skill by slug. `KeyError` names the ones that do exist.

    Listing them matters more here than it looks: the agent and the page both address
    skills by slug, and "no such skill" without the alternatives is an error you cannot
    act on without a second call.
    """
    folder = directory(base)
    _ensure_starters(folder)
    path = _path(slug, base)
    if not path.exists():
        known = [row["slug"] for row in available(base)]
        raise KeyError(f"no skill {slug!r}; have {known}")
    return _load(path)


def save(slug: str, name: str, when_to_use: str, body: str,
         base: Path | str | None = None) -> Skill:
    """Write a skill, creating or replacing it. Returns what was stored.

    The slug is passed rather than derived so that renaming a skill and re-filing it are
    separate decisions — a caller that wants the file to follow the name passes
    `slugify(name)`, and one that wants a stable identifier keeps the old slug.
    """
    if not _one_line(name):
        raise ValueError("a skill needs a name")
    path = _path(slug or name, base)
    existing = _load(path).extra if path.exists() else {}
    skill = Skill(slug=path.stem, name=_one_line(name),
                  when_to_use=_one_line(when_to_use), body=body, extra=existing)
    path.write_text(skill.document(), encoding="utf-8")
    skill.updated_at = _stamp(path)
    return skill


def refile(previous: str, name: str, when_to_use: str, body: str,
           base: Path | str | None = None) -> Skill:
    """An editor's save: the file follows the name, and the old file is removed.

    `previous` is the slug the editor loaded, `""` for a new document. Two things make
    this worth being an operation of its own rather than the caller's two calls.

    The old file has to go, or the library holds two documents claiming to be the same
    instruction and the agent — which loads every skill whose `when_to_use` matches —
    follows both, including the half that was edited out.

    And many titles share one filename: "Hook writing", "hook_writing", "Hook: writing!"
    and any two names agreeing on their first sixty characters all slugify alike. Landing
    on a document that was not the one being edited would overwrite that skill's prose
    and then delete the one being edited — two documents lost to one save. Which is why
    the check cannot live in the page: only a caller that says which file it loaded can
    tell an intended replacement from a collision, so this refuses on behalf of every
    caller that ever gets added.
    """
    target = slugify(name)
    before = slugify(previous)
    if target and target != before and exists(target, base):
        # Short: the page puts this in a banner through a query string it clips.
        raise ValueError(f"{target}.md is already another skill; rename this one")

    stored = save(target, name, when_to_use, body, base)
    if before and before != stored.slug:
        delete(before, base)
        log.info("skill %s renamed to %s", before, stored.slug)
    return stored


def delete(slug: str, base: Path | str | None = None) -> bool:
    """Remove a skill. False when there was nothing to remove."""
    path = _path(slug, base)
    if path.exists():
        path.unlink()
        return True
    return False


def _load(path: Path) -> Skill:
    skill = parse(path.read_text(encoding="utf-8"), slug=path.stem)
    skill.updated_at = _stamp(path)
    return skill


def _stamp(path: Path) -> str:
    try:
        moment = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:                                               # pragma: no cover
        return ""
    return moment.isoformat(timespec="seconds")


# ------------------------------------------------------------------- the starters


HOOK_SKILL = """
# The first fifteen seconds

Almost every faceless video that fails, fails here. The audience is not deciding
whether the topic is interesting — they are deciding whether *this* telling of it is
going to be worth eight minutes, and they decide with about six seconds of evidence.

## Write the opening line last, and to a budget

* Fourteen words or fewer. At a narration pace of 150 words per minute that is under
  six seconds, which is the whole budget.
* It states the stake, not the subject. "Titanic's sister ship sank the same way,
  twice" is a stake. "Today we're looking at the Britannic" is a subject.
* One concrete noun in the first five words. Abstractions ("innovation", "history",
  "the industry") read as filler and are skipped before they are parsed.
* No throat clearing: no greeting, no channel name, no "in this video", no apology for
  the gap since the last upload, no definition of the topic.

## Then owe the viewer something

By 0:08 there has to be a question on the table that the video has not answered. Say it
once, plainly, and do not restate it — a repeated question reads as padding and tells
the viewer the next thirty seconds are safe to skip.

Never say "but first". It is an explicit announcement that the thing they came for is
being withheld, and it is one of the few phrases with a visible retention cliff under
it.

## The picture has to work as hard as the line

* First cut inside 2.0 seconds, and a second cut before 0:06. A held wide shot over the
  opening line is the visual equivalent of a slow speaker.
* The sharpest image in the first thirty seconds goes at 0:00, not at 0:20. Saving it is
  saving it for people who left.
* If the strongest asset is a document, a diagram or a photograph, open on a detail of
  it, then pull out. Opening wide gives the viewer nothing to look for.

## Targets to judge it against

* 0:30 retention: 75% or better for long form, 85% for a Short.
* 1:00 retention: 55% or better for long form.
* Any single second in the first fifteen that loses more than 3% is a rewrite, not a
  trim — that is a promise that was not believed, and cutting a word does not fix it.

## The test before moving on

Read the first forty words with the visuals covered. If they could open a different
video on the same topic, they are not a hook yet. Then read them again and ask what the
viewer now wants to know. If the answer is "nothing", there is no reason for 0:16 to
exist.
"""


REVEAL_SKILL = """
# Structuring a documentary reveal

A documentary holds attention with one unresolved thing, and everything else in the
script exists to keep that thing unresolved without feeling withheld. The failure mode
is not boredom, it is the viewer working out the ending at 40% and leaving, satisfied.

## The beat map, in percentages of finished runtime

* **0-3% — Cold open.** The most specific image or fact you have, with no context. Not a
  summary of the video; a moment from inside it.
* **3-8% — The question.** Said once, in one sentence, in plain words. This is the
  contract, and it is the only thing the viewer is asked to remember.
* **8-30% — Beat one: the ordinary explanation.** Give the answer most people would give,
  make it genuinely persuasive, then show precisely why it does not hold. A straw man
  here costs you the rest of the video.
* **30-55% — Beat two: escalation.** New evidence that makes the question harder rather
  than easier. If this beat could be swapped with beat one and nothing would change, it
  is not escalation, it is a list.
* **55-70% — The turn.** The evidence arrives before the conclusion, always. Show the
  document, the number, the timeline, then let the viewer reach the answer roughly one
  sentence ahead of the narration. That single sentence of anticipation is what people
  mean when they say a documentary is satisfying.
* **70-88% — The reveal and its cost.** What the answer means, and what it cost whoever
  found it out. An answer without a cost is trivia.
* **88-100% — Consequence.** Where it stands now, and one door deliberately left open.
  Not a subscribe plea — a door.

## Rules of withholding

* Close a smaller loop every 90 seconds. Aim for roughly two loops closed for every
  three opened: all opening is a con, all closing is a lecture.
* Never tease the reveal ("we'll come back to that"). Instead, answer something adjacent
  that makes the reveal feel nearer.
* The main question is never restated in full after 8%. Reference it in three or four
  words at most.
* Chronology is a tool, not an obligation. Order beats by how much each one raises the
  stakes, and let the timeline be established once, visually.

## Where scripts go wrong

* **The reveal too early.** Before roughly the halfway mark there is nothing left to
  hold, and the last third becomes a summary of the first two.
* **Two reveals.** A second one of equal weight makes both feel smaller. Demote one to
  a beat inside the other, or cut it and keep it for its own video.
* **A conclusion nobody can check.** If the reveal cannot be pointed at — a source, a
  figure, a record — it will read as speculation regardless of how it is narrated, so
  either find the artefact or say plainly that this is the best available reading.

## The check

Write the question at 3-8% and the answer at 70% as two sentences, side by side. If the
answer is obvious from the question, restructure: you have a topic, not a reveal.
"""


CAPTION_SKILL = """
# Caption discipline

Burned-in captions are the second voice track. They are read faster than the narration
is spoken, which means every choice here is about whether they arrive with the audio or
race ahead of it and spoil the sentence.

## Layout

* 16:9 — baseline in the bottom third, at least 8% of frame height clear of the bottom
  edge. Type at 4.5-5.5% of frame height.
* 9:16 — baseline at 68-72% of frame height, never lower. The bottom quarter of a
  vertical frame belongs to the platform's own interface, and a caption behind a
  username is a caption nobody read. Type at 6.5-8% of frame height.
* Two lines maximum, 32-42 characters per line. A third line is a paragraph and reads
  as one.
* One treatment, not three. A solid backing plate at 55-70% opacity *or* an outline of
  2-3 px *or* a drop shadow — stacking them is what makes a frame look cheap.

## Timing

* Minimum 1.2 seconds on screen. Anything shorter is a flash the eye registers and
  cannot read, which is worse than no caption.
* Maximum 4.0 seconds. Past that the caption is stale against the narration and the eye
  starts skimming ahead.
* Three to seven words per card. Break at a clause boundary, never between an adjective
  and its noun or between a number and its unit.
* A card never crosses a cut. Land the change of card on the cut or 2-3 frames after it,
  so the eye moves once instead of twice.
* Never let a card show a word before it is spoken. Ahead of the audio is the single
  most common way a punchline, a number or a name gets spoiled.

## Wording

* Verbatim to the voiceover for everything spoken. A caption that paraphrases the
  narration reads as a bug to anyone with the sound on, and they are the majority.
* Keep every number, name and unit; drop only true filler ("you know", "sort of") and
  only when the audio is also cut.
* Numerals over words for anything countable — "12 hours", not "twelve hours".
  Captions are scanned, and digits scan.

## Emphasis

* One emphasised phrase per fifteen seconds at most, and three words at most inside it.
  Emphasis on everything is emphasis on nothing.
* One accent colour, used only for emphasis, and never on a word the narrator does not
  stress. Emphasis that disagrees with the audio makes both feel automated.
* No all-caps sentences. Capitals cost about 15% reading speed at these sizes because
  the word shapes go flat; reserve them for a single word.

## Never

* Captions over a face, a chart, or on-screen text that the viewer is being asked to
  read at the same time. Move the caption for those shots, or leave the shot silent.
* Auto-generated timings shipped unreviewed. The failure they produce is not a typo, it
  is a card that arrives late for the whole second half of the video.
"""


# The three scripting starters. These three, because they are the decisions that come up
# in every single faceless script: how it opens, how it holds, and what the type on screen
# may do. They ship as content rather than as a "your skill here" placeholder for a plain
# reason — a starter with nothing in it teaches the format and none of the craft, and an
# operator who has to invent both at once writes neither. The visual documents that ship
# beside them are in `SHIPPED_DOCS` below, as files.
STARTERS: tuple[tuple[str, str, str], ...] = (
    (
        "Hook writing",
        "Writing or rewriting the first fifteen seconds of any script, and whenever "
        "a video's 0:30 retention is below 75%.",
        HOOK_SKILL,
    ),
    (
        "Documentary reveal structure",
        "Outlining or reordering a documentary, explainer or mystery script that turns "
        "on one unanswered question.",
        REVEAL_SKILL,
    ),
    (
        "Caption discipline",
        "Writing, timing or reviewing burned-in captions, and when choosing caption "
        "size and position for a new channel.",
        CAPTION_SKILL,
    ),
)


# The production documents, shipped as files rather than as string literals for the
# reason in the module docstring — four on picture, two on sound. The two sound documents
# are the operator's own measured method and they are authoritative: where anything else
# in this app or in a model's own habits suggests a different loudness target, ducking
# depth, cue level or placement rule, these win. That is stated in the trigger line as
# well, because a model that loads both a generic instinct and a house standard needs to
# know which one loses. The `when_to_use` line beside each one is not
# a description: it is the entire basis on which the agent decides whether to spend a
# turn loading twelve kilobytes, so each names the moment work reaches the document, the
# artefact being produced, and — where the neighbouring document is the better answer —
# the case it does *not* cover. "Use when generating visuals" fires on every image the
# app ever makes, which is the same as never firing usefully.
DATA_DIR = Path(__file__).resolve().parent / "data"

SHIPPED_DOCS: tuple[tuple[str, str, str], ...] = (
    (
        "Reverse-engineer a reference format",
        "Before writing for a channel modelled on a creator: whether the runtime is "
        "one throughline or an anthology of repeating segments, the segment template, "
        "and what the picture does at each phase. Load it before hook-writing or a "
        "structure skill, which assume a shape this decides. Not for a channel with no "
        "reference.",
        "reverse-engineer-format.md",
    ),
    (
        "Image-to-video prompting",
        "Before submitting any image-to-video render: picking the i2v model against its "
        "per-second cost, writing the subject/action/camera/lighting/mood/technical "
        "prompt, setting motion intensity, running the Sample Gate before a full-length "
        "render, and inspecting returned frames. Not for stills, thumbnails or stock.",
        "image-to-video.md",
    ),
    (
        "i2v prompt cookbook",
        "While actually writing an i2v prompt, or after a clip came back melted, warped, "
        "looping or off-brief: match the shot to one of the ten templates, pick the model "
        "from the fingerprint table, check the verb against the clean/risky/forbidden "
        "tiers, diagnose the anti-pattern. Load with the image-to-video skill, not "
        "instead of it.",
        "i2v-prompt-cookbook.md",
    ),
    (
        "Photoreal vs cinematic register",
        "Before the first image or clip of a new channel or video exists, and whenever a "
        "host shot comes back glossier than the niche expects: choosing authentic-amateur, "
        "cinematic-polished or a deliberate mix per niche, audience and surface, locking "
        "that choice to channel memory, and diagnosing studio-lighting drift. Not for "
        "prompt wording or model choice.",
        "visual-register.md",
    ),
    (
        "Storyboard and scene breakdown",
        "When a script is approved and visuals are next: deciding whether this format "
        "needs a storyboard at all, at what depth, mapping beats or bars to shots with "
        "durations that fit the model's clip cap, and walking the four commit gates. Skip "
        "for a locked-host talking-head channel and for ambient single-scene loops.",
        "storyboard.md",
    ),
    (
        "Sound designer",
        "When a video and a separate mastered voiceover exist and the mix is next: "
        "find the beats in the picture rather than guessing them from the script, fetch "
        "a palette, place and level the cues, duck the bed, master, verify per tier. Also "
        "for why a mix sounds repetitive, cheap or badly synced. This is the house sound "
        "method; it outranks any other mixing advice, here or elsewhere.",
        "sound-designer.md",
    ),
    (
        "Sound design method",
        "Before changing any sound-design number or rule: the measurements and the "
        "failures behind each one. Load alongside the sound-designer skill when a "
        "non-negotiable needs to be understood or overridden, not instead of it.",
        "sound-designer-method.md",
    ),
)


def _without_front_matter(text: str) -> str:
    """A shipped document with any YAML front matter removed.

    Some documents arrive in the Claude Code skill format, which opens with a `---` block
    carrying `name:` and `description:`. Forgecast keeps its own trigger line beside the
    filename in `SHIPPED_DOCS`, so the block is a duplicate of information the app already
    holds — and left in place it becomes the first thing the agent reads, which is a
    second, differently-worded trigger competing with the real one.

    Only a block that opens on the very first line is treated as front matter. A `---`
    used as a horizontal rule further down is prose and stays.
    """
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1:]).strip()
    return text                                                      # unterminated: prose


def _shipped_body(filename: str) -> str:
    """The text of one shipped document, or "" with the reason logged.

    Read here rather than at import time so that a packaging mistake degrades the skills
    library instead of breaking every import of it — and named in the log because the
    symptom otherwise is a page listing three skills where seven were installed, which
    looks like a product decision rather than a missing wheel entry.
    """
    try:
        return _without_front_matter(
            (DATA_DIR / filename).read_text(encoding="utf-8").strip())
    except OSError as exc:
        log.warning(
            "shipped skill %s is missing from %s (%s) — the install is incomplete; "
            "package-data must carry forgecast/skills/data/*.md", filename, DATA_DIR, exc)
        return ""


def starters() -> list[Skill]:
    """Every document this install ships, as skills, in seeding order.

    Public because it is the only honest way to test that the shipped documents survived
    packaging: asserting on the seeded folder passes just as well when a document was
    silently dropped, since the folder is non-empty either way.
    """
    made = [Skill(slug=slugify(name), name=name, when_to_use=when_to_use,
                  body=body.strip())
            for name, when_to_use, body in STARTERS]
    made += [Skill(slug=slugify(name), name=name, when_to_use=when_to_use, body=body)
             for name, when_to_use, filename in SHIPPED_DOCS
             if (body := _shipped_body(filename))]
    return made


def _ensure_starters(folder: Path) -> list[Skill]:
    """Seed the starters into an empty folder, once.

    Guarded on the folder being empty rather than on a marker file, which means an
    install whose skills were all deleted gets them back on the next visit. That is the
    right trade: an empty skills page is indistinguishable from a broken one, and these
    documents are also the only worked examples of the format anyone editing a skill has
    to go on. Deleting one of them is respected — the seed only runs when there is
    nothing at all. The cost of that rule is the reverse case: an operator who deletes
    six and keeps one never gets an upgrade's new documents, and finds them on the
    Skills page of a fresh install instead.
    """
    if any(folder.glob("*.md")):
        return []
    made = starters()
    for skill in made:
        (folder / f"{skill.slug}.md").write_text(skill.document(), encoding="utf-8")
    return made
