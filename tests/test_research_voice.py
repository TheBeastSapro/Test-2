"""Research citation discipline and voice casting.

The research tests centre on one property: a claim whose supporting quote is not
present in the fetched page must never reach the script. That check is the only thing
standing between "research mode" and a machine that launders invented statistics
through a citation-shaped wrapper, so it gets tested from several angles.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from forgecast.config import get_settings
from forgecast.providers.base import ProviderError
from forgecast.providers.search import (
    FETCH_USER_AGENT,
    FetchedPage,
    MockSearch,
    SearchResult,
    WikipediaSearch,
    _TextExtractor,
    provider_for,
)
from forgecast.research.brief import Claim, ResearchBrief, Source
from forgecast.research.engine import _normalise, research_topic
from forgecast.voice.casting import (
    VoiceTarget,
    casting_summary,
    pace_band,
    shortlist,
    target_from_reference,
)
from forgecast.voice.catalogue import STOCK_VOICES, by_name, pitch_distance
from forgecast.voice.discover import MeasuredVoice, metadata_score, parse_voice, prerank

# Tests must never read a real cached catalogue: whether one exists on disk depends on
# whether someone ran a live sync, which would make these results vary by machine.
NO_CACHE = Path("/nonexistent/voice_catalogue.json")


def measured(name, hz, **kw):
    return MeasuredVoice(
        voice_id=f"id-{name.lower()}", name=name, pitch_hz=hz,
        pitch_band=("low" if hz < 110 else "low_mid" if hz < 165 else "mid" if hz < 215
                    else "high"),
        voiced_ratio=0.8, measurement="measured", preview_url="https://x.test/p.mp3",
        **kw,
    )

# --------------------------------------------------------------- research model


def test_unverified_claims_never_reach_the_prompt():
    brief = ResearchBrief(topic="cables")
    brief.claims = [
        Claim("Verified thing", "https://a.test/1", "quote one", verified=True),
        Claim("Unverified thing", "https://a.test/2", "quote two", verified=False),
    ]
    block = brief.prompt_block()
    assert "Verified thing" in block
    assert "Unverified thing" not in block


def test_prompt_block_forbids_invention_when_nothing_was_found():
    brief = ResearchBrief(topic="cables")
    block = brief.prompt_block()
    assert "no verifiable sources" in block
    assert "without factual claims" in block
    # Must not leave the model room to supply its own numbers.
    assert "invent" in block.lower() or "no statistics" in block


def test_prompt_block_names_unresolved_questions_as_off_limits():
    brief = ResearchBrief(topic="cables")
    brief.claims = [Claim("A fact", "https://a.test/1", "q", verified=True)]
    brief.open_questions = ["How many break per year?"]
    block = brief.prompt_block()
    assert "UNRESOLVED" in block
    assert "How many break per year?" in block
    assert "must not" in block


def test_statistics_are_identified_for_extra_scrutiny():
    brief = ResearchBrief(topic="t")
    brief.claims = [
        Claim("Roughly 200 cables break each year", "https://a.test/1", "q", verified=True),
        Claim("Cables are laid on the seabed", "https://a.test/2", "q", verified=True),
    ]
    stats = brief.statistics()
    assert len(stats) == 1
    assert "200" in stats[0].text


def test_source_trust_tiers():
    assert Source("u", "nasa.gov", "t").trust == "high"
    assert Source("u", "some-university.edu", "t").trust == "high"
    assert Source("u", "reuters.com", "t").trust == "high"
    assert Source("u", "randomblog.com", "t").trust == "medium"
    assert Source("u", "example.org", "t").trust == "low"


def test_counts_distinguish_fetched_from_found():
    brief = ResearchBrief(topic="t")
    brief.sources = [
        Source("a", "a.test", "A", fetched=True),
        Source("b", "b.test", "B", fetched=False, error="HTTP 403"),
    ]
    counts = brief.as_dict()["counts"]
    assert counts["sources"] == 2
    assert counts["sources_fetched"] == 1


# ------------------------------------------------------------ quote verification


class _StubLLM:
    """Returns canned JSON per schema so the engine can be driven offline."""

    def __init__(self, queries: dict, claims: dict) -> None:
        self._queries = queries
        self._claims = claims
        self.calls: list[str] = []

    async def complete(self, prompt, *, system="", json_object=False, schema_name="",
                       max_tokens=0, temperature=0.0):
        import json as _json

        from forgecast.providers.base import TextResult

        self.calls.append(schema_name)
        payload = self._queries if schema_name == "research_queries" else self._claims
        return TextResult(text=_json.dumps(payload), credits=1, provider="stub")


PAGE_TEXT = (
    "Undersea cables are protected by armouring near shore. Fishing gear and ship "
    "anchors cause the majority of faults in shallow water, and repairs require a "
    "specialised cable ship that may be days away."
)


@pytest.fixture
def patched_fetch(monkeypatch):
    """Serve one known page so quote matching runs against real text."""

    async def fake_fetch(url: str, *, timeout: float = 30.0) -> FetchedPage:
        return FetchedPage(url=url, title="Cable faults", text=PAGE_TEXT * 4)

    monkeypatch.setattr("forgecast.research.engine.fetch", fake_fetch)
    return fake_fetch


async def test_claim_with_a_real_quote_is_kept(patched_fetch):
    quote = "Fishing gear and ship anchors cause the majority of faults in shallow water"
    llm = _StubLLM(
        {"queries": ["cable faults causes"], "open_questions": []},
        {"claims": [{"text": "Most shallow-water faults come from fishing and anchors",
                     "quote": quote, "kind": "fact", "confidence": "high"}]},
    )
    brief = await research_topic("cable faults", llm=llm, search=MockSearch(), max_pages=2)

    assert len(brief.verified_claims) >= 1
    assert brief.verified_claims[0].verified is True
    assert not brief.rejected_claims


async def test_claim_with_a_fabricated_quote_is_rejected(patched_fetch):
    """The core guarantee: a quote that is not in the page kills the claim."""
    llm = _StubLLM(
        {"queries": ["cable faults"], "open_questions": []},
        {"claims": [{
            "text": "Exactly 8,432 cables break every year, according to the ITU",
            "quote": "The ITU reports exactly 8,432 cable breaks annually worldwide.",
            "kind": "statistic", "confidence": "high",
        }]},
    )
    brief = await research_topic("cable faults", llm=llm, search=MockSearch(), max_pages=2)

    assert brief.verified_claims == []
    assert brief.rejected_claims
    assert "does not appear" in brief.rejected_claims[0]["reason"]
    # And the fabricated number must not leak into what the script sees.
    assert "8,432" not in brief.prompt_block()


async def test_claim_with_a_too_short_quote_is_rejected(patched_fetch):
    llm = _StubLLM(
        {"queries": ["q"], "open_questions": []},
        {"claims": [{"text": "Cables exist", "quote": "cables", "kind": "fact"}]},
    )
    brief = await research_topic("cables", llm=llm, search=MockSearch(), max_pages=1)
    assert brief.verified_claims == []
    assert "too short" in brief.rejected_claims[0]["reason"]


async def test_quote_matching_tolerates_reflowed_whitespace(patched_fetch):
    """Models reflow whitespace even when told to copy exactly; that alone must not
    reject an otherwise good claim."""
    quote = "Fishing gear and ship anchors   cause the majority\n of faults"
    llm = _StubLLM(
        {"queries": ["q"], "open_questions": []},
        {"claims": [{"text": "Fishing and anchors dominate", "quote": quote,
                     "kind": "fact"}]},
    )
    brief = await research_topic("cables", llm=llm, search=MockSearch(), max_pages=1)
    assert len(brief.verified_claims) == 1


async def test_unfetchable_pages_yield_no_claims(monkeypatch):
    async def dead_fetch(url: str, *, timeout: float = 30.0) -> FetchedPage:
        return FetchedPage(url=url, title="", text="", status=403, error="HTTP 403")

    monkeypatch.setattr("forgecast.research.engine.fetch", dead_fetch)
    llm = _StubLLM({"queries": ["q"], "open_questions": []}, {"claims": []})
    brief = await research_topic("cables", llm=llm, search=MockSearch(), max_pages=3)

    assert brief.verified_claims == []
    assert "no page could be fetched" in brief.note
    assert all(source.fetched is False for source in brief.sources)


def test_normalise_makes_matching_whitespace_and_case_insensitive():
    assert _normalise("  Hello   WORLD\n") == "hello world"


# ------------------------------------------------------------------- search层


def test_mock_search_labels_itself_as_mock():
    """A mock that produced convincing facts would hide bugs in the verify step."""
    import asyncio

    results = asyncio.run(MockSearch().search("deep sea cables"))
    assert results
    assert all("MOCK" in item.title for item in results)
    assert all("MOCK" in item.snippet for item in results)


def test_search_result_domain_strips_www():
    assert SearchResult("t", "https://www.Example.COM/path").domain == "example.com"


def test_html_extraction_drops_scripts_and_nav():
    parser = _TextExtractor()
    parser.feed(
        "<html><head><title>Doc</title></head><body>"
        "<nav>Menu Home About</nav>"
        "<script>var secret='tracking';</script>"
        "<p>Real body sentence one.</p><p>Real body sentence two.</p>"
        "<footer>Copyright notice</footer></body></html>"
    )
    text = parser.text()
    assert parser.title == "Doc"
    assert "Real body sentence one." in text
    assert "tracking" not in text
    assert "Menu" not in text


def test_page_needs_enough_text_to_be_usable():
    assert FetchedPage("u", "t", "short").usable is False
    assert FetchedPage("u", "t", "x" * 500).usable is True
    assert FetchedPage("u", "t", "x" * 500, error="boom").usable is False


# ------------------------------------------------------------------ voice casting


def test_pace_bands():
    assert pace_band(90) == "slow"
    assert pace_band(130) == "measured"
    assert pace_band(165) == "brisk"
    assert pace_band(195) == "fast"
    assert pace_band(240) == "very_fast"
    assert pace_band(None) is None


def test_target_uses_measured_pitch_when_there_is_enough_speech():
    profile = {"audio": {"pitch_hz": 105.0, "pitch_band": "low", "voiced_ratio": 0.7}}
    target = target_from_reference(profile, words_per_minute=140)
    assert target.pitch_band == "low"
    assert any("105Hz" in item for item in target.evidence)
    assert target.pace == "measured"


def test_target_ignores_pitch_measured_from_almost_no_speech():
    """A music bed or click track reports a confident f0 that means nothing."""
    profile = {"audio": {"pitch_hz": 250.0, "pitch_band": "high", "voiced_ratio": 0.05}}
    target = target_from_reference(profile)
    assert target.pitch_band is None
    assert any("too little speech" in gap for gap in target.gaps)


def test_target_reports_gaps_when_there_is_no_reference():
    target = target_from_reference({})
    assert target.pitch_band is None
    assert target.gaps
    assert any("no pitch" in gap for gap in target.gaps)


def test_silence_drives_the_energy_read():
    busy = target_from_reference({"audio": {"silence_ratio": 0.02}})
    calm = target_from_reference({"audio": {"silence_ratio": 0.45}})
    assert busy.energy == "energetic"
    assert calm.energy == "calm"


def test_fast_edit_implies_an_energetic_read():
    target = target_from_reference(
        {"audio": {"silence_ratio": 0.15}, "shot_rhythm": {"cuts_per_minute": 45}}
    )
    assert target.energy == "energetic"
    assert any("cuts/min" in item for item in target.evidence)


def test_shortlist_prefers_the_matching_pitch_band():
    target = VoiceTarget(pitch_band="low", energy="measured")
    candidates = shortlist(target, limit=3, cache_path=NO_CACHE)
    top = candidates[0]
    assert top.catalogue.pitch_band in {"low", "low_mid"}
    assert any("pitch band" in reason for reason in top.reasons)


def test_shortlist_includes_a_deliberate_contrast():
    """Casting purely on similarity converges on the same three voices forever."""
    candidates = shortlist(
        VoiceTarget(pitch_band="low", energy="calm"), limit=3, cache_path=NO_CACHE
    )
    assert len(candidates) == 4
    assert any("contrast" in caveat for caveat in candidates[-1].caveats)


def test_shortlist_never_selects_silently():
    """Every candidate is a proposal; nothing in casting marks one as chosen.

    Carrying a resolvable voice_id is fine and desirable — the invariant is that no
    candidate is flagged as the choice and none has been synthesised yet.
    """
    pool = [measured("Alpha", 120.0), measured("Beta", 190.0), measured("Gamma", 230.0)]
    for candidates in (
        shortlist(VoiceTarget(pitch_band="mid"), limit=3, cache_path=NO_CACHE),
        shortlist(VoiceTarget(pitch_hz=125.0), limit=2, measured=pool),
    ):
        assert all(candidate.sample_path is None for candidate in candidates)
        assert not any(getattr(candidate, "selected", False) for candidate in candidates)


def test_candidates_admit_when_pitch_could_not_be_compared():
    candidates = shortlist(VoiceTarget(), limit=2, cache_path=NO_CACHE)
    assert all(
        any("pitch could not be compared" in caveat for caveat in candidate.caveats)
        for candidate in candidates
    )


def test_every_candidate_carries_a_reason():
    for candidate in shortlist(
        VoiceTarget(pitch_band="high", energy="warm"), limit=4, cache_path=NO_CACHE
    ):
        assert candidate.reasons, f"{candidate.name} has no stated reason"


def test_summary_tells_the_operator_to_listen():
    target = VoiceTarget(pitch_band="mid", evidence=["reference speaks at ~180Hz"])
    lines = casting_summary(target, shortlist(target, limit=2, cache_path=NO_CACHE))
    joined = "\n".join(lines)
    assert "Cast from:" in joined
    assert "Listen to the samples" in joined


def test_catalogue_ships_no_voice_ids():
    """IDs vary per account and cannot be verified offline; names resolve at runtime."""
    for voice in STOCK_VOICES:
        assert not hasattr(voice, "voice_id")
        assert voice.pitch_band in {"low", "low_mid", "mid", "high"}
        assert voice.name


def test_catalogue_lookup_is_case_insensitive():
    assert by_name("rachel") is not None
    assert by_name("RACHEL").name == "Rachel"
    assert by_name("nobody") is None


def test_pitch_distance_reports_unknown_rather_than_guessing():
    assert pitch_distance("low", "low") == 0
    assert pitch_distance("low", "low_mid") == 1
    assert pitch_distance("low", "high") == 3
    assert pitch_distance(None, "mid") == 99
    assert pitch_distance("mid", "nonsense") == 99


def test_sample_line_prefers_the_hook():
    from forgecast.voice.audition import sample_line

    line = sample_line(
        {"title": "A Title"},
        {"hook": "Most people get deep-sea cables completely wrong."},
    )
    assert "deep-sea cables" in line


def test_sample_line_falls_back_to_narration_then_topic():
    from forgecast.voice.audition import sample_line

    from_scene = sample_line({"scenes": [{"narration": "Here is the opening line spoken."}]})
    assert "opening line" in from_scene

    from_topic = sample_line({}, {}, topic="undersea cables")
    assert "undersea cables" in from_topic


# ------------------------------------------------- measured catalogue (live path)


def test_measured_catalogue_beats_the_static_fallback():
    """When a synced catalogue exists it must be used; the static names are stale."""
    pool = [measured("Alpha", 130.0), measured("Beta", 200.0)]
    candidates = shortlist(VoiceTarget(pitch_hz=132.0), limit=2, measured=pool)
    assert {candidate.name for candidate in candidates} <= {"Alpha", "Beta"}
    assert all(candidate.measured is not None for candidate in candidates)
    assert all(candidate.voice_id for candidate in candidates)


def test_ranking_is_on_measured_hz_not_bands():
    """Two voices in the same band should still be separated by actual distance."""
    pool = [measured("Near", 135.0), measured("Far", 163.0)]
    candidates = shortlist(VoiceTarget(pitch_hz=133.0), limit=2, measured=pool)
    assert candidates[0].name == "Near"
    assert any("within" in reason for reason in candidates[0].reasons)


def test_static_fallback_declares_itself():
    """An operator must know when they are seeing possibly-stale names."""
    candidates = shortlist(VoiceTarget(pitch_band="low"), limit=2, cache_path=NO_CACHE)
    assert all(
        any("offline fallback" in caveat for caveat in candidate.caveats)
        for candidate in candidates
    )
    lines = casting_summary(VoiceTarget(pitch_band="low"), candidates)
    assert any("forgecast-voice sync" in line for line in lines)


def test_unmeasurable_voice_is_penalised_not_hidden():
    good = measured("Good", 130.0)
    bad = MeasuredVoice(voice_id="id-bad", name="Bad", measurement="no_preview_url")
    candidates = shortlist(VoiceTarget(pitch_hz=131.0), limit=2, measured=[good, bad])
    assert candidates[0].name == "Good"
    names = {candidate.name for candidate in candidates}
    assert "Bad" in names          # still offered
    bad_candidate = next(c for c in candidates if c.name == "Bad")
    assert any("could not be measured" in caveat for caveat in bad_candidate.caveats)


def test_parse_voice_splits_descriptors_out_of_the_title():
    voice = parse_voice({
        "voice_id": "abc", "name": "Roger - Laid-Back, Casual, Resonant",
        "category": "premade",
        "labels": {"gender": "male", "accent": "american", "age": "middle_aged",
                   "use_case": "conversational", "descriptive": "classy"},
        "preview_url": "https://x.test/p.mp3",
    })
    assert voice.name == "Roger"
    assert voice.display_name == "Roger - Laid-Back, Casual, Resonant"
    assert voice.descriptors == ["Laid-Back", "Casual", "Resonant"]
    assert voice.gender == "male"
    assert voice.energy == "calm"        # "laid-back" maps to calm


def test_energy_mapping_from_vendor_words():
    assert measured("A", 150.0, use_case="social_media").energy == "energetic"
    assert measured("B", 150.0, descriptive="soothing").energy == "calm"
    assert measured("C", 150.0, descriptors=["Warm Storyteller"]).energy == "warm"
    assert measured("D", 150.0).energy == "measured"


def test_prerank_narrows_a_large_pool_without_measuring():
    """The point of pre-ranking: choose who to measure out of thousands, for free."""
    pool = [
        MeasuredVoice(voice_id=f"v{i}", name=f"V{i}",
                      accent="british" if i % 2 else "american",
                      use_case="narrative_story" if i % 3 == 0 else "advertisement",
                      gender="male", preview_url="https://x.test/p.mp3")
        for i in range(200)
    ]
    target = VoiceTarget(pitch_band="low_mid", accent="british", register="documentary")
    chosen = prerank(target, pool, limit=10)

    assert len(chosen) == 10
    assert all(voice.measurement == "not_measured" for voice in chosen)
    # British + narrative_story should dominate the measurement budget.
    assert sum(1 for voice in chosen if voice.accent == "british") >= 8


def test_metadata_score_prefers_requested_accent():
    target = VoiceTarget(accent="british")
    british = MeasuredVoice(voice_id="a", name="A", accent="british",
                            preview_url="https://x/p")
    american = MeasuredVoice(voice_id="b", name="B", accent="american",
                             preview_url="https://x/p")
    assert metadata_score(target, british) > metadata_score(target, american)


def test_catalogue_round_trips_through_the_cache(tmp_path):
    from forgecast.voice.discover import load_catalogue, save_catalogue

    original = [measured("Alpha", 128.0, accent="british", use_case="narrative_story")]
    path = save_catalogue(original, tmp_path / "cat.json")
    restored = load_catalogue(path)

    assert len(restored) == 1
    assert restored[0].name == "Alpha"
    assert restored[0].pitch_hz == 128.0
    assert restored[0].voice_id == "id-alpha"


def test_missing_cache_is_not_an_error():
    from forgecast.voice.discover import load_catalogue

    assert load_catalogue(Path("/nonexistent/nope.json")) == []


# --------------------------------------------------- keyless search (Wikipedia)
#
# Stubbed rather than live: a suite that needs Wikipedia to be reachable is a suite
# that fails for reasons that have nothing to do with the code.


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = ""

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Captures the request so the User-Agent can be asserted on."""

    last_headers: ClassVar[dict] = {}
    last_params: ClassVar[dict] = {}
    payload: ClassVar[dict] = {}
    status: int = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, params=None, headers=None):
        type(self).last_headers = dict(headers or {})
        type(self).last_params = dict(params or {})
        return _FakeResponse(type(self).payload, type(self).status)


@pytest.fixture
def fake_wikipedia(monkeypatch):
    _FakeClient.payload = {
        "query": {
            "search": [
                {"title": "Submarine communications cable",
                 "snippet": 'A <span class="searchmatch">cable</span> laid on the seabed',
                 "timestamp": "2026-01-02T03:04:05Z"},
                {"title": "2008 submarine cable disruption",
                 "snippet": "damage involving up to five cables"},
                {"title": ""},          # must be skipped, not crash
            ]
        }
    }
    _FakeClient.status = 200
    monkeypatch.setattr("forgecast.providers.search.httpx.AsyncClient",
                        lambda *a, **k: _FakeClient())
    return _FakeClient


async def test_wikipedia_search_returns_article_urls(fake_wikipedia):
    results = await WikipediaSearch().search("undersea cables", limit=5)
    assert [r.title for r in results] == [
        "Submarine communications cable", "2008 submarine cable disruption",
    ]
    assert results[0].url == (
        "https://en.wikipedia.org/wiki/Submarine_communications_cable"
    )
    assert results[0].rank == 1


async def test_wikipedia_snippets_are_stripped_of_highlight_markup(fake_wikipedia):
    results = await WikipediaSearch().search("undersea cables")
    assert results[0].snippet == "A cable laid on the seabed"
    assert "<span" not in results[0].snippet


async def test_wikipedia_sends_a_contact_bearing_user_agent(fake_wikipedia):
    """Wikimedia's UA policy 403s anything without a contact route."""
    await WikipediaSearch().search("undersea cables")
    agent = fake_wikipedia.last_headers.get("User-Agent", "")
    assert "http" in agent, agent
    assert "Mozilla" not in agent, "do not impersonate a browser"


async def test_wikipedia_clamps_the_result_limit(fake_wikipedia):
    await WikipediaSearch().search("x", limit=500)
    assert int(fake_wikipedia.last_params["srlimit"]) <= 20


async def test_wikipedia_reports_a_rate_limit_as_retryable(fake_wikipedia):
    _FakeClient.status = 429
    with pytest.raises(ProviderError) as caught:
        await WikipediaSearch().search("x")
    assert caught.value.retryable is True


def test_page_fetch_identifies_itself_with_a_contact_route():
    """Regression: a browser-shaped UA fetched 0 characters from every Wikipedia
    article — a 403 that emptied the research brief instead of failing loudly."""
    assert "http" in FETCH_USER_AGENT
    assert "Mozilla" not in FETCH_USER_AGENT


def test_live_mode_without_a_search_key_grounds_in_wikipedia_not_mock(monkeypatch):
    """The important one: research must never silently become fiction.

    MockSearch returns plausible-looking results, so falling back to it in live mode
    produces a brief full of sources that do not exist.
    """
    settings = get_settings()
    original = settings.provider_mode
    settings.provider_mode = "live"
    try:
        assert isinstance(provider_for(), WikipediaSearch)
    finally:
        settings.provider_mode = original


def test_a_vendor_key_still_wins_over_the_keyless_fallback(monkeypatch):
    settings = get_settings()
    original_mode, original_key = settings.provider_mode, settings.tavily_api_key
    settings.provider_mode = "live"
    settings.tavily_api_key = "tvly-test"
    try:
        assert provider_for().name == "tavily"
    finally:
        settings.provider_mode = original_mode
        settings.tavily_api_key = original_key


def test_mock_mode_still_uses_mock_search():
    assert isinstance(provider_for(), MockSearch)
