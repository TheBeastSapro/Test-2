"""The skills library: the file format, the guard on the filename, and the page.

The interesting failures here are not in the HTML. They are that a name is user input on
its way to becoming a path, and that seeding starter documents into a folder is a write
that must happen exactly once — a second pass that rewrites them silently discards
whatever the operator edited in between.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast import skills
from forgecast.api.main import create_app
from forgecast.api.routes_skills import router as skills_router


@pytest.fixture
def app():
    """The real app with this page's router attached.

    Attached here rather than assumed, because registering it in `api/main.py` is another
    agent's edit. The guard keeps the fixture correct either way — including it twice
    would leave a duplicate route shadowed by the first.
    """
    made = create_app()
    if not any(getattr(route, "path", "") == "/skills-library" for route in made.routes):
        made.include_router(skills_router)
    return made


@pytest.fixture
def client(app, user):
    with TestClient(app) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


# ------------------------------------------------------------------ the file format


def test_a_skill_round_trips_through_its_front_matter(tmp_path):
    saved = skills.save(
        "cold-open",
        "Cold opens",
        "Whenever a script opens on narration instead of an image.",
        "# Cold opens\n\nFirst cut inside 2.0 seconds.\n",
        tmp_path,
    )
    assert saved.slug == "cold-open"

    read = skills.get("cold-open", tmp_path)
    assert read.name == "Cold opens"
    assert read.when_to_use.startswith("Whenever a script opens")
    assert "First cut inside 2.0 seconds." in read.body
    # The front matter must not leak into the body, or every load appends the metadata
    # to the instructions the agent follows.
    assert "when_to_use:" not in read.body
    assert read.updated_at

    listed = {row["slug"]: row for row in skills.available(tmp_path)}
    assert listed["cold-open"]["name"] == "Cold opens"
    assert listed["cold-open"]["summary"].startswith("Whenever")


def test_a_multi_line_name_cannot_break_the_next_read(tmp_path):
    """A newline in a value would put a bare word where a `key: value` line is expected.

    The parser would then stop, treat the rest of the front matter as body, and the skill
    would come back with a truncated name and metadata glued to its instructions.
    """
    skills.save("odd", "Two\nlines: and a colon", "one\ntwo", "body text", tmp_path)
    read = skills.get("odd", tmp_path)
    assert read.name == "Two lines: and a colon"
    assert read.when_to_use == "one two"
    assert read.body == "body text"


def test_a_hand_added_key_is_not_deleted_by_an_edit(tmp_path):
    path = skills.directory(tmp_path) / "manual.md"
    path.write_text(
        "---\nname: Manual\nwhen_to_use: sometimes\nauthor: someone\n---\n\nrules\n",
        encoding="utf-8",
    )
    assert skills.get("manual", tmp_path).extra == {"author": "someone"}

    skills.save("manual", "Manual", "sometimes", "new rules", tmp_path)
    assert "author: someone" in path.read_text(encoding="utf-8")


def test_a_file_with_no_front_matter_still_loads(tmp_path):
    """The page that would let you fix a broken file must not be the page it breaks."""
    (skills.directory(tmp_path) / "raw.md").write_text("just prose\n", encoding="utf-8")
    read = skills.get("raw", tmp_path)
    assert read.body == "just prose"
    assert read.name == "raw"


def test_an_unnamed_skill_is_refused(tmp_path):
    with pytest.raises(ValueError):
        skills.save("", "   ", "", "body", tmp_path)
    with pytest.raises(ValueError):
        # Nothing survives slugification, so there is no filename to write to.
        skills.save("", "!!!", "", "body", tmp_path)


# ----------------------------------------------------------------- the path guard


def test_a_name_cannot_escape_the_skills_directory(tmp_path):
    # A read first, before anything by that name exists: the traversal must miss rather
    # than reach a file on the host.
    with pytest.raises(KeyError):
        skills.get("../../../etc/passwd", tmp_path)
    with pytest.raises(KeyError):
        skills.get("..\\..\\windows\\win.ini", tmp_path)

    saved = skills.save("../../../etc/passwd", "Escape attempt", "", "body", tmp_path)
    assert saved.slug == "etc-passwd"
    assert (skills.directory(tmp_path) / "etc-passwd.md").exists()
    # Nothing at all outside the skills folder, under any name.
    assert [item.name for item in tmp_path.iterdir()] == ["skills"]
    # And the sanitised name now reads back the skill that was written here, not the
    # host's file: the traversal has been collapsed, not followed.
    assert skills.get("../../../etc/passwd", tmp_path).body == "body"


def test_the_containment_check_holds_when_slugify_does_not(tmp_path, monkeypatch):
    """The second line of defence, tested on its own.

    `slugify` makes traversal impossible today, so the containment check in `_path` is
    unreachable through the front door. It exists for the day someone loosens the slug
    rules to allow a dot or a slash for namespacing, and this asserts that such a change
    produces a refused write rather than a file written outside the storage directory.
    """
    monkeypatch.setattr(skills, "slugify", lambda name: str(name))

    with pytest.raises(ValueError):
        skills.save("../escaped", "Escaped", "", "body", tmp_path)
    with pytest.raises(ValueError):
        skills.delete("../escaped", tmp_path)
    assert not (tmp_path / "escaped.md").exists()


# -------------------------------------------------------------------- the starters


def test_the_starters_are_created_once_and_never_rewritten(tmp_path):
    first = skills.available(tmp_path)
    assert [row["slug"] for row in first] == [
        "caption-discipline", "documentary-reveal-structure", "hook-writing"]

    folder = skills.directory(tmp_path)
    stamps = {path.name: path.stat().st_mtime_ns for path in folder.glob("*.md")}

    # An edit between the two calls is the case that matters: a seed that runs again
    # would silently replace the operator's work with the shipped text.
    skills.save("hook-writing", "Hook writing", "mine now", "my own rules", tmp_path)

    second = skills.available(tmp_path)
    assert len(second) == 3
    assert skills.get("hook-writing", tmp_path).body == "my own rules"
    assert {path.name for path in folder.glob("*.md")} == set(stamps)

    # And a starter deleted on purpose stays deleted while the others remain.
    skills.delete("caption-discipline", tmp_path)
    assert [row["slug"] for row in skills.available(tmp_path)] == [
        "documentary-reveal-structure", "hook-writing"]


def test_the_starters_are_real_craft_rather_than_placeholders(tmp_path):
    rows = {row["slug"]: row for row in skills.available(tmp_path)}
    assert set(rows) == {"hook-writing", "documentary-reveal-structure",
                         "caption-discipline"}

    for slug in rows:
        skill = skills.get(slug, tmp_path)
        assert skill.when_to_use, f"{slug} must say when it applies"
        assert len(skill.body) > 1200, f"{slug} is too thin to be craft"
        # Concrete numbers are the difference between an instruction the agent can act
        # on and an adjective it can only agree with.
        assert sum(character.isdigit() for character in skill.body) >= 8
        lowered = skill.body.lower()
        assert "todo" not in lowered
        assert "lorem" not in lowered
        assert "your skill" not in lowered
        # No emoji anywhere. Punctuation such as an em dash is fine; pictographs are
        # well above this point in the code space.
        assert max(ord(character) for character in skill.as_prompt()) < 0x2500


# ------------------------------------------------------------------------- the page


def test_the_page_needs_a_signed_in_user(app):
    with TestClient(app) as anonymous:
        response = anonymous.get("/skills-library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/skills-library"


def test_the_page_lists_the_starters_and_offers_an_editor(client):
    page = client.get("/skills-library")
    assert page.status_code == 200
    body = page.text
    assert "Hook writing" in body
    assert "Caption discipline" in body
    # The editor, not just a list: a skill you cannot change in the app gets changed in
    # a text editor instead.
    assert 'name="when_to_use"' in body
    assert 'action="/skills-library/save"' in body
    # And the sidebar, which is what `shell()` is for.
    assert 'class="side"' in body


def test_a_skill_is_created_edited_and_renamed_from_the_page(client):
    created = client.post("/skills-library/save", data={
        "slug": "",
        "name": "Zebra numbers",
        "when_to_use": "When a script quotes a statistic.",
        "body": "Cite the source in the same sentence.",
    }, follow_redirects=False)
    assert created.status_code == 303
    assert "selected=zebra-numbers" in created.headers["location"]

    stored = skills.get("zebra-numbers")
    assert stored.when_to_use == "When a script quotes a statistic."

    # Renaming must re-file the document. Two files claiming to be the same instruction
    # means the agent loads both, including the half that was edited out.
    client.post("/skills-library/save", data={
        "slug": "zebra-numbers",
        "name": "Zebra numbers and units",
        "when_to_use": "When a script quotes a statistic.",
        "body": "Cite the source in the same sentence. Keep the unit.",
    })
    slugs = [row["slug"] for row in skills.available()]
    assert "zebra-numbers-and-units" in slugs
    assert "zebra-numbers" not in slugs

    client.post("/skills-library/zebra-numbers-and-units/delete")
    assert "zebra-numbers-and-units" not in [row["slug"] for row in skills.available()]


def test_a_nameless_save_comes_back_with_a_reason(client):
    refused = client.post("/skills-library/save", data={
        "slug": "", "name": "  ", "when_to_use": "", "body": "orphan",
    }, follow_redirects=False)
    assert refused.status_code == 303
    assert "error=" in refused.headers["location"]
