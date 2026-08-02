"""Reading statistics from whatever the operator has, and reading the model's reply.

The parser is deliberately permissive, which is exactly the kind of code that quietly
accepts something and produces a wrong number. So every accepted format is asserted
against a known value, and the cases it must *refuse* — a row with no views, a row with
no date — are asserted too. A parser that guesses a missing number is worse than one
that rejects the row, because the guess is invisible downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forgecast.research import sources
from forgecast.research.outliers import find_outliers
from forgecast.research.titles import MAX_TITLE_CHARS, parse_ideas

NOW = datetime(2026, 8, 1, tzinfo=UTC)


# ------------------------------------------------------------------ field parsing


@pytest.mark.parametrize("text,expected", [
    ("1240000", 1_240_000),
    ("1,240,000", 1_240_000),
    ("1.2M", 1_200_000),
    ("3.4K views", 3_400),
    ("2B", 2_000_000_000),
    (240000, 240_000),
    ("", None),
    (None, None),
])
def test_view_counts(text, expected):
    assert sources.parse_count(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("PT10M12S", 612.0),
    ("PT1H2M11S", 3731.0),
    ("PT45S", 45.0),
    ("4:13", 253.0),
    ("1:02:11", 3731.0),
    (612, 612.0),
    ("", 0.0),
    ("garbage", 0.0),
])
def test_durations(text, expected):
    assert sources.parse_duration(text) == expected


def test_an_unknown_duration_scores_as_long_form():
    """The conservative direction: an unknown duration must not let a video be scored
    against the Shorts baseline, where a modest number looks like a triumph."""
    assert sources.parse_duration(None) == 0.0
    stat = sources.parse("title,views,published\nX,100,2026-01-01\n").videos[0]
    assert stat.cohort == "long"


@pytest.mark.parametrize("text,days_ago", [
    ("3 weeks ago", 21),
    ("2 days ago", 2),
    ("1 year ago", 365),
])
def test_relative_dates(text, days_ago):
    parsed = sources.parse_date(text, now=NOW)
    assert abs((NOW - parsed).days - days_ago) <= 1


@pytest.mark.parametrize("text", [
    "2026-05-02", "2026-05-02T14:30:00Z", "02/05/2026", "2 May 2026", "May 2, 2026",
])
def test_absolute_dates(text):
    parsed = sources.parse_date(text)
    assert parsed is not None and parsed.year == 2026


def test_a_watch_url_yields_its_video_id():
    result = sources.parse(
        "url,title,views,published\n"
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ,A video,1000,2026-01-01\n"
    )
    assert result.videos[0].video_id == "dQw4w9WgXcQ"


# ------------------------------------------------------------------ table parsing


def test_csv():
    result = sources.parse(
        "title,views,published,duration\n"
        "First,1.2M,2026-05-02,PT10M12S\n"
        "Second,240K,2026-06-01,PT45S\n"
    )
    assert [v.views for v in result.videos] == [1_200_000, 240_000]
    assert [v.cohort for v in result.videos] == ["long", "short"]
    assert result.skipped == []


def test_a_spreadsheet_paste_is_tab_separated():
    result = sources.parse("Title\tViews\tPublished\nFirst\t1000\t2026-05-02\n")
    assert result.videos[0].title == "First"


def test_column_names_are_matched_loosely():
    """viewCount / plays / Video Title all mean the same thing to a person."""
    result = sources.parse(
        "Video Title,viewCount,publishedAt,lengthSeconds\nX,5000,2026-05-02,300\n"
    )
    video = result.videos[0]
    assert video.title == "X" and video.views == 5000 and video.duration_seconds == 300


def test_json_arrays_and_wrapped_arrays():
    flat = sources.parse('[{"title":"A","views":100,"publishedAt":"2026-05-02"}]')
    wrapped = sources.parse('{"items":[{"title":"A","views":100,"publishedAt":"2026-05-02"}]}')
    assert len(flat.videos) == len(wrapped.videos) == 1


def test_youtube_api_shaped_json_is_flattened():
    """The API nests everything one level down; the alias table has to still see it."""
    result = sources.parse("""[{
      "id": "abc123",
      "snippet": {"title": "Nested", "publishedAt": "2026-05-02T00:00:00Z"},
      "statistics": {"viewCount": "12000", "likeCount": "300"},
      "contentDetails": {"duration": "PT8M"}
    }]""")
    video = result.videos[0]
    assert video.title == "Nested"
    assert video.views == 12_000
    assert video.likes == 300
    assert video.duration_seconds == 480


# ---------------------------------------------------------------- what it refuses


def test_a_row_with_no_views_is_skipped_with_a_reason():
    result = sources.parse("title,views,published\nMissing numbers,,2026-05-02\n")
    assert result.videos == []
    assert "no view count" in result.skipped[0]
    assert "Missing numbers" in result.skipped[0]


def test_a_row_with_no_date_is_skipped():
    """Without a date there is no age, and without age every score is meaningless."""
    result = sources.parse("title,views,published\nNo date,5000,\n")
    assert result.videos == []
    assert "no publish date" in result.skipped[0]


def test_good_rows_survive_bad_ones():
    result = sources.parse(
        "title,views,published\nGood,5000,2026-05-02\nBad,,2026-05-02\nAlso good,7000,2026-05-03\n"
    )
    assert len(result.videos) == 2
    assert len(result.skipped) == 1


def test_empty_input_is_an_empty_result():
    assert sources.parse("").videos == []
    assert sources.parse("   ").videos == []


def test_malformed_json_raises_rather_than_silently_returning_nothing():
    with pytest.raises(ValueError):
        sources.parse('[{"title": "unterminated')


# ------------------------------------------------------- parser feeding the scorer


def test_a_paste_scores_to_the_multiple_worked_out_by_hand():
    """End to end on constructed data: six at 5,000 views over 10 days is a 500/day
    median, and 40,000 over 10 days is 4,000/day — exactly 8x."""
    published = (NOW - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
    rows = ["title,views,published,duration"]
    rows += [f"Ordinary {i},5000,{published},PT10M" for i in range(6)]
    rows.append(f"The one that worked,40000,{published},PT10M")

    result = sources.parse("\n".join(rows))
    found = find_outliers(result.videos, now=NOW)

    assert len(found) == 1
    assert found[0].video.title == "The one that worked"
    assert found[0].multiple == pytest.approx(8.0, abs=0.01)


# -------------------------------------------------------------------- title ideas


def test_ideas_are_read_out_of_a_plain_json_reply():
    payload = parse_ideas("""{
      "mechanism": "A number that reframes something familiar.",
      "transferable": ["the reframe", "the specificity"],
      "avoid": ["the news peg"],
      "ideas": [{"angle": "cost of a thing", "title": "The real cost", "why": "same reframe"}]
    }""")
    assert payload["mechanism"].startswith("A number")
    assert payload["transferable"] == ["the reframe", "the specificity"]
    assert payload["ideas"][0]["title"] == "The real cost"
    assert payload["ideas"][0]["too_long"] is False


def test_a_fenced_reply_is_still_read():
    """Models wrap JSON in code fences often enough that failing on it would make the
    feature unreliable for no reason."""
    payload = parse_ideas('Here you go:\n```json\n{"mechanism":"x","ideas":[]}\n```')
    assert payload["mechanism"] == "x"


def test_a_long_title_is_flagged_not_truncated():
    """Cutting a title mid-word is worse than showing it and saying it is long."""
    long_title = "T" * (MAX_TITLE_CHARS + 10)
    payload = parse_ideas(f'{{"ideas":[{{"title":"{long_title}"}}]}}')
    assert payload["ideas"][0]["title"] == long_title
    assert payload["ideas"][0]["too_long"] is True


def test_ideas_without_a_title_are_dropped():
    payload = parse_ideas('{"ideas":[{"angle":"no title here"},{"title":"Real one"}]}')
    assert [item["title"] for item in payload["ideas"]] == ["Real one"]


def test_a_non_json_reply_reports_itself_rather_than_showing_a_blank_panel():
    payload = parse_ideas("I'm sorry, I can't help with that.")
    assert payload["ideas"] == []
    assert payload["error"]
    assert "sorry" in payload["raw"]


def test_a_string_where_a_list_was_expected_is_tolerated():
    payload = parse_ideas('{"transferable":"just the one thing","ideas":[]}')
    assert payload["transferable"] == ["just the one thing"]
