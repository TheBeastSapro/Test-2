"""The four visual documents that ship as files rather than as Python strings.

Two failures are worth a test here, and neither shows up in `tests/test_skills.py`.

The first is packaging. A wheel or a zip built without the data directory installs the
seeding code and none of the documents, and the symptom is a Skills page listing three
skills instead of seven — which reads as a product decision, not as a broken install. So
the shipping rule in `tools/package.py` is asserted against the real paths, and the
degraded case is asserted to degrade rather than to raise.

The wheel's half of that is `[tool.setuptools.package-data]` in pyproject.toml naming
`"forgecast.skills" = ["data/*.md"]`. That file belongs to another agent, so it is not
asserted from here; it was verified by building a wheel with and without the entry.

The second is the `when_to_use` line. It is the entire basis on which the agent decides
whether to spend a turn on twelve kilobytes, so a line that could describe any of the
four is a line that loads the wrong one.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

from forgecast import skills

ROOT = Path(__file__).resolve().parent.parent

# What each document must actually contain. Not a word count: a file truncated to its
# first heading passes a length check and teaches nothing, and these four are load-bearing
# rules rather than prose — the Sample Gate is the app's cost protection.
LOAD_BEARING: dict[str, tuple[str, ...]] = {
    "image-to-video.md": ("Sample Gate", "[SUBJECT] + [ACTION]", "per-second",
                          "bill separately"),
    "i2v-prompt-cookbook.md": ("Establishing exterior", "Hook close-up", "Forbidden",
                               "Anti-pattern diagnoses"),
    "visual-register.md": ("Register A", "Register B", "studio-lighting trap"),
    "storyboard.md": ("Gate 1", "Gate 4", "four depths", "Duration maths"),
    # The sound pair carries numbers rather than gates. Each marker below is a figure that
    # was measured, not chosen, so a document that lost them is a document that no longer
    # says what to do — and the mix would come back sounding like a default.
    "sound-designer.md": ("Non-negotiables", "Diagnose by measuring, never by ear",
                          "dBFS", "Order of work"),
    "sound-designer-method.md": ("Diagnose by measuring, never by ear",
                                 "Effects sit ABOVE the bed", "Anchoring", "Casting"),
}


def _package_tool():
    """`tools/package.py`, loaded by path — it is a script, not an importable module."""
    spec = importlib.util.spec_from_file_location("_pkg", ROOT / "tools" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ the documents


def test_every_shipped_document_is_present_and_whole():
    for _, _, filename in skills.SHIPPED_DOCS:
        path = skills.DATA_DIR / filename
        assert path.exists(), f"{filename} is missing from {skills.DATA_DIR}"
        text = path.read_text(encoding="utf-8")
        for marker in LOAD_BEARING[filename]:
            assert marker in text, f"{filename} no longer contains {marker!r}"


def test_the_documents_seed_as_skills_with_bodies_intact(tmp_path):
    rows = {row["slug"]: row for row in skills.available(tmp_path)}
    for name, _, filename in skills.SHIPPED_DOCS:
        slug = skills.slugify(name)
        assert slug in rows, f"{filename} did not seed"
        # Word counts are what the agent reads to decide whether loading one costs a
        # paragraph or a page, so a plausible number is part of the contract.
        # The floor catches a truncated or half-copied document, which is why it exists
        # at all; it is not a quality bar. It moved from 1200 when a complete 867-word
        # skill arrived and failed it — a real document being rejected for being concise
        # is the floor being wrong, not the document.
        assert 800 < rows[slug]["words"] < 3000, rows[slug]["words"]

        loaded = skills.get(slug, tmp_path)
        for marker in LOAD_BEARING[filename]:
            assert marker in loaded.body
        # The front matter must not have been absorbed into the prose the agent follows.
        assert "when_to_use:" not in loaded.body
        assert loaded.body.startswith("#")


def test_a_missing_document_degrades_the_library_instead_of_breaking_it(monkeypatch,
                                                                       caplog):
    """The packaging failure, simulated. A `data/` that did not ship must not raise.

    An exception here would take down the Skills page, the two agent tools and every
    caller of `available()` — turning a missing markdown file into an app that cannot
    list the skills the operator wrote by hand either.
    """
    monkeypatch.setattr(skills, "DATA_DIR", Path("/nonexistent/forgecast/skills/data"))
    with caplog.at_level(logging.WARNING, logger="forgecast.skills"):
        seeded = skills.starters()

    assert [skill.slug for skill in seeded] == [
        "hook-writing", "documentary-reveal-structure", "caption-discipline"]
    # Named in the log, because the alternative is an install that is quietly missing
    # four documents and looks complete.
    for _, _, filename in skills.SHIPPED_DOCS:
        assert filename in caplog.text
    assert "package-data" in caplog.text


# ------------------------------------------------------------------ the packaging


def test_the_zip_builder_ships_the_data_directory():
    """`tools/package.py` filters every path through one exclusion list.

    A `data` or `*.md` pattern reaching that list — or a future rule that excludes
    directories it does not recognise — would ship an app whose skills library is three
    documents short, with nothing at build time to say so.
    """
    package = _package_tool()
    members = [member for _, member in package.files_to_ship()]

    for _, _, filename in skills.SHIPPED_DOCS:
        relative = f"forgecast/skills/data/{filename}"
        assert package.excluded(relative) is None
        assert f"Forgecast/{relative}" in members


def test_the_documents_live_inside_the_installed_package():
    """Read relative to the module, not to the working directory.

    A path resolved from the process's cwd works in a checkout and fails in every
    installed copy, because the app is started from the operator's home directory.
    """
    assert Path(skills.__file__).resolve().parent / "data" == skills.DATA_DIR
    assert skills.DATA_DIR.is_dir()


# --------------------------------------------------------------- the trigger lines


VAGUE = ("generating visuals", "working with video", "making images", "when needed",
         "as appropriate", "any visual")


@pytest.mark.parametrize(("name", "when_to_use", "filename"), skills.SHIPPED_DOCS,
                         ids=[doc[2] for doc in skills.SHIPPED_DOCS])
def test_the_trigger_line_names_a_moment_rather_than_a_topic(name, when_to_use, filename):
    """The line has to fire at the right moment and not at the wrong one.

    "Use when generating visuals" is true of all four documents and of every still the
    app makes, so it either loads fifty kilobytes on every image or gets ignored. What
    makes a line usable is a named moment, the artefact being produced, and the case it
    hands to a neighbouring document.
    """
    assert 150 < len(when_to_use) < 400, len(when_to_use)
    lowered = when_to_use.lower()

    for phrase in VAGUE:
        assert phrase not in lowered, f"{filename}: {phrase!r} fires on everything"

    # A moment in the workflow, not just a subject area.
    assert any(word in lowered for word in
               ("before", "after", "while", "when", "whenever")), when_to_use
    # And a boundary: the neighbouring document, or the case this one does not cover.
    assert any(word in lowered for word in ("not for", "not ", "skip", "instead of",
                                            "rather than")), when_to_use


def test_no_two_documents_share_a_trigger():
    """Overlapping triggers mean the agent loads two documents to answer one question.

    Asserted on the leading clause, which is the part a model actually weighs.
    """
    heads = [when_to_use.split(":")[0].lower() for _, when_to_use, _ in
             skills.SHIPPED_DOCS]
    assert len(set(heads)) == len(heads)
    for head in heads:
        assert len(head) > 30, head


def test_the_model_table_in_the_i2v_skill_matches_the_code():
    """The skill was quoting prices out by more than 3x in both directions.

    It had Kling v3 Pro at $0.40/sec against a real $0.112, and WAN 2.2 at $0.02/sec
    against a real $0.08 — and four of its seven slugs did not exist in `VIDEO_MODELS`
    at all. `providers/media.py` had been corrected against fal's own pages; the
    document the agent quotes to the operator had not, so the agent was confidently
    reporting fiction about money.

    Asserted against the code rather than against a second hard-coded list, so the two
    cannot drift apart again without this failing.
    """
    import re
    from pathlib import Path

    from forgecast.providers.media import VIDEO_MODELS
    from forgecast import skills

    doc = (Path(skills.__file__).resolve().parent / "data"
           / "image-to-video.md").read_text(encoding="utf-8")

    # Every fal video slug the document names has to be one the app can actually run.
    quoted = set(re.findall(r"`(fal-ai/[a-z0-9./-]+image-to-video[a-z/]*)`", doc))
    assert quoted, "the model table has no slugs in it any more — has it been rewritten?"
    unknown = sorted(slug for slug in quoted if slug not in VIDEO_MODELS)
    assert not unknown, (
        "the i2v skill names models this app cannot run:\n  " + "\n  ".join(unknown))


def test_the_i2v_skill_does_not_promise_a_choice_the_app_cannot_make():
    """`registry.py` builds every provider as `cls(api_key)`, so `FalVideoProvider`
    always uses its default model. There is no per-shot, per-run or per-channel path to
    any other slug — so "pick a model per shot" was advice the agent could not follow
    and would report as done."""
    from pathlib import Path

    from forgecast import skills

    doc = (Path(skills.__file__).resolve().parent / "data"
           / "image-to-video.md").read_text(encoding="utf-8")
    assert "always the default" in doc, (
        "the skill no longer states that model selection is fixed — if that has been "
        "built, say so here instead of deleting the caveat")


def test_no_shipped_skill_names_a_service_this_app_does_not_use():
    """The i2v skill told the agent to query the Vercel AI Gateway's `/v1/models`.

    There is no gateway in this codebase and never has been — that sentence came from
    another product, and an instruction to call something that does not exist is an
    instruction the agent either ignores or hallucinates a result for.
    """
    from pathlib import Path

    from forgecast import skills

    data = Path(skills.__file__).resolve().parent / "data"
    offenders = []
    for document in sorted(data.glob("*.md")):
        body = document.read_text(encoding="utf-8").lower()
        for word in ("vercel", "ai gateway", "/v1/models"):
            if word in body:
                offenders.append(f"{document.name}: {word!r}")
    assert not offenders, "a shipped skill names a service this app does not use:\n  " \
        + "\n  ".join(offenders)
