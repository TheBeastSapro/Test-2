"""The keyless image path: what a fresh install can do before anybody signs up.

Every other generative provider in the catalogue needs a credential first, so until this
one existed a fresh install could not render an image — it fell through to stock search,
whose own relaxation ladder documents serving "Blue Grass Chemical Agent-Destruction" for
a film about undersea cables.

The behaviour worth pinning is mostly about honesty: it charges a real zero rather than
the one-credit floor the paid adapters round up to, it returns the same picture for the
same prompt, and it fails in a way that says what actually happened — the service queues
under load rather than refusing, so a timeout here is congestion and not an outage.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from forgecast.providers.base import Capability, ProviderError, ProviderTimeout
from forgecast.providers.pollinations import PollinationsProvider
from forgecast.providers.registry import CATALOGUE, DEFAULT_ROUTING, ProviderRegistry

# A minimal real JPEG header plus enough bytes to pass the size floor.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4000


def _stub(monkeypatch, recorder: dict, *, body: bytes = JPEG, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.setdefault("urls", []).append(str(request.url))
        return httpx.Response(status, content=body)

    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr("forgecast.providers.pollinations.httpx.AsyncClient", factory)


# ------------------------------------------------------------------ reachability


def test_a_fresh_install_with_no_keys_can_generate_an_image():
    """The whole reason this adapter exists."""
    assert ProviderRegistry(mode="live").image().name == "pollinations"


def test_a_configured_install_still_prefers_the_paid_path():
    """Free is the fallback, not the default. It queues, and quality is not the same."""
    assert ProviderRegistry(mode="live", user_keys={"fal": "k"}).image().name == "fal"


def test_it_outranks_stock_search_because_generation_is_on_prompt():
    order = DEFAULT_ROUTING[Capability.image]
    assert order.index("pollinations") < order.index("openverse")
    assert order.index("fal") < order.index("pollinations")


def test_it_is_registered_as_needing_no_credential():
    capability, _, key_name = CATALOGUE["pollinations"]
    assert capability is Capability.image
    assert key_name == ""
    assert PollinationsProvider().available() == (True, "")


def test_availability_does_not_make_a_network_call(monkeypatch):
    """`resolve` calls this while choosing a vendor, including for lookups that go on to
    choose someone else. A round trip there would put a live request in front of all of
    them."""
    def explode(*args, **kwargs):  # pragma: no cover - the point is that it is not hit
        raise AssertionError("available() made a request")

    monkeypatch.setattr("forgecast.providers.pollinations.httpx.AsyncClient", explode)
    assert PollinationsProvider().available()[0] is True


# ------------------------------------------------------------------ the charge


async def test_it_charges_a_real_zero_not_the_one_credit_floor(tmp_path, monkeypatch):
    """The paid adapters round up to one credit. Eighty shots of that is an eighty-credit
    charge for something that cost nothing, and the operator cannot tell it apart from a
    real one."""
    _stub(monkeypatch, {})
    result = await PollinationsProvider().generate(
        "a lighthouse", out_path=tmp_path / "a", width=512, height=288)
    assert result.credits == 0
    assert result.meta["usd"] == 0.0


async def test_the_result_says_it_carries_no_guarantee(tmp_path, monkeypatch):
    """Free is the reason to pick it and the reason not to depend on it."""
    _stub(monkeypatch, {})
    result = await PollinationsProvider().generate(
        "a lighthouse", out_path=tmp_path / "a", width=512, height=288)
    assert result.meta["method"] == "keyless_generation"
    assert "no contract" in result.meta["guarantee"]


# ------------------------------------------------------------------ determinism


async def test_the_same_prompt_returns_the_same_seed(tmp_path, monkeypatch):
    """A re-render after an unrelated failure must not silently change a picture the
    operator already approved."""
    _stub(monkeypatch, {})
    provider = PollinationsProvider()
    first = await provider.generate("a torn map", out_path=tmp_path / "a",
                                    width=512, height=288)
    second = await provider.generate("a torn map", out_path=tmp_path / "b",
                                     width=512, height=288)
    assert first.meta["seed"] == second.meta["seed"]


async def test_a_different_size_is_a_different_seed(tmp_path, monkeypatch):
    """Sharing one across sizes gives two near-identical compositions cropped
    differently, which looks like a bug rather than a set."""
    _stub(monkeypatch, {})
    provider = PollinationsProvider()
    wide = await provider.generate("a torn map", out_path=tmp_path / "a",
                                   width=1024, height=576)
    tall = await provider.generate("a torn map", out_path=tmp_path / "b",
                                   width=576, height=1024)
    assert wide.meta["seed"] != tall.meta["seed"]


async def test_a_different_prompt_is_a_different_seed(tmp_path, monkeypatch):
    _stub(monkeypatch, {})
    provider = PollinationsProvider()
    one = await provider.generate("a torn map", out_path=tmp_path / "a")
    two = await provider.generate("a lighthouse", out_path=tmp_path / "b")
    assert one.meta["seed"] != two.meta["seed"]


# ------------------------------------------------------------------ the request


async def test_a_prompt_with_punctuation_does_not_become_a_url_path(tmp_path, monkeypatch):
    """A prompt containing "16:9" otherwise addresses a URL nobody meant, and the service
    answers it with something unrelated instead of failing."""
    recorder: dict = {}
    _stub(monkeypatch, recorder)
    await PollinationsProvider().generate("aspect 16:9 / a torn map",
                                          out_path=tmp_path / "a")
    url = recorder["urls"][0]
    # Everything after /prompt/ is one escaped segment.
    tail = url.split("/prompt/", 1)[1].split("?", 1)[0]
    assert "/" not in tail
    assert ":" not in tail


async def test_the_requested_size_reaches_the_service(tmp_path, monkeypatch):
    recorder: dict = {}
    _stub(monkeypatch, recorder)
    await PollinationsProvider().generate("x", out_path=tmp_path / "a",
                                          width=1920, height=1080)
    assert "width=1920" in recorder["urls"][0]
    assert "height=1080" in recorder["urls"][0]


async def test_an_empty_prompt_is_refused_before_the_request(tmp_path, monkeypatch):
    recorder: dict = {}
    _stub(monkeypatch, recorder)
    with pytest.raises(ProviderError):
        await PollinationsProvider().generate("   ", out_path=tmp_path / "a")
    assert not recorder.get("urls")


# ------------------------------------------------------------------ failure


async def test_an_error_page_served_with_a_200_is_not_written_as_a_picture(
    tmp_path, monkeypatch
):
    """A shape free services fall into under load. Writing it puts a file on disk that
    every later stage treats as an image."""
    _stub(monkeypatch, {}, body=b"<html>rate limited</html>")
    with pytest.raises(ProviderError, match="not an image"):
        await PollinationsProvider().generate("x", out_path=tmp_path / "a")
    assert not (tmp_path / "a.jpg").exists()


async def test_a_truncated_image_is_refused(tmp_path, monkeypatch):
    _stub(monkeypatch, {}, body=b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    with pytest.raises(ProviderError):
        await PollinationsProvider().generate("x", out_path=tmp_path / "a")


async def test_a_server_error_is_retryable(tmp_path, monkeypatch):
    _stub(monkeypatch, {}, status=503)
    with pytest.raises(ProviderError) as caught:
        await PollinationsProvider().generate("x", out_path=tmp_path / "a")
    assert caught.value.retryable is True


async def test_a_timeout_says_it_is_probably_the_queue(tmp_path, monkeypatch):
    """Measured behaviour: it holds the connection rather than returning 429. Reporting
    that as an outage sends whoever reads the log looking for the wrong thing."""
    def factory(*args, **kwargs):
        class Stalled:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, *args, **kwargs):
                raise httpx.ReadTimeout("timed out")

        return Stalled()

    monkeypatch.setattr("forgecast.providers.pollinations.httpx.AsyncClient", factory)
    with pytest.raises(ProviderTimeout, match="queues under load"):
        await PollinationsProvider().generate("x", out_path=tmp_path / "a")


# ------------------------------------------------------------------ pacing


async def test_the_first_few_requests_are_not_paced(tmp_path, monkeypatch):
    """Three go through in about a second each. Delaying those buys nothing."""
    _stub(monkeypatch, {})
    slept: list[float] = []

    async def record(seconds):
        slept.append(seconds)

    monkeypatch.setattr("forgecast.providers.pollinations.asyncio.sleep", record)
    provider = PollinationsProvider()
    for index in range(3):
        await provider.generate(f"shot {index}", out_path=tmp_path / str(index))
    assert slept == []


async def test_later_requests_wait_deliberately_rather_than_inside_an_open_request(
    tmp_path, monkeypatch
):
    """Waiting here is cancellable and loggable. Waiting inside an open HTTP request is
    neither, and is indistinguishable from the service having hung."""
    _stub(monkeypatch, {})
    slept: list[float] = []

    async def record(seconds):
        slept.append(seconds)

    monkeypatch.setattr("forgecast.providers.pollinations.asyncio.sleep", record)
    provider = PollinationsProvider()
    for index in range(5):
        await provider.generate(f"shot {index}", out_path=tmp_path / str(index))
    assert len(slept) == 2
    assert all(0 < delay <= 15.0 for delay in slept)


async def test_concurrent_shots_do_not_all_fire_at_once(tmp_path, monkeypatch):
    """The pacer is behind a lock. Without one, eight shots started together each read the
    same 'last sent' timestamp, decide no wait is needed, and the pacing does nothing."""
    _stub(monkeypatch, {})
    slept: list[float] = []

    async def record(seconds):
        slept.append(seconds)

    monkeypatch.setattr("forgecast.providers.pollinations.asyncio.sleep", record)
    provider = PollinationsProvider()
    await asyncio.gather(*[
        provider.generate(f"shot {index}", out_path=tmp_path / str(index))
        for index in range(6)
    ])
    assert len(slept) == 3
