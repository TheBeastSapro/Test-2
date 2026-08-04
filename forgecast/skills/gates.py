"""The Sample Gate as arithmetic and a predicate, not as a paragraph in a document.

`data/image-to-video.md` states the rule that protects the wallet: never run a full-cost
image-to-video render without first surfacing one complete sample and getting approval on
its look **and** its motion. A rule stated in a document is followed when the document was
loaded, which is most of the time; image-to-video is the most expensive operation in the
pipeline, and most of the time is not good enough.

Everything decidable is here as pure functions so the pipeline can enforce it rather than
remember it. Three things are worth having in one file:

**Coverage is style AND motion, and it explains itself.** The tempting shape is one hash
per approved setup and a set-membership test. It fails in the way the skill warns about:
"style looking consistent is not enough — motion must match too", so a second setup that
kept the grade and swapped the locked camera for a whip-pan would test as covered and
render forty clips of melted faces. So an approval carries two keys, both must match, and
a miss names the facet that differed — "not covered" without the reason is a refusal the
operator cannot act on, and the next thing they do is waive the gate to get moving.

**A waiver is a value the operator supplies, never a conclusion this code reaches.** The
skill lists cases where the sample may be skipped and then says "never decide to skip on
your own". So `coverage` can report that a shot is *waivable* and never grants it.

**Two charges, never one.** Each provider submission is separately billed work; the sample
is not credited against the full render. `Quote` therefore has no total field that could
be quoted on its own, and `charges()` hands back one entry per submission so a caller
writing them to the ledger writes two rows. Anything that flattens them to one number is
the "rolled in" phrasing the skill forbids, in the ledger instead of in a sentence.

No database, no provider, no import from the rest of the app: the whole point is that the
pipeline can be wired to this later without either side growing a dependency on the other.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace

# What a sample is generated at. The skill's rule is the model's shortest supported
# duration, targeting about five seconds — long enough for motion to develop, and never
# "render ten seconds, show five, deliver the rest unreviewed".
SAMPLE_TARGET_SECONDS = 5.0

# Under this, the skill permits skipping the sample — the clip costs less than the sample
# would. It is a permission for the operator, not a decision this module makes.
SHORT_SHOT_SECONDS = 3.0

# A run with more distinct setups than this is not a style, it is a shot list nobody
# constrained — and sampling each one costs more than the batch it is protecting. The
# gate reports it rather than sampling them all, because the fix is to reduce the
# variation, not to buy thirty samples.
#
# It lives here rather than in the node that enforces it because it is also the ceiling
# the ledger reserves against: this is the largest number of clips the gate can buy, and
# a reserve that assumed one while the gate bought six was the shape of the bug.
MAX_SETUPS = 6


def _norm(value: str) -> str:
    """One spelling per facet, so cosmetic differences are not treated as new setups.

    "Push-in", "push in" and "  PUSH  IN " describe the same camera. Left un-normalised
    each would demand its own sample, and a gate that fires on every shot is a gate the
    operator turns off.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


@dataclass(frozen=True)
class StyleKey:
    """What "the same look" means, as fields rather than as a judgement.

    Aspect ratio is in here because a 9:16 crop of an approved 16:9 setup is a different
    composition, and register because `data/visual-register.md` is explicit that a
    Register A shot which came back with studio lighting is a rejection, not a variation.
    """

    register: str = ""          # "A" authentic-amateur / "B" cinematic / "C" mixed
    grade: str = ""             # warm sepia, cool cinematic, muted documentary…
    lighting: str = ""          # available/natural, three-point, low-key…
    aspect_ratio: str = ""

    def facets(self) -> dict[str, str]:
        return {"register": _norm(self.register), "grade": _norm(self.grade),
                "lighting": _norm(self.lighting),
                "aspect_ratio": _norm(self.aspect_ratio)}


@dataclass(frozen=True)
class MotionKey:
    """What "the same motion" means. The half that gets silently reused.

    `intensity` is the dial from the skill (static / subtle / moderate / high / extreme),
    `focal_verb` the one action the clip is about, `camera` the move. A change in any of
    them is a different failure mode: a locked camera that becomes an orbit distorts a
    face, and "subtle" becoming "high" is where limbs melt. So all three are compared,
    and none of them is inferred from the other two.
    """

    intensity: str = ""
    focal_verb: str = ""
    camera: str = ""

    def facets(self) -> dict[str, str]:
        return {"intensity": _norm(self.intensity), "focal_verb": _norm(self.focal_verb),
                "camera": _norm(self.camera)}


@dataclass(frozen=True)
class ShotSetup:
    """One i2v setup: the model plus the style and motion a sample would approve.

    `model` is a facet of its own rather than part of the style, because the same prompt
    on Kling and on LTX is two different pictures at forty times the price — and because
    a mismatch there needs its own sentence when the gate refuses.
    """

    model: str = ""
    style: StyleKey = field(default_factory=StyleKey)
    motion: MotionKey = field(default_factory=MotionKey)
    seconds: float = 0.0
    shot_id: str = ""

    def facets(self) -> dict[str, str]:
        return {"model": _norm(self.model),
                **{f"style.{k}": v for k, v in self.style.facets().items()},
                **{f"motion.{k}": v for k, v in self.motion.facets().items()}}

    @property
    def setup_id(self) -> str:
        """A short stable id for this style-and-motion combination.

        Stored beside the approval and on each rendered clip so an audit can answer
        "which sample authorised this charge" without re-deriving anything. Duration and
        shot id are deliberately excluded: they vary per shot inside one approved setup,
        and folding them in would give every shot its own id and make the approval cover
        exactly one clip.
        """
        payload = "|".join(f"{key}={value}" for key, value in sorted(self.facets().items()))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class SampleApproval:
    """One approved sample, and the exact setup it approves.

    `request_id` is the provider's own id for the billed submission. It is here because
    the audit question is not "was something approved" but "which charge was the sample",
    and a sample whose submission cannot be pointed at is indistinguishable from a full
    render that was called a sample afterwards.
    """

    setup: ShotSetup
    approved_by: str = ""
    approved_at: str = ""
    request_id: str = ""
    sample_seconds: float = 0.0
    sample_usd: float = 0.0
    note: str = ""

    @property
    def setup_id(self) -> str:
        return self.setup.setup_id


@dataclass(frozen=True)
class Waiver:
    """The operator's decision to proceed without a sample, recorded as data.

    Deliberately not a boolean: a waived batch that later produces forty unusable clips
    has to be answerable — who waived it, when, and on what grounds. `reason` is the
    operator's words, not a code, because the reason is the part worth reading.
    """

    reason: str
    granted_by: str
    scope: str = "shot"        # "shot" or "batch"
    granted_at: str = ""


@dataclass(frozen=True)
class Coverage:
    """Whether a shot may render at full cost, and why.

    Never a bare boolean. `mismatched` names the facets that differed so the answer can
    be surfaced as "this needs its own sample because the camera changed", which is
    actionable, instead of "not approved", which invites a blanket waiver.
    """

    covered: bool
    reason: str
    setup_id: str = ""
    approval_request_id: str = ""
    mismatched: tuple[str, ...] = ()
    waivable: bool = False
    waived: bool = False

    def as_dict(self) -> dict:
        return {"covered": self.covered, "reason": self.reason, "setup_id": self.setup_id,
                "approval_request_id": self.approval_request_id,
                "mismatched": list(self.mismatched), "waivable": self.waivable,
                "waived": self.waived}


_FACET_WORDS = {
    "model": "the model",
    "style.register": "the visual register",
    "style.grade": "the colour grade",
    "style.lighting": "the lighting",
    "style.aspect_ratio": "the aspect ratio",
    "motion.intensity": "the motion intensity",
    "motion.focal_verb": "the action",
    "motion.camera": "the camera move",
}


def mismatches(approval: SampleApproval, setup: ShotSetup) -> tuple[str, ...]:
    """Which facets of `setup` differ from the approved one, in a stable order.

    An empty facet on either side counts as a difference rather than a wildcard. A shot
    that forgot to say what its camera does is not a shot that matches every camera —
    treating unknown as "same" is how a whip-pan renders under a locked-camera approval.
    """
    approved, wanted = approval.setup.facets(), setup.facets()
    return tuple(key for key in _FACET_WORDS if approved.get(key, "") != wanted.get(key, ""))


def covers(approval: SampleApproval, setup: ShotSetup) -> Coverage:
    """Whether one approval covers one shot. Style AND motion AND model, all three."""
    if not approval.request_id:
        # An approval with no billed submission behind it is a claim, not a sample.
        return Coverage(False, "that approval has no sample submission recorded against it",
                        setup_id=setup.setup_id, mismatched=("request_id",))

    differing = mismatches(approval, setup)
    if not differing:
        return Coverage(True, f"covered by the sample approved as setup "
                              f"{approval.setup_id} ({approval.request_id})",
                        setup_id=setup.setup_id,
                        approval_request_id=approval.request_id)

    named = ", ".join(_FACET_WORDS[key] for key in differing if key in _FACET_WORDS)
    return Coverage(False, f"this shot needs its own sample: {named} differs from the "
                           f"approved setup {approval.setup_id}",
                    setup_id=setup.setup_id, mismatched=differing)


def coverage(setup: ShotSetup, approvals: list[SampleApproval] | tuple[SampleApproval, ...],
             *, waiver: Waiver | None = None) -> Coverage:
    """The gate's answer for one shot against every approval the run holds.

    Order matters only for the message: the closest miss is reported rather than the
    first, because "the camera move differs" points at the fix and "the model, the grade,
    the lighting and the camera differ" reads as an unrelated setup and gets waived.
    """
    results = [covers(approval, setup) for approval in approvals]
    for result in results:
        if result.covered:
            return result

    if waiver is not None:
        return Coverage(
            True,
            f"no sample covers this shot; rendering under a {waiver.scope} waiver from "
            f"{waiver.granted_by or 'the operator'}: {waiver.reason}",
            setup_id=setup.setup_id, waived=True,
            mismatched=min((r.mismatched for r in results), key=len, default=()),
        )

    short = 0 < setup.seconds < SHORT_SHOT_SECONDS
    if not results:
        return Coverage(False, "no sample has been approved for this run yet",
                        setup_id=setup.setup_id, waivable=short)

    closest = min(results, key=lambda result: len(result.mismatched))
    return replace(closest, waivable=short)


# ------------------------------------------------------------------------- the money


def sample_seconds_for(shortest_supported: float, *,
                       target: float = SAMPLE_TARGET_SECONDS,
                       longest_supported: float = 0.0) -> float:
    """How long the sample clip is generated at, for a model with this minimum.

    The skill's wording is "the model's shortest supported sample duration, targeting
    about five seconds", which is two constraints and not one: a model whose minimum is
    six seconds samples at six, and a model that will accept two seconds still samples at
    five, because two seconds of a five-second motion shows a start and no development —
    an approval given on that is an approval of nothing.

    The sample is generated at this duration directly. Rendering longer and surfacing a
    trimmed preview is the specific thing the skill forbids, because the untrimmed
    remainder was paid for and never reviewed.
    """
    seconds = max(float(shortest_supported or 0.0), float(target))
    if longest_supported:
        seconds = min(seconds, float(longest_supported))
    return round(seconds, 3)


@dataclass(frozen=True)
class Charge:
    """One billable provider submission. The unit the ledger writes a row for."""

    label: str
    seconds: float
    usd: float

    def as_dict(self) -> dict:
        return {"label": self.label, "seconds": self.seconds, "usd": round(self.usd, 4)}


@dataclass(frozen=True)
class Quote:
    """What running this shot costs, as the two charges it actually is.

    There is no `total` field on purpose. A single number is what gets quoted, and a
    single number is indistinguishable from "the full render, sample included" — which is
    the sentence the skill forbids because it is false: on fal each submission bills on
    its own `request_id` and the sample is not credited against anything. Callers that
    want a sum call `sum_usd()`, whose name says it is an addition of separate charges.
    """

    model: str
    usd_per_second: float
    sample: Charge
    remainder: Charge

    def charges(self) -> tuple[Charge, ...]:
        return (self.sample, self.remainder)

    def sum_usd(self) -> float:
        return round(self.sample.usd + self.remainder.usd, 4)

    def sentence(self) -> str:
        """The line the gate surfaces. Two prices, and the words "separate charge"."""
        return (f"sample {self.sample.seconds:g}s ${self.sample.usd:.2f} + "
                f"{self.remainder.label} {self.remainder.seconds:g}s "
                f"${self.remainder.usd:.2f} — two separate charges, "
                f"${self.sum_usd():.2f} in total")

    def as_dict(self) -> dict:
        return {"model": self.model, "usd_per_second": self.usd_per_second,
                "charges": [charge.as_dict() for charge in self.charges()],
                "sum_usd": self.sum_usd(), "billed_separately": True,
                "sentence": self.sentence()}


def quote(*, model: str, usd_per_second: float, full_seconds: float,
          shortest_supported: float, longest_supported: float = 0.0,
          extension_seconds: float = 0.0) -> Quote:
    """Price a sample and the render that follows it, as two charges.

    `extension_seconds` is for the case the skill allows: a *verified* continuation
    endpoint can extend the approved sample instead of re-rendering the whole shot, so
    the second charge prices the extension. It is a parameter rather than an inference
    because assuming a continuation endpoint exists and quoting the cheaper number is how
    an estimate comes in under what the run then spends.
    """
    rate = float(usd_per_second)
    sample_seconds = sample_seconds_for(shortest_supported,
                                        longest_supported=longest_supported)
    sample = Charge("sample", sample_seconds, round(rate * sample_seconds, 4))

    if extension_seconds:
        remainder = Charge("extension", float(extension_seconds),
                           round(rate * float(extension_seconds), 4))
    else:
        # The full length, not the length minus the sample. The sample buys information,
        # not footage: the approved clip is five seconds of an eight-second shot and the
        # remaining three cannot be generated on their own.
        remainder = Charge("full render", float(full_seconds),
                           round(rate * float(full_seconds), 4))
    return Quote(model=model, usd_per_second=rate, sample=sample, remainder=remainder)


@dataclass(frozen=True)
class BatchBudget:
    """The aggregate the skill requires surfacing before a multi-setup batch starts.

    Per-shot quotes are what an operator approves one at a time; this is the number that
    changes their mind. A forty-clip batch across six style-and-motion setups owes six
    samples before a single production clip exists, and finding that out on the sixth
    gate is finding it out after paying for five.
    """

    setups: int
    samples_usd: float
    renders_usd: float
    quotes: tuple[Quote, ...] = ()

    def sum_usd(self) -> float:
        return round(self.samples_usd + self.renders_usd, 4)

    def sentence(self) -> str:
        return (f"{self.setups} distinct style-and-motion setup"
                f"{'s' if self.setups != 1 else ''}, so "
                f"{self.setups} sample{'s' if self.setups != 1 else ''} at "
                f"${self.samples_usd:.2f} before any production clip, then "
                f"${self.renders_usd:.2f} of renders — ${self.sum_usd():.2f} in total")

    def as_dict(self) -> dict:
        return {"setups": self.setups, "samples_usd": round(self.samples_usd, 4),
                "renders_usd": round(self.renders_usd, 4), "sum_usd": self.sum_usd(),
                "sentence": self.sentence()}


def batch_budget(quotes_by_setup: dict[str, Quote]) -> BatchBudget:
    """Aggregate one quote per distinct setup into the pre-batch number.

    Keyed by `setup_id` by the caller, which is the point: two shots sharing a setup owe
    one sample between them, and counting per shot would quote six samples for a batch
    that needs two — an over-quote that gets the gate argued out of the pipeline.
    """
    quotes = tuple(quotes_by_setup.values())
    return BatchBudget(
        setups=len(quotes),
        samples_usd=round(sum(item.sample.usd for item in quotes), 4),
        renders_usd=round(sum(item.remainder.usd for item in quotes), 4),
        quotes=quotes,
    )


# ------------------------------------------------------------------------ the surface


def surface(*, setup: ShotSetup, prompt: str, clip_path: str, quote_: Quote,
            usd_spent_so_far: float, batch: BatchBudget | None = None) -> dict:
    """The payload a sample gate node hands the operator, as one shape.

    Four things have to be in front of them together, because each one alone invites the
    wrong answer: the whole clip (a trimmed preview is not the sample), the prompt that
    produced it (otherwise "make it warmer" cannot be turned into an edit), what the run
    has spent, and what proceeding costs. Assembling this in the node would let a caller
    surface three of the four and still call it a gate.
    """
    return {
        "setup_id": setup.setup_id,
        "model": setup.model,
        "prompt": prompt,
        "clip": clip_path,
        "clip_seconds": quote_.sample.seconds,
        "usd_spent_so_far": round(float(usd_spent_so_far), 4),
        "proceeding": quote_.as_dict(),
        "batch": batch.as_dict() if batch else None,
        "approves": "shots sharing this exact style and motion only — a different "
                    "camera move, grade or action needs its own sample",
        "question": f"Here is the sample, the full {quote_.sample.seconds:g}-second clip. "
                    f"Spent so far ${float(usd_spent_so_far):.2f}. {quote_.sentence()}. "
                    f"Render it, or revise the prompt?",
    }
