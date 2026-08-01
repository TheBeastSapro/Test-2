"""Outlier scoring, tested against constructed distributions.

Every fixture here has a known answer: the videos are built so that the correct
multiple can be worked out by hand, which is the only way to tell a scoring bug from a
scoring opinion. Four of these are regressions for the specific ways a naive
`views / median` gets the answer wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from forgecast.research.outliers import (
    Candidate,
    VideoStat,
    band_for,
    baselines,
    find_outliers,
    rank,
    summarise,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def video(video_id: str, views: int, *, days_old: float, seconds: float = 600.0,
          **extra) -> VideoStat:
    return VideoStat(
        video_id=video_id,
        title=extra.pop("title", f"video {video_id}"),
        views=views,
        published_at=NOW - timedelta(days=days_old),
        duration_seconds=seconds,
        **extra,
    )


# --------------------------------------------------------------------- basics


def test_views_per_day_normalises_age():
    old = video("a", 36_500, days_old=100)
    fresh = video("b", 3_650, days_old=10)
    assert old.views_per_day(NOW) == 365.0
    assert fresh.views_per_day(NOW) == 365.0


def test_a_video_hours_old_does_not_report_millions_per_day():
    """Dividing by a fraction of a day is how a naive rate becomes nonsense."""
    minutes_old = video("a", 5_000, days_old=0.02)
    assert minutes_old.views_per_day(NOW) == 5_000


def test_duration_decides_the_cohort():
    assert video("a", 1, days_old=10, seconds=45).cohort == "short"
    assert video("b", 1, days_old=10, seconds=61).cohort == "long"


def test_bands():
    assert band_for(1.0) == "normal"
    assert band_for(3.0) == "soft"
    assert band_for(5.0) == "clear"
    assert band_for(25.0) == "strong"


# ----------------------------------------------------- correction 1: age


def test_an_old_video_is_not_an_outlier_just_for_being_old():
    """Regression: total views rewards survival, not performance.

    The old video has 10x the views of every other, and exactly the same rate.
    """
    videos = [video("old", 100_000, days_old=200)]
    videos += [video(f"n{i}", 5_000, days_old=10) for i in range(6)]

    found = find_outliers(videos, now=NOW)
    assert [item.video.video_id for item in found] == []


def test_a_genuine_outlier_is_still_found_after_age_normalisation():
    videos = [video(f"n{i}", 5_000, days_old=10) for i in range(6)]
    videos.append(video("hit", 40_000, days_old=10))

    found = find_outliers(videos, now=NOW)
    assert len(found) == 1
    assert found[0].video.video_id == "hit"
    assert found[0].multiple == 8.0
    assert found[0].band == "clear"


# -------------------------------------------------- correction 2: cohort


def test_shorts_and_long_form_are_scored_separately():
    """Regression: mixing formats makes every Short look like a triumph."""
    longform = [video(f"l{i}", 5_000, days_old=10, seconds=600) for i in range(6)]
    shorts = [video(f"s{i}", 50_000, days_old=10, seconds=30) for i in range(6)]

    found = find_outliers(longform + shorts, now=NOW)
    # Every Short has 10x the views of every long-form video, and none of them is an
    # outlier — they are simply Shorts.
    assert found == []

    bases = baselines(longform + shorts, now=NOW)
    assert bases["short"].median_views_per_day == 5_000
    assert bases["long"].median_views_per_day == 500


def test_a_short_is_scored_against_other_shorts():
    shorts = [video(f"s{i}", 50_000, days_old=10, seconds=30) for i in range(6)]
    shorts.append(video("viral", 300_000, days_old=10, seconds=30))
    longform = [video(f"l{i}", 5_000, days_old=10, seconds=600) for i in range(6)]

    found = find_outliers(shorts + longform, now=NOW)
    assert [item.video.video_id for item in found] == ["viral"]
    assert found[0].multiple == 6.0


# --------------------------------------------- correction 3: sample size


def test_a_tiny_cohort_is_reported_as_unreliable_not_scored():
    """A median over three videos is one of the three videos."""
    videos = [video("a", 1_000, days_old=10), video("b", 2_000, days_old=10),
              video("c", 90_000, days_old=10)]

    assert find_outliers(videos, now=NOW) == []

    base = baselines(videos, now=NOW)["long"]
    assert base.reliable is False
    assert "at least" in base.note


def test_an_unreliable_cohort_can_be_asked_for_explicitly_with_a_warning():
    videos = [video("a", 1_000, days_old=10), video("b", 2_000, days_old=10),
              video("c", 90_000, days_old=10)]

    found = find_outliers(videos, now=NOW, include_unreliable=True)
    assert [item.video.video_id for item in found] == ["c"]
    assert found[0].reliable is False
    assert found[0].notes, "an unreliable score must say why"


# --------------------------------------------------- correction 4: youth


def test_a_video_published_yesterday_is_not_scored():
    """Its rate is the subscriber notification push, not the algorithm."""
    videos = [video(f"n{i}", 5_000, days_old=30) for i in range(6)]
    videos.append(video("brand_new", 9_000, days_old=1))

    found = find_outliers(videos, now=NOW)
    assert "brand_new" not in [item.video.video_id for item in found]


def test_a_young_video_does_not_distort_the_baseline_either():
    steady = [video(f"n{i}", 5_000, days_old=30) for i in range(6)]
    spike = [video(f"y{i}", 20_000, days_old=0.5) for i in range(6)]

    base = baselines(steady + spike, now=NOW)["long"]
    # 5000 views over 30 days is 166.7/day. The day-old spikes would drag the median
    # to 20,000/day and hide every real outlier behind it.
    assert base.median_views_per_day < 200
    assert base.sample_size == 6


# ------------------------------------------------------------------- median


def test_the_baseline_uses_a_median_so_one_giant_video_cannot_hide_the_rest():
    """With a mean, a channel's own biggest hit raises the bar past every other."""
    videos = [video(f"n{i}", 5_000, days_old=10) for i in range(6)]
    videos.append(video("monster", 5_000_000, days_old=10))

    base = baselines(videos, now=NOW)["long"]
    assert base.median_views_per_day == 500

    found = find_outliers(videos, now=NOW)
    assert found[0].video.video_id == "monster"
    assert found[0].band == "strong"


# --------------------------------------------------------------- reporting


def test_reach_beyond_the_subscriber_base_is_flagged():
    videos = [video(f"n{i}", 5_000, days_old=10, channel_subscribers=1_000)
              for i in range(6)]
    videos.append(video("recommended", 80_000, days_old=10,
                        channel_subscribers=1_000))

    found = find_outliers(videos, now=NOW)
    assert any("algorithmic" in note for note in found[0].notes)


def test_engagement_rate_is_reported():
    videos = [video(f"n{i}", 5_000, days_old=10) for i in range(6)]
    videos.append(video("hit", 50_000, days_old=10, likes=4_000, comments=1_000))

    found = find_outliers(videos, now=NOW)
    assert found[0].engagement_rate == 0.1


def test_results_are_strongest_first():
    videos = [video(f"n{i}", 5_000, days_old=10) for i in range(6)]
    videos += [video("big", 100_000, days_old=10),
               video("medium", 30_000, days_old=10)]

    found = find_outliers(videos, now=NOW)
    assert [item.video.video_id for item in found] == ["big", "medium"]


def test_summary_counts_bands_and_names_the_strongest():
    videos = [video(f"n{i}", 5_000, days_old=10) for i in range(6)]
    videos += [video("big", 100_000, days_old=10),
               video("medium", 20_000, days_old=10)]

    report = summarise(find_outliers(videos, now=NOW))
    assert report["count"] == 2
    assert report["by_band"] == {"strong": 1, "soft": 1}
    assert report["strongest"]["video_id"] == "big"


def test_an_empty_input_is_an_empty_result_not_a_crash():
    assert find_outliers([], now=NOW) == []
    assert summarise([])["count"] == 0


def test_a_channel_with_no_outliers_says_so():
    videos = [video(f"n{i}", 5_000 + i * 50, days_old=10) for i in range(8)]
    assert find_outliers(videos, now=NOW) == []


# ---------------------------------------------------------------- ranking


def test_feasibility_multiplies_rather_than_offsets():
    """An idea the channel cannot execute is worth nothing, not "a lot, minus a bit"."""
    brilliant_impossible = Candidate("A", outlier_multiple=10, confidence=0.7,
                                     feasibility=0.05, rpm=8, production_credits=100)
    modest_shippable = Candidate("B", outlier_multiple=3, confidence=0.6,
                                 feasibility=1.0, rpm=8, production_credits=100)
    assert rank([brilliant_impossible, modest_shippable])[0].topic == "B"


def test_cost_is_divided_out_so_cheap_ideas_win_ties():
    expensive = Candidate("A", outlier_multiple=5, confidence=0.6, rpm=5,
                          production_credits=900)
    cheap = Candidate("B", outlier_multiple=5, confidence=0.6, rpm=5,
                      production_credits=100)
    assert rank([expensive, cheap])[0].topic == "B"


def test_a_zero_cost_candidate_does_not_divide_by_zero():
    free = Candidate("A", outlier_multiple=4, production_credits=0)
    assert free.score() > 0


def test_rpm_moves_the_ranking():
    finance = Candidate("A", outlier_multiple=3, confidence=0.6, rpm=20,
                        production_credits=200)
    vlog = Candidate("B", outlier_multiple=3, confidence=0.6, rpm=2,
                     production_credits=200)
    assert rank([finance, vlog])[0].topic == "A"


def test_rank_can_be_limited():
    candidates = [Candidate(f"c{i}", outlier_multiple=float(i)) for i in range(10)]
    assert len(rank(candidates, limit=3)) == 3


def test_candidates_serialise_with_their_score():
    payload = Candidate("A", outlier_multiple=4, confidence=0.5).as_dict()
    assert payload["score"] > 0
    assert payload["topic"] == "A"
