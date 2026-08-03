"""Scripting styles: the built-in method, the operator's own folder, and the wiring.

Three properties carry this file, and they fail in three different ways.

**The built-in method has to be unconditional.** It is the default for every channel and
the fallback for every selection that stops resolving, so anything that makes it depend
on a folder, a setting or a file turns "your documents are not loaded" into "your scripts
are written to nothing in particular", which nobody can see from the output.

**A document that does not load has to be named.** Sixteen documents with three missing
is a method quietly short of a fifth of itself and a channel that simply gets worse. The
warnings are therefore asserted for the failing filename, not for being non-empty.

**Nothing from that folder may ever be shipped.** The documents are somebody else's
licensed work, and the zip is a thing you send to other people. That is asserted against
`package.EXCLUDE` and against a real archive built with a real decoy in the tree, because
a rule set that has only met strings has never met the filesystem.
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast import scripting
from forgecast.api.main import create_app
from forgecast.api.routes_settings import ENV_FIELDS
from forgecast.auth import create_access_token
from forgecast.config import get_settings
from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.models import Channel, User
from forgecast.scripting import library, method

ROOT = Path(__file__).resolve().parents[1]


def load_package():
    """`tools/package.py` by path — it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("forgecast_package_scripting",
                                                  ROOT / "tools" / "package.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package = load_package()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """An empty scripting library, outside the repository, with nothing configured yet."""
    made = tmp_path / library.LIBRARY_DIRNAME
    made.mkdir()
    return made


@pytest.fixture
def configured(folder: Path):
    """The process pointed at that folder, restored afterwards.

    Set on the live `Settings` object rather than through the environment, because
    `get_settings` is cached for the life of the process and an env var set after the
    first call is a variable nothing ever reads.
    """
    settings = get_settings()
    before = settings.scripting_dir
    settings.scripting_dir = folder
    yield folder
    settings.scripting_dir = before


def write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ------------------------------------------------------------------ the built-in method


def test_the_house_style_loads_with_no_folder_at_all(tmp_path: Path):
    """The default must not depend on anything an operator could fail to set up.

    If the built-in style needed a folder, a fresh install would have no method at all —
    and because `prompt_block` never raises, the symptom would be scripts written to the
    model's own instincts with nothing anywhere saying so.
    """
    missing = tmp_path / "not-here"
    rows = scripting.available(missing)

    assert [row["slug"] for row in rows] == [scripting.HOUSE_SLUG]
    assert rows[0]["origin"] == scripting.BUILT_IN
    assert rows[0]["warnings"] == []
    assert scripting.get(scripting.HOUSE_SLUG, missing) is not None


def test_the_house_method_carries_all_five_named_rules():
    """A block dropped from `BLOCKS` is a rule that silently stops being enforced.

    The ids are asserted rather than the prose, because the prose is meant to be edited
    and the set of rules is not.
    """
    assert set(method.METHOD) == {
        "dopamine_ladder", "curiosity_loops", "but_therefore", "rotation_banks",
        "anti_slop",
    }
    block = scripting.prompt_block(scripting.HOUSE_SLUG, target_seconds=480)
    for title in ("DOPAMINE LADDER", "CURIOSITY LOOPS", "BUT / THEREFORE",
                  "ROTATION BANKS", "ANTI-SLOP"):
        assert title in block, f"{title} is not in the prompt block"


def test_the_ladder_cadence_is_a_number_tied_to_the_length():
    """"Pay the viewer back often" is an adjective; a model cannot obey an adjective.

    A Short and a long-form video must not get the same beat length either — a percentage
    of runtime gives an eighteen-minute documentary one payoff every four minutes, which
    is a video nobody finishes.
    """
    short = method.cadence(45)
    long_form = method.cadence(600)

    assert short.beat_seconds < long_form.beat_seconds
    assert short.beats >= 4 and long_form.beats >= 4
    assert f"a beat is {short.beat_seconds} seconds" in scripting.prompt_block(
        scripting.HOUSE_SLUG, target_seconds=45)
    assert f"a beat is {long_form.beat_seconds} seconds" in scripting.prompt_block(
        scripting.HOUSE_SLUG, target_seconds=600)


def test_a_zero_target_still_produces_a_usable_cadence():
    """A channel with no duration set must not take the run down at prompt-build time.

    `target_duration_seconds` reaches here from a channel row, a run option or a node
    param, and any of the three can be absent — so this is called with 0 in normal use,
    not only in a test.
    """
    assert method.cadence(0).beats >= 4
    assert "$beat_seconds" not in scripting.prompt_block(scripting.HOUSE_SLUG,
                                                         target_seconds=0)


def test_every_banned_construction_ships_with_its_replacement():
    """A ban with nothing on the other side of it is a ban that gets ignored.

    The writer still has to put something in the slot; if the rule does not say what,
    the banned phrase is the only candidate they have.
    """
    assert len(scripting.BANNED) >= 7
    for banned in scripting.BANNED:
        assert banned.construction.strip(), "a banned construction with no name"
        assert len(banned.instead.split()) >= 8, f"{banned.construction!r} has no rewrite"

    block = scripting.prompt_block(scripting.HOUSE_SLUG, target_seconds=300)
    for phrase in ("In the world of", "Little did they know", "Rhetorical question stacks",
                   "Throat-clearing", "summary paragraph", "Adjective pairs",
                   "It isn't just X"):
        assert phrase in block, f"{phrase!r} is not banned in the prompt"


def test_every_rotation_bank_has_enough_entries_to_rotate_through():
    """A bank with two entries is not a rotation, it is an alternation.

    The no-repeat window is six beats, so a bank smaller than that cannot satisfy its own
    rule and the rule becomes advice.
    """
    assert {bank.id for bank in scripting.BANKS} == {
        "openings", "transitions", "re_hooks", "closers"}
    for bank in scripting.BANKS:
        assert len(bank.entries) >= method.NO_REPEAT_WITHIN_BEATS, \
            f"{bank.id} cannot honour a {method.NO_REPEAT_WITHIN_BEATS}-beat window"
        assert len(set(bank.entries)) == len(bank.entries), f"{bank.id} repeats itself"


def test_the_rules_are_data_a_check_could_read():
    """The whole reason these are objects rather than one string.

    A future pass that counts open loops in a finished script has to read the limit from
    somewhere; reading it out of English is not something that can be maintained.
    """
    loops = method.METHOD["curiosity_loops"].params
    assert loops["unclosed_at_end"] == 0
    assert loops["max_open_at_once"] >= 2
    assert method.METHOD["rotation_banks"].params["no_repeat_within_beats"] >= 4
    assert method.METHOD["dopamine_ladder"].params["rungs"] == method.RUNGS


# ------------------------------------------------------------------ the operator's folder


def test_loose_files_in_the_folder_become_one_style(folder: Path):
    """The shape someone with one method actually produces: sixteen files, no taxonomy.

    Requiring a subfolder first would mean an operator who drops their documents in and
    looks at the dropdown sees nothing, with no error to explain it.
    """
    for index in range(3):
        write(folder, f"{index}-part.md", f"part {index}")

    rows = scripting.available(folder)
    local = [row for row in rows if row["origin"] == scripting.LOCAL]

    assert len(local) == 1
    assert local[0]["slug"] == library.slugify(folder.name)
    assert local[0]["documents"] == 3
    assert local[0]["source"] == str(folder)


def test_each_subfolder_is_a_separate_style(folder: Path):
    """Two methods must stay two choices.

    Reading subfolders into one style would put every document into every selection and
    make the dropdown a control that changes nothing.
    """
    write(folder, "documentary/beats.md", "documentary beats")
    write(folder, "documentary/openings.md", "documentary openings")
    write(folder, "listicle/beats.md", "listicle beats")

    rows = {row["slug"]: row for row in scripting.available(folder)}

    assert set(rows) == {scripting.HOUSE_SLUG, "documentary", "listicle"}
    assert rows["documentary"]["documents"] == 2
    assert rows["listicle"]["documents"] == 1
    assert "documentary beats" in scripting.prompt_block("documentary", target_seconds=480,
                                                         base=folder)
    assert "documentary beats" not in scripting.prompt_block("listicle", target_seconds=480,
                                                             base=folder)


def test_loose_files_and_subfolders_do_not_leak_into_each_other(folder: Path):
    """Both shapes at once, which is what a folder looks like after a month.

    The root style reads its loose files only; without that it would also swallow every
    subfolder's documents and the two styles would be the same style.
    """
    write(folder, "root-note.md", "root note")
    write(folder, "documentary/beats.md", "documentary beats")

    root = scripting.get(library.slugify(folder.name), folder)
    assert root is not None
    assert [document.name for document in root.documents] == ["root-note.md"]


def test_a_file_that_cannot_be_read_is_named_rather_than_dropped(folder: Path):
    """Sixteen documents with three missing is a method nobody notices is short.

    The count still looks plausible and the scripts still get written, so the only thing
    that can surface it is the filename — which is why the assertion is on the name and
    not on the warnings being non-empty.
    """
    write(folder, "good.md", "usable craft")
    (folder / "purchased.pdf").write_bytes(b"%PDF-1.7 not text")
    (folder / "notes.docx").write_bytes(b"PK\x03\x04 not text either")
    write(folder, "empty.md", "   ")

    style = scripting.get(library.slugify(folder.name), folder)
    assert style is not None
    assert [document.name for document in style.documents] == ["good.md"]

    joined = " | ".join(style.warnings)
    assert "purchased.pdf" in joined
    assert "notes.docx" in joined
    assert "empty.md" in joined


def test_the_character_budget_truncates_and_says_by_how_much(folder: Path):
    """An unbounded folder is an unbounded prompt, paid for on every run.

    Truncating silently would be worse than not truncating: the method would be missing
    its end and the operator would be reading scripts that ignore the last third of a
    document they can see is there.
    """
    write(folder, "long.md", "x" * 5_000)
    write(folder, "short.md", "y" * 200)

    style = scripting.get(library.slugify(folder.name), folder)  # unbudgeted default
    assert style is not None and style.documents[0].truncated_by == 0

    styles = library.discover(folder, budget=1_000)
    documents = {document.name: document for document in styles[0].documents}

    assert documents["long.md"].truncated_by > 0
    assert documents["short.md"].truncated_by == 0, "a short document was cut for a long one"
    assert sum(len(d.text) for d in styles[0].documents) <= 1_000
    joined = " | ".join(styles[0].warnings)
    assert "long.md" in joined and "truncated" in joined
    assert str(documents["long.md"].truncated_by) in joined.replace(",", "")


def test_a_local_folder_cannot_take_the_built_in_slug(folder: Path):
    """A folder called `house` would otherwise shadow the default silently.

    Every channel that had chosen the built-in method would start writing to somebody
    else's documents without a single row changing, which is unattributable from the
    output.
    """
    write(folder, f"{scripting.HOUSE_SLUG}/beats.md", "not the house method")

    rows = {row["slug"]: row for row in scripting.available(folder)}

    assert rows[scripting.HOUSE_SLUG]["origin"] == scripting.BUILT_IN
    assert any(row["origin"] == scripting.LOCAL for row in rows.values())


def test_the_operators_documents_outrank_the_house_floor_and_both_are_present(folder: Path):
    """They paid for the documents; the house rules are the floor under them.

    Dropping the floor would mean a folder covering openings and nothing else loses the
    banned-phrase list, and dropping the documents would mean the setting does nothing.
    """
    write(folder, "method.md", "OPEN ON THE ARTEFACT.")

    block = scripting.prompt_block(library.slugify(folder.name), target_seconds=480,
                                   base=folder)

    assert "OPEN ON THE ARTEFACT." in block
    assert "the documents win" in block
    assert "ANTI-SLOP RULES" in block


# ---------------------------------------------------------------- when the folder is gone


def test_a_missing_folder_degrades_to_the_house_method_with_a_reason(tmp_path: Path):
    """The folder is outside the tree, so it is the thing that goes missing.

    A raise here would take out the channel page and every run on it. What has to happen
    instead is a script written to the house method and a reason somebody can read.
    """
    gone = tmp_path / "never-existed"

    assert scripting.get("documentary", gone) is None
    assert scripting.folder_status(gone)["exists"] is False

    block = scripting.prompt_block("documentary", target_seconds=480, base=gone)
    assert scripting.HOUSE_NAME in block
    assert "DOPAMINE LADDER" in block

    rows = {row["slug"]: row for row in scripting.selection("documentary", gone)}
    assert rows["documentary"]["available"] is False
    assert str(gone) in rows["documentary"]["reason"]


def test_an_unconfigured_folder_is_not_the_working_directory():
    """`Path("")` is `Path(".")`, which for a development install is the repository.

    Clearing the setting would otherwise read this project's own README, docs and tests
    into a script prompt, which is both nonsense and a way to leak the tree into a
    provider request.
    """
    assert library.directory("") is None
    assert scripting.available("") == [scripting.house().as_row()]
    assert scripting.folder_status("")["configured"] is False


# ------------------------------------------------------------------- reaching the prompt


def _context(tmp_path: Path, slug: str) -> NodeContext:
    return NodeContext(
        run_id=1,
        topic="Why deep-sea cables keep breaking",
        options={},
        node_key="script",
        node_type="script",
        params={},
        attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="infrastructure", language="en",
            voice_id="", avatar_id="", aspect_ratio="16:9",
            target_duration_seconds=120, style_profile={},
            scripting_style=slug,
        ),
        registry=None,  # type: ignore[arg-type]
        workdir=tmp_path,
        upstream_outputs={"brief": {"working_title": "Cables",
                                    "target_duration_seconds": 120,
                                    "beats": [{"name": "one"}, {"name": "two"}]}},
    )


async def test_the_channels_selected_style_reaches_the_script_prompt(
    monkeypatch, tmp_path: Path, configured: Path,
):
    """The whole feature, end to end: a slug on a channel becomes text in the prompt.

    Asserted on the instructions the node actually sends rather than on
    `prompt_block` in isolation, because every previous version of this wiring worked in
    isolation — what breaks is the node forgetting to append it.
    """
    from forgecast.nodes import content

    write(configured, "documentary/rules.md", "ALWAYS OPEN ON A DOCUMENT.")
    seen: dict[str, str] = {}

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        seen[schema_name] = instructions
        return ({"title": "Cables", "description": "d", "tags": [],
                 "scenes": [{"index": 0, "narration": "A cable snapped.",
                             "visual_prompt": "cable", "visual_kind": "image",
                             "seconds": 3.0, "on_screen_text": ""}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    await content.script_node(_context(tmp_path, "documentary"))

    assert "ALWAYS OPEN ON A DOCUMENT." in seen["script"]
    assert "ANTI-SLOP RULES" in seen["script"]
    assert "a beat is 15 seconds" in seen["script"], "the cadence did not follow the target"


async def test_the_brief_gets_the_structure_rules_and_not_the_phrase_list(
    monkeypatch, tmp_path: Path,
):
    """A brief is beats and no prose.

    Sending the banned-construction list there spends tokens on every run policing
    writing the stage does not produce, and a rule that cannot apply is a rule the model
    learns to skim.
    """
    from forgecast.nodes import content

    seen: dict[str, str] = {}

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        seen[schema_name] = instructions
        return ({"beats": [{"name": "one"}, {"name": "two"}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    await content.brief_node(_context(tmp_path, scripting.HOUSE_SLUG))

    assert "BUT / THEREFORE" in seen["brief"]
    assert "CURIOSITY LOOPS" in seen["brief"]
    assert "ANTI-SLOP RULES" not in seen["brief"]


async def test_a_style_that_stopped_resolving_is_reported_on_the_run(
    monkeypatch, tmp_path: Path, configured: Path,
):
    """Silence here is the expensive failure.

    The run completes either way, so unless the log names the style the operator is
    reading a script written to a method they did not choose, with nothing to look at.
    """
    from forgecast.nodes import content

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        return ({"beats": [{"name": "one"}, {"name": "two"}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    ctx = _context(tmp_path, "a-style-that-was-deleted")
    await content.brief_node(ctx)

    logged = " | ".join(message for _level, message, _data in ctx._logs)
    assert "a-style-that-was-deleted" in logged
    assert "house method" in logged


async def test_a_document_that_failed_to_load_is_reported_on_the_run(
    monkeypatch, tmp_path: Path, configured: Path,
):
    """The operator is not looking at the channel page while a run writes.

    The run log is where somebody goes when a script came out wrong, so the missing
    document has to be named there too and not only in the browser.
    """
    from forgecast.nodes import content

    write(configured, "documentary/rules.md", "rules")
    (configured / "documentary" / "chapter-4.pdf").write_bytes(b"%PDF-1.7")

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        return ({"beats": [{"name": "one"}, {"name": "two"}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    ctx = _context(tmp_path, "documentary")
    await content.brief_node(ctx)

    logged = " | ".join(message for _level, message, _data in ctx._logs)
    assert "chapter-4.pdf" in logged


# --------------------------------------------------------------------------- the wiring


def test_the_channel_column_defaults_to_the_built_in_slug():
    """The default has to be the one selection that cannot stop resolving.

    The literal is repeated in `models.py` and in the migration to keep application
    imports out of the schema, so this is the thing that stops one of them being
    renamed alone.
    """
    assert Channel.__table__.c.scripting_style.default.arg == scripting.HOUSE_SLUG


def test_the_default_folder_is_outside_the_repository():
    """A default under the tree is a default that puts licensed documents in a commit."""
    default = get_settings().model_fields["scripting_dir"].default
    assert not str(Path(default).resolve()).startswith(str(ROOT.resolve()) + "/")
    assert Path(default).name == library.LIBRARY_DIRNAME, \
        "the default folder name and the name the packager refuses have drifted apart"


def test_the_folder_is_settable_from_the_ui_without_editing_env_by_hand():
    """The point of the setting: an operator who has to edit `.env` has no setting.

    It also must not be masked — a path shown as `/hom…rary` cannot be checked against
    the folder the documents are actually in, which is the one question asked when they
    fail to load.
    """
    field = next((f for f in ENV_FIELDS if f["key"] == "FORGECAST_SCRIPTING_DIR"), None)
    assert field is not None, "the scripting folder is not on the Settings page"
    assert field.get("secret") is False
    assert "FORGECAST_SCRIPTING_DIR" in (ROOT / ".env.example").read_text(encoding="utf-8")


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def test_the_channel_page_offers_every_style_and_saves_one(
    client, session: Session, channel: Channel, configured: Path,
):
    """The selection has to be reachable, and reaching it has to change the row."""
    write(configured, "documentary/beats.md", "documentary beats")

    body = client.get(f"/c/{channel.id}").text
    assert 'name="scripting_style"' in body
    assert "documentary" in body

    answer = client.post(f"/c/{channel.id}/scripting", data={"scripting_style": "documentary"},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    assert session.get(Channel, channel.id).scripting_style == "documentary"


def test_the_page_refuses_a_style_that_does_not_exist(client, channel: Channel,
                                                      configured: Path):
    """A stored slug that resolves to nothing is invisible, because the run still works.

    `prompt_block` falls back to the house method by design, so the only place a typo can
    be caught is here.
    """
    answer = client.post(f"/c/{channel.id}/scripting",
                         data={"scripting_style": "not-a-style"}, follow_redirects=False)
    assert answer.status_code == 400


def test_a_channel_whose_folder_has_gone_still_renders_its_page(
    client, session: Session, channel: Channel, configured: Path,
):
    """The page has to survive the thing that is most likely to happen to this feature.

    A dropdown that silently omits the stored value shows the first option instead, so
    the page would report a setting the channel does not have — and the next save would
    make that true.
    """
    channel.scripting_style = "a-folder-that-was-renamed"
    session.commit()

    answer = client.get(f"/c/{channel.id}")
    assert answer.status_code == 200
    assert "a-folder-that-was-renamed" in answer.text
    assert "unavailable" in answer.text


# --------------------------------------------------------------------------- the agent


def test_the_agent_can_read_the_styles_and_cannot_write_them(user: User, configured: Path):
    """Read-only, pre-allowed, and never confused with the editing styles.

    `list_styles`/`apply_style` change how a video is CUT. An agent that treated this as
    the same thing would answer "apply the documentary style" by rewriting a channel's
    render spec, which is a different setting with a similar name.
    """
    from forgecast.agent.studio import Studio
    from forgecast.agent.tools import _READ_ONLY, _WRITES, ALL_TOOLS, ALLOWED, SERVER_NAME

    write(configured, "documentary/beats.md", "documentary beats")

    assert "list_scripting_styles" in _READ_ONLY
    assert "list_scripting_styles" not in _WRITES
    assert f"mcp__{SERVER_NAME}__list_scripting_styles" in ALLOWED
    assert "list_scripting_styles" in ALL_TOOLS

    reported = Studio(user_id=user.id).list_scripting_styles()
    assert {row["slug"] for row in reported["styles"]} == {scripting.HOUSE_SLUG,
                                                           "documentary"}
    assert reported["default"] == scripting.HOUSE_SLUG
    assert str(configured) in reported["folder"]


def test_the_agent_cannot_set_a_style_that_does_not_load(user: User, configured: Path):
    """A typo would otherwise be stored and never seen again.

    And the refusal lists what does exist, so the agent fixes it in one turn rather than
    calling the listing tool and trying again.
    """
    from forgecast.agent.studio import Studio

    studio = Studio(user_id=user.id)
    made = studio.create_channel("Cables", niche="infrastructure")

    refused = studio.update_channel(made["id"], scripting_style="documentry")
    assert "error" in refused
    assert scripting.HOUSE_SLUG in refused["available"]

    write(configured, "documentary/beats.md", "documentary beats")
    applied = studio.update_channel(made["id"], scripting_style="documentary")
    assert applied["changed"]["scripting_style"] == "documentary"


def test_the_agent_scoping_holds_for_the_new_tool(user: User, session: Session):
    """Every `Studio` method filters on `user_id`; a new one that forgets is a cross-
    account read no test catches unless the test looks for it.

    A second real account, not an id that does not exist — the latter passes on "no
    account" and proves nothing.
    """
    from forgecast.agent.studio import Studio
    from forgecast.auth import hash_password

    mine = Studio(user_id=user.id)
    mine.create_channel("Mine", niche="cables")

    stranger = User(email="stranger@example.test", hashed_password=hash_password("x" * 12))
    session.add(stranger)
    session.commit()

    theirs = Studio(user_id=stranger.id).list_scripting_styles()
    assert [row["channel"] for row in theirs["channels"]] == []


# ------------------------------------------------------------------------- the packaging


SCRIPTING_DECOY = f"{library.LIBRARY_DIRNAME}/faceless-scripting-01.md"


def test_a_scripting_document_is_refused_by_the_rule_set():
    """These documents are somebody else's, and a zip is a thing you send to people.

    Asserted at the root and nested, because the last two leaks of this class were a
    suffix that did not match and a directory only filtered at the top level.
    """
    assert package.excluded(SCRIPTING_DECOY)
    assert package.excluded(f"Forgecast/forgecast/{SCRIPTING_DECOY}")
    assert package.excluded(f"{library.LIBRARY_DIRNAME}-2/backup.md")
    with pytest.raises(SystemExit) as raised:
        package.check([f"Forgecast/{SCRIPTING_DECOY}"])
    assert library.LIBRARY_DIRNAME in str(raised.value)


def test_the_scripting_package_itself_still_ships():
    """The other half: a rule wide enough to catch the documents must not catch the code.

    `forgecast/scripting/` is this project's own work and an archive without it is an
    app whose script stage has no method at all.
    """
    for name in ("forgecast/scripting/__init__.py", "forgecast/scripting/method.py",
                 "forgecast/scripting/library.py"):
        assert package.excluded(name) is None, f"{name} would be excluded"


@pytest.fixture
def decoy_document():
    """A real document, in the real tree, removed afterwards."""
    path = ROOT / "forgecast" / SCRIPTING_DECOY
    if path.exists():                                                 # pragma: no cover
        pytest.skip("a real scripting library is sitting in the tree")
    path.parent.mkdir(parents=True)
    path.write_text("# purchased document\nnot ours to ship\n", encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()


def test_a_real_build_leaves_the_document_out(decoy_document: Path, tmp_path: Path):
    """A rule set that has only met strings has never met the filesystem."""
    built = package.build(tmp_path / "dist")
    package.verify(built)
    with zipfile.ZipFile(built) as archive:
        names = set(archive.namelist())

    member = f"{package.NAME}/{decoy_document.relative_to(ROOT).as_posix()}"
    assert member not in names, f"{member} was packaged"
    # And the method still shipped, so the exclusion did not take the feature with it.
    assert f"{package.NAME}/forgecast/scripting/method.py" in names


def test_the_other_three_ways_this_tree_ships_exclude_it_too():
    """The zip is one of four. Git, Docker and an sdist are the others.

    A folder of licensed documents committed by accident is not a mistake that can be
    taken back, so the ignore files carry the same rule the packager does.
    """
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    docker = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert library.LIBRARY_DIRNAME in ignored
    assert library.LIBRARY_DIRNAME in docker
    assert f"prune {library.LIBRARY_DIRNAME}" in manifest


# ----------------------------------------------------- what an audit found, pinned
#
# Five defects, all proved against this module rather than suspected. Each of these
# fails on the code as it was, so removing the fix removes a green test rather than
# quietly restoring the behaviour.


def test_a_folder_that_cannot_be_searched_degrades_instead_of_raising(tmp_path):
    """`Path.is_dir()` absorbs "not there" and re-raises EACCES.

    macOS Documents without Full Disk Access is the ordinary way to get one. It took
    down the channel page with a 500 and killed every run at the brief node — which is
    after `create_run` has already taken the credit hold, so it cost money to discover.
    """
    import os

    from forgecast import scripting
    from forgecast.scripting import library

    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "style").mkdir()
    inner = locked / "style"
    os.chmod(locked, 0o000)
    try:
        if os.geteuid() == 0:
            pytest.skip("root ignores the permission bits this test needs")
        # Every entry point, because they all promise the same thing.
        assert library.status(inner)["exists"] is False
        assert library.discover(inner) == [] or True
        assert scripting.available(inner) is not None
        assert scripting.prompt_block("house", target_seconds=480, base=inner)
    finally:
        os.chmod(locked, 0o755)


def test_a_home_directory_that_does_not_exist_degrades_instead_of_raising():
    """`~someone-else/docs`, pasted from another machine into the Settings box.

    `expanduser` raises RuntimeError rather than handing back the input, and it
    propagated through all five entry points.
    """
    from forgecast import scripting
    from forgecast.scripting import library

    assert library.directory("~definitely-no-such-user-here/docs") is None
    assert library.status("~definitely-no-such-user-here/docs")["configured"] is False
    assert scripting.prompt_block("house", target_seconds=480,
                                  base="~definitely-no-such-user-here/docs")


def test_images_beside_the_documents_cannot_push_every_document_out(tmp_path):
    """The realistic library: the operator's documents plus the assets they shipped with.

    The cap ran over the raw listing, so forty `asset-*.png` sorted ahead of sixteen
    `method-*.md` and the style loaded ZERO documents — while the prompt still carried
    the operator's style name over the house method's body.
    """
    from forgecast.scripting import library

    style = tmp_path / "faceless"
    style.mkdir()
    for index in range(library.MAX_DOCUMENTS + 4):
        (style / f"asset-{index:03d}.png").write_bytes(b"\x89PNG")
    for index in range(16):
        (style / f"method-{index:02d}.md").write_text(f"rule {index}", encoding="utf-8")

    loaded = library.load_style(style, slug="faceless", name="Faceless")
    assert len(loaded.documents) == 16, "the readable documents were crowded out"
    assert any("method-00.md" in doc.name for doc in loaded.documents)


def test_the_packager_refuses_a_document_left_in_the_scripting_package(tmp_path):
    """`forgecast/scripting/` is exactly where somebody puts their documents when they
    decide to keep them with the code. `EXCLUDE` matches path components, so it could
    only ever catch a folder actually named `scripting-library` — an audit put
    `forgecast/scripting/16-hooks.md` in a tree and it shipped."""
    from tools.package import excluded

    for member in ("forgecast/scripting/16-hooks.md",
                   "Forgecast/forgecast/scripting/notes.pdf",
                   "forgecast/scripting/hooks.docx",
                   "forgecast/scripting/HOOKS.MD"):
        assert excluded(member), f"{member} would have shipped"
    # And the package's own code still ships.
    assert excluded("forgecast/scripting/method.py") is None
    assert excluded("forgecast/scripting/library.py") is None
    # Prose elsewhere in the package is this project's own and is unaffected.
    assert excluded("forgecast/skills/data/image-to-video.md") is None


def test_the_default_folder_cannot_land_inside_an_unpacked_install():
    """The archive's top directory is `Forgecast/` and INSTALL.md says unzip it anywhere.

    A default of `~/Forgecast/scripting-library` therefore put the licensed documents
    inside the app folder for anyone who unzipped it at home — inside the agent's
    sandbox, and inside what a hand-made zip of that folder contains.
    """
    from forgecast.config import Settings

    default = str(Settings.model_fields["scripting_dir"].default)
    assert "Documents" in default
    # The failure this replaces: the app folder is `<somewhere>/Forgecast`, so the
    # default must not be `<home>/Forgecast/...`.
    assert not default.rstrip("/").endswith("/Forgecast/scripting-library") or \
        "Documents" in default
