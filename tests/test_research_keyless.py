"""Reading a channel's public numbers with no API key, and being honest about the cost.

## Why the fixture below is real output and not something plausible

`REAL_PAYLOAD` is genuine `yt-dlp --flat-playlist --dump-single-json` output, captured
from `@Kurzgesagt` on 2026-08-03 and trimmed to the fields this code reads. Inventing a
payload tests the parser against my idea of the format, which is exactly the assumption
that breaks silently when the real shape differs.

It also happens to be the evidence for the whole approximate-date design: three of the
six entries carry the identical timestamp `1780444800`. Three videos were not published
in the same second — they all said "2 months ago" on the page, and yt-dlp reconstructed
one date for all three. That is what `date_is_approximate` exists to record.

The real subprocess is blocked suite-wide by an autouse fixture in conftest, so every
test here substitutes `_run`. The live path was verified by hand against the same
channel: 40 uploads read, 0 skipped, 5 outliers found, 3 of them correctly flagged.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest

from forgecast.research import keyless, sources
from forgecast.research.outliers import find_outliers

# The day the payload below was captured. Anything scored from it is scored as of then,
# so the expected numbers do not drift with the wall clock.
CAPTURED_AT = datetime(2026, 8, 3, tzinfo=UTC)

REAL_PAYLOAD = {
    "_type": "playlist",
    "channel": "Kurzgesagt – In a Nutshell",
    "channel_follower_count": 25400000,
    "channel_id": "UCsXVk37bltHxD1rDPwtNM8Q",
    "uploader": "Kurzgesagt – In a Nutshell",
    "title": "Kurzgesagt – In a Nutshell - Videos",
    "entries": [
        {"id": "PqtggjVAi8M", "title": "How Are Memories Stored Inside Your Brain?",
         "duration": 836, "timestamp": 1783036800, "view_count": 2300000},
        {"id": "8qQW4LTWgtc", "title": "Why Earth Sucks Compared to the Planet Hestia",
         "duration": 893, "timestamp": 1780444800, "view_count": 5500000},
        {"id": "TYhNHX372ek",
         "title": "The Uncomfortable Truth About Ozempic (Updated Version)",
         "duration": 953, "timestamp": 1780444800, "view_count": 5000000},
        {"id": "n-gYFcVx-8Y", "title": "GERMANY IS OVER",
         "duration": 845, "timestamp": 1780444800, "view_count": 4600000},
        {"id": "dl0-TveDDGA", "title": "Our Minds Are Weirder than You Think",
         "duration": 742, "timestamp": 1777766400, "view_count": 2500000},
        {"id": "h3DCdWyb0cc",
         "title": "The Most Insane Megaproject You Never Heard About",
         "duration": 786, "timestamp": 1775174400, "view_count": 3300000},
    ],
}


def done(stdout: str = "", *, code: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(["yt-dlp"], code, stdout, stderr)


@pytest.fixture
def yt_dlp(monkeypatch):
    """Stand in for the binary, and record the command it was given."""
    import json

    calls: list[list[str]] = []
    state = {"result": done(json.dumps(REAL_PAYLOAD)), "raise": None}

    def fake(command):
        calls.append(command)
        if state["raise"] is not None:
            raise state["raise"]
        return state["result"]

    monkeypatch.setattr(keyless, "_executable", lambda: "/usr/bin/yt-dlp")
    monkeypatch.setattr(keyless, "_run", fake)
    return type("Stub", (), {"calls": calls, "state": state})()


# ----------------------------------------------------------------- the real payload


def test_a_real_listing_parses_into_scoreable_videos(yt_dlp):
    parsed = keyless.channel_uploads("@Kurzgesagt")

    assert len(parsed.videos) == 6
    assert parsed.skipped == []
    first = parsed.videos[0]
    assert first.video_id == "PqtggjVAi8M"
    assert first.views == 2_300_000
    assert first.duration_seconds == 836.0
    assert first.channel == "Kurzgesagt – In a Nutshell"
    assert first.channel_subscribers == 25_400_000
    # Long-form, which is what decides the cohort it will be scored in.
    assert first.cohort == "long"


def test_every_date_from_this_source_is_marked_approximate(yt_dlp):
    parsed = keyless.channel_uploads("@Kurzgesagt")
    assert all(video.date_is_approximate for video in parsed.videos)


def test_the_real_payload_shows_why_the_dates_cannot_be_trusted(yt_dlp):
    """Three videos share one timestamp, because they shared one "2 months ago" label."""
    parsed = keyless.channel_uploads("@Kurzgesagt")
    stamps = [video.published_at for video in parsed.videos]
    assert len(set(stamps)) < len(stamps)


def test_the_scorer_flags_what_the_approximation_can_move(yt_dlp):
    """End to end: read a real channel, score it as of the capture date, check the flags.

    Scored at `CAPTURED_AT` rather than "now" so the arithmetic below stays checkable by
    hand. Ages come out at 31, 61, 61, 61, 92 and 122 days, giving rates of 74.2k, 90.2k,
    82.0k, 75.4k, 27.2k and 27.0k views/day and a median of 74.8k. Only one video beats
    that median by the 1.1x asked for here — a real channel's six most recent uploads
    are not supposed to contain a 3x outlier, and this one does not.
    """
    parsed = keyless.channel_uploads("@Kurzgesagt")
    found = find_outliers(parsed.videos, now=CAPTURED_AT, threshold=1.1)

    assert len(found) == 1
    top = found[0]
    assert top.video.video_id == "8qQW4LTWgtc"
    assert round(top.multiple, 2) == 1.21
    # 1.205 * 61/76 = 0.97, which is under 1.1 — so its presence in this list is not
    # something the reconstructed date can support, and it says so.
    assert top.reliable is False
    assert "may not clear 1.1x at all" in top.notes[0]

    for item in found:
        assert item.multiple_low <= item.multiple <= item.multiple_high
        if not item.reliable:
            assert any("relative label" in note for note in item.notes)


# ------------------------------------------------------------------- the listing url


@pytest.mark.parametrize("reference,expected", [
    ("https://www.youtube.com/@Kurzgesagt", "https://www.youtube.com/@Kurzgesagt/videos"),
    ("@Veritasium", "https://www.youtube.com/@Veritasium/videos"),
    ("https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
     "https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA/videos"),
    ("UCX6OQ3DkcsbYNE6H8uQQuVA",
     "https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA/videos"),
])
def test_references_resolve_to_an_uploads_listing(reference, expected):
    assert keyless._listing_url(reference) == expected


def test_the_url_always_ends_in_videos_not_the_featured_tab():
    """A bare channel URL is the *featured* tab — a curated highlights reel.

    Scoring that would compare a channel against the videos it chose to promote, so
    every one of them looks average and the actual outliers are missing entirely.
    """
    for reference in ("@a_channel", "UCX6OQ3DkcsbYNE6H8uQQuVA",
                      "https://www.youtube.com/@a_channel"):
        assert keyless._listing_url(reference).endswith("/videos")


def test_a_single_video_link_is_refused_with_the_reason():
    with pytest.raises(keyless.KeylessError) as caught:
        keyless._listing_url("https://youtu.be/dQw4w9WgXcQ")
    assert "cohort" in str(caught.value)


def test_something_that_is_not_a_channel_is_refused():
    with pytest.raises(keyless.KeylessError):
        keyless._listing_url("make me a video about ships")


def test_the_limit_is_passed_through_and_clamped(yt_dlp):
    keyless.channel_uploads("@x", limit=9)
    assert "9" in yt_dlp.calls[0]

    keyless.channel_uploads("@x", limit=99_999)
    assert "200" in yt_dlp.calls[1]


def test_the_date_extractor_arg_is_always_sent(yt_dlp):
    """Without it every timestamp is null and there is nothing at all to score."""
    keyless.channel_uploads("@x")
    assert "youtubetab:approximate_date" in yt_dlp.calls[0]


# ---------------------------------------------------------------------- absence


def test_without_the_binary_the_fix_names_both_ways_out(monkeypatch):
    monkeypatch.setattr(keyless, "_executable", lambda: None)

    ready, fix = keyless.available()
    assert ready is False
    assert "pip install yt-dlp" in fix
    assert "Settings" in fix

    with pytest.raises(keyless.KeylessError) as caught:
        keyless.channel_uploads("@x")
    assert "pip install yt-dlp" in str(caught.value)


# ------------------------------------------------------------------ failure modes


def test_a_failing_binary_reports_what_it_said(yt_dlp):
    yt_dlp.state["result"] = done(code=1, stderr="ERROR: [youtube:tab] not found")
    with pytest.raises(keyless.KeylessError) as caught:
        keyless.channel_uploads("@nope")
    assert "not found" in str(caught.value)


def test_a_silent_success_is_still_a_failure(yt_dlp):
    """Exit 0 with no output is not an empty channel, it is a broken read."""
    yt_dlp.state["result"] = done("   ")
    with pytest.raises(keyless.KeylessError):
        keyless.channel_uploads("@x")


def test_output_that_is_not_json_says_so(yt_dlp):
    yt_dlp.state["result"] = done("Downloading webpage...")
    with pytest.raises(keyless.KeylessError) as caught:
        keyless.channel_uploads("@x")
    assert "not JSON" in str(caught.value)


def test_a_timeout_suggests_the_thing_that_would_help(yt_dlp):
    yt_dlp.state["raise"] = subprocess.TimeoutExpired(["yt-dlp"], keyless.TIMEOUT_SECONDS)
    with pytest.raises(keyless.KeylessError) as caught:
        keyless.channel_uploads("@huge")
    assert "smaller limit" in str(caught.value)


def test_a_binary_that_will_not_start_is_reported_as_such(yt_dlp):
    yt_dlp.state["raise"] = OSError("Exec format error")
    with pytest.raises(keyless.KeylessError) as caught:
        keyless.channel_uploads("@x")
    assert "could not run yt-dlp" in str(caught.value)


# ----------------------------------------------------------------------- skipping


def test_unreadable_entries_are_named_rather_than_quietly_dropped(yt_dlp, monkeypatch):
    """"6 read, 3 skipped" is a fact about the channel; a silent 3 is not."""
    import json

    payload = {
        "channel": "Mixed", "channel_follower_count": 10,
        "entries": [
            {"id": "ok", "title": "fine", "duration": 600,
             "timestamp": 1775174400, "view_count": 1000},
            {"id": "members", "title": "Members only", "duration": 600,
             "timestamp": 1775174400, "view_count": None},
            {"id": "undated", "title": "No date at all", "duration": 600,
             "timestamp": None, "view_count": 5000},
            {"id": "gone", "title": "[Private video]", "duration": 600,
             "timestamp": 1775174400, "view_count": 0},
            "not an object at all",
        ],
    }
    yt_dlp.state["result"] = done(json.dumps(payload))

    parsed = keyless.channel_uploads("@mixed")
    assert [video.video_id for video in parsed.videos] == ["ok"]
    assert len(parsed.skipped) == 4
    joined = " | ".join(parsed.skipped)
    assert "no public view count" in joined
    assert "no date" in joined
    assert "[Private video]" in joined


# ------------------------------------------------------------------- read_channel


def test_a_configured_key_wins_and_the_fallback_is_not_touched(monkeypatch, yt_dlp):
    from forgecast.research.outliers import VideoStat

    def api(reference, key, *, limit):
        assert key == "AIza-test"
        return sources.ParseResult(videos=[VideoStat("v", "t", 1, _when())])

    monkeypatch.setattr(sources, "from_youtube_api", api)
    parsed, via = sources.read_channel("@x", api_key="AIza-test")

    assert len(parsed.videos) == 1
    assert "API key" in via
    assert yt_dlp.calls == []


def test_a_failing_api_falls_back_to_the_public_page(monkeypatch, yt_dlp):
    """A quota that ran out at lunchtime is the ordinary way this breaks."""
    def api(reference, key, *, limit):
        raise sources.ResearchError("YouTube API videos returned 403: quotaExceeded")

    monkeypatch.setattr(sources, "from_youtube_api", api)
    parsed, via = sources.read_channel("@Kurzgesagt", api_key="AIza-test")

    assert len(parsed.videos) == 6
    assert via == keyless.SOURCE_NOTE
    assert yt_dlp.calls


def test_when_both_sources_fail_the_error_names_both(monkeypatch, yt_dlp):
    def api(reference, key, *, limit):
        raise sources.ResearchError("YouTube API channels returned 403: quotaExceeded")

    monkeypatch.setattr(sources, "from_youtube_api", api)
    yt_dlp.state["result"] = done(code=1, stderr="ERROR: channel does not exist")

    with pytest.raises(sources.ResearchError) as caught:
        sources.read_channel("@nope", api_key="AIza-test")
    message = str(caught.value)
    assert "quotaExceeded" in message
    assert "does not exist" in message


def test_with_no_key_at_all_the_public_page_is_the_source(yt_dlp):
    parsed, via = sources.read_channel("@Kurzgesagt")
    assert len(parsed.videos) == 6
    assert "no API key needed" in via


def test_with_no_key_and_no_binary_the_error_is_actionable(monkeypatch):
    monkeypatch.setattr(keyless, "_executable", lambda: None)
    with pytest.raises(sources.ResearchError) as caught:
        sources.read_channel("@x")
    assert "pip install yt-dlp" in str(caught.value)


def _when():
    return datetime(2026, 1, 1, tzinfo=UTC)


# --------------------------------------------------------- the studio, as the agent


def test_the_agent_can_research_a_channel_with_no_key_configured(user, yt_dlp):
    """The wall this whole module exists to remove.

    This used to answer "No YouTube Data API key is set, so I cannot fetch the numbers
    for that link" — the tool's most obvious use, refused on every fresh install.
    """
    from forgecast.agent.studio import Studio

    out = Studio(user_id=user.id).research_channel("https://youtube.com/@Kurzgesagt")

    assert "error" not in out
    assert out["videos"] == 6
    assert "no API key needed" in out["via"]


def test_the_agent_still_refuses_a_single_video_before_reading_anything(user, yt_dlp):
    """The wrong link is a more specific problem, so it is reported without fetching."""
    from forgecast.agent.studio import Studio

    out = Studio(user_id=user.id).research_channel("https://youtu.be/dQw4w9WgXcQ")
    assert "cohort" in out["error"]
    assert yt_dlp.calls == []


def test_setting_up_a_channel_measures_it_without_a_key(user, yt_dlp):
    from forgecast.agent.studio import Studio

    out = Studio(user_id=user.id).study_youtube_channel("@Kurzgesagt")

    assert out["measured"] is True
    assert out["subscribers"] == 25_400_000
    assert out["uploads_read"] == 6
    # Median of 742, 786, 836, 845, 893, 953 is over 90s, so long-form, not Shorts.
    assert out["format"] == "longform"
    assert "no API key needed" in out["via"]


def test_a_channel_that_cannot_be_read_is_still_a_channel_that_can_be_created(user, yt_dlp):
    """Setting a channel up does not depend on measuring one.

    The numbers are a shortcut past four questions. Losing the shortcut means asking
    the questions, not refusing to continue — so this is not an error.
    """
    from forgecast.agent.studio import Studio

    yt_dlp.state["result"] = done(code=1, stderr="ERROR: channel does not exist")
    out = Studio(user_id=user.id).study_youtube_channel("@ghost")

    assert out["measured"] is False
    assert out["suggested_name"] == "Ghost"
    assert "does not exist" in out["why_not"]
    assert "niche" in out["note"]


# ------------------------------------------------------------------- the HTTP end


@pytest.fixture
def client(user):
    from fastapi.testclient import TestClient

    from forgecast.api.main import create_app

    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


def test_the_fetch_box_is_open_when_yt_dlp_is_installed_and_no_key_is(client, yt_dlp):
    """It used to be `disabled` unless a key was set, on an install that could fetch."""
    page = client.get("/research")
    assert page.status_code == 200
    box = page.text.split('id="channel"', 1)[1][:200]
    assert "disabled" not in box


def test_the_fetch_box_names_the_fix_when_nothing_can_read_a_channel(client, monkeypatch):
    monkeypatch.setattr(keyless, "_executable", lambda: None)

    page = client.get("/research")
    box = page.text.split('id="channel"', 1)[1][:400]
    assert "disabled" in box
    assert "pip install yt-dlp" in page.text


def test_the_desk_scores_a_channel_link_with_no_key(client, yt_dlp):
    answer = client.post("/api/research/score", json={"channel": "@Kurzgesagt"})

    assert answer.status_code == 200
    body = answer.json()
    assert body["count"] == 6
    assert "no API key needed" in body["via"]
    # Six videos in one cohort is enough for a median, so the baseline is real.
    assert body["baselines"]["long"]["reliable"] is True


def test_a_channel_that_cannot_be_read_is_a_502_that_says_why(client, yt_dlp):
    yt_dlp.state["result"] = done(code=1, stderr="ERROR: channel does not exist")
    answer = client.post("/api/research/score", json={"channel": "@ghost"})

    assert answer.status_code == 502
    assert "does not exist" in answer.json()["detail"]
