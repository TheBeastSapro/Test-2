"""The shipped pipelines.

`faceless_longform` is the flagship: an 8–12 minute narrated documentary-style
video with generated B-roll, optional talking-head insert, burned captions and a
scheduled upload. `faceless_shorts` is the same spine compressed to a vertical clip.

Gates are placed where a human veto is cheapest. Approving a brief costs nothing;
approving a finished render costs whatever the shots already burned. So the
expensive stages sit *behind* gates on the cheap stages that determine them.
"""

from __future__ import annotations

from .spec import NodeSpec, PipelineSpec

WORDS_PER_SECOND = 2.6
SECONDS_PER_SHOT = 6.0


def faceless_longform(
    *, target_seconds: int = 480, use_avatar: bool = False, publish: bool = True
) -> PipelineSpec:
    words = int(target_seconds * WORDS_PER_SECOND)
    shots = max(4, round(target_seconds / SECONDS_PER_SHOT))

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create production brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write full script",
            depends_on=("brief",),
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
            key="voice",
            type="voice",
            title="Narrate script",
            depends_on=("script",),
            estimated_units=words * 5.5,  # ≈ characters
        ),
        NodeSpec(
            key="broll_plan",
            type="broll_plan",
            title="Plan B-roll shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="shots",
            type="shots",
            title="Generate B-roll",
            depends_on=("broll_plan",),
            estimated_units=shots,
            params={"width": 1280, "height": 720},
        ),
    ]

    render_deps = ["shots", "voice"]
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
    shots = max(3, round(target_seconds / 4))

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create short brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write hook-first script",
            depends_on=("brief",),
            requires_approval=True,
            estimated_units=words,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="voice", type="voice", title="Narrate script", depends_on=("script",),
            estimated_units=words * 5.5,
        ),
        NodeSpec(
            key="broll_plan", type="broll_plan", title="Plan vertical shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="shots", type="shots", title="Generate vertical B-roll",
            depends_on=("broll_plan",), estimated_units=shots,
            params={"width": 1080, "height": 1920},
        ),
        NodeSpec(
            key="thumbnail", type="thumbnail", title="Generate cover frame",
            depends_on=("script",), estimated_units=1,
            params={"concepts": 1, "width": 1080, "height": 1920},
        ),
        NodeSpec(
            key="render", type="render", title="Render vertical video",
            depends_on=("shots", "voice"),
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
