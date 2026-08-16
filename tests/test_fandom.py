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


def test_a_search_answer_about_a_different_subject_is_refused():
    """MediaWiki's search answers everything, and the canon lane believed it.

    Every pair here was measured against the live Doors wiki. A brief whose beats never
    got the creatures written into them hands the lane `Beat 1`..`Beat 8`, and the wiki
    returns a real, readable, illustrated page for each one — so a run built canon
    segments about a Tower Heroes crossover and the soundtrack listing. For a format
    whose audience polices canon, a confident page about the wrong subject is worse than
    a missing one.
    """
    from forgecast.research.fandom import resembles

    for query, title in [("Beat 1", "Soundtracks/Volume 1"),
                         ("Beat 2", "Second Tower Heroes Collab"),
                         ("Beat 3", "Floor 3"),
                         ("Beat 5", "Achievements/List"),
                         ("Sirenhead", "First Tower Heroes Collab")]:
        assert not resembles(query, title), f"{query!r} accepted {title!r}"


def test_the_overlap_is_on_whole_words_because_beat_is_inside_heartbeat():
    """`Beat 1` returns `Heartbeat Control Minigame` on the real wiki, and on a
    substring test that reads as a match."""
    from forgecast.research.fandom import resembles

    assert not resembles("Beat 1", "Heartbeat Control Minigame")


def test_a_near_miss_a_human_would_accept_still_resolves():
    """Loose on purpose. Being loose costs a near-miss somebody has to correct; being
    tight costs a segment about the wrong creature, and only one of those is
    recoverable."""
    from forgecast.research.fandom import resembles

    assert resembles("seek and figure", "Seek")
    assert resembles("The Rake", "Rake")
    assert resembles("Siren Head", "Siren Head (creature)")


def test_a_query_with_no_identity_in_it_is_refused_rather_than_matched():
    """There is nothing to check the answer against, so there is no way to tell whether
    it is right — and 'cannot tell' resolves to no, not to yes."""
    from forgecast.research.fandom import resembles

    assert not resembles("the", "Seek")
    assert not resembles("", "Seek")


def test_an_asset_knows_whether_it_can_be_a_cut_out_without_being_downloaded():
    """The shape is a hint and the alpha channel is the answer, and the API gives both.

    Measured against the Doors wiki's Figure gallery, fourteen usable files: every PNG
    reports a `colorType` in `imageinfo`'s metadata and JPEG, GIF and WEBP report none.
    `truecolour` is decisive — no alpha channel, so certainly not a cut-out — which is
    what separates `FIGURE WITH EARS OMGGG.png`, a near-black motion-blurred capture of
    the game, from the two real cut-outs it sits beside at the same aspect ratio.
    """
    cutout = fandom.Asset(name="a", url="u", page="p", width=1932, height=2464,
                          colour_type="truecolour-alpha", mime="image/png")
    flat = fandom.Asset(name="b", url="u", page="p", width=1166, height=1080,
                        colour_type="truecolour", mime="image/png")

    assert cutout.is_portrait_crop and flat.is_portrait_crop, \
        "the shapes have to match or this test is not about the alpha channel"
    assert cutout.has_alpha
    assert not flat.has_alpha


def test_a_jpeg_is_never_a_cut_out_even_though_it_reports_no_colour_type():
    """JPEG carries no alpha channel by construction, so the mime type answers it and
    the missing metadata is not a reason to guess."""
    assert not fandom.Asset(name="j", url="u", page="p", width=1128, height=684,
                            mime="image/jpeg").has_alpha


def test_a_file_the_api_says_nothing_about_is_left_in_rather_than_guessed_out():
    """WEBP and GIF report no colour type on these wikis. This filter exists to exclude
    what is provably flat, not to decide about what it cannot see — `layers.shot`
    checks the real pixels at render time, and over-filtering here would drop a real
    cut-out with no way to find out."""
    assert fandom.Asset(name="w", url="u", page="p", width=620, height=620,
                        mime="image/webp").has_alpha


def test_the_colour_type_is_read_out_of_mediawikis_name_value_list():
    """It arrives buried in a generic metadata list beside resolutions and a schema
    version, and only PNGs carry it at all — so a miss is the ordinary case."""
    metadata = [{"name": "bitDepth", "value": 8},
                {"name": "colorType", "value": "truecolour-alpha"},
                {"name": "_MW_PNG_VERSION", "value": 1}]

    assert fandom._colour_type(metadata) == "truecolour-alpha"
    assert fandom._colour_type([{"name": "bitDepth", "value": 8}]) is None
    assert fandom._colour_type(None) is None


def test_the_gallery_call_asks_for_the_metadata_that_carries_the_colour_type():
    """One batched request already fetches the sizes; the colour type rides along in it
    for nothing. Asserted on the source because the alternative is a live wiki call."""
    import inspect

    source = inspect.getsource(fandom.images)
    assert "metadata" in source and "iiprop" in source


def _sized(name, width, height, *, alpha=True):
    return fandom.Asset(name=name, url="u", page="p", width=width, height=height,
                        colour_type="truecolour-alpha" if alpha else "truecolour",
                        mime="image/png")


def test_the_gallery_limit_does_not_spend_itself_on_screenshots():
    """Size orders the candidates well and truncates them badly.

    Measured on Doors' Figure article: 32 usable images, 9 of them cut-outs, and the
    twelve biggest contain 2 of those 9 — a 1080p gameplay screenshot is three times
    the pixels of a 600x600 render and this wiki has a lot of gameplay screenshots.
    The planner then narrowed to the cut-outs it had been handed and put 40 shots on 2
    pictures, which is the one-monster-shot failure with its cause a layer upstream of
    where it showed.
    """
    found = sorted(
        [_sized(f"screenshot{i}.png", 1920, 1080, alpha=False) for i in range(20)]
        + [_sized(f"cutout{i}.png", 600, 600) for i in range(9)],
        key=lambda asset: asset.pixels, reverse=True)

    kept = fandom._keep(found, 12)

    cutouts = [a for a in kept if a.name.startswith("cutout")]
    assert len(kept) == 12
    assert len(cutouts) == 6, f"only {len(cutouts)} cut-outs survived the limit"


def test_a_page_with_no_cut_outs_still_returns_a_full_gallery():
    """Half the budget is reserved for cut-outs only where there are cut-outs. A page
    of pure scene photography has to come back with its twelve, or narrowing the pool
    upstream turns a poor segment into no segment."""
    found = [_sized(f"wide{i}.png", 1920, 1080, alpha=False) for i in range(20)]

    assert len(fandom._keep(found, 12)) == 12


def test_the_kept_gallery_is_still_handed_back_largest_first():
    """This changes which twelve, not how they are ordered — callers downstream read
    the list as ranked."""
    found = sorted(
        [_sized("big-wide.png", 1920, 1080, alpha=False),
         _sized("small-cutout.png", 600, 600),
         _sized("huge-cutout.png", 2000, 2000)],
        key=lambda asset: asset.pixels, reverse=True)

    kept = fandom._keep(found, 3)

    assert [a.pixels for a in kept] == sorted((a.pixels for a in kept), reverse=True)


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
