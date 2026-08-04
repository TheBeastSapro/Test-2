"""Licensed footage, and the lane where the operator overrides the licence.

The rule this suite exists to hold: nothing in this module may vouch for a licence it did
not establish. The failure it is written against is not a crash — it is a credit block
that reads as though Forgecast checked something, beside a file nobody checked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgecast.providers import footage
from forgecast.providers.footage import FootageClip, FootageError


def _clip(**kwargs) -> FootageClip:
    base = {"url": "https://example.test/a.mp4", "title": "A clip",
            "creator": "Someone", "licence": "cc0", "source": "nasa"}
    return FootageClip(**{**base, **kwargs})


# ------------------------------------------------------------------- the licence rule


def test_only_licences_this_app_can_stand_behind_are_safe():
    assert _clip(licence="cc0").commercially_safe
    assert _clip(licence="usgov").commercially_safe
    assert _clip(licence="pexels").commercially_safe
    # Share-alike would oblige the whole video to the same licence; non-commercial and
    # no-derivatives are breached by a monetised edit. None of them are in the set.
    for refused in ("by-sa", "by-nc", "by-nd", "", "unknown"):
        assert not _clip(licence=refused).commercially_safe, refused


def test_attribution_is_required_where_the_licence_requires_it():
    assert _clip(licence="by").needs_attribution
    assert not _clip(licence="cc0").needs_attribution


def test_an_operator_clip_is_never_safe_however_it_is_licensed():
    """Not pessimism about the file. The app did not establish the licence, the operator
    did, and a property named `commercially_safe` returning true on someone else's say-so
    is the quiet claim this codebase keeps removing."""
    assert not _clip(licence="cc0", operator_directed=True).commercially_safe
    assert not _clip(licence="pdm", operator_directed=True).commercially_safe


def test_an_operator_clip_never_prints_a_licence_it_was_handed():
    """The credit block is exactly where an unchecked claim would be believed."""
    line = _clip(licence="cc0", operator_directed=True).credit_line()
    assert "CC0" not in line
    assert "licence not established here" in line


def test_a_credit_line_is_never_empty_for_a_clip_that_needs_one():
    for clip in (_clip(licence="by", creator=""), _clip(operator_directed=True, creator="")):
        assert clip.credit_line().strip()


def test_the_two_kinds_of_credit_are_not_flattened_together():
    """One is a credit a licence requires, the other is a record of a decision somebody
    made. In one list the second reads as the first."""
    text = footage.attribution_markdown([
        _clip(licence="by", title="Licensed"),
        _clip(operator_directed=True, title="Supplied"),
    ])
    assert "## Footage credits" in text
    assert "## Operator-directed footage" in text
    assert text.index("Licensed") < text.index("Operator-directed")


def test_archive_is_searched_by_collection_and_not_by_age():
    """The site hosts a great deal its uploaders had no right to post, and 'it was on
    archive.org' is not a licence. The collection is what establishes one."""
    assert "prelinger" in footage.PUBLIC_DOMAIN_COLLECTIONS
    assert "nasa" in footage.PUBLIC_DOMAIN_COLLECTIONS


# ------------------------------------------------------------------- the operator lane


def test_operator_footage_must_be_a_file_this_machine_can_read(tmp_path: Path):
    """No fetcher reaches an unlicensed index, and this is where that is enforced: the
    lane takes a file, so there is nothing here that can be pointed at one."""
    with pytest.raises(FootageError):
        footage.operator_clip("https://somewhere.test/film.mp4", tmp_path / "out.mp4")
    with pytest.raises(FootageError):
        footage.operator_clip(tmp_path / "absent.mp4", tmp_path / "out.mp4")


def test_operator_footage_is_muted_attributed_and_flagged(tmp_path: Path, monkeypatch):
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"not really a video")
    out = tmp_path / "muted.mp4"

    seen: dict = {}

    def fake_strip(src, dest, *, start=0.0, seconds=0.0):
        seen.update(src=Path(src), dest=Path(dest), start=start, seconds=seconds)
        Path(dest).write_bytes(b"muted")
        return Path(dest)

    monkeypatch.setattr(footage, "strip_audio", fake_strip)
    clip = footage.operator_clip(source, out, start=12.5, seconds=3.0, title="The scene")

    assert seen["start"] == 12.5 and seen["seconds"] == 3.0, "the timecode has to reach ffmpeg"
    assert clip.operator_directed
    assert clip.flag_reason, "a flag with no reason is a boolean an operator has to interpret"
    assert not clip.commercially_safe
    assert clip.licence not in footage.COMMERCIAL_LICENCES


def test_the_flag_says_why_in_words_and_mentions_the_audio(tmp_path: Path, monkeypatch):
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(footage, "strip_audio",
                        lambda src, dest, **kw: Path(dest).write_bytes(b"m") or Path(dest))
    clip = footage.operator_clip(source, tmp_path / "out.mp4")
    assert "operator" in clip.flag_reason.lower()
    assert "audio" in clip.flag_reason.lower()


def test_the_audio_is_taken_off_at_ingest_not_at_render(tmp_path: Path, monkeypatch):
    """A clip that arrives muted cannot be un-muted by a later stage, and every later
    stage is written by somebody who does not know where the file came from."""
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"x")
    out = tmp_path / "out.mp4"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"muted")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(footage.subprocess, "run", fake_run)
    monkeypatch.setattr(footage, "_ffmpeg", lambda: "ffmpeg")
    footage.strip_audio(source, out, start=4.0, seconds=3.0)

    assert "-an" in commands[0], "the whole point of the lane"
    assert "-ss" in commands[0] and "4.000" in commands[0]
    assert "-t" in commands[0] and "3.000" in commands[0]


def test_a_stream_copy_that_cannot_start_mid_frame_falls_back_rather_than_failing(
    tmp_path: Path, monkeypatch
):
    """Telling an operator a perfectly good file 'failed' because a remux could not seek
    is the kind of dead end this app keeps removing."""
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"x")
    out = tmp_path / "out.mp4"
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, b"", b"seek failed")
        Path(command[-1]).write_bytes(b"muted")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(footage.subprocess, "run", fake_run)
    monkeypatch.setattr(footage, "_ffmpeg", lambda: "ffmpeg")
    footage.strip_audio(source, out, start=4.0, seconds=3.0)

    assert len(calls) == 2
    assert "libx264" in calls[1], "the fallback re-encodes"
    assert "-an" in calls[1], "and it is still muted"


def test_a_missing_ffmpeg_names_the_fix_rather_than_the_internal_state(monkeypatch):
    monkeypatch.setattr(footage.shutil, "which", lambda name: None)
    with pytest.raises(FootageError, match="Setup"):
        footage._ffmpeg()


# ------------------------------------------------------------------------ the search


def test_a_source_being_down_does_not_fail_the_whole_search(monkeypatch):
    """The caller wanted footage. Three sources answering is an answer."""
    async def boom(*args, **kwargs):
        raise FootageError("down")

    async def fine(*args, **kwargs):
        return [_clip(licence="usgov", width=1920)]

    monkeypatch.setattr(footage, "search_archive", boom)
    monkeypatch.setattr(footage, "search_nasa", fine)
    monkeypatch.setattr(footage, "search_pexels", boom)
    monkeypatch.setattr(footage, "search_pixabay", boom)

    import asyncio
    found = asyncio.run(footage.find("apollo"))
    assert len(found) == 1 and found[0].licence == "usgov"


def test_the_search_never_returns_something_it_cannot_stand_behind(monkeypatch):
    async def mixed(*args, **kwargs):
        return [_clip(licence="by-nc"), _clip(licence="cc0"), _clip(licence="")]

    async def none(*args, **kwargs):
        return []

    monkeypatch.setattr(footage, "search_nasa", mixed)
    for name in ("search_archive", "search_pexels", "search_pixabay"):
        monkeypatch.setattr(footage, name, none)

    import asyncio
    found = asyncio.run(footage.find("anything"))
    assert [clip.licence for clip in found] == ["cc0"]


def test_a_keyed_source_with_no_key_is_skipped_rather_than_an_error():
    """A Pexels key meters, it does not bill — so an absent one is the same category as
    no key at all and must not read as a failure."""
    import asyncio
    assert asyncio.run(footage.search_pexels("q", api_key="")) == []
    assert asyncio.run(footage.search_pixabay("q", api_key="  ")) == []


# ------------------------------------------------------- and the credits reach the run


class _Ctx:
    """Enough of `NodeContext` for the credit writer, which is all it touches."""

    def __init__(self, refs):
        self._refs = refs
        self.logs: list[str] = []
        self.emitted: list[tuple] = []

    def artifacts(self, node_key, kind=None):
        return [ref for ref in self._refs if kind is None or ref.kind == kind]

    def log(self, message, level="info", **data):
        self.logs.append(message)


def _ref(kind="image", **meta):
    from forgecast.graph.engine import ArtifactRef
    return ArtifactRef(kind=kind, path=Path("plate.png"), mime="image/png",
                       node_key="shots", meta=meta)


def test_a_licence_that_requires_a_credit_gets_one_written(tmp_path: Path):
    """The gap this closes: `stock.attribution_markdown` could produce this block since
    stock imagery was added and nothing ever called it, so every `by`-licensed photograph
    shipped without the credit its licence obliges."""
    from forgecast.nodes.finalize import _write_attribution

    ctx = _Ctx([_ref(licence="by", creator="A Photographer", title="A river")])
    path = _write_attribution(ctx, tmp_path)

    assert path is not None and path.name == "attribution.md"
    text = path.read_text(encoding="utf-8")
    assert "A Photographer" in text
    assert "Footage credits" in text


def test_a_run_of_generated_plates_owes_nobody_a_line(tmp_path: Path):
    """An empty credits file trains an operator to ignore the one that matters."""
    from forgecast.nodes.finalize import _write_attribution

    ctx = _Ctx([_ref(prompt="a generated plate"), _ref(prompt="another")])
    assert _write_attribution(ctx, tmp_path) is None
    assert not (tmp_path / "attribution.md").exists()


def test_an_operator_directed_clip_is_recorded_in_its_own_section(tmp_path: Path):
    from forgecast.nodes.finalize import _write_attribution

    ctx = _Ctx([
        _ref(licence="by", creator="A Photographer", title="A river"),
        _ref(kind="video", licence="operator_supplied", title="The scene",
             operator_directed=True, flag_reason="operator-directed"),
    ])
    text = _write_attribution(ctx, tmp_path).read_text(encoding="utf-8")

    assert "Operator-directed footage" in text
    assert "licence not established here" in text
    assert any("operator-directed" in line for line in ctx.logs)
