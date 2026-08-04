"""The shipped pipelines.

`faceless_longform` is the flagship: an 8–12 minute narrated documentary-style
video with generated B-roll, optional talking-head insert, burned captions and a
scheduled upload. `faceless_shorts` is the same spine compressed to a vertical clip.

Gates are placed where a human veto is cheapest. Approving a brief costs nothing;
approving a finished render costs whatever the shots already burned. So the
expensive stages sit *behind* gates on the cheap stages that determine them.
"""

from __future__ import annotations

from ..render.cutting import estimate_plates
from .spec import NodeSpec, PipelineSpec

WORDS_PER_SECOND = 2.6


def faceless_longform(
    *, target_seconds: int = 480, use_avatar: bool = False, publish: bool = True
) -> PipelineSpec:
    words = int(target_seconds * WORDS_PER_SECOND)
    # The shots node buys *plates*, not shots: one image carries several shots at
    # different crops. This used to reserve `target_seconds / 6` units — about 80 for an
    # 8-minute video against the eight the node then spent, wrong by an order of
    # magnitude in the safe direction. Deriving it from the same constants the node uses
    # means the reserve now tracks the spend instead of guessing at it.
    shots = estimate_plates(target_seconds)

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create production brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds},
        ),
        NodeSpec(
            key="research",
            type="research",
            title="Research & verify sources",
            depends_on=("brief",),
            params={"max_queries": 5, "max_pages": 8},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write full script",
            # Research first: a documentary script with no sources invents its
            # statistics, and the citation rule needs real claims to point at.
            depends_on=("brief", "research"),
            requires_approval=True,
            estimated_units=words,
            params={"target_duration_seconds": target_seconds},
        ),
        NodeSpec(
            key="thumbnail",
            type="thumbnail",
            title="Generate thumbnail",
            depends_on=("script",),
            requires_approval=True,
            estimated_units=2,
            params={"concepts": 2, "width": 1280, "height": 720},
        ),
        NodeSpec(
            key="voice_casting",
            type="voice_casting",
            title="Cast the voice",
            depends_on=("script",),
            # Gated: the voice is the most audible decision in the video, so the
            # system auditions candidates and a human picks.
            requires_approval=True,
            estimated_units=3,
            params={"shortlist": 3},
        ),
        NodeSpec(
            key="voice",
            type="voice",
            title="Narrate script",
            depends_on=("script", "voice_casting"),
            estimated_units=words * 5.5,  # ≈ characters
        ),
        NodeSpec(
            key="sound",
            type="sound",
            title="Score the sound",
            # After the narration, because the bed's length and its level are both derived
            # from the voiceover that actually exists rather than from the script's
            # estimate of it. No `estimated_units`: the bed comes out of a flat
            # subscription rather than a per-unit price, so there is no quantity to
            # multiply and the node's base estimate is the whole reserve.
            depends_on=("script", "voice"),
        ),
        NodeSpec(
            key="broll_plan",
            type="broll_plan",
            title="Plan B-roll shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="sample",
            type="sample",
            title="Sample the look",
            # The gate this file's own preamble describes: the expensive stage sits
            # behind an approval on the cheap stage that determines it. One short clip
            # per distinct style-and-motion setup — two or three on a normal video —
            # costs about a fiftieth of the batch it authorises, and the failure it
            # catches is not one bad clip but the same defect in all eighty at once.
            depends_on=("broll_plan",),
            requires_approval=True,
            # Priced as one setup rather than as the run's real count, which is not known
            # until `broll_plan` has produced its shots. The node settles on what it
            # actually generated, so an under-estimate here is released rather than
            # charged — and over-reserving on a gate would defeat the point of a gate
            # that exists to protect a budget.
            estimated_units=1,
        ),
        NodeSpec(
            key="shots",
            type="shots",
            title="Generate B-roll",
            # Both, deliberately. `broll_plan` because that is where the shot list comes
            # from, and `sample` because the approval is the whole reason this stage is
            # allowed to spend — an edge only on the plan would let the batch render
            # while the sample was still being looked at.
            depends_on=("broll_plan", "sample"),
            estimated_units=shots,
            params={"width": 1280, "height": 720},
        ),
    ]

    # `sound` is a dependency of the render rather than a sibling of it. Both depend on
    # `voice`, so without this edge the two are in the same wave and the render can mux
    # the dry narration while the bed is still being fetched — a video with no music and a
    # node output claiming one, which is the one failure worse than having no music.
    render_deps = ["shots", "voice", "sound"]
    if use_avatar:
        nodes.append(
            NodeSpec(
                key="avatar",
                type="avatar",
                title="Render avatar pass",
                depends_on=("voice",),
                estimated_units=target_seconds,
            )
        )
        render_deps.append("avatar")

    nodes.append(
        NodeSpec(
            key="render",
            type="render",
            title="Render final video",
            depends_on=tuple(render_deps),
            params={"width": 1280, "height": 720, "subtitles": True},
            max_attempts=2,
        )
    )
    nodes.append(
        NodeSpec(
            key="compliance",
            type="compliance",
            title="Compliance & policy check",
            depends_on=("render", "thumbnail"),
        )
    )
    if publish:
        nodes.append(
            NodeSpec(
                key="final_review",
                type="final_review",
                title="Preview & approve upload",
                depends_on=("compliance", "thumbnail"),
                requires_approval=True,
            )
        )
        nodes.append(
            NodeSpec(
                key="publish",
                type="publish",
                title="Publish to YouTube",
                depends_on=("final_review",),
                params={"privacy_status": "private"},
                max_attempts=2,
            )
        )

    spec = PipelineSpec(
        name="faceless_longform",
        title="Faceless long-form video",
        description="Narrated 8–12 minute video with generated B-roll and captions.",
        nodes=tuple(nodes),
    )
    spec.validate()
    return spec


def faceless_shorts(*, target_seconds: int = 45, publish: bool = True, **_) -> PipelineSpec:
    words = int(target_seconds * WORDS_PER_SECOND)
    # A short is mostly floor rather than rate: its beats are too brief to want a second
    # plate, so the reserve is one per scene and the runtime term barely contributes.
    shots = estimate_plates(target_seconds)

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create short brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="research",
            type="research",
            title="Research & verify sources",
            depends_on=("brief",),
            params={"max_queries": 3, "max_pages": 4},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write hook-first script",
            depends_on=("brief", "research"),
            requires_approval=True,
            estimated_units=words,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="voice_casting", type="voice_casting", title="Cast the voice",
            depends_on=("script",), requires_approval=True, estimated_units=3,
            params={"shortlist": 3},
        ),
        NodeSpec(
            key="voice", type="voice", title="Narrate script",
            depends_on=("script", "voice_casting"),
            estimated_units=words * 5.5,
        ),
        NodeSpec(
            key="sound", type="sound", title="Score the sound",
            depends_on=("script", "voice"),
        ),
        NodeSpec(
            key="broll_plan", type="broll_plan", title="Plan vertical shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="sample", type="sample", title="Sample the look",
            # On a short the ratio is nearer one to eight than one to fifty, so the gate
            # buys less. It is still here, because what it catches does not scale with
            # the batch: a camera move that melts faces is wrong in all eight clips of a
            # short exactly as it is wrong in all eighty of a long-form, and a short that
            # has to be regenerated has lost the whole render rather than a fraction.
            depends_on=("broll_plan",), requires_approval=True, estimated_units=1,
        ),
        NodeSpec(
            key="shots", type="shots", title="Generate vertical B-roll",
            depends_on=("broll_plan", "sample"), estimated_units=shots,
            params={"width": 1080, "height": 1920},
        ),
        NodeSpec(
            key="thumbnail", type="thumbnail", title="Generate cover frame",
            depends_on=("script",), estimated_units=1,
            params={"concepts": 1, "width": 1080, "height": 1920},
        ),
        NodeSpec(
            key="render", type="render", title="Render vertical video",
            depends_on=("shots", "voice", "sound"),
            params={"width": 1080, "height": 1920, "subtitles": True},
            max_attempts=2,
        ),
        NodeSpec(
            key="compliance", type="compliance", title="Compliance & policy check",
            depends_on=("render",),
        ),
    ]
    if publish:
        nodes.append(
            NodeSpec(
                key="final_review", type="final_review", title="Preview & approve upload",
                depends_on=("compliance", "thumbnail"), requires_approval=True,
            )
        )
        nodes.append(
            NodeSpec(
                key="publish", type="publish", title="Publish Short",
                depends_on=("final_review",),
                params={"privacy_status": "private"}, max_attempts=2,
            )
        )

    spec = PipelineSpec(
        name="faceless_shorts",
        title="Faceless short",
        description="Vertical hook-first clip under 60 seconds.",
        nodes=tuple(nodes),
    )
    spec.validate()
    return spec


PIPELINES = {
    "faceless_longform": faceless_longform,
    "faceless_shorts": faceless_shorts,
}

PIPELINE_META = [
    {
        "name": "faceless_longform",
        "title": "Faceless long-form video",
        "description": "Narrated 8–12 minute video with generated B-roll and captions.",
        "default_seconds": 480,
    },
    {
        "name": "faceless_shorts",
        "title": "Faceless short",
        "description": "Vertical hook-first clip under 60 seconds.",
        "default_seconds": 45,
    },
]


def get_pipeline(name: str, **options) -> PipelineSpec:
    builder = PIPELINES.get(name)
    if builder is None:
        raise KeyError(f"unknown pipeline '{name}'; have {sorted(PIPELINES)}")
    return builder(**options)
