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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import get_settings

FOLDER_NAME = "skills"

# Long enough for a real title, short enough that the filename stays a filename on every
# platform this runs on — Windows still counts a whole path against 260 characters, and
# the storage directory is already deep.
MAX_SLUG_CHARS = 60

_KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_FENCE = "---"


def slugify(name: str) -> str:
    """A filesystem-safe key from a human name, or "" when nothing survives.

    This is the boundary where user input becomes a path, so it is a whitelist rather
    than a blacklist: everything that is not a letter or a digit becomes a hyphen. That
    disposes of separators, `..`, leading dots, colons, and the reserved characters on
    Windows in one rule instead of five that each have to be remembered.

    Empty is returned rather than a default like "skill", because a caller that has no
    name should be told so — silently filing an unnamed skill under a generic slug is
    how the second unnamed skill overwrites the first.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return cleaned[:MAX_SLUG_CHARS].strip("-")


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


# Three, and these three, because they are the decisions that come up in every single
# faceless script: how it opens, how it holds, and what the type on screen may do. They
# ship as content rather than as a "your skill here" placeholder for a plain reason — a
# starter with nothing in it teaches the format and none of the craft, and an operator
# who has to invent both at once writes neither.
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


def _ensure_starters(folder: Path) -> list[Skill]:
    """Seed the three starters into an empty folder, once.

    Guarded on the folder being empty rather than on a marker file, which means an
    install whose skills were all deleted gets them back on the next visit. That is the
    right trade: an empty skills page is indistinguishable from a broken one, and these
    three documents are also the only worked examples of the format anyone editing a
    skill has to go on. Deleting one of the three is respected — the seed only runs when
    there is nothing at all.
    """
    if any(folder.glob("*.md")):
        return []
    made = []
    for name, when_to_use, body in STARTERS:
        skill = Skill(slug=slugify(name), name=name, when_to_use=when_to_use,
                      body=body.strip())
        (folder / f"{skill.slug}.md").write_text(skill.document(), encoding="utf-8")
        made.append(skill)
    return made
