"""The cross-video pass: what the winners share, and on how many different channels.

Three things are defended here, and the first is the one the feature exists for.

**A habit must never be printed as a convention.** A title shape on one channel's
outliers is that channel's tic; the same shape on three is what the niche does. The
arithmetic cannot tell them apart — a share is a share — so the channel count is the
only thing that can, and every finding has to carry it and say it in words. The
regression is not a wrong number, it is a quarter spent copying one competitor.

**A small sample must refuse to generalise.** Three videos is a coincidence with a name.
The tests below walk the boundary at `MIN_SUPPORT` from both sides, because a threshold
nothing tests is a threshold that gets tuned to whatever makes the demo look full.

**Nothing may be claimed that the fetch cannot see.** The desk has titles, view counts,
durations and dates. It has no transcript, no thumbnail and no retention curve, and a
report that quietly omits them reads as a report that checked them.

The arithmetic fixtures use a frozen `NOW` and rates that divide exactly, so an expected
multiple can be worked out by hand — a scoring bug and a scoring opinion look identical
otherwise. `uploads` gives every ordinary video the same views-per-day on purpose: the
median is then that rate exactly, and a hit's multiple is whatever it was built to be.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from forgecast.research import synthesis
from forgecast.research.outliers import VideoStat
from forgecast.research.synthesis import (
    MIN_SUPPORT,
    SCOPE_CHANNEL,
    SCOPE_CONVENTION,
    SCOPE_PICKS,
    SCOPE_SHARED,
    SCOPE_SPLIT,
    synthesise,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)

ORDINARY = "the sea explained"


def uploads(channel: str, *, now: datetime = NOW, count: int = 8, rate: int = 500,
            cadence: float = 7.0, start: float = 15.0, seconds: float = 600.0,
            title: str = ORDINARY, approximate: bool = False,
            engagement: float = 0.0) -> list[VideoStat]:
    """A channel's back catalogue, every video sitting exactly on the median rate."""
    out: list[VideoStat] = []
    for index in range(count):
        age = start + cadence * index
        views = int(rate * age)
        out.append(VideoStat(
            video_id=f"{channel[:4].lower()}{index}",
            title=f"{title} {index}",
            views=views,
            published_at=now - timedelta(days=age),
            duration_seconds=seconds,
            channel=channel,
            likes=int(views * engagement),
            date_is_approximate=approximate,
        ))
    return out


def hit(channel: str, video_id: str, title: str, *, now: datetime = NOW,
        multiple: float = 6.0, days_old: float = 10.0, rate: int = 500,
        seconds: float = 600.0, priority: bool = False, approximate: bool = False,
        engagement: float = 0.0) -> VideoStat:
    """One video on `channel` that beat its own median by exactly `multiple`."""
    views = int(rate * days_old * multiple)
    return VideoStat(
        video_id=video_id, title=title, views=views,
        published_at=now - timedelta(days=days_old), duration_seconds=seconds,
        channel=channel, likes=int(views * engagement), is_priority=priority,
        date_is_approximate=approximate,
    )


def kinds(result, kind: str) -> list:
    return [item for item in result.findings if item.kind == kind]


def as_paste(videos: list[VideoStat]) -> str:
    """The same videos as a spreadsheet paste, for the tests that go through HTTP."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "views", "published", "duration", "channel"])
    for video in videos:
        writer.writerow([
            video.title, video.views,
            video.published_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            int(video.duration_seconds), video.channel,
        ])
    return buffer.getvalue()


# ------------------------------------------------- one channel is never a niche pattern


def test_a_pattern_on_one_channel_is_never_reported_as_a_niche_pattern():
    """The regression the whole module exists for.

    Five of one channel's outliers open with an interrogative and none of its ordinary
    uploads do. That is a solid, usable fact about that channel and it is not evidence
    about the niche at all — and the two are one careless sentence apart.
    """
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(5)],
    ]

    result = synthesise(videos, now=NOW)

    assert result.channels == ["Solo"]
    titles = kinds(result, "title")
    assert titles, "the shape is there to be found"
    assert all(item.scope == SCOPE_CHANNEL for item in titles)
    assert all(len(item.channels) == 1 for item in titles)
    # And it says so in the sentence a person reads, not only in a field a template
    # might not print.
    assert all("one channel's habit" in item.scope_note for item in titles)
    assert not any(item.scope == SCOPE_CONVENTION for item in result.findings)
    assert "one channel's habit" in result.headline


def test_a_one_channel_finding_is_still_usable_because_it_is_still_true():
    """`usable` and `scope` answer different questions and must not be collapsed.

    Enough data to state it is not the same as far enough to generalise. Ten outliers on
    one channel is a confident statement about one channel.
    """
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(5)],
    ]

    (found,) = [item for item in kinds(synthesise(videos, now=NOW), "title")
                if "how / why / what" in item.headline]

    assert found.usable is True
    assert found.confidence == "medium"
    assert found.scope == SCOPE_CHANNEL


def test_the_same_pattern_on_three_channels_is_the_niches_convention():
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo", "Charlie"):
        videos += uploads(name, count=10)
        videos += [
            hit(name, f"{name[:2].lower()}hit{i}", f"Why the cables broke: part {i}",
                days_old=9 + i)
            for i in range(4)
        ]

    result = synthesise(videos, now=NOW)

    (found,) = [item for item in kinds(result, "title")
                if "how / why / what" in item.headline]
    assert found.scope == SCOPE_CONVENTION
    assert sorted(found.channels) == ["Alpha", "Bravo", "Charlie"]
    assert found.support == 12
    assert found.confidence == "high"
    assert "not one channel's habit" in found.scope_note
    assert "across 3 of the 3 channel(s) in this fetch" in result.headline


def test_two_channels_agreeing_is_not_yet_a_convention():
    """Three is the line, so two has to read as two — a pair, not the niche."""
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo"):
        videos += uploads(name, count=10)
        videos += [
            hit(name, f"{name[:2].lower()}hit{i}", f"Why the cables broke: part {i}",
                days_old=9 + i)
            for i in range(4)
        ]

    (found,) = [item for item in kinds(synthesise(videos, now=NOW), "title")
                if "how / why / what" in item.headline]

    assert found.scope == SCOPE_SHARED
    assert "two channels agreeing is a pair" in found.scope_note


# ------------------------------------------------------------- refusing to generalise


@pytest.mark.parametrize("outliers", [2, 3])
def test_too_few_videos_refuses_to_generalise(outliers):
    """Three videos is not a trend, and `MIN_SUPPORT` is where that is enforced."""
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(outliers)],
    ]

    result = synthesise(videos, now=NOW)

    patterns = [item for item in result.findings
                if item.kind in {"title", "duration", "engagement"}]
    assert patterns, "computed, so the reader can see what was too thin"
    assert all(item.confidence == "low" for item in patterns)
    assert all(not item.usable for item in patterns)
    # And the split reaches the payload, so a page cannot print the two the same way.
    payload = result.as_dict()
    assert not [row for row in payload["findings"] if row["kind"] == "title"]
    assert [row for row in payload["thin"] if row["kind"] == "title"]


def test_three_outliers_on_three_different_channels_is_still_too_few():
    """Breadth does not buy depth. One video each from three channels is three
    coincidences, and a channel count of three must not promote it past the sample."""
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo", "Charlie"):
        videos += uploads(name, count=10)
        videos.append(hit(name, f"{name[:2].lower()}hit", "Why the cables broke: part 1"))

    (found,) = [item for item in kinds(synthesise(videos, now=NOW), "title")
                if "how / why / what" in item.headline]

    assert len(found.channels) == 3
    assert found.support == 3
    assert found.confidence == "low"
    assert found.usable is False


def test_the_fourth_video_is_where_a_pattern_starts():
    """The boundary from the other side, so `MIN_SUPPORT` cannot drift untested."""
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(MIN_SUPPORT)],
    ]

    (found,) = [item for item in kinds(synthesise(videos, now=NOW), "title")
                if "how / why / what" in item.headline]

    assert found.support == MIN_SUPPORT
    assert found.usable is True


def test_every_finding_says_how_many_channels_and_how_many_videos_back_it():
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo", "Charlie"):
        videos += uploads(name, count=10, engagement=0.01)
        videos += [
            hit(name, f"{name[:2].lower()}hit{i}", f"Why the cables broke: part {i}",
                days_old=9 + i, seconds=1500.0, engagement=0.05)
            for i in range(4)
        ]

    for row in synthesise(videos, now=NOW).as_dict()["findings"]:
        assert row["support"] >= 1
        assert row["support_unit"]
        assert row["channel_count"] >= 1
        assert row["channel_count"] <= row["of_channels"]
        assert row["scope_note"]
        assert row["confidence"] in {"medium", "high"}


# ------------------------------------------------------- computing only what is there


def test_no_finding_claims_anything_the_fetch_could_not_see():
    """Titles, views, durations and dates. Not a transcript, not a thumbnail, not a
    retention curve — and the absences are stated rather than left to be noticed."""
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(5)],
    ]

    result = synthesise(videos, now=NOW)

    stated = " ".join(
        f"{item.headline} {item.detail} {' '.join(item.notes)}"
        for item in result.findings
    ).lower()
    for forbidden in ("thumbnail", "transcript", "retention", "words per minute",
                      "watch time", "click-through"):
        assert forbidden not in stated

    missing = " ".join(result.not_assessed).lower()
    for named in ("thumbnail", "transcript", "retention", "pace", "hook"):
        assert named in missing


def test_a_fetch_with_no_durations_says_so_and_measures_nothing_from_them():
    """Most pasted tables have no duration column at all. Reporting a length band off
    zeroes would put every video in the Shorts cohort at nought seconds."""
    videos = [
        *uploads("Solo", count=10, seconds=0.0),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i,
              seconds=0.0)
          for i in range(5)],
    ]

    result = synthesise(videos, now=NOW)

    assert not kinds(result, "duration")
    assert any("not one row in this fetch carries a duration" in line
               for line in result.not_assessed)


def test_engagement_is_refused_when_the_source_never_carried_any():
    """A zero is indistinguishable from a video nobody engaged with. The public-page
    reader returns no like counts for a listing, which is most fetches."""
    videos = [
        *uploads("Solo", count=10),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i)
          for i in range(5)],
    ]

    result = synthesise(videos, now=NOW)

    assert not kinds(result, "engagement")
    assert any("no like or comment counts" in line for line in result.not_assessed)


def test_engagement_is_measured_when_the_source_did_carry_it():
    videos = [
        *uploads("Solo", count=10, engagement=0.01),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i,
              engagement=0.05)
          for i in range(5)],
    ]

    (found,) = kinds(synthesise(videos, now=NOW), "engagement")

    assert "more engagement per view" in found.headline
    assert "5.0%" in found.headline and "1.0%" in found.headline


# ------------------------------------------------------------------------- cadence


def test_a_cadence_is_refused_when_the_dates_were_reconstructed():
    """`keyless` marks every listing date approximate because "3 weeks ago" is a 30-day
    window. A gap between two of those carries a month of slop — larger than most of the
    schedules this would report."""
    videos = [
        *uploads("Solo", count=10, approximate=True),
        *[hit("Solo", f"solohit{i}", f"Why the cables broke: part {i}", days_old=9 + i,
              approximate=True)
          for i in range(4)],
    ]

    result = synthesise(videos, now=NOW)

    assert not kinds(result, "cadence")
    refusal = next(line for line in result.not_assessed if line.startswith("Upload cadence"))
    assert "Solo" in refusal
    assert "reconstructed" in refusal
    assert "±15 days" in refusal


def test_channels_on_the_same_schedule_are_reported_as_a_convention():
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo", "Charlie"):
        videos += uploads(name, count=10, cadence=7.0)

    (found,) = kinds(synthesise(videos, now=NOW), "cadence")

    assert "keep to the same schedule" in found.headline
    assert "every 7d" in found.headline
    assert found.scope == SCOPE_CONVENTION
    # Nine gaps per channel, not three channels: the evidence is the waits, and printing
    # "3" beside a figure computed from twenty-seven would understate it tenfold.
    assert found.support == 27
    assert found.support_unit == "gaps between uploads"


def test_channels_that_do_not_share_a_schedule_are_reported_as_disagreeing():
    """Where they disagree is as informative as where they agree: there is no cadence to
    copy, and a pooled average would invent one neither channel keeps."""
    videos = [*uploads("Fast", count=10, cadence=3.0),
              *uploads("Slow", count=10, cadence=21.0)]

    (found,) = kinds(synthesise(videos, now=NOW), "disagreement")

    assert "do not share a schedule" in found.headline
    assert "Fast every 3d" in found.headline
    assert "Slow every 21d" in found.headline
    # And it is scoped as a split, not as two channels agreeing about something. The
    # convention wording is precisely false about a finding whose content is the
    # difference between them.
    assert found.scope == SCOPE_SPLIT
    assert "they do not agree" in found.scope_note


def test_outliers_that_landed_after_a_longer_gap_than_usual_are_named():
    """Measured against that channel's own usual gap, not against a number of days.

    A fortnight off is a long break on a daily channel and nothing at all on a monthly
    one, so pooling raw days across channels would report the slowest channel's habits as
    everybody's. What this cannot say is why, and it says that it cannot: a video that
    took longer to make and a video that got a rested audience are identical from here.
    """
    videos: list[VideoStat] = []
    index = 0
    age = 200.0
    while age > 30:
        for _ in range(4):
            videos.append(uploads("Solo", count=1, start=age)[0])
            videos[-1].video_id = f"solo{index}"
            index += 1
            age -= 7.0
        age -= 14.0    # the extra wait, on top of the usual seven days
        videos.append(hit("Solo", f"solohit{index}", f"the big one {index}", days_old=age))
        index += 1
        age -= 7.0

    (found,) = [item for item in kinds(synthesise(videos, now=NOW), "cadence")
                if "longer gap" in item.headline]

    assert "3.0x the channel's own typical gap" in found.headline
    assert found.support == 4
    assert found.usable is True
    assert "says nothing about cause" in found.detail


# ------------------------------------------------------------------------- duration


def test_channels_pointing_opposite_ways_about_length_are_not_averaged_away():
    """The pooled median says length does not matter. It matters on both channels, in
    opposite directions, and only the per-channel reading can say so."""
    videos = [
        *uploads("Long", count=8, seconds=600.0),
        *[hit("Long", f"lohit{i}", f"a longer one {i}", seconds=1500.0, days_old=10 + i)
          for i in range(2)],
        *uploads("Short", count=8, seconds=1200.0),
        *[hit("Short", f"shhit{i}", f"a shorter one {i}", seconds=300.0, days_old=10 + i)
          for i in range(2)],
    ]

    result = synthesise(videos, now=NOW)

    (pooled,) = kinds(result, "duration")
    assert "Length is not what separates" in pooled.headline

    (split,) = [item for item in kinds(result, "disagreement")
                if "length" in item.headline]
    assert "on Long the outliers run longer" in split.headline
    assert "on Short they run shorter" in split.headline
    assert sorted(split.channels) == ["Long", "Short"]
    assert split.scope == SCOPE_SPLIT


def test_the_length_finding_is_computed_per_cohort():
    """A 45-second Short averaged with a 20-minute video is a median describing neither."""
    videos = [
        *uploads("Solo", count=8, seconds=600.0),
        *uploads("Solo", count=8, seconds=45.0, start=16.0),
        *[hit("Solo", f"lohit{i}", f"a longer one {i}", seconds=1500.0, days_old=10 + i)
          for i in range(4)],
    ]

    found = kinds(synthesise(videos, now=NOW), "duration")

    assert found, "the long-form comparison is there"
    assert all("long-form" in item.headline for item in found)
    assert all("Shorts" not in item.headline for item in found)


# ---------------------------------------------------------------- the operator's picks


def test_a_pick_is_measured_against_the_median_of_its_own_channel():
    videos = [
        *uploads("Rival", count=10, seconds=600.0),
        hit("Rival", "pasted", "the one I picked", multiple=4.0, seconds=1500.0,
            priority=True),
    ]

    (found,) = kinds(synthesise(videos, now=NOW), "picks")

    # "1 picks" under a finding is where a reader stops trusting the numbers above it.
    assert found.support_note == "1 pick"
    assert found.scope == SCOPE_PICKS
    assert found.usable is True
    assert "1 of your 1 measured pick(s) beat the median" in found.headline
    (line,) = found.notes
    assert "4.0x its channel's median views-per-day" in line
    assert "25 min against a channel median of 10 min — longer" in line


def test_a_pick_from_a_channel_nobody_fetched_says_what_it_was_measured_against():
    """A cross-channel multiple that looks like a like-for-like one is the misreading
    this list exists to prevent."""
    videos = [
        *uploads("Rival", count=10),
        hit("Someone Else", "pasted", "the one I picked", multiple=4.0, priority=True),
    ]

    (found,) = kinds(synthesise(videos, now=NOW), "picks")

    (line,) = found.notes
    assert "the median of the channels in this fetch" in line
    assert "its own channel is not among them" in line
    assert "its channel's median" not in line


def test_a_pick_that_turned_out_ordinary_is_counted_as_ordinary():
    """"It measured 0.4x" is the answer to the question they asked by pasting it."""
    videos = [
        *uploads("Rival", count=10),
        hit("Rival", "pasted", "the one I picked", multiple=0.4, priority=True),
    ]

    (found,) = kinds(synthesise(videos, now=NOW), "picks")

    assert "0 of your 1 measured pick(s) beat the median" in found.headline
    assert "0 cleared 3x" in found.headline


def test_a_pick_is_never_the_evidence_for_a_pattern_it_helped_choose():
    """Picks stay out of the comparison group for the same reason `outliers.baselines`
    keeps them out of the median: they were chosen because somebody thought they were
    unusual, so counting them as ordinary uploads biases the very thing being compared."""
    videos = [
        *uploads("Rival", count=10, seconds=600.0),
        *[hit("Rival", f"pick{i}", f"picked one {i}", multiple=4.0, seconds=1500.0,
              priority=True, days_old=9 + i)
          for i in range(5)],
    ]

    (pooled,) = kinds(synthesise(videos, now=NOW), "duration")

    # 10 min against 10 min if the picks had leaked into the comparison group; 25 against
    # 10 because they did not.
    assert "25 min against 10 min" in pooled.headline
    assert pooled.compared_with == 10


# ----------------------------------------------------------------- nothing to report


def test_a_fetch_where_nothing_outperformed_says_that_rather_than_inventing_a_pattern():
    result = synthesise(uploads("Solo", count=10), now=NOW)

    assert "Nothing cleared 3x" in result.headline
    assert "which is an answer, not a failure" in result.headline
    assert not [item for item in result.findings
                if item.kind in {"title", "duration", "engagement"}]


def test_an_empty_fetch_produces_a_synthesis_rather_than_an_exception():
    result = synthesise([], [], now=NOW)

    assert result.findings == []
    assert result.not_assessed, "the permanent limits are stated whatever was fetched"
    assert result.as_dict()["headline"]


def test_the_synthesis_needs_no_provider_and_no_network():
    """The hard rule: this runs offline from numbers already fetched. A model call in
    here would make the cross-video answer the first thing to disappear when a key
    expires — and it is the answer several channels were fetched for."""
    source = Path(synthesis.__file__).read_text()

    assert "from ..providers" not in source
    assert "import httpx" not in source
    assert "async def" not in source
    assert "from .outliers import" in source


# --------------------------------------------------------------------- the HTTP end


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


def two_channels() -> str:
    """Two competitors whose outliers share a title shape, as a spreadsheet paste.

    Built against the wall clock rather than the frozen `NOW`, because this path scores
    against `datetime.now`. The rates still divide exactly: every ordinary upload is at
    the same views-per-day, so the median is that rate and a hit's multiple is what it
    was built to be, whatever day the suite runs on.
    """
    now = datetime.now(UTC)
    videos: list[VideoStat] = []
    for name in ("Alpha", "Bravo"):
        videos += uploads(name, now=now, count=10)
        videos += [
            hit(name, f"{name[:2].lower()}hit{i}", f"Why the cables broke: part {i}",
                now=now, days_old=9 + i, seconds=1500.0)
            for i in range(4)
        ]
    return as_paste(videos)


def test_the_synthesis_reaches_the_api_response(client):
    answer = client.post("/api/research/score", json={"pasted": two_channels()})

    assert answer.status_code == 200
    synth = answer.json()["synthesis"]

    assert "across 2 of the 2 channel(s) in this fetch" in synth["headline"]
    assert synth["channels"] == ["Alpha", "Bravo"]
    assert synth["outliers"] == 8
    (shape,) = [row for row in synth["findings"]
                if row["kind"] == "title" and "how / why / what" in row["headline"]]
    assert shape["channel_count"] == 2
    assert shape["scope"] == SCOPE_SHARED
    assert shape["support"] == 8
    assert synth["not_assessed"]


def test_the_api_answer_never_calls_one_channel_a_niche_pattern(client):
    """The same paste with one competitor removed. Every finding has to come back
    scoped to that channel — this is the assertion that would have caught the defect if
    the scoping were ever computed in the template instead of in the pass."""
    now = datetime.now(UTC)
    videos = [
        *uploads("Alpha", now=now, count=10),
        *[hit("Alpha", f"alhit{i}", f"Why the cables broke: part {i}", now=now,
              days_old=9 + i, seconds=1500.0)
          for i in range(4)],
    ]

    answer = client.post("/api/research/score", json={"pasted": as_paste(videos)})

    synth = answer.json()["synthesis"]
    assert "one channel's habit" in synth["headline"]
    for row in [*synth["findings"], *synth["thin"]]:
        assert row["scope"] != SCOPE_CONVENTION
        assert row["channel_count"] == 1
        assert "one channel's habit" in row["scope_note"]


def test_the_synthesis_is_in_the_answer_even_when_nothing_scored(client):
    """A key a page has to test for is a key that eventually goes unrendered."""
    answer = client.post("/api/research/score",
                         json={"pasted": "title,views\nA video,1000\n"})

    body = answer.json()
    assert body["count"] == 0
    assert body["synthesis"]["headline"]
    assert body["synthesis"]["findings"] == []
    assert body["synthesis"]["not_assessed"]


def test_the_page_actually_renders_the_synthesis(client):
    """A synthesis nothing displays is this project's most common defect. The endpoint
    returning it is half the feature; being called from `render` is the other half."""
    page = client.get("/research")

    assert page.status_code == 200
    assert "payload.synthesis" in page.text
    assert "What they have in common" in page.text
    # Defined is not displayed: this is the line that puts it on screen, above the
    # per-video table rather than under it.
    assert "parts.push(synthesis(payload))" in page.text
    assert page.text.index("parts.push(synthesis(payload))") < page.text.index(
        "<h2 style=\"margin-top:22px\">Baseline</h2>"
    )
    # The scope pill is what separates a convention from one channel's habit on screen.
    assert 'class="scope ${esc(item.scope)}"' in page.text
    assert ".scope.convention" in page.text
