"""Locating a named scene, and refusing to claim more about it than was established.

Two rules this suite exists to hold. The first is that no piracy-class source is reachable
from here — not by an allow-list entry, not by a search result that slipped through, not by
a URL left in the source. The second is the one `providers.footage` already holds and this
module inherits: a lawful place to *watch* a scene is not a licence to *use* it, and
nothing here may print one the app did not obtain.

The failure both are written against is not a crash. It is a run page that reads as though
Forgecast checked something, beside a clip nobody checked.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from forgecast.research import scenes
from forgecast.research.scenes import SceneMatch

TRUCK_FLIP = "the scene where the truck flips in The Dark Knight"


def _completed(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, json.dumps(payload), "")


def _entry(**kwargs) -> dict:
    base = {
        "id": "abc123",
        "title": "The Dark Knight (2008) - Truck Flip Scene (7/9) | Movieclips",
        "url": "https://www.youtube.com/watch?v=abc123",
        "duration": 148,
        "channel": "Movieclips",
        "uploader_id": "@MOVIECLIPS",
        "channel_id": "UC3gNmTGu-TTbFPpfSs5kNkg",
    }
    return {**base, **kwargs}


def _match(**kwargs) -> SceneMatch:
    base = {
        "url": "https://www.youtube.com/watch?v=abc123",
        "title": "The Dark Knight - Truck Flip Scene | Movieclips",
        "source": scenes.MOVIECLIPS,
        "licence": scenes.LICENCE_DISTRIBUTION,
        "channel": "Movieclips",
        "start_seconds": 0.0,
        "end_seconds": 148.0,
        "duration_seconds": 148.0,
        "confidence": 0.9,
        "confidence_reason": "the title names the film and the action",
        # The real note rather than a stand-in, so a test asserting what it says is
        # asserting what an operator will actually read.
        "flag_reason": scenes._rights_note(scenes.MOVIECLIPS, "Movieclips", ""),
    }
    return SceneMatch(**{**base, **kwargs})


@pytest.fixture
def yt(monkeypatch):
    """Stand in for yt-dlp at `keyless`'s seam, dispatching on what was asked for.

    The suite already refuses a real run at that function; this replaces it rather than
    disabling it, so a lane that grew its own subprocess call would still be caught.
    """
    calls: list[list[str]] = []
    payloads: dict[str, dict] = {"search": {}, "cc": {}, "video": {}}

    def fake_run(command):
        calls.append(list(command))
        target = command[-1]
        if target.startswith("ytsearch"):
            return _completed(payloads["search"])
        if "results?search_query" in target:
            return _completed(payloads["cc"])
        return _completed(payloads["video"])

    monkeypatch.setattr(scenes, "_binary", lambda: "yt-dlp")
    monkeypatch.setattr(scenes.keyless, "_run", fake_run)
    return type("Yt", (), {"calls": calls, "payloads": payloads})()


class _Search:
    """The two lines of `SearchProvider` the press lane touches."""

    name = "stub"

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls
        self.queries: list[str] = []

    async def search(self, query, *, limit=8):
        from forgecast.providers.search import SearchResult

        self.queries.append(query)
        return [SearchResult(title=f"page {index}", url=url, rank=index)
                for index, url in enumerate(self.urls)]


# ------------------------------------------------------------- no piracy-class source


def test_the_refusal_list_covers_the_things_a_scene_search_actually_returns():
    """A plain web search for a film scene puts these above every legitimate result."""
    for host in ("hdhub4u.ms", "www.123movies.st", "fmovies.to", "yts.mx",
                 "kodi-repo.example", "solarmovie.pe", "1337x.to"):
        assert scenes._refused(f"https://{host}/the-dark-knight"), host
    assert scenes._refused("magnet:?xt=urn:btih:0000")


def test_a_video_id_that_happens_to_spell_a_marker_is_not_a_piracy_result():
    """Eleven arbitrary characters will eventually contain any four of them, and a
    refusal driven by the query string would empty the search at random."""
    assert not scenes._refused("https://www.youtube.com/watch?v=kodiA1b2C3d")


def test_a_refused_host_is_dropped_by_the_press_lane_whatever_it_ranks(monkeypatch):
    assert scenes._permitted_page("https://hdhub4u.ms/dark-knight-truck-flip") == ""
    assert scenes._permitted_page("https://fmovies.to/watch/tdk") == ""
    # And the allow-list is the mechanism, so an ordinary site is dropped too.
    assert scenes._permitted_page("https://example.org/dark-knight") == ""
    assert scenes._permitted_page("https://media.netflix.com/en/photos/12345")


def test_no_allow_list_entry_is_itself_a_refused_source():
    """The refusal list is a check on the allow-list, and this is the check running."""
    for domain in scenes.PRESS_DOMAINS:
        assert not scenes._refused(f"https://{domain}/"), domain
    for handle in scenes.LICENSED_CHANNELS:
        assert not scenes._refused(f"https://www.youtube.com/{handle}"), handle


def test_the_module_ships_no_url_for_a_piracy_class_host():
    """A URL literal is how a source gets added by accident. There is none here — the
    refusal markers appear in the refusal list and nowhere that could be fetched."""
    source = Path(scenes.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        if "http://" not in line and "https://" not in line:
            continue
        assert not any(marker in line.lower() for marker in scenes.REFUSED_MARKERS), line


def test_a_refused_result_never_survives_the_channel_lane(yt):
    """Belt and braces: identity would already have dropped this, and so does the guard."""
    yt.payloads["search"] = {"entries": [
        _entry(id="rip1", url="https://hdhub4u.ms/watch/tdk", uploader_id="@MOVIECLIPS"),
    ]}
    assert scenes._from_channels("The Dark Knight", "truck flips", want=5) == []


# ------------------------------------------------------------------ the licence rule


def test_no_studio_lane_is_ever_commercially_safe():
    """Movieclips is a licensed distributor: the upload is lawful. The film's copyright is
    still the studio's, and this app obtained no licence to re-cut it."""
    for licence in (scenes.LICENCE_DISTRIBUTION, scenes.LICENCE_STUDIO,
                    scenes.LICENCE_PRESS, scenes.LICENCE_NONE, "", "unknown"):
        assert not _match(licence=licence).commercially_safe, licence


def test_the_lane_vocabulary_is_not_smuggled_into_the_licence_set():
    """These strings are statements about an upload, not licences, and the set that
    decides what may be used is imported from `providers.footage` rather than restated."""
    from forgecast.providers.footage import COMMERCIAL_LICENCES

    for word in (scenes.LICENCE_DISTRIBUTION, scenes.LICENCE_STUDIO,
                 scenes.LICENCE_PRESS, scenes.LICENCE_NONE):
        assert word not in COMMERCIAL_LICENCES, word
    assert scenes.LICENCE_CC_BY in COMMERCIAL_LICENCES


def test_a_match_this_app_cannot_stand_behind_says_why_in_words():
    match = _match()
    assert not match.commercially_safe
    assert match.flag_reason, "a flag with no reason is a boolean an operator must decode"
    lowered = match.flag_reason.lower()
    assert "lawful" in lowered, "what is established comes first — it is the useful half"
    assert "yours" in lowered, "and whose decision the rest of it is"


def test_a_located_scene_never_prints_a_licence_it_was_not_given():
    """The credit block is exactly where an unchecked claim would be believed."""
    line = _match().credit_line()
    assert "LICENSED_DISTRIBUTION" not in line.upper()
    assert "reuse licence not established here" in line
    assert _match().needs_attribution


def test_the_creative_commons_lane_carries_the_uploader_s_assertion_and_says_so(yt):
    yt.payloads["cc"] = {"entries": [_entry(
        id="cc1", title="Falcon 9 booster landing on the drone ship",
        url="https://www.youtube.com/watch?v=cc1", channel="Someone", duration=95,
        uploader_id="@someone",
    )]}
    found = scenes._from_creative_commons("falcon 9 booster landing", want=3)

    assert len(found) == 1
    assert found[0].licence == scenes.LICENCE_CC_BY
    assert found[0].commercially_safe, "CC BY is the one lane where reuse is cleared"
    assert found[0].needs_attribution
    assert "did not verify" in found[0].flag_reason


def test_the_creative_commons_filter_is_not_asked_about_somebody_else_s_film(yt):
    """A stranger's CC mark on a studio film is a mistake, not a licence, and honouring
    it would be this app laundering a rip through a checkbox."""
    yt.payloads["search"] = {"entries": []}
    yt.payloads["cc"] = {"entries": [_entry(id="rip", uploader_id="@stranger")]}

    asyncio.run(scenes.locate(TRUCK_FLIP, limit=5))
    assert not any("results?search_query" in call[-1] for call in yt.calls), \
        "the CC lane ran on a description that named a film"


def test_the_creative_commons_filter_is_asked_when_nothing_is_named(yt):
    yt.payloads["search"] = {"entries": []}
    yt.payloads["cc"] = {"entries": []}

    asyncio.run(scenes.locate("a drone shot over a glacier calving", limit=5))
    assert any("results?search_query" in call[-1] for call in yt.calls)


# ------------------------------------------------------------------- channel identity


def test_a_channel_is_kept_by_handle_and_not_by_what_it_calls_itself():
    source, label, caveat = scenes._permitted_channel(_entry())
    assert (source, label, caveat) == (scenes.MOVIECLIPS, "Movieclips", "")


def test_a_look_alike_channel_does_not_get_in_on_its_display_name():
    """'Warner Bros. Pictures HD' is not Warner Bros. Pictures, and a display-name match
    is the door a re-uploader walks through."""
    impostor = _entry(channel="Warner Bros. Pictures HD", uploader_id="@wbpicturesHD1080",
                      channel_id="UCsomethingelse")
    assert scenes._permitted_channel(impostor) == ("", "", "")


def test_an_exact_display_name_cannot_overturn_a_handle_that_is_not_on_the_list():
    """The name fallback exists for an entry with no identity field at all. An entry that
    has a handle has already answered the question, and a channel calling itself exactly
    'Warner Bros. Pictures' is precisely who would walk through that door."""
    impostor = _entry(channel="Warner Bros. Pictures", uploader_id="@wbpicturesofficialhd",
                      channel_id="UCimpostor")
    assert scenes._permitted_channel(impostor) == ("", "", "")


def test_a_name_only_match_is_taken_but_flagged_as_a_presumption(yt):
    """YouTube permits duplicate display names, so a name is a presumption and a handle
    is a fact — and a result that only had the presumption says so."""
    entry = {"id": "x", "title": "Truck Flip | The Dark Knight",
             "url": "https://www.youtube.com/watch?v=x", "duration": 120,
             "channel": "Warner Bros. Pictures"}
    source, label, caveat = scenes._permitted_channel(entry)

    assert source == scenes.STUDIO_CHANNEL and label == "Warner Bros. Pictures"
    assert "duplicate display names" in caveat

    yt.payloads["search"] = {"entries": [entry]}
    found = scenes._from_channels("The Dark Knight", "truck flips", want=3)
    assert "duplicate display names" in found[0].flag_reason


def test_a_channel_nobody_licensed_is_dropped_however_good_the_title_looks(yt):
    yt.payloads["search"] = {"entries": [_entry(
        id="rip", title="The Dark Knight - Truck Flip Scene FULL HD 4K",
        url="https://www.youtube.com/watch?v=rip", channel="MovieScenes4K",
        uploader_id="@moviescenes4k", channel_id="UCrip",
    )]}
    assert scenes._from_channels("The Dark Knight", "truck flips", want=5) == []


# -------------------------------------------------------------------- the timecode


def test_an_upload_short_enough_to_be_the_scene_gets_the_clip_s_own_window(yt):
    yt.payloads["search"] = {"entries": [_entry(duration=148)]}
    match = scenes._from_channels("The Dark Knight", "truck flips", want=3)[0]

    assert (match.start_seconds, match.end_seconds) == (0.0, 148.0)
    assert match.trim_seconds == 148.0
    assert match.timecode == "00:00:00.000-00:02:28.000"
    assert any("channel ident" in note for note in match.notes), \
        "the boundary is the upload's, not a measured cut, and the note says so"


def test_an_upload_long_enough_to_contain_the_scene_returns_no_window(yt):
    """`None` and not 0.0: a caller reading 0.0 as a start would trim from the wrong
    place and never find out."""
    yt.payloads["search"] = {"entries": [_entry(
        id="full", title="The Dark Knight | Full Movie", duration=9120,
        url="https://www.youtube.com/watch?v=full", uploader_id="@wbpictures",
        channel="Warner Bros. Pictures",
    )]}
    match = scenes._from_channels("The Dark Knight", "truck flips", want=3)[0]

    assert match.start_seconds is None and match.end_seconds is None
    assert not match.has_window
    assert match.timecode == "", "an empty string, not a zero-length window"
    assert match.trim_seconds == 0.0, "which strip_audio already reads as no trim"
    assert any("cannot say where" in note for note in match.notes)


def test_a_chapter_mark_that_names_the_action_becomes_a_real_window(yt):
    yt.payloads["search"] = {"entries": [_entry(
        id="full", title="The Dark Knight | Official Full Scene Compilation",
        duration=3600, url="https://www.youtube.com/watch?v=full",
        uploader_id="@wbpictures", channel="Warner Bros. Pictures",
    )]}
    yt.payloads["video"] = {"chapters": [
        {"title": "Opening bank robbery", "start_time": 0, "end_time": 300},
        {"title": "The truck flip", "start_time": 1820.5, "end_time": 1904.0},
    ]}
    found = asyncio.run(scenes.locate(TRUCK_FLIP, limit=3))

    assert (found[0].start_seconds, found[0].end_seconds) == (1820.5, 1904.0)
    assert any("chapter mark" in note for note in found[0].notes)
    assert any("--skip-download" in call for call in yt.calls), \
        "the chapter read is metadata; the download stays vision.acquire's job"


def test_a_chapter_list_that_names_nothing_asked_for_leaves_the_window_alone(yt):
    yt.payloads["search"] = {"entries": [_entry(
        id="full", title="The Dark Knight | Behind The Scenes", duration=3600,
        url="https://www.youtube.com/watch?v=full", uploader_id="@wbpictures",
        channel="Warner Bros. Pictures",
    )]}
    yt.payloads["video"] = {"chapters": [
        {"title": "Casting", "start_time": 0, "end_time": 300},
    ]}
    found = asyncio.run(scenes.locate(TRUCK_FLIP, limit=3))
    assert not found[0].has_window


# -------------------------------------------------------------------- the confidence


def test_a_low_confidence_match_says_so_rather_than_being_dropped():
    """Dropping it would answer 'the scene is nowhere', which is a different and wrong
    answer. It comes back, ranked last, saying what did not match."""
    match = _match(title="Christopher Nolan on practical effects", confidence=0.0)
    match.confidence, match.confidence_reason = scenes._score(
        match, "The Dark Knight", {"truck", "flip"}
    )

    assert match.confidence_label == "low"
    assert match.low_confidence
    assert match.confidence_reason, "a low score with no reason is a number to argue with"
    assert "does not name the film" in match.confidence_reason
    assert match.as_dict()["confidence_label"] == "low"


def test_the_exact_scene_outranks_a_long_upload_that_merely_contains_it(yt):
    yt.payloads["search"] = {"entries": [
        _entry(id="full", title="The Dark Knight | Full Movie", duration=9120,
               url="https://www.youtube.com/watch?v=full", uploader_id="@wbpictures",
               channel="Warner Bros. Pictures"),
        _entry(id="clip", url="https://www.youtube.com/watch?v=clip"),
    ]}
    yt.payloads["video"] = {"chapters": []}
    found = asyncio.run(scenes.locate(TRUCK_FLIP, limit=5))

    assert [match.url.rsplit("=", 1)[-1] for match in found] == ["clip", "full"]
    assert found[0].confidence_label == "high"
    assert found[0].confidence > found[1].confidence


def test_confidence_is_about_identification_and_not_about_rights():
    """A clip this app is certain about and certain it may not reuse is the ordinary
    case. Rolling the rights into the score would hide it."""
    match = _match()
    match.confidence, _ = scenes._score(match, "The Dark Knight", {"truck", "flip"})
    assert match.confidence >= scenes.HIGH_CONFIDENCE
    assert not match.commercially_safe


# ------------------------------------------------------------------ reading the ask


def test_the_film_and_the_action_come_out_of_one_sentence():
    """The opening filler goes with it: the action is put into a YouTube query verbatim,
    and "the scene where the truck flips scene" is a worse query than "the truck flips
    scene" against titles that all carry the word already."""
    assert scenes.read_description(TRUCK_FLIP) == ("The Dark Knight", "the truck flips")
    assert scenes.read_description("the bus jump in Speed (1994)")[0] == "Speed"
    assert scenes.read_description('the diner scene from "Heat"')[0] == "Heat"
    # The last marker wins: a film is named once, at the end.
    assert scenes.read_description("the shootout in the street in Heat")[0] == "Heat"


def test_a_phrase_that_is_not_a_title_does_not_silence_the_creative_commons_lane():
    """'in slow motion' names no film, and reading it as one would shut the only lane
    that can answer a description like this."""
    film, action = scenes.read_description("The truck flips in slow motion")
    assert film == ""
    assert "slow motion" in action


def test_a_lower_case_line_is_read_as_naming_a_film_because_that_is_the_safe_way_to_be_wrong():
    """The capital-letter test has no signal to read here, so the tie goes to "this is a
    title". Being wrong that way costs a silenced lane; being wrong the other way asks the
    Creative Commons filter about a studio film, which is the one thing this module is for
    not doing."""
    assert scenes.read_description("the truck flips in the dark knight")[0] == "the dark knight"


def test_flips_finds_flip():
    """Without the stem the strongest signal in a description misses the title holding it."""
    assert scenes._stem("flips") == "flip"
    assert scenes._content_words("the truck flips") == {"truck", "flip"}


# ------------------------------------------------------------------------- the lanes


def test_a_lane_that_is_down_does_not_fail_the_lookup(yt, monkeypatch):
    """The operator asked where a scene is. One lane answering is an answer."""
    def broken(*args, **kwargs):
        raise scenes.SceneLookupError("yt-dlp fell over")

    monkeypatch.setattr(scenes, "_from_channels", broken)
    search = _Search(["https://media.netflix.com/en/photos/999"])
    found = asyncio.run(scenes.locate("the corridor fight in Daredevil", limit=4,
                                      search=search))

    assert len(found) == 1 and found[0].source == scenes.PRESS_KIT


def test_the_press_lane_keeps_only_the_studio_press_hosts():
    search = _Search([
        "https://hdhub4u.ms/the-dark-knight",
        "https://example.org/blog/the-truck-flip",
        "https://mediapass.warnerbros.com/asset/tdk-truck",
    ])
    found = asyncio.run(scenes._from_press("The Dark Knight", "truck flips",
                                           search=search, want=3))

    assert [match.url for match in found] == [
        "https://mediapass.warnerbros.com/asset/tdk-truck"
    ]
    assert found[0].licence == scenes.LICENCE_PRESS
    assert not found[0].commercially_safe
    assert "has not read those terms" in found[0].flag_reason


def test_the_press_lane_runs_without_a_caller_knowing_to_switch_it_on(yt, monkeypatch):
    """A capability reached only by passing an argument is a capability nobody uses."""
    yt.payloads["search"] = {"entries": []}
    search = _Search(["https://dmedmedia.disney.com/assets/andor-corridor"])
    monkeypatch.setattr(scenes, "provider_for", lambda: search)

    found = asyncio.run(scenes.locate("the corridor fight in Andor", limit=4))
    assert [match.source for match in found] == [scenes.PRESS_KIT]
    assert search.queries, "the configured provider was never asked"


def test_the_press_lane_is_not_run_against_the_keyless_wikipedia_fallback(yt):
    """Real search, right default for the research desk, and no way at all to hold a
    studio press page — so running it spends a request that cannot succeed and then
    reports the emptiness as though the press sites had nothing."""
    class _Wikipedia(_Search):
        name = "wikipedia"

        async def search(self, query, *, limit=8):        # pragma: no cover
            raise AssertionError("the press lane searched Wikipedia for a press kit")

    found = asyncio.run(scenes._from_press("Andor", "corridor fight",
                                           search=_Wikipedia([]), want=3))
    assert found == []


def test_a_press_page_has_no_window_and_is_not_asked_for_one(yt):
    search = _Search(["https://media.netflix.com/en/photos/999"])
    found = asyncio.run(scenes._from_press("Stranger Things", "the upside down",
                                           search=search, want=3))
    assert not found[0].has_window
    assert not any("--skip-download" in call for call in yt.calls)


def test_the_search_is_over_fetched_because_most_hits_are_re_uploads(yt):
    yt.payloads["search"] = {"entries": []}
    scenes._from_channels("The Dark Knight", "truck flips", want=3)

    target = yt.calls[0][-1]
    assert target.startswith("ytsearch")
    asked = int(target[len("ytsearch"):].split(":", 1)[0])
    assert asked >= 10, "asking for three would leave the allow-list nothing to keep"
    query = target.split(":", 1)[1]
    assert query == "The Dark Knight truck flips scene", query
    assert query.lower().count("scene") == 1, "the word is not doubled onto the query"


def test_nothing_legitimate_found_is_an_empty_list_and_not_a_wider_search(yt):
    """There is no lane here that reaches further when the licensed ones come back
    empty, and an empty answer is the correct one."""
    yt.payloads["search"] = {"entries": [_entry(
        id="rip", uploader_id="@somebody", channel_id="UCrip", channel="Movie Scenes")]}
    assert asyncio.run(scenes.locate(TRUCK_FLIP, limit=5)) == []


def test_the_limit_is_respected(yt):
    yt.payloads["search"] = {"entries": [
        _entry(id=f"clip{index}", url=f"https://www.youtube.com/watch?v=clip{index}")
        for index in range(10)
    ]}
    assert len(asyncio.run(scenes.locate(TRUCK_FLIP, limit=3))) == 3


def test_a_missing_yt_dlp_costs_the_youtube_lanes_and_not_the_lookup(monkeypatch):
    monkeypatch.setattr(scenes.shutil, "which", lambda name: None)
    search = _Search(["https://media.netflix.com/en/photos/999"])
    found = asyncio.run(scenes.locate(TRUCK_FLIP, limit=3, search=search))
    assert [match.source for match in found] == [scenes.PRESS_KIT]


# ---------------------------------------------------------- and no fifth fetcher here


def test_the_handoff_speaks_the_existing_fetch_path_s_own_argument_names(yt):
    """`vision.acquire.acquire` takes the reference and `footage.strip_audio` takes the
    window. There is nothing here that downloads anything."""
    yt.payloads["search"] = {"entries": [_entry(duration=148)]}
    handoff = asyncio.run(scenes.locate(TRUCK_FLIP, limit=1))[0].handoff()

    assert handoff["reference"].startswith("https://www.youtube.com/watch?v=")
    assert handoff["start"] == 0.0
    assert handoff["seconds"] == 148.0
    assert handoff["note"], "the rights position travels with the file, not beside it"


def test_the_window_is_the_shape_strip_audio_already_takes(tmp_path, monkeypatch):
    from forgecast.providers import footage

    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"muted")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(footage.subprocess, "run", fake_run)
    monkeypatch.setattr(footage, "_ffmpeg", lambda: "ffmpeg")

    source = tmp_path / "scene.mp4"
    source.write_bytes(b"x")
    handoff = _match(start_seconds=1820.5, end_seconds=1904.0).handoff()
    footage.strip_audio(source, tmp_path / "out.mp4",
                        start=handoff["start"], seconds=handoff["seconds"])

    assert "1820.500" in commands[0] and "83.500" in commands[0]
    assert "-an" in commands[0], "and it still arrives muted"


def test_every_yt_dlp_call_goes_through_the_seam_the_suite_can_refuse(yt):
    """Not tidiness. The suite refuses a real yt-dlp run at `keyless._run`, so a lane
    that grew its own subprocess call would reach youtube.com from a test."""
    yt.payloads["search"] = {"entries": [_entry()]}
    asyncio.run(scenes.locate(TRUCK_FLIP, limit=2))
    assert yt.calls, "nothing reached the seam at all"
    assert all(call[0] == "yt-dlp" for call in yt.calls)


def test_as_dict_carries_the_rights_position_and_the_confidence_together():
    payload = _match().as_dict()
    for key in ("url", "timecode", "source", "licence", "confidence",
                "confidence_label", "confidence_reason", "commercially_safe",
                "flag_reason"):
        assert key in payload, key
    assert payload["commercially_safe"] is False
    assert payload["timecode"] == "00:00:00.000-00:02:28.000"


# ------------------------------------------------------- the locator reaches the agent
#
# §8 of docs/BROLL-SCENE-LOCATOR.md said the locator "is reachable from the agent". It
# was not: 31 tools were declared and none of them was this one, so the only way to reach
# 928 tested lines was to import them in Python. These hold the connection, and hold that
# connecting it did not quietly turn a lookup into a clearance.

def test_the_locator_is_declared_as_an_agent_tool():
    from forgecast.agent import tools as agent_tools
    assert "locate_scene" in agent_tools.ALL_TOOLS


def test_looking_a_scene_up_needs_no_permission():
    """It fetches nothing, cuts nothing and spends nothing.

    A check the agent must ask permission for is a check it stops making, and then it
    guesses where a scene is instead of looking.
    """
    from forgecast.agent import tools as agent_tools
    assert f"mcp__{agent_tools.SERVER_NAME}__locate_scene" in agent_tools.ALLOWED


@pytest.mark.asyncio
async def test_an_empty_description_asks_rather_than_searching(monkeypatch):
    from forgecast.agent.studio import Studio
    out = await Studio.locate_scene(object.__new__(Studio), "  ")
    assert "error" in out


@pytest.mark.asyncio
async def test_nothing_found_is_reported_as_an_answer_not_a_failure(monkeypatch):
    """There is no lane that reaches further when the licensed ones come back empty."""
    from forgecast.agent import studio as studio_mod
    from forgecast.research import scenes as scenes_mod

    async def nothing(*_a, **_k):
        return []

    monkeypatch.setattr(scenes_mod, "locate", nothing)
    out = await studio_mod.Studio.locate_scene(
        object.__new__(studio_mod.Studio), "a scene that does not exist")
    assert out["matches"] == []
    assert "error" not in out
    assert "allow-list" in out["note"]


@pytest.mark.asyncio
async def test_every_result_carries_the_rights_position(monkeypatch):
    """A licensed upload is never handed over as a licence to re-cut."""
    from forgecast.agent import studio as studio_mod
    from forgecast.research import scenes as scenes_mod

    match = scenes_mod.SceneMatch(
        url="https://www.youtube.com/watch?v=x", title="The scene",
        source="licensed_channel", licence="licensed_distribution",
        channel="Movieclips", film="The Dark Knight", confidence=0.9,
    )

    async def found(*_a, **_k):
        return [match]

    monkeypatch.setattr(scenes_mod, "locate", found)
    out = await studio_mod.Studio.locate_scene(
        object.__new__(studio_mod.Studio), "the truck flip in The Dark Knight")

    assert out["matches"][0]["commercially_safe"] is False
    assert "None of these is cleared for re-use" in out["rights"]
    # The handoff is coordinates in the names the fetch path already takes.
    assert set(out["handoff"]) == {"reference", "start", "seconds", "note"}
