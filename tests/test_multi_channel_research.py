"""Several competitors in one fetch, plus the videos the operator picked out by hand.

Two things are being defended here and they fail in opposite directions.

**Pooling.** Reading three channels and taking one median produces a number none of them
has been near: every video on the small channel scores under 1x and half of the big
one's clear 3x. The regression below builds exactly that pair and asserts the small
channel's genuine 6x hit is still found — under a shared median it is not merely
mis-scored, it disappears.

**Merging.** A pasted video that arrives silently among forty others is, on screen,
indistinguishable from a box that ignored what was typed into it. So every pasted link
comes back as its own row whatever became of it, and a pasted video that turned out to
be ordinary says so rather than being absent.

The arithmetic fixtures use a frozen `NOW` and round numbers so the expected multiple
can be worked out by hand — a scoring bug and a scoring opinion look the same otherwise.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from forgecast.research import keyless, sources
from forgecast.research.outliers import (
    PRIORITY_RANK_WEIGHT,
    VideoStat,
    baselines,
    baselines_by_channel,
    find_outliers,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def video(video_id: str, views: int, *, days_old: float = 10, channel: str = "Rival",
          priority: bool = False, seconds: float = 600.0) -> VideoStat:
    return VideoStat(
        video_id=video_id, title=f"video {video_id}", views=views,
        published_at=NOW - timedelta(days=days_old), duration_seconds=seconds,
        channel=channel, is_priority=priority,
    )


def cohort_of(channel: str, *, rate_per_day: int, count: int = 6,
              days_old: float = 10) -> list[VideoStat]:
    """`count` videos on one channel, every one at exactly `rate_per_day`."""
    return [
        video(f"{channel[:3].lower()}{i}", int(rate_per_day * days_old),
              days_old=days_old, channel=channel)
        for i in range(count)
    ]


# ------------------------------------------------------------- splitting what was pasted


@pytest.mark.parametrize("pasted,expected", [
    ("@one\n@two\n@three", ["@one", "@two", "@three"]),
    ("@one, @two", ["@one", "@two"]),
    ("@one,@two;@three", ["@one", "@two", "@three"]),
    ("  @one  \n\n  @two  ", ["@one", "@two"]),
    ("@one", ["@one"]),
    ("", []),
    ("   ", []),
])
def test_however_several_links_were_pasted_they_come_back_as_a_list(pasted, expected):
    """One per line, comma-separated, or both at once — all of which actually arrive.

    Rejecting any of these shapes teaches the operator to fetch one channel at a time,
    which is the thing this replaces.
    """
    assert sources.split_references(pasted) == expected


def test_the_same_channel_pasted_twice_is_read_once():
    """The handle and its URL are one channel, and reading it twice prints every one of
    its outliers twice."""
    assert sources.split_references(
        "@Kurzgesagt\nhttps://www.youtube.com/@Kurzgesagt/videos"
    ) == ["@Kurzgesagt"]


def test_a_link_pasted_out_of_a_chat_client_loses_its_wrapper():
    """`<https://…>` is what a mail client hands over, and it resolves to nothing."""
    assert sources.split_references("<https://www.youtube.com/@one>") == [
        "https://www.youtube.com/@one"
    ]


@pytest.mark.parametrize("reference,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_a_video_reference_resolves_to_its_id(reference, expected):
    assert sources.as_video_id(reference) == expected


def test_a_channel_link_in_the_videos_box_is_refused_pointing_at_the_other_box():
    with pytest.raises(sources.ResearchError) as caught:
        sources.as_video_id("https://www.youtube.com/@Kurzgesagt")
    assert "channels box" in str(caught.value)


def test_prose_in_the_videos_box_is_refused_rather_than_handed_to_yt_dlp():
    """`_video_id` passes unknown text through, which would send "make me a video about
    ships" to the reader as if it were an id."""
    with pytest.raises(sources.ResearchError):
        sources.as_video_id("make me a video about ships")


# --------------------------------------------------- one median per channel, never shared


def test_two_channels_of_different_sizes_are_never_scored_against_one_median():
    """The regression: pooling does not mis-score the small channel, it erases it.

    Small runs at 500 views/day, large at 50,000, and Small has one video at 3,000/day —
    six times its own median and a clear outlier. Pooled, the median of the twelve is
    25,250 and that same video scores 0.12x, which is not in the list at any threshold.
    """
    small = cohort_of("Small", rate_per_day=500)
    large = cohort_of("Large", rate_per_day=50_000)
    hit = video("hit", 30_000, channel="Small")

    found = find_outliers([*small, *large, hit], now=NOW)

    assert [item.video.video_id for item in found] == ["hit"]
    assert found[0].multiple == pytest.approx(6.0)
    assert found[0].baseline.median_views_per_day == 500


def test_each_channel_gets_its_own_baseline_card():
    bases = baselines_by_channel(
        [*cohort_of("Small", rate_per_day=500), *cohort_of("Large", rate_per_day=50_000)],
        now=NOW,
    )
    assert set(bases) == {"Small", "Large"}
    assert bases["Small"]["long"].median_views_per_day == 500
    assert bases["Large"]["long"].median_views_per_day == 50_000
    assert bases["Small"]["long"].sample_size == 6


def test_a_channel_named_two_ways_by_two_sources_is_still_one_channel():
    """A listing read with the API and a video read from its own page must group, or the
    pasted video is measured against a baseline built from nothing."""
    videos = [
        *cohort_of("Rival Channel", rate_per_day=500),
        video("pasted", 20_000, channel="  rival channel ", priority=True),
    ]
    (found,) = [item for item in find_outliers(videos, now=NOW)
                if item.video.video_id == "pasted"]
    assert found.multiple == pytest.approx(4.0)
    assert not any("not in this fetch" in note for note in found.notes)


def test_a_single_channel_scores_exactly_as_it_did_before():
    """Grouping must be a no-op for the one-channel case, which is most of them."""
    videos = [*cohort_of("Rival", rate_per_day=500), video("hit", 40_000)]
    found = find_outliers(videos, now=NOW)
    assert [item.video.video_id for item in found] == ["hit"]
    assert found[0].multiple == pytest.approx(8.0)


# ------------------------------------------------- the videos the operator picked out


def test_a_pasted_video_is_kept_out_of_the_median_it_is_measured_against():
    """The regression the design note names: do not just append them to the pool.

    Six ordinary videos at 500/day and six pasted ones at 2,500/day. Excluded, the median
    is 500 and each pasted video reads 5x. Appended, the median of the twelve is 1,500 —
    the pasted videos drop to 1.7x, and the channel's own 3.5x hit falls to 1.2x and out
    of the list entirely. Pasting your best videos would demote everything, including
    them.
    """
    videos = [
        *cohort_of("Rival", rate_per_day=500),
        *[video(f"p{i}", 25_000, priority=True) for i in range(6)],
        video("own_hit", 17_500),
    ]

    assert baselines(videos, now=NOW)["long"].median_views_per_day == 500

    found = find_outliers(videos, now=NOW)
    assert {item.video.video_id for item in found} == {
        "p0", "p1", "p2", "p3", "p4", "p5", "own_hit"
    }
    assert all(item.multiple == pytest.approx(5.0)
               for item in found if item.priority)
    assert [item.multiple for item in found
            if item.video.video_id == "own_hit"] == [pytest.approx(3.5)]


def test_a_pasted_video_outranks_the_channels_own_at_a_lower_multiple():
    """4x that somebody chose sorts above 6x that nobody did — that is the weight."""
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("channel_hit", 30_000),
              video("pasted", 20_000, priority=True)]

    found = find_outliers(videos, now=NOW)

    assert [item.video.video_id for item in found] == ["pasted", "channel_hit"]
    assert found[0].multiple == pytest.approx(4.0)
    assert found[1].multiple == pytest.approx(6.0)


def test_the_weight_is_bounded_so_a_real_hit_is_never_buried():
    """A 4x pick does not outrank a 9x. The reason to paste a video is to compare it
    against the channel's best, not to hide it."""
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("channel_hit", 45_000),
              video("pasted", 20_000, priority=True)]

    found = find_outliers(videos, now=NOW)
    assert [item.video.video_id for item in found] == ["channel_hit", "pasted"]
    assert PRIORITY_RANK_WEIGHT * 4.0 < 9.0


def test_the_weight_never_reaches_the_number_on_screen():
    """The multiple is measured. A weighted number printed as a measurement is a lie in
    the one column that has to be true."""
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("pasted", 20_000, priority=True)]

    (found,) = [item for item in find_outliers(videos, now=NOW) if item.priority]
    row = found.as_dict()

    assert row["multiple"] == 4.0
    assert row["rank_score"] == 8.0
    assert row["priority"] is True


def test_a_pasted_video_that_turned_out_ordinary_is_reported_not_dropped():
    """"It measured 0.2x" is the answer to the question they asked by pasting it."""
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("pasted", 1_000, priority=True)]

    (found,) = [item for item in find_outliers(videos, now=NOW) if item.priority]

    assert found.multiple == pytest.approx(0.2)
    assert found.band == "normal"
    assert "you pasted this one" in found.notes[0]
    assert "under the 3x" in found.notes[0]


def test_a_pasted_video_from_a_channel_that_was_not_fetched_says_what_it_borrowed():
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("stranger", 20_000, channel="Someone Else", priority=True)]

    (found,) = [item for item in find_outliers(videos, now=NOW) if item.priority]

    assert found.reliable is False
    assert any("not in this fetch" in note for note in found.notes)
    assert any("add its channel" in note for note in found.notes)


def test_a_channel_with_a_cohort_of_its_own_never_borrows_one():
    """The fallback must not fire where a real median exists, or two competitors are
    back to sharing one."""
    videos = [*cohort_of("Small", rate_per_day=500),
              *cohort_of("Large", rate_per_day=50_000),
              video("hit", 30_000, channel="Small")]

    (found,) = [item for item in find_outliers(videos, now=NOW)
                if item.video.video_id == "hit"]
    assert found.baseline.median_views_per_day == 500
    assert found.reliable is True
    assert found.notes == []


def test_one_video_from_a_channel_is_not_scored_against_itself():
    """A rate divided by itself is 1.0x, which is how a table holding one video from
    each of twenty channels reports all twenty as precisely average.

    The stray is measured against everything read instead, and the row says so — the
    honest report of a cross-channel comparison is the comparison plus the caveat.
    """
    videos = [*cohort_of("Rival", rate_per_day=500),
              video("stray", 20_000, channel="Someone Else")]

    (found,) = [item for item in find_outliers(videos, now=NOW)
                if item.video.video_id == "stray"]

    assert found.multiple == pytest.approx(4.0)
    assert found.reliable is False
    assert any("across channels, not like for like" in note for note in found.notes)


# ---------------------------------------------------------------- reading video pages


def entry(video_id: str, *, views: int, days_old: float, seconds: int = 700,
          channel: str = "Rival", **extra) -> dict:
    """The fields `yt-dlp --dump-json` fills for one video, trimmed to those read here."""
    published = datetime.now(UTC) - timedelta(days=days_old)
    return {
        "id": video_id, "title": f"video {video_id}", "view_count": views,
        "duration": seconds, "channel": channel, "channel_follower_count": 120_000,
        "like_count": 900, "comment_count": 40,
        "upload_date": published.strftime("%Y%m%d"),
        "timestamp": int(published.timestamp()),
        **extra,
    }


def listing(channel: str, *entries: dict) -> dict:
    return {"_type": "playlist", "channel": channel, "uploader": channel,
            "channel_follower_count": 120_000, "entries": list(entries)}


def done(stdout: str = "", *, code: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(["yt-dlp"], code, stdout, stderr)


@pytest.fixture
def yt_dlp(monkeypatch):
    """Stand in for the binary, answering per channel and per video as the real one does.

    One stub rather than one canned reply, because the whole feature is several reads in
    one fetch: a stub that answers everything identically cannot tell a test that read
    three channels from one that read the first channel three times.
    """
    state = {"channels": {}, "videos": {}, "calls": []}

    def fake(command: list[str]):
        state["calls"].append(command)
        if "--dump-json" in command:
            lines, errors = [], []
            for argument in command:
                if "watch?v=" not in argument:
                    continue
                video_id = argument.split("watch?v=")[1]
                found = state["videos"].get(video_id)
                if found is None:
                    errors.append(f"ERROR: [youtube] {video_id}: Video unavailable")
                else:
                    lines.append(json.dumps(found))
            # yt-dlp exits non-zero under --ignore-errors when any link failed, while
            # still printing the ones that worked.
            return done("\n".join(lines), code=1 if errors else 0,
                        stderr="\n".join(errors))

        url = command[-1]
        for fragment, payload in state["channels"].items():
            if fragment.lower() in url.lower():
                return done(json.dumps(payload))
        return done(code=1, stderr=f"ERROR: [youtube:tab] {url}: channel does not exist")

    monkeypatch.setattr(keyless, "_executable", lambda: "/usr/bin/yt-dlp")
    monkeypatch.setattr(keyless, "_run", fake)
    return state


def test_pasted_videos_are_read_from_their_own_pages(yt_dlp):
    yt_dlp["videos"] = {"aaaaaaaaaaa": entry("aaaaaaaaaaa", views=40_000, days_old=10),
                        "bbbbbbbbbbb": entry("bbbbbbbbbbb", views=9_000, days_old=20)}

    parsed = keyless.video_stats(["aaaaaaaaaaa", "bbbbbbbbbbb"])

    assert [stat.video_id for stat in parsed.videos] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert parsed.videos[0].views == 40_000
    assert parsed.videos[0].channel == "Rival"
    assert parsed.videos[0].likes == 900
    assert parsed.skipped == []


def test_a_date_off_a_video_page_carries_no_range(yt_dlp):
    """A ±15-day band belongs to dates reconstructed from "2 months ago". Attaching it
    to a date the page states would flag solid multiples until nobody reads the flag."""
    yt_dlp["videos"] = {"aaaaaaaaaaa": entry("aaaaaaaaaaa", views=1_000, days_old=10)}
    parsed = keyless.video_stats(["aaaaaaaaaaa"])
    assert parsed.videos[0].date_is_approximate is False


def test_a_premiere_is_dated_from_when_it_went_live(yt_dlp):
    """`upload_date` for a scheduled video is when it was queued, and a week of age it
    never had is a week the denominator of every score here is wrong by."""
    live = datetime.now(UTC) - timedelta(days=3)
    yt_dlp["videos"] = {"aaaaaaaaaaa": entry(
        "aaaaaaaaaaa", views=1_000, days_old=10,
        release_timestamp=int(live.timestamp()),
    )}
    parsed = keyless.video_stats(["aaaaaaaaaaa"])
    assert abs(parsed.videos[0].age_days() - 3) < 0.1


def test_the_whole_paste_is_one_process(yt_dlp):
    """A process launch and a TLS handshake per link is how five links take long enough
    that the page reads as hung."""
    yt_dlp["videos"] = {f"{letter * 11}": entry(letter * 11, views=1_000, days_old=10)
                        for letter in "abcde"}
    keyless.video_stats([letter * 11 for letter in "abcde"])
    assert len(yt_dlp["calls"]) == 1


def test_the_playlist_behind_a_sidebar_link_is_not_read(yt_dlp):
    """A watch URL copied from the sidebar carries `&list=`, which without --no-playlist
    reads 200 videos where one was asked for."""
    yt_dlp["videos"] = {"aaaaaaaaaaa": entry("aaaaaaaaaaa", views=1_000, days_old=10)}
    keyless.video_stats(["aaaaaaaaaaa"])
    assert "--no-playlist" in yt_dlp["calls"][0]
    assert "--ignore-errors" in yt_dlp["calls"][0]


def test_one_dead_link_does_not_cost_the_others(yt_dlp):
    yt_dlp["videos"] = {"aaaaaaaaaaa": entry("aaaaaaaaaaa", views=1_000, days_old=10)}

    parsed = keyless.video_stats(["aaaaaaaaaaa", "zzzzzzzzzzz"])

    assert [stat.video_id for stat in parsed.videos] == ["aaaaaaaaaaa"]
    assert parsed.skipped == ["zzzzzzzzzzz: ERROR: [youtube] zzzzzzzzzzz: Video unavailable"]


def test_a_batch_that_read_nothing_at_all_is_an_error(yt_dlp):
    with pytest.raises(keyless.KeylessError) as caught:
        keyless.video_stats(["zzzzzzzzzzz"])
    assert "Video unavailable" in str(caught.value)


# ------------------------------------------------------------------- the whole fetch


@pytest.fixture
def desk(yt_dlp):
    """Two channels and two loose videos, one of which is also in a channel's listing."""
    yt_dlp["channels"] = {
        "@small": listing("Small", *[
            entry(f"small{i:06d}", views=5_000, days_old=10) | {"channel": "Small"}
            for i in range(6)
        ], entry("smallhit000", views=30_000, days_old=10) | {"channel": "Small"}),
        "@large": listing("Large", *[
            entry(f"large{i:06d}", views=500_000, days_old=10) | {"channel": "Large"}
            for i in range(6)
        ]),
    }
    yt_dlp["videos"] = {
        "pasted00000": entry("pasted00000", views=20_000, days_old=10, channel="Small"),
        "smallhit000": entry("smallhit000", views=30_000, days_old=10, channel="Small"),
    }
    return yt_dlp


def test_one_fetch_reads_every_channel_it_was_given(desk):
    readout = sources.read_desk("@small\n@large", "")

    assert [row.name for row in readout.channels] == ["Small", "Large"]
    assert [row.count for row in readout.channels] == [7, 6]
    assert len(readout.videos) == 13


def test_a_channel_that_cannot_be_read_does_not_cost_the_others(desk):
    readout = sources.read_desk("@small, @ghost, @large", "")

    assert [row.name or row.reference for row in readout.channels] == [
        "Small", "@ghost", "Large"
    ]
    assert "does not exist" in readout.channels[1].error
    assert readout.channels[1].count == 0
    assert len(readout.videos) == 13


def test_channels_past_the_limit_are_reported_rather_than_dropped(desk):
    """A competitor that silently never got fetched is a comparison the operator
    believes they made."""
    references = "\n".join(f"@handle{i}" for i in range(sources.MAX_CHANNELS + 2))
    readout = sources.read_desk(references, "")

    assert len(readout.channels) == sources.MAX_CHANNELS + 2
    assert all("not read: one fetch takes" in row.error
               for row in readout.channels[sources.MAX_CHANNELS:])
    # And nothing past the limit was actually fetched.
    assert len(desk["calls"]) == sources.MAX_CHANNELS


def test_pasted_videos_come_back_flagged_and_listed_by_name(desk):
    readout = sources.read_desk("@small", "https://youtu.be/pasted00000")

    assert [row.video_id for row in readout.priority] == ["pasted00000"]
    assert readout.priority[0].title == "video pasted00000"
    assert readout.priority[0].channel == "Small"
    assert readout.priority[0].error == ""

    flagged = [stat for stat in readout.videos if stat.is_priority]
    assert [stat.video_id for stat in flagged] == ["pasted00000"]


def test_a_pasted_video_that_is_also_in_the_listing_is_counted_once(desk):
    """Both copies in the pool would put the operator's own pick into the median it is
    being measured against — the unflagged one sets the bar the flagged one has to
    clear."""
    readout = sources.read_desk("@small", "https://youtu.be/smallhit000")

    copies = [stat for stat in readout.videos if stat.video_id == "smallhit000"]
    assert len(copies) == 1
    assert copies[0].is_priority is True
    assert len(readout.videos) == 7


def test_a_link_that_is_not_a_video_gets_its_own_row_with_the_reason(desk):
    readout = sources.read_desk("@small", "https://www.youtube.com/@large\nnonsense")

    assert [row.reference for row in readout.priority] == [
        "https://www.youtube.com/@large", "nonsense"
    ]
    assert "channels box" in readout.priority[0].error
    assert "could not tell" in readout.priority[1].error
    assert not [stat for stat in readout.videos if stat.is_priority]


def test_the_rows_come_back_in_the_order_they_were_pasted(desk):
    """They are read against the box they were typed into, so the fourth line of the
    box has to be the fourth row of the report."""
    readout = sources.read_desk("@small", "\n".join([
        "https://youtu.be/pasted00000",
        "nonsense",
        "https://youtu.be/zzzzzzzzzzz",
        "https://youtu.be/smallhit000",
    ]))

    assert [row.video_id for row in readout.priority] == [
        "pasted00000", "", "zzzzzzzzzzz", "smallhit000"
    ]


def test_a_video_that_could_not_be_read_still_gets_a_row(desk):
    readout = sources.read_desk("@small", "https://youtu.be/zzzzzzzzzzz")

    assert readout.priority[0].video_id == "zzzzzzzzzzz"
    assert "Video unavailable" in readout.priority[0].error


def test_the_source_note_says_both_sources_once_each(desk):
    readout = sources.read_desk("@small\n@large", "https://youtu.be/pasted00000")

    assert readout.via.count("no API key needed") == 2
    assert "reconstructed from relative labels" in readout.via
    assert "rather than reconstructed" in readout.via


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


def test_the_desk_scores_two_channels_against_their_own_medians(client, desk):
    answer = client.post("/api/research/score", json={"channel": "@small\n@large"})

    assert answer.status_code == 200
    body = answer.json()
    assert body["count"] == 13
    assert [row["name"] for row in body["channels"]] == ["Small", "Large"]
    # Approximate only because this path scores against the wall clock, so the ages are
    # ten days and a few milliseconds. The multiple below is exact regardless: the drift
    # is in both the rate and the median it is divided by.
    small = body["channel_baselines"]["Small"]["long"]["median_views_per_day"]
    large = body["channel_baselines"]["Large"]["long"]["median_views_per_day"]
    assert small == pytest.approx(500, rel=1e-3)
    assert large == pytest.approx(50_000, rel=1e-3)
    # Small's hit is 6x its own median, and invisible against a pooled one.
    assert [row["video_id"] for row in body["outliers"]] == ["smallhit000"]
    assert body["outliers"][0]["multiple"] == 6.0


def test_the_answer_says_the_pasted_videos_were_fetched(client, desk):
    answer = client.post("/api/research/score", json={
        "channel": "@small", "videos": "https://youtu.be/pasted00000",
    })

    body = answer.json()
    (row,) = body["priority"]
    assert row["fetched"] is True
    assert row["scored"] is True
    assert row["title"] == "video pasted00000"
    assert row["multiple"] == 4.0
    assert body["summary"]["priority"] == 1
    # And it is marked on its row in the table as well as in the receipt above it.
    pasted = [item for item in body["outliers"] if item["priority"]]
    assert [item["video_id"] for item in pasted] == ["pasted00000"]


def test_a_pasted_video_ranks_above_the_channels_own_at_a_lower_multiple(client, desk):
    answer = client.post("/api/research/score", json={
        "channel": "@small", "videos": "https://youtu.be/pasted00000",
    })

    body = answer.json()
    assert [item["video_id"] for item in body["outliers"]] == [
        "pasted00000", "smallhit000"
    ]
    assert body["outliers"][0]["multiple"] == 4.0
    assert body["outliers"][1]["multiple"] == 6.0


def test_a_pasted_video_that_could_not_be_read_is_still_on_screen(client, desk):
    answer = client.post("/api/research/score", json={
        "channel": "@small", "videos": "https://youtu.be/zzzzzzzzzzz",
    })

    body = answer.json()
    assert answer.status_code == 200
    (row,) = body["priority"]
    assert row["fetched"] is False
    assert "Video unavailable" in row["error"]


def test_a_pasted_video_too_new_to_score_says_that_rather_than_vanishing(client, desk):
    desk["videos"]["freshest000"] = entry("freshest000", views=90_000, days_old=0.5,
                                          channel="Small")
    answer = client.post("/api/research/score", json={
        "channel": "@small", "videos": "https://youtu.be/freshest000",
    })

    body = answer.json()
    (row,) = body["priority"]
    assert row["fetched"] is True
    assert row["scored"] is False
    assert "notification push" in row["why"]
    assert not [item for item in body["outliers"] if item["priority"]]


def test_videos_with_no_channel_to_measure_them_against_are_refused_with_the_layout(
    client, desk
):
    answer = client.post("/api/research/score",
                         json={"videos": "https://youtu.be/pasted00000"})

    assert answer.status_code == 400
    assert "top box" in answer.json()["detail"]


def test_a_blob_of_links_in_the_paste_box_goes_to_the_right_boxes(client, desk):
    """Someone will paste everything into the biggest box on the page."""
    answer = client.post("/api/research/score", json={
        "pasted": "https://www.youtube.com/@small\nhttps://youtu.be/pasted00000",
    })

    body = answer.json()
    assert [row["name"] for row in body["channels"]] == ["Small"]
    assert [row["video_id"] for row in body["priority"]] == ["pasted00000"]


def test_a_table_with_a_url_column_is_still_a_table(client, desk):
    """One unrecognised token hands the whole blob back to the table parser — otherwise
    a spreadsheet paste is read as links and every row but the URLs is lost."""
    answer = client.post("/api/research/score", json={"pasted":
        "url,title,views,published\n"
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ,A video,1000,2026-01-01\n"
    })

    body = answer.json()
    assert body["channels"] == []
    assert body["priority"] == []
    assert body["count"] == 1


def test_the_page_offers_a_videos_box_under_the_channels_box(client, desk):
    page = client.get("/research")

    assert page.status_code == 200
    assert page.text.index('id="channel"') < page.text.index('id="videos"')
    box = page.text.split('id="videos"', 1)[1][:200]
    assert "disabled" not in box


def test_the_videos_box_is_gated_by_the_same_thing_the_channels_box_is(client, monkeypatch):
    """Nothing that can read a channel page cannot read a video page, and vice versa."""
    monkeypatch.setattr(keyless, "_executable", lambda: None)

    page = client.get("/research")
    assert "disabled" in page.text.split('id="videos"', 1)[1][:200]
