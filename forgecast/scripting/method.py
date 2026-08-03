"""Forgecast's own scripting method, as blocks a prompt can carry and a check can count.

## Why this is not one long string

The craft below is five rules, and each of them has a number in it: how often the video
pays the viewer back, how long a question may stay open, how many beats before a device
may be reused. A rule written into a paragraph is a rule nobody can assert against a
finished script — you can read it and agree with it, and that is all. So every rule is a
`MethodBlock` with an id, a title, the prose a writer follows, and the parameters the
prose is built from. A later pass that wants to count open loops in `script.json` reads
`METHOD["curiosity_loops"].params`, not a regular expression over English.

The prose and the numbers live in the same object on purpose. Keeping them apart is how a
constant gets tuned to 8 and a paragraph goes on saying six, and the prompt is then two
instructions that disagree — which the model resolves by ignoring both.

## Why the cadence is computed rather than written down

"Pay the viewer back often" is an adjective. `$beat_seconds` seconds is an instruction.
The bands in `cadence()` are absolute rather than a percentage of runtime, because
attention is absolute: a percentage that gives a 45-second Short one payoff every eleven
seconds gives an eighteen-minute documentary one every four and a half minutes, and the
second of those is a video nobody finishes.

## Why none of this quotes anybody

This file ships inside the zip, so every word in it has to be Forgecast's own. The
operator's purchased scripting documents are the other half of this feature and they are
never in the tree at all — `library.py` reads them from a folder on their machine at
prompt-build time and nothing writes them anywhere. If you are tempted to paste a
paragraph from one of those documents in here to make a block sharper: that is the one
edit this package exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Template

# The built-in style's slug. It is the default for every channel and needs no folder, no
# configuration and no files — an install that has never heard of the scripting library
# still writes to a method rather than to a model's instincts.
HOUSE_SLUG = "house"
HOUSE_NAME = "Forgecast house method"


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class MethodBlock:
    """One rule: what a writer does, and the numbers the rule is made of.

    `prose` carries `$name` placeholders filled from `params` and from the cadence for
    the video being written. `string.Template` rather than `str.format` because the prose
    is full of prices, ratios and quoted narration, and a stray brace in a rewritten
    paragraph would turn a prompt-build into an exception at the top of a run.
    """

    id: str
    title: str
    prose: str
    params: dict = field(default_factory=dict)

    def body(self, values: dict | None = None) -> str:
        """The prose with its numbers substituted.

        `safe_substitute`, so a placeholder added to the prose before the value exists
        renders as a visible `$token` in the prompt instead of raising. A defect you can
        read in the transcript costs one script; an exception here costs the run.

        Non-scalar params — the bank and banned-construction tuples — are deliberately
        not offered to the substitution. Rendering a tuple's `repr` into a prompt is how
        a model ends up reading Python instead of instructions; those two are formatted
        by `render` and passed in as text.
        """
        merged = {**self.params, **(values or {})}
        usable = {key: value for key, value in merged.items()
                  if isinstance(value, (str, int, float))}
        return Template(self.prose).safe_substitute(usable).strip()

    def text(self, values: dict | None = None) -> str:
        """The block as it goes into a prompt: its title, then its prose."""
        return f"{self.title.upper()}\n{self.body(values)}"


@dataclass(frozen=True)
class RotationBank:
    """A pool of interchangeable devices that do one structural job."""

    id: str
    title: str
    purpose: str
    entries: tuple[str, ...]

    def text(self) -> str:
        listed = "\n".join(f"  - {entry}" for entry in self.entries)
        return f"{self.title} — {self.purpose}\n{listed}"


@dataclass(frozen=True)
class BannedConstruction:
    """A phrase that is forbidden, and the thing to write instead.

    The replacement is not politeness. A ban with nothing on the other side of it gets
    obeyed for two paragraphs and then quietly dropped, because the writer still has to
    put *something* in the slot and the banned phrase is the only candidate they have.
    """

    construction: str
    instead: str

    def text(self) -> str:
        return f"  BANNED: {self.construction}\n  INSTEAD: {self.instead}"


@dataclass(frozen=True)
class Cadence:
    """How often this particular video has to pay the viewer back."""

    target_seconds: int
    beat_seconds: int
    beats: int
    rungs: int
    rung_beats: int

    def as_dict(self) -> dict:
        return {
            "target_seconds": self.target_seconds,
            "beat_seconds": self.beat_seconds,
            "beats": self.beats,
            "rungs": self.rungs,
            "rung_beats": self.rung_beats,
        }


# Four rungs, because the shape being described is quarters of a runtime and a viewer can
# feel a video getting bigger four times. Eight rungs is a ladder nobody can climb in
# order and a writer stops trying somewhere around the third.
RUNGS = 4

# Beat length by runtime band. A Short has to settle something every few seconds because
# the whole thing is over before a long-form video has finished its first beat.
_BANDS: tuple[tuple[int, int], ...] = ((90, 7), (300, 15))
_LONG_FORM_BEAT_SECONDS = 25

# Below this a "video" is a single sentence and the cadence is meaningless; above it the
# arithmetic is the same but nothing here has been thought about past an hour.
_MIN_SECONDS, _MAX_SECONDS = 15, 7200
_DEFAULT_SECONDS = 480


def cadence(target_seconds: int) -> Cadence:
    """The per-beat schedule for a video of this length.

    Clamped rather than validated: this is called while a prompt is being assembled, and a
    target of 0 — which is what a channel with no duration set produces — must yield a
    usable schedule instead of an exception three stages into a run.
    """
    seconds = int(target_seconds or 0) or _DEFAULT_SECONDS
    seconds = max(_MIN_SECONDS, min(_MAX_SECONDS, seconds))
    beat = next((length for limit, length in _BANDS if seconds <= limit),
                _LONG_FORM_BEAT_SECONDS)
    beats = max(4, round(seconds / beat))
    return Cadence(
        target_seconds=seconds,
        beat_seconds=beat,
        beats=beats,
        rungs=RUNGS,
        rung_beats=max(1, beats // RUNGS),
    )


# ------------------------------------------------------------------- rotation banks


OPENINGS = RotationBank(
    id="openings",
    title="Openings",
    purpose="how the first beat starts, before anything has been explained",
    entries=(
        "Cold detail — one object, number or moment from the middle of the story, with "
        "no context around it at all.",
        "Flat contradiction — a plain sentence that cannot be true, said as though it is.",
        "The stake — what was lost, or nearly lost, before anybody is named.",
        "A place and a date, and one thing that happened there that has no explanation yet.",
        "The wrong answer — the explanation everyone gives, stated fairly and at its "
        "strongest, so it can be taken apart later.",
        "A count — a number of things, where the size of the number is the surprise.",
        "The last line first — the end of the story, so the video is about how it got there.",
        "A rule and its exception, in that order, in two sentences.",
    ),
)

TRANSITIONS = RotationBank(
    id="transitions",
    title="Transitions",
    purpose="how one beat hands over to the next",
    entries=(
        "The consequence — name what the last beat makes true, then start from that.",
        "The objection — say the strongest reason the last beat is wrong, then deal with it.",
        "The scale shift — same subject, from one person to a whole system, or back down.",
        "The clock — jump to a named time and let the size of the gap carry the tension.",
        "The witness — hand the next beat to whoever was actually there.",
        "The artefact — go to the document, the photograph or the recording, and read from it.",
        "The comparison — one other case where the same thing happened, in two sentences.",
        "The narrowing — from the general claim to the single instance that proves or breaks it.",
    ),
)

RE_HOOKS = RotationBank(
    id="re_hooks",
    title="Re-hooks",
    purpose="devices that open a fresh debt in the middle of a video, where attention sags",
    entries=(
        "The unpaid detail — name something mentioned earlier that still does not add up.",
        "The number that is wrong — quote a figure everyone repeats, then say it is not right.",
        "The person who knew — introduce somebody who had the answer and was ignored.",
        "The absence — a record, a part or a body of work that should exist and does not.",
        "The reversal warning — say plainly that what has been established is about to "
        "stop being true, then make it stop being true within the same beat.",
        "The cost — what finding this out took from whoever found it out.",
        "The near miss — the moment it almost went the other way.",
    ),
)

CLOSERS = RotationBank(
    id="closers",
    title="Closers",
    purpose="how the last beat lands",
    entries=(
        "The consequence now — what the answer means for something the viewer could go "
        "and look at today.",
        "The open door — one specific question the video deliberately did not take on, named.",
        "The reframe — the opening line again, now meaning something different.",
        "The price — what it cost, stated flatly, with no summary attached.",
        "The next case — one sentence naming a second instance, with no pitch for a "
        "video about it.",
        "The correction — what the viewer believed at 0:00 and what they know now, in one "
        "sentence, without the word 'so'.",
    ),
)

BANKS: tuple[RotationBank, ...] = (OPENINGS, TRANSITIONS, RE_HOOKS, CLOSERS)

# How long a device has to stay on the shelf. Six beats is roughly a third of a long-form
# video and most of a Short, which is the distance at which a repeat stops reading as a
# callback and starts reading as the channel having one trick.
NO_REPEAT_WITHIN_BEATS = 6


# ------------------------------------------------------------------ banned constructions


BANNED: tuple[BannedConstruction, ...] = (
    BannedConstruction(
        construction='"In the world of X", "When it comes to X", "In today\'s world"',
        instead="Open on the specific instance. \"In the world of deep-sea salvage, few "
                "operations were stranger\" is a sentence about the world; \"The Glomar "
                "Explorer was 619 feet long and its stated purpose was a lie\" is a "
                "sentence about the video.",
    ),
    BannedConstruction(
        construction='"Little did they know", "what happened next would change everything"',
        instead="Say what they did know, in their own terms, and let the gap between that "
                "and the outcome do the work. The phrase spends the reveal in advance and "
                "puts the narrator outside the story, pointing at it.",
    ),
    BannedConstruction(
        construction="Rhetorical question stacks — two or more questions in a row with no "
                     "answer between them",
        instead="Keep one question, make it the loop, and close it later on screen. Three "
                "questions in a row is not tension; it is the script admitting it has not "
                "decided what the video is about.",
    ),
    BannedConstruction(
        construction="Throat-clearing before the first fact — a greeting, the channel "
                     "name, \"in this video\", \"before we get started\", or a definition "
                     "of the topic",
        instead="Delete every word before the first concrete noun. The opening sentence "
                "carries a fact; the context arrives after the viewer has a reason to "
                "want it.",
    ),
    BannedConstruction(
        construction="A summary paragraph restating what was just said — \"to recap\", "
                     "\"as we've seen\", \"so what does all this mean\"",
        instead="Cut it and go straight to the consequence. Whoever followed the beat does "
                "not need it and whoever did not has already gone; the paragraph exists to "
                "give the writer somewhere to land, not the viewer.",
    ),
    BannedConstruction(
        construction="Adjective pairs — \"dark and mysterious\", \"strange and "
                     "unsettling\", \"bold and ambitious\"",
        instead="Keep the adjective that is doing work and delete the other, or replace "
                "both with the detail that made you reach for them. Two adjectives on one "
                "noun is a writer describing a feeling instead of showing its cause.",
    ),
    BannedConstruction(
        construction='"It isn\'t just X, it\'s Y" and "more than just X"',
        instead="Say Y. The construction is the narrator asserting that Y is surprising "
                "rather than the evidence earning it — and if Y is genuinely surprising, "
                "the fact before it has already done the work.",
    ),
    BannedConstruction(
        construction='"Buckle up", "you won\'t believe", "this changes everything"',
        instead="Name the thing that changes and what it changes, in the same sentence. A "
                "promise with no object in it is one the video cannot pay, and the viewer "
                "has heard it before from a video that did not.",
    ),
    BannedConstruction(
        construction="Hedge stacks — \"arguably\", \"some say\", \"many believe\", \"it "
                     "could be argued\"",
        instead="Name who said it, or drop the claim. An unattributed hedge is a fact the "
                "script does not have, dressed as one it does.",
    ),
)


# --------------------------------------------------------------------------- the blocks


DOPAMINE_LADDER = MethodBlock(
    id="dopamine_ladder",
    title="The dopamine ladder",
    params={"rungs": RUNGS, "max_flat_beats": 1},
    prose="""
The video pays the viewer back on a rising schedule. Every beat opens a small debt and
settles it, and the settlements get bigger as the video goes on.

Cadence for this video: a beat is $beat_seconds seconds long, which makes about $beats
of them. The viewer is therefore paid back $beats times, and there is no stretch longer
than $beat_seconds seconds anywhere in the script that does not settle something.

Per beat, in this order:
  1. Open the debt in the beat's first sentence. A debt is one specific thing the viewer
     now wants and does not have — a number, a name, a reason, an outcome.
  2. Spend the middle of the beat earning it: the evidence, the detail, the thing that
     makes the answer worth having.
  3. Settle it before the beat ends. Say the number. Name the person. Give the reason. A
     beat that ends unsettled has spent the viewer's attention and paid nothing back.

The ladder is the size of those settlements, and it climbs across $rungs rungs of about
$rung_beats beats each. Size is not volume — the narration does not get louder or more
excited. It is how much the settlement changes what the viewer already believes:

  Rung 1 — a fact they did not have.
  Rung 2 — a fact that makes an earlier fact mean something different.
  Rung 3 — a fact that makes the obvious explanation impossible.
  Rung 4 — the one that reframes the whole video, and it is the last thing said before
     the close.

No more than $max_flat_beats beat in a row may settle on the same rung as the beat
before it. Two of equal size is flat, and flat is where people leave.

The largest settlement never goes in the first quarter. Putting it there leaves three
quarters of the runtime with nothing to climb towards, and no amount of pace hides that.
""",
)

CURIOSITY_LOOPS = MethodBlock(
    id="curiosity_loops",
    title="Curiosity loops",
    params={"min_open_beats": 1, "max_open_at_once": 3, "unclosed_at_end": 0},
    prose="""
A loop is a question the video puts on the table and does not answer yet. This is a
counting rule, not a mood:

  - Open a loop by asking it out loud, once, in plain words. A loop the viewer has to
    infer is not open.
  - Leave it open across at least $min_open_beats following beat before closing it. A
    question asked and answered inside one beat is not a loop, it is a sentence.
  - Close it on screen, in the narration, at a beat you can point to. Every loop you open
    has a beat index where it closes — write that index down as you outline, because
    writing it down is how you find out you never closed it.
  - At most $max_open_at_once loops are open at any one moment. One more than that is
    not tension: it is the viewer losing track of which question they were promised an
    answer to, and a promise nobody is holding cannot be paid.
  - Loops may nest, and closing an inner one is a payoff in its own right. They close
    inside-out: never close the outer loop while an inner one is still open, or an answer
    arrives for a question the viewer has already put down.

Loops still open at the final beat: $unclosed_at_end. An unclosed loop at the end is a
defect, not a cliffhanger. If a loop cannot be closed, cut the sentence that opened it —
an unanswered question is what the comments end up being about instead of the video.

Never announce a loop as a delay. "We'll come back to that", "more on that in a moment"
and "but first" all tell the viewer the next stretch is safe to skip, and they skip it.
Open the question and move.
""",
)

BUT_THEREFORE = MethodBlock(
    id="but_therefore",
    title="But / therefore",
    params={"joins": ("but", "therefore"), "forbidden_join": "and then"},
    prose="""
Consecutive beats are joined by contrast or by consequence. Never by sequence.

Before writing a beat, name the join to the one before it out loud. Exactly one of these
has to be true:

  BUT — this beat contradicts, complicates or undercuts the last one.
        "The salvage crew found the hull. But it was the wrong ship."
  THEREFORE — this beat is caused by the last one.
        "The wrong ship meant the search area was wrong. Therefore every measurement
        taken from it had to be thrown out."

If the only honest join is "and then", this is not a beat. Cut it, or find the
contradiction or the consequence that makes it one. A run of "and then" is a list, and a
list gives nobody a reason to watch to the end: two entries in, the viewer can tell the
order does not matter, and once the order does not matter neither does staying.

The words themselves usually should not appear in the narration — the join is a property
of the structure, not a piece of vocabulary. But if you cannot say which of the two it
is, the join does not exist yet.

This is the strongest rule here. A script that obeys only this one still holds together.
A script that breaks this one is not rescued by any of the others.
""",
)

ROTATION_BANKS = MethodBlock(
    id="rotation_banks",
    title="Rotation banks",
    params={"no_repeat_within_beats": NO_REPEAT_WITHIN_BEATS, "banks": BANKS},
    prose="""
A bank is a pool of interchangeable devices that do the same structural job. Rotate
through the bank instead of reaching for whichever entry comes to mind — the one that
comes to mind is the one you used last time, and a device used three times has stopped
being a device and become the channel's tic.

No entry may be reused within $no_repeat_within_beats beats, and no entry is used twice
in one video while the bank still has an unused entry that would do the job. Keep a note
of what you have spent as you write.

$banks_text
""",
)

ANTI_SLOP = MethodBlock(
    id="anti_slop",
    title="Anti-slop rules",
    params={"banned": BANNED},
    prose="""
These constructions are banned by name, and each one has the thing to write instead. A
ban with nothing on the other side of it survives two paragraphs — the writer still has
to put something in the slot, and the banned phrase is the only candidate they have.

$banned_text

None of these is a matter of taste. Every one of them can be written without knowing
anything about the subject, which is exactly why it turns up and exactly why a viewer
reads it as filler and starts skipping.
""",
)


METHOD: dict[str, MethodBlock] = {
    block.id: block for block in (
        DOPAMINE_LADDER, CURIOSITY_LOOPS, BUT_THEREFORE, ROTATION_BANKS, ANTI_SLOP,
    )
}

BLOCKS: tuple[MethodBlock, ...] = tuple(METHOD.values())

# The blocks that are about the shape of the outline rather than about the sentences. The
# brief stage produces beats and no prose, so injecting the banned-phrase list there costs
# tokens on every run to police writing the brief does not contain.
STRUCTURE_IDS: tuple[str, ...] = ("dopamine_ladder", "curiosity_loops", "but_therefore")


def render(*, target_seconds: int, only: tuple[str, ...] = ()) -> str:
    """The method as prompt text, numbered, with its cadence resolved.

    `only` names block ids and keeps their declared order, so a caller cannot silently
    reorder the rules by passing them in a different sequence — the ladder before the
    loops before the joins is the order a writer works in.
    """
    beat = cadence(target_seconds)
    values = {
        **beat.as_dict(),
        "banks_text": "\n\n".join(bank.text() for bank in BANKS),
        "banned_text": "\n\n".join(item.text() for item in BANNED),
    }
    wanted = [block for block in BLOCKS if not only or block.id in only]
    return "\n\n".join(
        f"[{index}] {block.title.upper()}\n{block.body(values)}"
        for index, block in enumerate(wanted, start=1)
    )
