"""The skills library, reached the way the agent reaches it.

`tests/test_skills.py` covers the file format, the path guard and the editor page. What
is asserted here is the thing that makes any of that matter: that a document the
operator wrote actually arrives in a turn. The failures worth guarding are that the
listing quietly starts carrying bodies and floods the transcript, that a wrong slug
raises across the MCP boundary instead of coming back as something to act on, and that
these two tools drift out of the pre-allowed set and stop being called at all.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from forgecast import skills
from forgecast.agent import skills_tools
from forgecast.agent.studio import Studio


@pytest.fixture
def library(tmp_path, monkeypatch):
    """Point the skills folder at a directory of this test's own.

    The tools read the installation's storage directory rather than taking a path, so
    the redirection happens at the one place that resolves it. Without it these tests
    would write into the suite's shared storage and the next test to list skills would
    see whatever this one left behind.
    """
    monkeypatch.setattr(skills, "get_settings",
                        lambda: SimpleNamespace(storage_dir=tmp_path))
    return skills.directory()


def call(tool, **args) -> dict:
    """Invoke one MCP tool the way the SDK would, and return its content block."""
    return asyncio.run(tool.handler(args))


def text_of(result: dict) -> str:
    return "\n".join(part.get("text", "") for part in result["content"])


@pytest.fixture
def tools(user, library):
    return {item.name: item for item in skills_tools.build(Studio(user_id=user.id))}


# ------------------------------------------------------------------- the round trip


def test_a_skill_the_operator_wrote_reaches_the_agent(tools, library):
    """The whole point: written on the page, loaded in a turn."""
    skills.save("thumbnail-faces", "Thumbnail faces",
                "Whenever a thumbnail brief is written for a longform video.",
                "# Faces\n\nOne face, filling 40% of the frame, eyes on the lens.\n")

    listed = json.loads(text_of(call(tools["list_skills"])))
    row = next(item for item in listed["skills"] if item["slug"] == "thumbnail-faces")
    assert row["name"] == "Thumbnail faces"
    assert row["when_to_use"].startswith("Whenever a thumbnail brief")
    # The word count is what tells the agent whether loading this costs a paragraph or
    # a page, so it has to be a real count of the body.
    assert row["words"] == 13

    loaded = json.loads(text_of(call(tools["load_skill"], slug="thumbnail-faces")))
    assert "eyes on the lens" in loaded["body"]
    assert loaded["name"] == "Thumbnail faces"
    # And loading it says out loud that following it has to be declared, or the agent
    # follows a document the transcript never names.
    assert "followed" in loaded["follow"]


def test_the_listing_does_not_carry_bodies(tools):
    """A listing that shipped the bodies would be a tool the agent stops calling.

    The three starters are roughly nine thousand characters between them. Returned on
    every check, most of a tool result goes on documents that turned out not to apply —
    and the model learns to skip the call that floods it.
    """
    result = text_of(call(tools["list_skills"]))
    listed = json.loads(result)
    assert listed["count"] == 3

    for row in listed["skills"]:
        assert set(row) == {"slug", "name", "when_to_use", "words"}
        assert row["words"] > 100                 # they are long, and stayed elsewhere
    # Sentences that only exist inside the bodies, checked against the whole payload.
    assert "Never say \"but first\"" not in result
    assert "Minimum 1.2 seconds on screen" not in result
    assert len(result) < 2000


def test_an_unknown_slug_is_an_error_the_agent_can_act_on(tools):
    """Not an exception: a refusal carrying the slugs that do exist.

    A KeyError crossing the MCP boundary is a stack trace in a log nobody opens. The
    agent's only sensible next move is to ask for the right slug, and it needs the
    alternatives in this result rather than in a second call.
    """
    result = call(tools["load_skill"], slug="hook-writting")
    # `is_error` is what stops the model reading a returned error as a successful call
    # that happened to mention a problem.
    assert result["is_error"] is True
    # The MCP wrapper sends `error` as the entire tool result, so the real slugs have to
    # be in that sentence. Kept in a sibling key they would never reach the agent.
    assert "hook-writing" in text_of(result)

    failed = Studio().load_skill("hook-writting")
    assert "hook-writting" in failed["error"]
    assert "hook-writing" in failed["skills"]

    # An empty slug is the same kind of answer rather than a different failure.
    empty = call(tools["load_skill"], slug="")
    assert empty["is_error"] is True
    assert "list_skills" in text_of(empty)
    # And a slug that cannot even become a filename is refused, not followed out of
    # the skills folder.
    assert Studio().load_skill("../../etc/passwd")["error"]


def test_a_skill_without_a_when_to_use_line_is_still_judgeable(tools, library):
    """An empty string gives the agent nothing to decide with.

    Hand-written files and files saved with the field left blank both happen, and the
    listing is the only place the decision to load is made.
    """
    (library / "terse.md").write_text("---\nname: Terse\n---\n\nCut on the beat.\n",
                                      encoding="utf-8")
    listed = json.loads(text_of(call(tools["list_skills"])))
    row = next(item for item in listed["skills"] if item["slug"] == "terse")
    assert row["when_to_use"] == "Cut on the beat."


# ------------------------------------------------------------------- the discipline


def test_both_skill_tools_are_pre_allowed(user):
    """Read-only, so they may be called without a prompt.

    A check the agent has to ask permission for is a check it stops making, and an
    unread skill is indistinguishable from one nobody wrote. The gate stays out of the
    allowed set for the opposite reason, and that must not have moved.
    """
    from forgecast.agent import tools as agent_tools

    for name in ("list_skills", "load_skill"):
        assert f"mcp__forgecast__{name}" in agent_tools.ALLOWED
        assert name in agent_tools.ALL_TOOLS

    assert "mcp__forgecast__decide_gate" not in agent_tools.ALLOWED
    assert "decide_gate" in agent_tools.ALL_TOOLS


def test_the_description_says_when_to_call_it(user):
    """The description is the only thing that decides whether it is ever called.

    "List skills" is accurate and gets called never, because nothing in it says the
    listing is worth a turn before writing. So it has to name the moment and the
    citation, and it is asserted here because shortening it breaks nothing else.
    """
    listing = skills_tools.LIST_DESCRIPTION.lower()
    assert "before" in listing
    for moment in ("script", "hook", "caption"):
        assert moment in listing
    assert "load_skill" in listing
    assert len(skills_tools.LIST_DESCRIPTION) > 300

    loading = skills_tools.LOAD_DESCRIPTION.lower()
    assert "follow" in loading
    assert "slug" in loading


def test_the_system_prompt_tells_the_agent_the_skills_exist(user):
    """Tools nothing points at get called on the model's own initiative, which is to say
    inconsistently. The prompt is what makes checking the library the default."""
    from forgecast.agent.assistant import system_prompt

    prompt = system_prompt(Studio(user_id=user.id))
    assert "list_skills" in prompt
    assert "load_skill" in prompt
    # The paragraphs that were already there must survive the insertion.
    assert "THE GATE IS THEIRS, NOT YOURS." in prompt
    assert "PREVIEW BEFORE RENDER." in prompt
