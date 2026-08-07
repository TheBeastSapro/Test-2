"""Reading a fandom wiki as the structure a segment is made of.

The reference channel this was built against does not generate the thing its videos are
about — it fetches it. Each segment is one creature's wiki page: the page's image is the
shot, its infobox is the stat card, and its Appearance / Behaviour / How to Survive
sections are the three narration beats. "How to Survive" is a wiki heading.

Every fixture below is real wikitext, trimmed. Both failures these tests pin were found
by running the module against a *second* wiki after it worked on the first — the exact
failure this codebase has already recorded as its most expensive habit.
"""

from __future__ import annotations

from forgecast.research import fandom

# doctor-nowhere-creatures.fandom.com/wiki/Amber — the page the reference's first
# segment is built from, infobox and all three beats.
AMBER = """{{Character|
name=Amber|
image=Amber111.png|
species=Unknown|
height=Around 13 to 33 feet|
weight=Approximately 456 lbs (206 kg)|
hazardtype=Emergency Alert}}

'''Amber''' is a creature by [[Doctor Nowhere]].

==Appearance==
'''Amber''' appears to be a vaguely humanoid creature with a reddish-brown skin tone,
long fingers strong enough to break glass. No discernible head is present.

==Behaviour==
'''Amber''' has been seen galloping along rooftops at night, normally between fall and
winter. A young man in ''Tennessee'' reported watching Amber break its hand through the
window of his neighbor's home.

==How to Survive==
#Stay indoors during the night.
#Secure your home, board up windows.
"""

# trevorhenderson.fandom.com/wiki/Watchtower — a maintenance banner sits *above* the
# infobox, and the height field is named `height_size`.
WATCHTOWER = """{{ToBeRedone}}{{Cryptid-Infobox
|Box title = Watchtower
|image = Watchtower.jpg
|alias = Our protector<br>
Giantess
|height_size = 1.5 kilometers
|species = Mammalian Deity}}

==Appearance==
A colossal humanoid figure standing over the treeline.

==Behavior and Origin==
It has been sighted standing motionless for hours.
"""


def test_the_infobox_survives_a_maintenance_banner_above_it():
    """`{{ToBeRedone}}{{Cryptid-Infobox|...}}` is real. Taking the first template found
    returned an empty dict for every page a wiki had flagged for cleanup — which on an
    active wiki is a lot of them."""
    fields = fandom.parse_infobox(WATCHTOWER)

    assert fields.get("image") == "Watchtower.jpg"
    assert fields.get("height_size") == "1.5 kilometers"


def test_a_banner_with_no_fields_is_not_mistaken_for_an_infobox():
    assert fandom.parse_infobox("{{Stub}}{{Cleanup}}") == {}


def test_a_named_infobox_wins_over_an_earlier_template_that_has_fields():
    """Order alone is not enough — some pages open with a quote box that does carry
    fields. The template whose name says infobox is the one that is one."""
    text = "{{Quote|text=Run.|source=A witness}}{{Creature-Infobox|image=X.png|height=9 m}}"

    assert fandom.parse_infobox(text).get("image") == "X.png"


def test_stat_keys_match_by_prefix_when_the_wiki_renamed_the_field():
    """One wiki says `height`, the next says `height_size`. An exact-only lookup found
    the height on the wiki it was written against and nothing on the next one."""
    assert fandom.stats_from({"height_size": "1.5 kilometers"})["height"] == "1.5 kilometers"
    assert fandom.stats_from({"height": "23 m"})["height"] == "23 m"


def test_an_exact_key_beats_a_prefix_match():
    stats = fandom.stats_from({"height_estimate": "guess", "height": "23 m"})

    assert stats["height"] == "23 m"


def test_the_image_is_taken_from_whichever_image_key_the_wiki_used():
    assert fandom.image_name_from({"image1": "Thing.png"}) == "Thing.png"
    assert fandom.image_name_from({"img": "Thing.jpg"}) == "Thing.jpg"


def test_a_caption_in_an_image_field_is_not_mistaken_for_a_filename():
    """These fields hold captions and gallery blocks as often as filenames, and asking
    the file API about a sentence returns nothing while looking like the page had no
    art — an absence that reads as a stub rather than as a parse failure."""
    assert fandom.image_name_from({"image1": "What are they?"}) == ""
    assert fandom.image_name_from({"image1": ""}) == ""
    assert fandom.image_name_from({"image1": "a.png\nb.png\nc.png"}) == ""


def test_the_three_beats_come_off_the_section_headings():
    beats = fandom.beats_from(fandom.parse_sections(AMBER))

    assert set(beats) == {"appearance", "behaviour", "survival"}
    assert "reddish-brown" in beats["appearance"]
    assert "Tennessee" in beats["behaviour"]
    # The numbered list reads as prose, not as `#`-prefixed lines.
    assert beats["survival"].startswith("Stay indoors")
    assert "#" not in beats["survival"]


def test_a_wiki_that_spells_the_heading_differently_still_lands_on_a_beat():
    """`Behavior and Origin` against `Behaviour`. A parser that understood one spelling
    came back empty on half the canon."""
    beats = fandom.beats_from(fandom.parse_sections(WATCHTOWER))

    assert "appearance" in beats
    assert "behaviour" in beats


def test_markup_does_not_reach_the_narration():
    beats = fandom.beats_from(fandom.parse_sections(AMBER))
    joined = " ".join(beats.values())

    for markup in ("'''", "[[", "]]", "<br>", "''"):
        assert markup not in joined, markup


def test_a_page_with_prose_and_no_art_reports_itself_unusable():
    """The case that must not silently become a generated shot. A page without its
    canonical image cannot carry a segment of this format at all."""
    entity = fandom.Entity(title="Stub", wiki="w", url="u",
                           beats={"appearance": "words"})

    assert entity.usable is False


def test_attribution_says_unknown_rather_than_assuming_a_licence():
    """Fandom site content is CC-BY-SA, but an uploaded image is frequently the
    artist's own copyright and the API usually returns no licence fields. Recording
    "not stated" is the honest output; picking the convenient answer is the expensive
    kind of wrong."""
    entity = fandom.Entity(title="Amber", wiki="doctor-nowhere-creatures",
                           url="https://x/wiki/Amber", image_url="https://x/a.png",
                           image_name="Amber111.png",
                           image_page="https://x/wiki/File:Amber111.png",
                           beats={"appearance": "words"})

    line = entity.attribution()
    assert "licence not stated" in line
    assert "File:Amber111.png" in line


# ── reachability ────────────────────────────────────────────────────────────────
#
# This module was written, tested and committed with no caller — which is this
# repository's most common defect and the one it names in its own docs. These tests are
# the guard: a reader nothing can reach is a reader that does not exist.

def test_the_reader_is_reachable_as_an_agent_tool():
    from forgecast.agent import tools

    assert "read_fandom" in tools.ALL_TOOLS


def test_it_is_pre_allowed_because_it_only_reads():
    """Keyless, fetches no file, spends nothing. It is also the lookup the agent should
    be making *instead of* generating a picture of a named creature, and a check that
    has to be asked for is a check that gets skipped."""
    from forgecast.agent import tools

    assert "read_fandom" in tools._READ_ONLY
    assert "read_fandom" not in tools._WRITES


def test_the_studio_method_exists_and_the_tool_calls_it():
    import inspect

    from forgecast.agent import tools
    from forgecast.agent.studio import Studio

    assert callable(getattr(Studio, "read_fandom", None))
    assert "studio.read_fandom(" in inspect.getsource(tools.build_server)


def test_the_tool_description_forbids_calling_the_art_cleared():
    """The rights position is unresolved by design, so the one thing the description
    must not let the agent do is summarise it into a verdict."""
    import inspect

    source = inspect.getsource(__import__("forgecast.agent.tools", fromlist=["x"]).build_server)
    block = source[source.index('@tool("read_fandom"'):source.index("async def read_fandom")]

    assert "never call an asset safe, cleared or free" in block
    assert "CC-BY-SA" in block


async def test_a_missing_entity_is_reported_rather_than_falling_through_to_generation():
    """The substitution this whole module exists to prevent. An entity that cannot be
    found must come back as a stated absence, not as an empty result a caller reads as
    'go ahead and make one up'."""
    from forgecast.agent.studio import Studio

    async def nothing(site, wanted):
        return None

    import forgecast.research.fandom as reader

    original = reader.lookup
    reader.lookup = nothing
    try:
        answer = await Studio.read_fandom(object(), "some-wiki", "Nobody")
    finally:
        reader.lookup = original

    assert answer["found"] is False
    assert "generating a picture" in answer["note"]


async def test_a_blank_argument_asks_for_what_is_missing():
    from forgecast.agent.studio import Studio

    answer = await Studio.read_fandom(object(), "", "Amber")

    assert "error" in answer
    assert ".fandom.com" in answer["error"], "say how to find the wiki name"


# ── the gallery ─────────────────────────────────────────────────────────────────
#
# A page is not one picture. Amber's carries five, and the infobox pick is the smallest
# of them, while a 62-second segment cut at two to four seconds a shot needs roughly
# twenty. Returning one image is what turns an edit into a slideshow, and no amount of
# Ken Burns on a single still fixes it.

def test_wiki_chrome_is_never_a_shot_candidate():
    """Every page carries the same logos, badges and placeholders. Without this they
    outrank real artwork on pages whose art happens to be small."""
    for name in ("Wiki-wordmark.png", "Site-logo.png", "Favicon.ico",
                 "Placeholder_creature.png", "Stub_badge.png", "Spoiler-icon.png"):
        assert not fandom._worth_fetching(name), name


def test_real_artwork_passes_the_filter():
    for name in ("Amber111.png", "Amber in the fog111.png",
                 "IMG 20200304 212847.jpg", "Housewalker.webp"):
        assert fandom._worth_fetching(name), name


def test_animated_gifs_are_left_to_a_different_path():
    """They arrive as reaction images and gag material rather than as the subject, and
    this reader is the subject path."""
    assert not fandom._worth_fetching("Reaction.gif")


def test_an_asset_knows_whether_it_is_a_subject_or_a_shot():
    """Square or taller is the shape a cut-out arrives in and wants compositing onto a
    plate; a wide one is already a shot. That decides how it gets used, so it is
    measured rather than guessed at each call site."""
    square = fandom.Asset(name="a", url="u", page="p", width=2265, height=2265)
    wide = fandom.Asset(name="b", url="u", page="p", width=1920, height=1080)
    tall = fandom.Asset(name="c", url="u", page="p", width=1546, height=2048)

    assert square.is_portrait_crop
    assert tall.is_portrait_crop
    assert not wide.is_portrait_crop


def test_assets_sort_largest_first_by_pixels_not_by_edge():
    """A 1546x2048 is a bigger asset than a 2000x900 despite the shorter long edge."""
    tall = fandom.Asset(name="t", url="u", page="p", width=1546, height=2048)
    wide = fandom.Asset(name="w", url="u", page="p", width=2000, height=900)

    assert tall.pixels > wide.pixels


def test_the_tool_returns_the_gallery_and_says_size_does_not_pick():
    """Size orders the candidates; it does not choose between them. A tool that
    presented the largest file as 'the' image would have reproduced the one-shot
    problem with extra steps."""
    import inspect

    from forgecast.agent.studio import Studio

    source = inspect.getsource(Studio.read_fandom)
    assert '"gallery"' in source
    assert "orders the candidates and does not pick" in source


# --------------------------------------------------------------- headings with markup
#
# Both failures below were found the same way the two at the top of this file were: by
# running the reader against a wiki it had not been written from. `doors-game` is 76,000
# characters of exactly the sections this module wants, and it read as zero beats.

# doors-game.fandom.com/wiki/Seek — heading shapes copied from the live page. Every
# `==` heading on that wiki is prefixed with an icon template, and its sections break
# down into per-area subsections.
DOORS = """{{Infobox entity|name=Seek|image=Seek2.png|type=Hostile (Lethal)}}

=={{icons|overview}} Appearance==
Seek is an entity consisting of an amorphous, black, slime-like substance.

=={{icons|behavior}} Behavior==
Seek's chase is triggered on entering the room.

==={{icons|hotel}} [[The Hotel]]===
In the Hotel, Seek's chase begins at Door 30 and runs to Door 40.

===[[The Mines]]===
In the Mines, the chase is longer and the corridors branch.

=={{icons|trivia}} Trivia==
Seek's design was revealed before release.
"""


def test_a_heading_wrapped_in_markup_still_names_its_beat():
    """`== {{icons|overview}} Appearance ==` is an Appearance section.

    Keyed raw it becomes `{{icons|overview}} appearance`, which matches no alias in
    BEAT_SECTIONS and never would. The Doors wiki writes every heading that way, so the
    whole wiki read as a page with no readable sections — not a wiki the reader could
    not handle, one it silently declined to.
    """
    sections = fandom.parse_sections(DOORS)

    assert "appearance" in sections
    assert "behavior" in sections
    assert fandom.heading_key("{{icons|overview}} Appearance") == "appearance"
    assert fandom.heading_key("[[The Mines]]") == "the mines"
    assert set(fandom.beats_from(sections)) == {"appearance", "behaviour"}


def test_a_section_carries_its_subsections():
    """A `==` section runs to the next heading at its level or shallower.

    Stopping at the first `===` returned Seek's one-line lead and left the twelve
    thousand characters of actual behaviour on the floor — the narration beat is the
    section *and* what it breaks down into.
    """
    behaviour = fandom.parse_sections(DOORS)["behavior"]

    assert "chase is triggered" in behaviour
    assert "Door 30" in behaviour       # the Hotel subsection
    assert "corridors branch" in behaviour  # and the Mines one
    # ...but not the next `==` section, which is a different beat entirely.
    assert "design was revealed" not in behaviour


def test_a_repeated_heading_keeps_the_one_the_page_leads_with():
    """Pages carry a heading per form — Seek's has four Appearances. Whichever the dict
    happened to end on is not a decision; the first is."""
    twice = "==Appearance==\nThe first form is tall.\n\n==Appearance==\nThe second is not.\n"

    assert fandom.parse_sections(twice)["appearance"] == "The first form is tall."
