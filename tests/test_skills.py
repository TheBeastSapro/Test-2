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
from forgecast.config import get_settings


@pytest.fixture(autouse=True)
def isolated_skills_folder(tmp_path, monkeypatch):
    """Point the default skills folder at this test's own directory.

    The suite shares one storage directory for the whole session, so without this a test
    that deletes a skill decides what the next test sees. Most of the cases below delete
    or overwrite skills on purpose, and one of them would otherwise leave the shipped
    starters missing for whatever ran next.
    """
    private = get_settings().model_copy(update={"storage_dir": tmp_path})
    monkeypatch.setattr(skills, "get_settings", lambda: private)


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


# --------------------------------------------------------------- the hostile names

# `nul.md` on Windows is the null device rather than a file: the write is discarded and
# every later read returns an empty document, so a skill filed under one of these names
# is a skill that silently loses its prose.
_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in "0123456789"}
    | {f"lpt{digit}" for digit in "0123456789"}
)

# Every name anyone has tried to turn into a filename here, and what it must become.
# `""` means the name has to be refused outright rather than filed under something
# invented. The table is kept whole, including the cases that were already safe, because
# the value of it is the list: a future edit to `slugify` that re-opens one of these rows
# fails here rather than in someone's storage directory.
HOSTILE_NAMES: tuple[tuple[str, str, str], ...] = (
    # Nothing survives the whitelist, so there is no filename to write to.
    ("bare dots", "...", ""),
    ("dot dot", "..", ""),
    ("slashes", "///", ""),
    ("blanks", "   ", ""),
    ("tab and newline", "\t\n\r", ""),
    ("hyphens only", "  -  ", ""),
    ("underscores only", "___", ""),
    ("latin accents only", "\u00e9\u00fc\u00f8", ""),
    ("greek only", "\u03a9\u03b1\u03b2", ""),
    ("cjk only", "\u6f22\u5b57", ""),
    ("emoji", "\U0001f600", ""),
    ("arabic-indic digits", "\u0663\u0664\u0665", ""),
    ("zero width space", "\u200b\u200b", ""),
    ("null byte alone", "\x00", ""),

    # Traversal in every spelling. Each one collapses to a plain name inside the folder.
    ("posix traversal", "../../../etc/passwd", "etc-passwd"),
    ("percent-encoded traversal", "..%2f..%2fx", "2f-2fx"),
    ("traversal in the middle", "a/../../b", "a-b"),
    ("absolute posix path", "/etc/shadow", "etc-shadow"),
    ("home relative path", "~/.ssh/authorized_keys", "ssh-authorized-keys"),
    ("backslashes on posix", "..\\..\\windows\\win.ini", "windows-win-ini"),
    ("windows drive letter", "C:\\Windows\\System32\\config\\SAM",
     "c-windows-system32-config-sam"),
    ("unc path", "\\\\server\\share\\x", "server-share-x"),
    ("null byte truncation", "hook-writing\x00.md", "hook-writing-md"),
    ("null byte inside", "a\x00b", "a-b"),
    ("trailing dot and space", "notes. ", "notes"),
    ("leading dot", ".hidden", "hidden"),

    # Windows resolves these as devices in every directory and with any extension, so a
    # file called `nul.md` is not a file there at all.
    ("device CON", "CON", "con-skill"),
    ("device PRN", "PRN", "prn-skill"),
    ("device AUX", "AUX", "aux-skill"),
    ("device NUL", "NUL", "nul-skill"),
    ("device NUL lowercase", "nul", "nul-skill"),
    ("device NUL with extension", "NUL.md", "nul-md"),
    ("device COM1", "COM1", "com1-skill"),
    ("device COM9", "com9", "com9-skill"),
    ("device LPT1", "LPT1", "lpt1-skill"),
    ("device LPT9", "lpt9", "lpt9-skill"),
    ("device with punctuation", "con.txt", "con-txt"),
    ("device-like word", "control", "control"),
    ("console stream", "CONIN$", "conin"),

    # Length, and the injection attempts that are only text once they are a filename.
    ("300 characters", "A" * 300, "a" * 60),
    ("300 characters of punctuation", "!" * 300, ""),
    ("html", '<img src=x onerror="alert(1)">', "img-src-x-onerror-alert-1"),
    ("sql", "'; DROP TABLE skills; --", "drop-table-skills"),
    ("shell", "$(rm -rf ~)", "rm-rf"),
    ("front matter fence", "---", ""),
    ("forged front matter key", "x\nwhen_to_use: forged", "x-when-to-use-forged"),
    ("glob", "*.md", "md"),
    ("leading hyphen argument", "--force", "force"),
)

_NAME_CASES = [pytest.param(name, slug, id=label) for label, name, slug in HOSTILE_NAMES]


@pytest.mark.parametrize(("name", "expected"), _NAME_CASES)
def test_a_hostile_name_slugifies_to_exactly_this(name, expected):
    assert skills.slugify(name) == expected


@pytest.mark.parametrize(("name", "expected"), _NAME_CASES)
def test_a_hostile_name_writes_one_file_inside_the_folder_or_none(tmp_path, name, expected):
    """The write half of the table: where does the file actually land."""
    folder = skills.directory(tmp_path)
    canary = tmp_path / "canary.md"
    canary.write_text("do not touch", encoding="utf-8")

    if not expected:
        with pytest.raises(ValueError):
            skills.save(name, name, "", "body", tmp_path)
        assert list(folder.glob("*")) == []
    else:
        stored = skills.save(name, name, "", "body", tmp_path)
        assert stored.slug == expected
        assert [path.name for path in folder.iterdir()] == [f"{expected}.md"]
        # A device name would make this read back empty on Windows, and the slug rules
        # are what keep the filename off that list.
        assert stored.slug not in _WINDOWS_DEVICES
        # Addressed by the raw name again, the skill that comes back is the one just
        # written here — the traversal was collapsed, not followed.
        assert skills.get(name, tmp_path).body == "body"

    # Nothing anywhere else, under any name, at any point.
    assert sorted(item.name for item in tmp_path.iterdir()) == ["canary.md", "skills"]
    assert canary.read_text(encoding="utf-8") == "do not touch"


@pytest.mark.parametrize(("name", "expected"), _NAME_CASES)
def test_a_hostile_slug_reads_and_deletes_nothing_outside_the_folder(tmp_path, name,
                                                                     expected):
    """The read and delete half: a slug taken straight from a URL cannot reach out."""
    outside = tmp_path / "passwd"
    outside.write_text("root:x:0:0", encoding="utf-8")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "passwd.md").write_text("host file", encoding="utf-8")

    with pytest.raises((KeyError, ValueError)):
        skills.get(name, tmp_path)
    try:
        # False, not an exception, is the right answer for a name that is merely absent.
        assert skills.delete(name, tmp_path) is False
    except ValueError:
        assert not expected

    assert outside.read_text(encoding="utf-8") == "root:x:0:0"
    assert (tmp_path / "etc" / "passwd.md").read_text(encoding="utf-8") == "host file"


@pytest.mark.parametrize("device", sorted(_WINDOWS_DEVICES))
def test_a_reserved_device_name_never_becomes_the_filename(tmp_path, device):
    for spelling in (device, device.upper(), device.capitalize(), f" {device} "):
        assert skills.slugify(spelling) not in _WINDOWS_DEVICES
        stored = skills.save(spelling, spelling, "", "body", tmp_path)
        assert stored.slug == f"{device}-skill"
    # And the mangled slug is stable: a second pass over it must not keep appending.
    assert skills.slugify(f"{device}-skill") == f"{device}-skill"
    assert [path.name for path in skills.directory(tmp_path).iterdir()] == [
        f"{device}-skill.md"]
    assert skills.get(device, tmp_path).body == "body"


# --------------------------------------------------------------- colliding names


COLLIDING_NAMES: tuple[tuple[str, str, str], ...] = (
    ("case", "Hook Writing", "hook writing"),
    ("separator", "Hook writing", "hook_writing"),
    ("punctuation", "Hook writing", "Hook: writing!"),
    ("accents both dropped", "Caf\u00e9 notes", "Caf\u00e8 notes"),
    ("truncated at sixty characters", "y" * 60 + " alpha", "y" * 60 + " beta"),
    ("device suffix", "NUL", "nul skill"),
)


@pytest.mark.parametrize(("first", "second"),
                         [pytest.param(a, b, id=label) for label, a, b in COLLIDING_NAMES])
def test_two_names_that_share_a_slug_share_one_document(tmp_path, first, second):
    """Established as fact first, then defended against by `refile`.

    `save` is a write to a named file and stays one — the CLI and the starter seed both
    depend on being able to replace a skill by slug — so it is `refile`, the editor's
    save, that has to refuse.
    """
    assert skills.slugify(first) == skills.slugify(second)

    skills.refile("", first, "first", "FIRST PROSE", tmp_path)
    with pytest.raises(ValueError):
        skills.refile("", second, "second", "SECOND PROSE", tmp_path)

    kept = skills.get(skills.slugify(first), tmp_path)
    assert kept.body == "FIRST PROSE"
    assert kept.name == first
    assert len(list(skills.directory(tmp_path).glob("*.md"))) == 1


def test_refile_moves_the_document_and_leaves_no_duplicate(tmp_path):
    """A rename that does not collide still has to take the old file with it.

    Two files claiming to be the same instruction means the agent loads both, including
    the half that was edited out.
    """
    skills.refile("", "Theta notes", "t", "FIRST", tmp_path)
    stored = skills.refile("theta-notes", "Theta notes and units", "t", "SECOND",
                           tmp_path)

    assert stored.slug == "theta-notes-and-units"
    assert [path.name for path in skills.directory(tmp_path).iterdir()] == [
        "theta-notes-and-units.md"]
    assert skills.get("theta-notes-and-units", tmp_path).body == "SECOND"


def test_refile_over_the_document_it_was_given_is_a_plain_replace(tmp_path):
    """The guard must not turn every second save of one skill into an error."""
    skills.refile("", "Iota notes", "i", "FIRST", tmp_path)
    stored = skills.refile("iota-notes", "Iota notes", "i", "SECOND", tmp_path)

    assert stored.slug == "iota-notes"
    assert skills.get("iota-notes", tmp_path).body == "SECOND"
    # And a spelling of the same slug is the same document, not a collision.
    assert skills.refile("Iota Notes", "iota_notes", "i", "THIRD", tmp_path).slug == \
        "iota-notes"
    assert len(list(skills.directory(tmp_path).glob("*.md"))) == 1


def test_refile_refuses_a_name_that_slugifies_to_nothing(tmp_path):
    for name in ("", "   ", "...", "\U0001f600"):
        with pytest.raises(ValueError):
            skills.refile("", name, "", "body", tmp_path)
    # And the refusal must not have deleted the document being edited on the way out.
    skills.refile("", "Kappa notes", "k", "PROSE", tmp_path)
    with pytest.raises(ValueError):
        skills.refile("kappa-notes", "!!!", "k", "PROSE", tmp_path)
    assert skills.get("kappa-notes", tmp_path).body == "PROSE"


def test_a_new_name_may_not_land_on_an_occupied_slug(client):
    """Two titles, one filename: the second save must not eat the first one's prose."""
    client.post("/skills-library/save", data={
        "slug": "", "name": "Zebra numbers", "when_to_use": "statistics",
        "body": "ORIGINAL PROSE",
    })

    collided = client.post("/skills-library/save", data={
        "slug": "", "name": "Zebra: Numbers!", "when_to_use": "anything",
        "body": "REPLACEMENT",
    }, follow_redirects=False)
    assert collided.status_code == 303
    assert "error=" in collided.headers["location"]

    kept = skills.get("zebra-numbers")
    assert kept.body == "ORIGINAL PROSE"
    assert kept.name == "Zebra numbers"
    assert [row["slug"] for row in skills.available()].count("zebra-numbers") == 1


def test_a_rename_onto_an_occupied_slug_destroys_neither_document(client):
    """The dangerous half: the rename path deletes the old file after writing the new.

    Landing on an occupied slug would overwrite that skill and then delete the one being
    edited, so a single save would lose two documents.
    """
    client.post("/skills-library/save", data={
        "slug": "", "name": "Alpha notes", "when_to_use": "a", "body": "ALPHA PROSE",
    })
    client.post("/skills-library/save", data={
        "slug": "", "name": "Beta notes", "when_to_use": "b", "body": "BETA PROSE",
    })

    refused = client.post("/skills-library/save", data={
        "slug": "alpha-notes", "name": "Beta Notes!", "when_to_use": "b",
        "body": "TAKEOVER",
    }, follow_redirects=False)
    assert refused.status_code == 303
    assert "error=" in refused.headers["location"]

    assert skills.get("alpha-notes").body == "ALPHA PROSE"
    assert skills.get("beta-notes").body == "BETA PROSE"


def test_editing_a_skill_in_place_is_still_allowed(client):
    """The guard above must not turn every second save of one skill into an error."""
    client.post("/skills-library/save", data={
        "slug": "", "name": "Gamma notes", "when_to_use": "g", "body": "FIRST",
    })
    again = client.post("/skills-library/save", data={
        "slug": "gamma-notes", "name": "Gamma notes", "when_to_use": "g",
        "body": "SECOND",
    }, follow_redirects=False)
    assert "error=" not in again.headers["location"]
    assert skills.get("gamma-notes").body == "SECOND"

    # A rename onto a free slug still re-files the document and removes the old file.
    client.post("/skills-library/save", data={
        "slug": "gamma-notes", "name": "Gamma notes and units", "when_to_use": "g",
        "body": "THIRD",
    })
    slugs = [row["slug"] for row in skills.available()]
    assert "gamma-notes-and-units" in slugs
    assert "gamma-notes" not in slugs


# --------------------------------------------------------- front matter injection


def test_a_body_containing_the_fence_cannot_forge_metadata(tmp_path):
    """The body is prose and may legitimately contain `---`.

    Parsing stops at the first closing fence, so a second block inside the body is text.
    If it were read as front matter, anyone who could edit a body could rewrite the
    `when_to_use` that decides whether the agent loads the document at all.
    """
    skills.save(
        "fenced", "Fenced", "the real trigger",
        "before\n---\nname: Forged\nwhen_to_use: always, for everything\n---\nafter",
        tmp_path,
    )
    read = skills.get("fenced", tmp_path)
    assert read.name == "Fenced"
    assert read.when_to_use == "the real trigger"
    assert read.extra == {}
    assert "name: Forged" in read.body
    assert "Forged" not in read.as_prompt().splitlines()[0]


def test_a_forged_key_in_a_value_stays_a_value(tmp_path):
    """`when_to_use` is one line on disk, so a newline in it cannot open a second key."""
    skills.save("forge", "Forge\nname: Other", "when\nauthor: someone else",
                "body", tmp_path)
    read = skills.get("forge", tmp_path)
    assert read.name == "Forge name: Other"
    assert read.when_to_use == "when author: someone else"
    assert read.extra == {}
    assert read.body == "body"


def test_a_hand_added_slug_key_cannot_repoint_a_skill(tmp_path):
    """The filename is the identity. A `slug:` line in the file is preserved, not obeyed.

    Obeying it would make one file able to claim another's slug, and the page and the
    agent both address skills by slug.
    """
    path = skills.directory(tmp_path) / "pointer.md"
    path.write_text("---\nname: Pointer\nslug: ../../escape\n---\n\nbody\n",
                    encoding="utf-8")
    read = skills.get("pointer", tmp_path)
    assert read.slug == "pointer"
    assert read.extra == {"slug": "../../escape"}

    skills.save("pointer", "Pointer", "", "new body", tmp_path)
    assert [item.name for item in tmp_path.iterdir()] == ["skills"]
    assert skills.get("pointer", tmp_path).body == "new body"


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


# ------------------------------------------------------------ the page, attacked


# Slugs as they arrive from a URL, which is the only place the app takes one it did not
# generate itself. Read through `?selected=`, deleted through the path segment.
URL_SLUGS: tuple[str, ...] = (
    "../../../etc/passwd",
    "..%2f..%2f..%2fetc%2fpasswd",
    "%2e%2e%2f%2e%2e%2fpasswd",
    "....//....//passwd",
    "..\\..\\..\\windows\\win.ini",
    "%00",
    ".",
    "..",
    "nul",
    "CON",
    "*",
    "x" * 400,
)


@pytest.mark.parametrize("slug", URL_SLUGS)
def test_a_slug_from_the_url_cannot_read_outside_the_folder(client, tmp_path, slug):
    """A miss renders the page with no skill chosen. It must never render a host file."""
    secret = tmp_path / "passwd.md"
    secret.write_text("root:x:0:0", encoding="utf-8")

    page = client.get("/skills-library", params={"selected": slug})
    assert page.status_code == 200
    assert "root:x:0:0" not in page.text

    assert sorted(item.name for item in tmp_path.iterdir()) == ["passwd.md", "skills"]


@pytest.mark.parametrize("slug", URL_SLUGS)
def test_a_slug_from_the_url_cannot_delete_outside_the_folder(client, tmp_path, slug):
    """Either the route does not match, or the slug collapses to a name in the folder.

    What must not survive is a request that unlinks anything above the skills directory.
    """
    client.get("/skills-library")                        # seeds the starters to be lost
    canary = tmp_path / "passwd.md"
    canary.write_text("do not touch", encoding="utf-8")

    response = client.post(f"/skills-library/{slug}/delete", follow_redirects=False)
    assert response.status_code in (303, 404, 405)

    assert canary.read_text(encoding="utf-8") == "do not touch"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["passwd.md", "skills"]
    assert len(list((tmp_path / "skills").glob("*.md"))) == 3


def test_a_delete_by_display_name_hits_that_same_document(client):
    """Deliberate aliasing, pinned so it cannot become a surprise.

    Every entry point slugifies, so `Delta Notes`, `delta_notes` and `delta-notes` are
    three spellings of one document rather than three documents. That is what makes the
    traversal cases above collapse instead of escaping, and the cost is that a
    non-canonical slug still resolves — to the same file, never to another one.
    """
    client.post("/skills-library/save", data={
        "slug": "", "name": "Delta notes", "when_to_use": "d", "body": "prose",
    })
    assert "delta-notes" in [row["slug"] for row in skills.available()]

    client.post("/skills-library/Delta_Notes%20/delete")
    assert "delta-notes" not in [row["slug"] for row in skills.available()]


def test_a_name_that_looks_like_markup_is_escaped_in_the_banner(client):
    """The saved name is echoed back through the query string into the page."""
    saved = client.post("/skills-library/save", data={
        "slug": "", "name": '<img src=x onerror="alert(1)">Bad', "when_to_use": "",
        "body": "b",
    }, follow_redirects=True)
    assert saved.status_code == 200
    assert "<img src=x" not in saved.text
    assert "&lt;img" in saved.text

    reflected = client.get("/skills-library", params={"error": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in reflected.text


def test_the_write_endpoints_refuse_an_anonymous_caller(app, client):
    """An unauthenticated editor for files on disk is a remote file write."""
    client.post("/skills-library/save", data={
        "slug": "", "name": "Epsilon notes", "when_to_use": "e", "body": "prose",
    })

    with TestClient(app) as anonymous:
        saved = anonymous.post("/skills-library/save", data={
            "slug": "", "name": "Intruder", "when_to_use": "", "body": "x",
        }, follow_redirects=False)
        removed = anonymous.post("/skills-library/epsilon-notes/delete",
                                 follow_redirects=False)
    assert saved.status_code == 401
    assert removed.status_code == 401

    slugs = [row["slug"] for row in skills.available()]
    assert "intruder" not in slugs
    assert "epsilon-notes" in slugs
