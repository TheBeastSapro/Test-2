"""The sound stage: fetching a bed, levelling it, and refusing to fetch one uninvited.

Three things are being pinned here, and each of them is a decision that would be cheap to
undo by accident:

  1. **Music is chosen, never inherited.** A connector configured for narration must not
     start spending an operator's music subscription on channels that never asked. The
     enforcement is an empty routing list, which is one keystroke from being "helpfully"
     filled in.
  2. **What shipped can be named.** Every bed carries its Epidemic track id into the node
     output, because an untraceable track in a monetised render is the failure the
     licence terms are about.
  3. **A vendor failure produces a video, not a dead run.** Every stage before this one
     has already been paid for.

Nothing here touches the network. The MCP session is refused outright at module level and
the node tests run in `FORGECAST_PROVIDER_MODE=mock`, which is also every fresh install's
first run.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from forgecast.agent import connectors
from forgecast.db import SessionLocal
from forgecast.graph.engine import ChannelSnapshot, GraphEngine, NodeContext, create_run
from forgecast.graph.pipelines import get_pipeline
from forgecast.models import Channel, Node, NodeStatus, RunStatus
from forgecast.nodes import sound as sound_node
from forgecast.providers import epidemic, registry
from forgecast.providers.base import Capability, MusicTrack, ProviderError, ProviderTimeout
from forgecast.render import audio as mixing
from forgecast.render import ffmpeg as ff
from forgecast.style import SoundBrief, brief_from, design


@pytest.fixture(autouse=True)
def nothing_connected():
    """Same reasoning as test_voice_epidemic: the connector store is a file beside the
    database and `conftest` only recreates the schema, so a connector written by one test
    is still there for the next one — which made "not connected" tests pass for the wrong
    reason and then attempt real calls once ordering changed."""
    path = connectors.default_path()
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def no_real_mcp_session(monkeypatch):
    @contextlib.asynccontextmanager
    async def refuse(**kwargs):                                    # pragma: no cover
        raise AssertionError(
            "a test tried to open a real MCP session with Epidemic Sound. "
            "Patch forgecast.providers.epidemic.open_session instead."
        )
        yield  # unreachable; keeps this a valid async generator

    monkeypatch.setattr(epidemic, "open_session", refuse)


class _Remote:
    """Stands in for a live MCP session. Records what was asked of it."""

    def __init__(self, replies: dict[str, list[dict]]) -> None:
        self.replies = {name: list(items) for name, items in replies.items()}
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, arguments))
        queue = self.replies.get(tool) or []
        return queue.pop(0) if len(queue) > 1 else (queue[0] if queue else {})

    def args(self, tool: str) -> dict:
        return next(args for name, args in self.calls if name == tool)


def _session_returning(monkeypatch, remote: _Remote) -> _Remote:
    @contextlib.asynccontextmanager
    async def fake_session(**_kwargs):
        yield remote

    monkeypatch.setattr(epidemic, "open_session", fake_session)
    return remote


def _write_connector(token: str = "epidemic_live_test") -> Path:
    path = connectors.default_path()
    connectors.Store(path=path).set(epidemic.CONNECTOR_KEY, "", token, True)
    return path


RECORDING = {
    "recording": {
        "id": "11112222-3333-4444-5555-666677778888",
        "title": "Slow Water",
        "bpm": 124,
        "coverArtUrl": "https://example.invalid/cover.jpg",
        "audioFile": {"durationInMilliseconds": 194_000,
                      "lqmp3Url": "https://example.invalid/preview.mp3",
                      "waveformUrl": "https://example.invalid/wave.json"},
        "stems": [
            {"type": "DRUMS", "audioFile": {"durationInMilliseconds": 194_000}},
            {"type": "INSTRUMENTS", "audioFile": {"durationInMilliseconds": 194_000}},
        ],
        "tags": [
            {"displayName": "Hopeful", "dimension": {"name": "mood"}},
            {"displayName": "Ambient", "dimension": {"name": "genre"}},
            {"displayName": "2010s", "dimension": {"name": "decade"}},
        ],
        "credits": [
            {"role": "MAIN_ARTIST", "artist": {"name": "Ola Fen", "slug": "ola-fen"}},
            {"role": "COMPOSER", "artist": {"name": "A Composer", "slug": "a-composer"}},
        ],
    }
}


# ------------------------------------------------------------------ cost and consent


def test_music_has_no_fallback_vendor_at_all():
    """The consent mechanism is an empty list, and it must stay empty.

    Every other capability has a fallback because a run without one produces no video. A
    run without a music vendor produces a video with no music, which is a far smaller loss
    than a connector configured for narration quietly spending a music subscription on a
    channel that never asked — and, on this vendor, exporting a track nobody chose into a
    monetised render.
    """
    assert registry.DEFAULT_ROUTING[Capability.music] == []
    # The vendor exists and is reachable; it is only never *reached for*.
    capability, cls, key_name = registry.CATALOGUE["epidemic-music"]
    assert capability is Capability.music
    assert cls is epidemic.EpidemicMusicProvider
    # Keyless in the registry's sense: the credential is a connector, not a provider key.
    assert key_name == ""


def test_resolving_music_without_a_choice_refuses_rather_than_picking_one():
    live = registry.ProviderRegistry(mode="live")
    with pytest.raises(ProviderError) as caught:
        live.resolve(Capability.music)
    assert "music" in str(caught.value)


def test_naming_the_vendor_is_what_makes_it_resolvable():
    _write_connector()
    chosen = registry.ProviderRegistry(mode="live").music("epidemic-music")
    assert isinstance(chosen, epidemic.EpidemicMusicProvider)


def test_a_run_override_beats_the_channels_standing_choice():
    """"Render this one with the other bed" is the more specific instruction.

    The same precedence the engine already applies to narration vendors — and the reason
    `music()` uses setdefault rather than assignment.
    """
    live = registry.ProviderRegistry(mode="mock", overrides={"music": "epidemic-music"})
    live.music("some-other-vendor")
    assert live.overrides["music"] == "epidemic-music"


def test_an_unconnected_vendor_names_the_fix_and_the_capability():
    """Not-connected must not read as "narration is broken" when music is what stopped."""
    usable, reason = epidemic.available("music")
    assert usable is False
    assert "music bed" in reason and "Connectors" in reason
    # Printed under a form, where a backtick reads as a typo.
    assert "`" not in reason
    # The narration wording is untouched — the two failures are not the same sentence.
    assert "voice artists" in epidemic.available()[1]


# ---------------------------------------------------------------------- the catalogue


def test_a_search_hit_becomes_a_track_carrying_its_id_and_its_tempo():
    """The mapping is the fragile part of any adapter, so it is asserted field by field.

    `bpm` in particular: the beat-locked cut maths is `bar = 240 / bpm`, so a field
    dropped here turns a cut that can land on a bar into one that lands wherever the
    scene happened to end.
    """
    track = epidemic._music_track(RECORDING)

    assert track is not None
    assert track.track_id == "11112222-3333-4444-5555-666677778888"
    assert track.bpm == 124
    assert track.bar_seconds == pytest.approx(1.9355, abs=1e-3)
    assert track.duration_seconds == pytest.approx(194.0)
    # Composers and producers are credited too; listing them as the artists of a bed
    # would put the wrong names in a record that exists to be checked.
    assert track.artists == ["Ola Fen"]
    # A taxonomy dimension this app has no field for is dropped, not shovelled into the
    # nearest list — a bed tagged with the genre "2010s" is a search that returns nothing.
    assert track.moods == ["Hopeful"] and track.genres == ["Ambient"]
    assert track.has_vocals is False
    assert track.instrumental_stem == "INSTRUMENTS"


def test_a_vocal_stem_is_what_marks_a_track_as_singing():
    payload = {"recording": {**RECORDING["recording"],
                             "stems": [{"type": "CLEAN_VOCALS", "audioFile": {}}]}}
    assert epidemic._music_track(payload).has_vocals is True


@pytest.mark.asyncio
async def test_the_search_sends_one_query_field_and_a_tempo_window(monkeypatch):
    """`term`, `topic` and `externalID` are mutually exclusive — "specify exactly one".

    Sending two is a rejected call rather than a narrower search, and a rejected search
    reads downstream as "the library has nothing", which is a different and wrong fact.
    """
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote({
        "SearchRecordings": [{"nodes": [RECORDING], "pageInfo": {"hasNextPage": False}}],
    }))

    found = await epidemic.EpidemicMusicProvider().search_tracks(
        topic="why deep-sea cables keep breaking", bpm_min=120, bpm_max=136,
        seconds_min=90.0, instrumental_only=True, limit=5,
    )

    assert [track.track_id for track in found] == [RECORDING["recording"]["id"]]
    args = remote.args("SearchRecordings")
    assert args["query"] == {"topic": "why deep-sea cables keep breaking"}
    assert "term" not in args["query"]
    # A window, not a point: no catalogue holds a track at exactly 127.4 BPM.
    assert args["filter"]["bpm"] == {"min": 120, "max": 136}
    # Milliseconds on the wire, seconds in this codebase.
    assert args["filter"]["duration"] == {"min": 90_000}
    # The filter, not a check on the results: a bed that sings is a second narrator, and
    # finding that out after a page of results costs a page of results.
    assert args["filter"]["vocals"] is False


@pytest.mark.asyncio
async def test_an_explicit_term_wins_over_a_derived_topic(monkeypatch):
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote({"SearchRecordings": [{"nodes": []}]}))
    await epidemic.EpidemicMusicProvider().search_tracks(term="taiko", topic="anything")
    assert remote.args("SearchRecordings")["query"] == {"term": "taiko"}


@pytest.mark.asyncio
async def test_sound_effects_come_back_with_their_ids_and_lengths(monkeypatch):
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote({
        "SearchSoundEffects": [{"nodes": [{"soundEffect": {
            "id": "sfx-1", "title": "Whoosh Short",
            "audioFile": {"durationInMilliseconds": 900},
            "tags": [{"displayName": "whoosh", "slug": "whoosh"}],
        }}]}],
    }))

    found = await epidemic.EpidemicMusicProvider().search_sound_effects(
        term="whoosh transition", seconds_max=6.0, limit=4
    )

    assert [effect.effect_id for effect in found] == ["sfx-1"]
    assert found[0].duration_seconds == pytest.approx(0.9)
    assert remote.args("SearchSoundEffects")["filter"]["duration"] == {"max": 6000}


# ------------------------------------------------------------------- fetching a bed


def _edit_replies(asset: str = "https://example.invalid/bed.mp3") -> dict:
    return {
        "EditRecording": [{"id": "job-1", "status": "PENDING"}],
        "PollEditRecordingJob": [{"id": "job-1", "status": "COMPLETED",
                                  "edits": [{"id": "edit-1", "durationMs": 300_000}]}],
        "DownloadRecordingEdit": [{"assetUrl": asset}],
    }


async def _fake_download(monkeypatch, tmp_path: Path) -> None:
    async def fake(asset_url, out_path, *, provider, what):
        return ff.make_tone_audio(Path(out_path).with_suffix(".m4a"), 1.0)

    monkeypatch.setattr(epidemic, "download_asset", fake)


@pytest.mark.asyncio
async def test_a_bed_under_the_cap_is_cut_to_the_exact_length(monkeypatch, tmp_path):
    """`forceDuration` is the point of the edit: a bed that ends when the video ends,
    musically, rather than being faded out mid-phrase."""
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote(_edit_replies()))
    await _fake_download(monkeypatch, tmp_path)

    result = await epidemic.EpidemicMusicProvider().make_bed(
        "track-1", out_path=tmp_path / "bed", seconds=200.0
    )

    edit = remote.args("EditRecording")["input"]
    assert edit["targetDurationMs"] == 200_000
    assert edit["forceDuration"] is True and edit["loopable"] is False
    # Nothing can download an edit's stems, so generating them is time spent on a file
    # that cannot be fetched.
    assert edit["skipStems"] is True
    # The licence record travels with the file, not separately from it.
    assert result.meta["track_id"] == "track-1"
    assert "subscription" in result.meta["licence"]
    assert result.credits == 0


@pytest.mark.asyncio
async def test_a_bed_longer_than_the_vendor_cap_is_asked_for_as_a_loop(monkeypatch, tmp_path):
    """Five minutes is the vendor's ceiling and this app's default target is eight, so
    the cap is reached by the normal case rather than an edge one. The answer is one
    loopable edit repeated locally — stitching independent edits puts two musical
    resolutions back to back at every join."""
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote(_edit_replies()))
    await _fake_download(monkeypatch, tmp_path)

    result = await epidemic.EpidemicMusicProvider().make_bed(
        "track-1", out_path=tmp_path / "bed", seconds=480.0
    )

    edit = remote.args("EditRecording")["input"]
    assert edit["targetDurationMs"] == epidemic.EDIT_MAX_DURATION_MS
    assert edit["loopable"] is True and edit["forceDuration"] is False
    assert result.meta["loopable"] is True


@pytest.mark.asyncio
async def test_a_hit_point_becomes_a_required_region_at_an_offset(monkeypatch, tmp_path):
    """The mechanism for putting a musical change *on* a reveal rather than near it."""
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote(_edit_replies()))
    await _fake_download(monkeypatch, tmp_path)

    await epidemic.EpidemicMusicProvider().make_bed(
        "track-1", out_path=tmp_path / "bed", seconds=120.0,
        hit_points=((30.0, 34.0, 61.5),),
    )

    assert remote.args("EditRecording")["input"]["requiredRegionsAtOffsets"] == [
        {"startMs": 30_000, "endMs": 34_000, "offsetMsInEdit": 61_500}
    ]


@pytest.mark.asyncio
async def test_an_unfetchable_stem_falls_back_to_the_full_mix(monkeypatch, tmp_path):
    """`StemType` and `RecordingDownloadStemType` are different enums.

    A track can report a MELODY stem that `DownloadRecording` will refuse, which would
    arrive as a rejected call at the end of a search that appeared to have worked.
    """
    _write_connector()
    remote = _session_returning(monkeypatch, _Remote({
        "DownloadRecording": [{"assetUrl": "https://example.invalid/stem.mp3"}],
    }))
    await _fake_download(monkeypatch, tmp_path)

    result = await epidemic.EpidemicMusicProvider().make_bed(
        "track-1", out_path=tmp_path / "bed", seconds=120.0, stem="MELODY"
    )

    assert remote.args("DownloadRecording")["options"]["stemType"] == "FULL"
    assert result.meta["route"] == "stem"


@pytest.mark.asyncio
async def test_an_edit_that_never_finishes_stops_instead_of_hanging_the_run(monkeypatch):
    _write_connector()
    monkeypatch.setattr(epidemic, "EDIT_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(epidemic, "EDIT_POLL_TIMEOUT_SECONDS", 0.05)
    remote = _Remote({"PollEditRecordingJob": [{"id": "job-9", "status": "IN_PROGRESS"}]})

    with pytest.raises(ProviderTimeout) as caught:
        await epidemic.EpidemicMusicProvider()._await_edit(
            remote, "job-9", {"id": "job-9", "status": "IN_PROGRESS"}
        )
    message = str(caught.value)
    assert "job-9" in message
    # Says what is true of the licence as well as of the wait.
    assert "nothing was exported" in message


def test_both_shapes_of_a_completed_edit_job_are_read():
    """`edit` is documented as deprecated in favour of `edits`. A server that finishes
    that migration would otherwise complete a job this code then called empty."""
    assert epidemic._first_edit_id({"edits": [{"id": "new"}]}) == "new"
    assert epidemic._first_edit_id({"edit": {"id": "old"}}) == "old"
    assert epidemic._first_edit_id({"status": "COMPLETED"}) == ""


# -------------------------------------------------------------------- measured levels


def test_the_bed_is_levelled_from_measurement_not_by_a_constant_trim(tmp_path):
    """A constant trim put every bed at -55 to -65 dBFS — inaudible — because library
    tracks arrive at their own levels. Nobody noticed for several renders, because
    silence is exactly what "no music" sounds like.

    So two beds at different levels must produce two different gains, and both must land
    the same distance under the voice.
    """
    voice = ff.make_tone_audio(tmp_path / "voice.m4a", 4.0, frequency=150)
    loud = ff.make_tone_audio(tmp_path / "loud.m4a", 4.0, frequency=96)
    quiet = tmp_path / "quiet.m4a"
    ff.run_ffmpeg(["-i", str(loud), "-af", "volume=-12dB", *ff.ACODEC, str(quiet)],
                  label="quieter bed")

    loud_gain, voice_level, loud_level = mixing.bed_gain_for(voice, loud, under_db=13.0)
    quiet_gain, _, quiet_level = mixing.bed_gain_for(voice, quiet, under_db=13.0)

    assert quiet_gain > loud_gain + 6.0, (loud_gain, quiet_gain)
    for gain, level in ((loud_gain, loud_level), (quiet_gain, quiet_level)):
        landed = (level.integrated_lufs + gain) - voice_level.integrated_lufs
        assert landed == pytest.approx(-13.0, abs=1.0)


def test_a_silent_bed_is_not_amplified_into_a_hiss(tmp_path):
    """A near-silent file measures about -99 LUFS, which would ask for eighty-odd dB of
    make-up gain on a bed that had nothing in it to amplify."""
    voice = ff.make_tone_audio(tmp_path / "voice.m4a", 3.0, frequency=150)
    silent = tmp_path / "silent.m4a"
    ff.run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3",
                   *ff.ACODEC, str(silent)], label="silence")

    gain, _, bed_level = mixing.bed_gain_for(voice, silent, under_db=13.0)
    assert gain == 0.0
    assert bed_level.silent is True


def test_accents_sit_on_top_of_the_mix_rather_than_inside_it(tmp_path):
    """Effects mixed into the bed before it is ducked end up under the music *and* under
    the voice — a -23.7 dB effects bus against a -13 dB bed, which is how whole minutes
    of a render came out reading as having no sound design at all.

    Asserted as measurement rather than by inspection: placing accents must make the
    programme louder, and must not push it past the ceiling.
    """
    mix = ff.make_tone_audio(tmp_path / "mix.m4a", 6.0, frequency=150)
    hit = ff.make_tone_audio(tmp_path / "hit.m4a", 0.8, frequency=440)

    out = mixing.place_accents(mix, tmp_path / "scored.m4a",
                               [(hit, 1.0, 0.0), (hit, 3.0, 0.0)])

    before = mixing.measure(mix)
    after = mixing.measure(out)
    assert after.integrated_lufs > before.integrated_lufs
    assert after.true_peak_dbfs <= -0.5
    assert ff.ffprobe_duration(out) == pytest.approx(6.0, abs=0.2)


def test_placing_nothing_is_an_error_rather_than_a_silent_copy(tmp_path):
    mix = ff.make_tone_audio(tmp_path / "mix.m4a", 2.0)
    with pytest.raises(Exception, match="no accent files"):
        mixing.place_accents(mix, tmp_path / "out.m4a", [])


# ------------------------------------------------------------------ rationing a palette


def _cues(times: list[float], action: str = "whoosh"):
    from forgecast.style import SoundCue

    return [SoundCue(at, "accent", action, 0.35, -18.0, "") for at in times]


def test_no_file_comes_back_inside_its_cooldown():
    """Repetition, not density, is what "sounds cheap" actually means: one tick played
    240 times. A cue that cannot be served without repeating is dropped, not served."""
    palette = {"whoosh": [{"effect_id": "a", "path": "a.wav"},
                          {"effect_id": "b", "path": "b.wav"}]}
    placements, used, dropped = sound_node.assign_files(_cues([0.0, 1.0, 2.0]), palette)

    assert len(placements) == 2 and dropped == 1
    assert set(used) == {"a", "b"}
    # Two files, two placements, and the third had nowhere to go inside 30 seconds.
    assert [round(at, 1) for _, at, _ in placements] == [0.0, 1.0]


def test_no_file_is_used_more_than_its_share_of_a_whole_video():
    from forgecast.style.sound import FILE_COOLDOWN_SECONDS, MAX_USES_PER_FILE

    spacing = FILE_COOLDOWN_SECONDS + 1.0
    times = [index * spacing for index in range(MAX_USES_PER_FILE + 4)]
    palette = {"whoosh": [{"effect_id": "only", "path": "only.wav"}]}

    placements, used, dropped = sound_node.assign_files(_cues(times), palette)
    assert len(placements) == MAX_USES_PER_FILE
    assert dropped == 4 and used == ["only"]


def test_a_role_with_no_palette_drops_its_cues_rather_than_borrowing_another():
    """A missing palette category must warn, not silently reuse: rebuilding a palette
    once dropped a category and every strike lost its weight layer for a whole render."""
    palette = {"whoosh": [{"effect_id": "a", "path": "a.wav"}]}
    placements, _, dropped = sound_node.assign_files(_cues([0.0], action="impact"),
                                                     palette)
    assert placements == [] and dropped == 1


# --------------------------------------------------------------------------- the node


def _context(tmp_path: Path, *, style: dict | None = None, options: dict | None = None,
             seconds: tuple[float, ...] = (4.0, 5.0, 4.0, 5.0)) -> NodeContext:
    """A sound node with real narration on disk, because every number it works from is
    measured off that file rather than read out of the script."""
    narration = ff.make_tone_audio(tmp_path / "narration.m4a", sum(seconds), frequency=150)
    return NodeContext(
        run_id=1,
        topic="Why deep-sea cables keep breaking",
        options=dict(options or {}),
        node_key="sound",
        node_type="sound",
        params={},
        attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="infrastructure documentary", language="en",
            voice_id="", avatar_id="", aspect_ratio="16:9",
            target_duration_seconds=120, style_profile=dict(style or {}),
        ),
        registry=registry.ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={
            "script": {"title": "The cables that hold the internet up"},
            "voice": {
                "narration_path": str(narration),
                "total_seconds": sum(seconds),
                "segments": [
                    {"scene_index": index, "seconds": value, "path": str(narration)}
                    for index, value in enumerate(seconds)
                ],
            },
        },
    )


MEASURED_STYLE = {
    "music_vendor": "epidemic-music",
    "audio": {"present": True, "likely_music": True, "tempo_bpm": 126.0,
              "tempo_confidence": "high", "onsets_per_minute": 44.0,
              "silence_ratio": 0.14, "dynamic_range_db": 26.0},
    "beat_alignment": {"measured": True, "verdict": "cuts_locked_to_beat",
                       "cuts_on_beat_ratio": 0.78},
}


@pytest.mark.asyncio
async def test_nothing_is_fetched_for_a_channel_that_never_asked(tmp_path, monkeypatch):
    """The consent gate, asserted by making any resolution at all an error.

    A channel with no music vendor must not reach the registry, never mind the vendor:
    "we only fetch if a provider happens to be configured" is exactly the accident an
    empty routing list exists to prevent, and this proves the node does not route around
    it.
    """
    def refuse(self, vendor=""):                                   # pragma: no cover
        raise AssertionError("the sound node asked for a music vendor uninvited")

    monkeypatch.setattr(registry.ProviderRegistry, "music", refuse)

    result = await sound_node.sound_node(_context(tmp_path))

    assert result.output["music"] is False
    assert result.output["mixed_path"] is None
    # Not a degradation: a channel that scores nothing and a channel whose bed failed are
    # different facts, and collapsing them hides a broken connector for a month.
    assert result.output["degraded"] is False
    assert "no music vendor" in result.output["reason"]
    assert result.credits == 0


@pytest.mark.asyncio
async def test_a_named_vendor_scores_the_video_and_names_the_track(tmp_path):
    """The whole stage, offline: brief, search, bed, level, duck, place.

    The track id is the assertion that matters. An untraceable bed in a monetised render
    is the failure the licence terms are about, so the run has to be able to say what
    played.
    """
    context = _context(tmp_path, style=MEASURED_STYLE)
    result = await sound_node.sound_node(context)
    output = result.output

    assert output["music"] is True and output["degraded"] is False
    track = output["track"]
    assert track["track_id"] and track["title"]
    assert "subscription" in track["licence"]
    assert track["why"], "a bed nobody can argue with is a bed nobody checked"

    mixed = Path(output["mixed_path"])
    assert mixed.exists()
    # The mix is the narration's length: the video is not extended to fit the music.
    assert ff.ffprobe_duration(mixed) == pytest.approx(18.0, abs=0.5)

    # Levelled from measurement rather than trimmed by a constant.
    levels = output["levels"]
    assert levels["bed_gain_db"] != 0.0
    assert levels["narration_lufs"] < 0
    # This channel has a reference, so its own measured placement wins over the house
    # figure — and the house figure is still reported, so drift is visible.
    assert levels["bed_under_voice_db"] == 12.0
    assert "measured" in levels["bed_under_voice_from"]
    assert levels["house_bed_under_voice_db"] == 13.0
    # The sidechain depth is never taken from a reference: it and the bed's level are not
    # separable without the stems, which is what the brief itself says about them.
    assert levels["duck_depth_db"] == 4.0

    # The brief came from the channel's own measurements, and says so.
    assert "measured" in output["brief_from"]
    assert output["brief"]["tempo_bpm"] == 126.0

    # And the bed is an artifact in its own right, carrying the id and the licence.
    beds = [item for item in context._artifacts if item.meta.get("role") == "music_bed"]
    assert len(beds) == 1
    assert beds[0].meta["track_id"] == track["track_id"]
    assert beds[0].meta["licence"]


def test_a_channel_with_no_reference_gets_the_house_numbers_and_says_so():
    """The two failures this sits between: inheriting a stranger's mix, and dressing a
    convention up as a measurement.

    A brief with no evidence behind it has a `duck_under_db` that is a dataclass default,
    not a reading, so it must not displace the operator's own measured figure — and the
    output has to say which of the two was used.
    """
    from forgecast.style import recommend

    measured = brief_from(MEASURED_STYLE["audio"], MEASURED_STYLE["beat_alignment"])
    under, depth, source = sound_node.bed_levels(measured)
    assert (under, depth) == (12.0, 4.0) and "measured" in source

    under, depth, source = sound_node.bed_levels(recommend("space documentary"))
    assert (under, depth) == (13.0, 4.0)
    assert "house" in source and "nothing measured" in source


@pytest.mark.asyncio
async def test_the_bed_matches_the_tempo_the_reference_was_measured_at(tmp_path):
    """A brief that measured 126 BPM must not come back with the 96 BPM track."""
    result = await sound_node.sound_node(_context(tmp_path, style=MEASURED_STYLE))
    assert result.output["track"]["bpm"] == pytest.approx(124, abs=4)


@pytest.mark.asyncio
async def test_a_tempo_window_that_matches_nothing_is_widened_not_given_up_on(
    tmp_path, monkeypatch
):
    """The tempo window is the tightest thing in the search and the cheapest to lose.

    A bed at the wrong tempo under a narrated video is a mild mismatch; no bed at all is
    the video having no sound design. So the window is dropped once and the fact is
    recorded, rather than an empty page being reported as "the library has nothing".
    """
    original = epidemic.MockEpidemicMusic.search_tracks
    asked: list[dict] = []

    async def narrow_finds_nothing(self, **kwargs):
        asked.append(kwargs)
        if kwargs.get("bpm_min"):
            return []
        return await original(self, **kwargs)

    monkeypatch.setattr(epidemic.MockEpidemicMusic, "search_tracks",
                        narrow_finds_nothing)

    result = await sound_node.sound_node(_context(tmp_path, style=MEASURED_STYLE))

    assert result.output["music"] is True
    assert result.output["degraded"] is False
    # Asked twice, the second time without the window — and the record says so, so a bed
    # that does not match the reference's tempo is visible rather than puzzling.
    assert len(asked) == 2 and not asked[1].get("bpm_min")
    assert result.output["track"]["tempo_window_dropped"] is True
    assert "tempo window" in result.output["track"]["why"]


@pytest.mark.asyncio
async def test_a_bed_that_sings_is_refused_rather_than_ducked_harder(tmp_path,
                                                                    monkeypatch):
    """No amount of ducking fixes two people talking at once — a bed does not duck out
    of its own vocal, so it is a second narrator for as long as it runs."""
    async def only_vocals(self, **kwargs):
        return [MusicTrack(track_id="v-1", title="Sing Along", bpm=126,
                           duration_seconds=200.0, has_vocals=True)]

    monkeypatch.setattr(epidemic.MockEpidemicMusic, "search_tracks", only_vocals)

    result = await sound_node.sound_node(_context(tmp_path, style=MEASURED_STYLE))

    assert result.output["music"] is False
    assert result.output["degraded"] is True
    assert "vocal" in result.output["reason"]


@pytest.mark.asyncio
async def test_a_vendor_failure_leaves_a_finished_video_and_a_named_reason(tmp_path,
                                                                          monkeypatch):
    """Every stage before this one has been paid for and the picture renders either way.

    A named reason on a finished video beats a run that dies at the last stage. Both
    searches are broken here because that is what a rejected key does — it does not take
    down half a catalogue.
    """
    async def broken(self, **kwargs):
        raise ProviderError("epidemic sound refused the connection (401)",
                            provider="epidemic-music")

    monkeypatch.setattr(epidemic.MockEpidemicMusic, "search_tracks", broken)
    monkeypatch.setattr(epidemic.MockEpidemicMusic, "search_sound_effects", broken)

    result = await sound_node.sound_node(_context(tmp_path, style=MEASURED_STYLE))

    assert result.output["music"] is False
    assert result.output["degraded"] is True
    assert "401" in result.output["reason"]
    assert result.output["mixed_path"] is None


@pytest.mark.asyncio
async def test_a_failed_bed_does_not_take_the_accents_with_it(tmp_path, monkeypatch):
    """A fetched bed has already been exported against the licence.

    So the two halves fail separately: losing the accents must not discard a bed that has
    been reported, and losing the bed must not discard the design that could still be
    placed. This is the second of those, which is the one that is easy to get wrong by
    wrapping the whole stage in one try.
    """
    async def no_beds(self, **kwargs):
        return []

    monkeypatch.setattr(epidemic.MockEpidemicMusic, "search_tracks", no_beds)

    result = await sound_node.sound_node(_context(tmp_path, style=MEASURED_STYLE))

    assert result.output["music"] is False
    # Still degraded: a video with accents and no bed is not the sound it was designed to
    # have, and reporting it as complete is how half a broken vendor stays unnoticed.
    assert result.output["degraded"] is True
    assert "no instrumental bed" in result.output["reason"]
    assert result.output["effects"], "the accents were discarded with the bed"
    assert Path(result.output["mixed_path"]).exists()


@pytest.mark.asyncio
async def test_an_unusable_vendor_is_reported_by_name_not_as_a_shrug(tmp_path):
    """Live mode with nothing connected: the reason has to reach the run's log."""
    context = _context(tmp_path, style=MEASURED_STYLE)
    context.registry = registry.ProviderRegistry(mode="live")

    result = await sound_node.sound_node(context)

    assert result.output["degraded"] is True
    assert "epidemic-music" in result.output["reason"]


@pytest.mark.asyncio
async def test_a_reference_with_no_bed_is_not_given_one(tmp_path):
    """Adding music to a voice-and-room reference is not matching it, and the run says
    which measurement decided that rather than reporting a failure."""
    style = {"music_vendor": "epidemic-music",
             "audio": {"present": True, "likely_music": False, "silence_ratio": 0.02,
                       "dynamic_range_db": 9.0}}
    result = await sound_node.sound_node(_context(tmp_path, style=style))

    assert result.output["music"] is False
    assert result.output["degraded"] is False
    assert "voice and room" in result.output["reason"]


@pytest.mark.asyncio
async def test_effects_can_be_turned_off_without_turning_the_bed_off(tmp_path):
    result = await sound_node.sound_node(
        _context(tmp_path, style=MEASURED_STYLE, options={"sound_effects": False})
    )
    assert result.output["music"] is True
    assert result.output["effects"] == []


@pytest.mark.asyncio
async def test_the_accents_that_played_are_recorded_with_their_ids(tmp_path):
    """Same rule as the bed: a one-shot that shipped is a licensed asset that shipped."""
    result = await sound_node.sound_node(
        _context(tmp_path, style=MEASURED_STYLE,
                 seconds=(5.0, 8.0, 9.0, 7.0, 6.0))
    )
    effects = result.output["effects"]
    assert effects, "the plan asked for accents and none were recorded"
    assert all(entry["effect_id"] and entry["path"] for entry in effects)
    # Distinct files, because one file placed everywhere is the thing being avoided.
    assert len({entry["effect_id"] for entry in effects}) > 1


# ------------------------------------------------------------------- the graph wiring


@pytest.mark.parametrize("pipeline", ["faceless_longform", "faceless_shorts"])
def test_the_render_waits_for_the_sound(pipeline: str):
    """Both depend on `voice`, so without this edge they are in the same wave and the
    render can mux the dry narration while the bed is still being fetched — a video with
    no music and a node output claiming one."""
    spec = get_pipeline(pipeline)
    by_key = {node.key: node for node in spec.nodes}

    assert "sound" in by_key
    assert "voice" in by_key["sound"].depends_on
    assert "sound" in by_key["render"].depends_on
    # And the DAG still resolves, with sound before render in every ordering.
    order = [node.key for node in spec.topological_order()]
    assert order.index("sound") < order.index("render")
    spec.validate()


def test_the_sound_node_never_holds_a_gate():
    """A gate here would stop an unattended run on a stage that can only ever degrade."""
    for name in ("faceless_longform", "faceless_shorts"):
        spec = get_pipeline(name)
        sound = next(node for node in spec.nodes if node.key == "sound")
        assert sound.requires_approval is False


def test_the_stage_is_priced_even_though_the_bed_has_no_unit_price():
    """Epidemic publishes no per-track price — it is a flat subscription — so there is
    nothing to mark up and `credits.PER_UNIT_COSTS` has no music entry to derive from.

    The node still has to *reserve* something, or a stage that runs appears in no
    estimate at all. The default base cost covers it, and the node settles at zero, which
    is what `render` already does for its own CPU.
    """
    from forgecast import credits as billing

    assert "sound" not in billing.PER_UNIT_COSTS
    estimate = billing.estimate_node("sound", 0).credits
    assert estimate > 0


# ---------------------------------------------------------------- end to end, in mock


@pytest.mark.asyncio
async def test_a_scored_run_puts_the_bed_in_the_finished_file(session: Session,
                                                              channel: Channel):
    """The wiring, end to end: naming a vendor on the run makes the render mux the scored
    mix rather than the dry narration.

    Asserted on what the render *recorded*, because "the sound node bought a bed" and
    "the video contains it" are two different claims and the gap between them is silent.
    """
    channel.style_profile = {**(channel.style_profile or {}), **MEASURED_STYLE}
    run = create_run(
        session, channel=channel, topic="Why deep-sea cables keep breaking",
        pipeline="faceless_shorts", options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    graph = GraphEngine(SessionLocal, worker_id="test-sound", concurrency=2)
    status = RunStatus.queued
    for _ in range(9):
        status = await graph.advance(run_id)
        if status is not RunStatus.awaiting_approval:
            break
        with SessionLocal() as db:
            gate = db.execute(
                select(Node).where(Node.run_id == run_id,
                                   Node.status == NodeStatus.awaiting_approval)
            ).scalars().first()
            if gate is None:
                break
            graph.approve(db, gate, note="test approval")
            db.commit()

    assert status is RunStatus.completed, f"run ended as {status}"

    with SessionLocal() as db:
        nodes = {node.key: node for node in db.get(type(run), run_id).nodes}
        scored = nodes["sound"].output
        assert scored["music"] is True
        assert scored["track"]["track_id"]
        assert nodes["render"].output["audio_source"] == "sound"


# The unscored end-to-end case is not repeated here: `test_engine`'s full run drives the
# same pipeline with no music vendor and asserts a finished video, which is exactly the
# default path. Rendering a second one would buy the same assurance for another minute of
# suite time.


# ------------------------------------------------------------------ the brief, reused


def test_the_stage_reads_the_orphaned_brief_rather_than_a_second_one():
    """`style.sound` was written, tested, and reachable only by its own test.

    This is the assertion that it is now the thing deciding: the same builder, the same
    search filter shape, and the node's search arguments derived from it.
    """
    assert isinstance(brief_from({"present": True, "likely_music": True,
                                  "tempo_bpm": 126.0, "tempo_confidence": "high"}),
                      SoundBrief)
    brief = brief_from(MEASURED_STYLE["audio"], MEASURED_STYLE["beat_alignment"])
    assert brief.search_filter()["bpm"] == {"min": 118, "max": 134}
    plan = design(brief, [10.0, 40.0, 50.0, 45.0])
    assert plan.at_layer("music"), "the plan has to place a bed for the node to buy one"
