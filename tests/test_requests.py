"""What the audience asked for, read out of a channel's own comments.

Measured, not assumed. The reference ends every video with "tell me in the comments
which creature or horror topic you want to see in the next video", its comments answer
by name, and two of the names they answer with are already published videos. That is the
channel's topic backlog and the cheapest research it does.

Nothing in this app read comment text — `research/outliers.py` reads comment counts for
an engagement ratio, and that is all.

Every comment below is real, taken verbatim from the reference's videos this session.
"""

from __future__ import annotations

from forgecast.research.requests import MIN_MENTIONS, read

REAL = [
    {"textDisplay": "An explanation of some of the biggest SCPs would be awesome!! "
                    "My son would love that :)", "likesCount": "4"},
    {"textDisplay": "can you do the biggest SCPs next", "likesCount": "2"},
    {"textDisplay": "I wanna see the Bolid One", "likesCount": "7"},
    {"textDisplay": "Please make us see the Anchorage on your next video", "likesCount": "1"},
    {"textDisplay": "can you do the anchorage next pls", "likesCount": "3"},
    {"textDisplay": "PLEASE DO SIRENHEAD", "likesCount": "12"},
    {"textDisplay": "please do sirenhead next", "likesCount": "5"},
    {"textDisplay": "2:46 cameraman never dies", "likesCount": "2"},
    {"textDisplay": "Bloodbath Godzilla is so creepy 😱", "likesCount": "2"},
]


def _subjects(backlog):
    return [item.subject for item in backlog.requests]


def test_two_phrasings_of_one_request_tally_together():
    """The whole value. "Please make us see the Anchorage on your next video" and "can
    you do the anchorage next pls" are one request — and with a thinner filler list they
    came out as "see the anchorage on your next" and "anchorage", one mention each,
    which is below the threshold, so the most-asked thing on the video reported as
    nothing at all."""
    assert "anchorage" in _subjects(read(REAL))


def test_the_polite_noun_form_is_caught_too():
    """"An explanation of the biggest SCPs would be awesome" is a request, and every
    verb pattern misses it."""
    assert "biggest scps" in _subjects(read(REAL))


def test_likes_are_summed_across_the_phrasings():
    backlog = read(REAL)
    sirenhead = next(item for item in backlog.requests if item.subject == "sirenhead")

    assert sirenhead.mentions == 2
    assert sirenhead.likes == 17


def test_ordinary_comments_are_not_requests():
    """A timestamp joke and "that's creepy" are not asks, and a pattern loose enough to
    catch them turns every mention of a creature into a demand."""
    assert not read([{"textDisplay": "2:46 cameraman never dies"},
                     {"textDisplay": "Bloodbath Godzilla is so creepy"},
                     {"textDisplay": "this is my favourite monster 3:40"}]).requests


def test_one_person_asking_once_is_noise():
    """Below the threshold a request is one viewer, and reporting it as a signal is how
    a backlog fills with things nobody wants."""
    backlog = read([{"textDisplay": "please do the Bolid One"}])

    assert backlog.with_a_request == 1
    assert backlog.requests == []
    assert MIN_MENTIONS >= 2


def test_findings_carry_the_comment_they_came_from():
    """Counts with no source are a summary nobody can check, which is the thing this
    counts instead of asking a model for."""
    backlog = read(REAL)

    for item in backlog.requests:
        assert item.examples
        assert item.subject.split()[0] in item.examples[0].lower()


def test_comments_may_be_dicts_or_strings_from_either_source():
    """The two things that can supply comments name their fields differently, and a
    reader that understood one of them would be a reader with one caller."""
    assert _subjects(read(["please do sirenhead", "can you do sirenhead"])) == ["sirenhead"]
    assert _subjects(read([{"text": "please do sirenhead", "likes": 3},
                           {"text": "can you do sirenhead"}])) == ["sirenhead"]


def test_a_missing_like_count_does_not_break_the_tally():
    """The live API returns " " rather than 0 for an unliked comment."""
    backlog = read([{"textDisplay": "please do sirenhead", "likesCount": " "},
                    {"textDisplay": "can you do sirenhead", "likesCount": ""}])

    assert backlog.requests[0].mentions == 2
    assert backlog.requests[0].likes == 0


def test_it_counts_and_never_decides():
    backlog = read(REAL)

    assert "asked for" in backlog.as_text()
    # No ranking, scoring or recommendation anywhere in the shape.
    assert not any(key in backlog.as_dict() for key in ("recommended", "score", "best"))


def test_the_miner_is_reachable_as_an_agent_tool():
    from forgecast.agent import tools

    assert "audience_requests" in tools.ALL_TOOLS
    assert "audience_requests" in tools._READ_ONLY


def test_it_says_it_does_not_fetch():
    """A fifth thing in this app that shells out to yt-dlp would be a fourth copy of the
    same subprocess call, so this takes the comments rather than getting them — and has
    to say so, or it will be called with nothing and look broken."""
    from forgecast.agent.studio import Studio

    answer = Studio.audience_requests(object(), [])
    assert "error" in answer
    assert "does not fetch" in answer["error"]
