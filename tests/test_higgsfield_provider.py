"""Higgsfield: the async job protocol, and the reasons it stays opt-in.

This vendor differs from every other image provider in the tree in one structural way: the
call does not return a picture, it returns a *job*. Submit, poll, then download. Three
places to get wrong, each of which costs a generation that has already been paid for:

* treating a `queued` submit response as a finished result — writes nothing and reports
  success;
* abandoning a poll on a network hiccup — the job finishes on their side and is billed,
  with no file to show for it;
* reading `nsfw` as a failure — sends the operator to check their key and their network
  for something only a rewritten prompt will fix.

The fourth test group is about money rather than protocol. Higgsfield bills per generation
against its own credit balance, so it must be reachable by being chosen and unreachable by
being fallen back to.
"""

from __future__ import annotations

import httpx
import pytest

from forgecast.providers import higgsfield as hf
from forgecast.providers.base import Capability, ProviderError, ProviderTimeout
from forgecast.providers.registry import CATALOGUE, DEFAULT_ROUTING, ProviderRegistry

pytestmark = pytest.mark.anyio

PNG = b"\x89PNG\r\n\x1a\n" + b"forgecast"
ASSET = "https://cdn.higgsfield.invalid/out.png"


def _serve(monkeypatch, script: list, recorder: dict | None = None):
    """Answer each request from `script` in order; the last entry repeats.

    A list rather than a single response because the whole point of this adapter is a
    sequence — submit, then N polls, then a download.
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if recorder is not None:
            recorder["calls"] = calls
        index = min(len(calls) - 1, len(script) - 1)
        entry = script[index]
        return entry(request) if callable(entry) else entry

    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(hf.httpx, "AsyncClient", factory)
    return calls


def _no_sleep(monkeypatch):
    """The poll loop's backoff, removed. Without this the timeout tests take minutes."""
    async def instant(_seconds):
        return None

    monkeypatch.setattr(hf.asyncio, "sleep", instant)


# ------------------------------------------------------------------ the credential


async def test_a_single_value_credential_is_refused_with_the_reason(tmp_path, monkeypatch):
    """The header is `Key {id}:{secret}`. One half is a 401 with no explanation.

    Caught locally instead, because "Invalid credentials" against a key that was pasted
    correctly-but-halfway is unresolvable from the message the API sends.
    """
    _serve(monkeypatch, [httpx.Response(500, text="never reached")])
    provider = hf.HiggsfieldProvider(api_key="only-one-half")

    with pytest.raises(ProviderError, match="key:secret"):
        await provider.generate("a face", out_path=tmp_path / "still")


async def test_the_header_is_the_pair_verbatim(tmp_path, monkeypatch):
    recorder: dict = {}
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "completed",
                                  "images": [{"url": ASSET}]}),
        httpx.Response(200, content=PNG),
    ], recorder)
    provider = hf.HiggsfieldProvider(api_key="abc:secret")

    await provider.generate("a face", out_path=tmp_path / "still")

    assert recorder["calls"][0].headers["Authorization"] == "Key abc:secret"


# --------------------------------------------------------------- the job protocol


async def test_a_queued_submit_is_polled_rather_than_returned(tmp_path, monkeypatch):
    """The structural difference from every other image provider here.

    A submit answers `queued`. Returning at that point would report success and write
    nothing, which is the worst of the three failure modes because it looks fine.
    """
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "in_progress"}),
        httpx.Response(200, json={"status": "completed", "images": [{"url": ASSET}]}),
        httpx.Response(200, content=PNG),
    ])
    _no_sleep(monkeypatch)
    provider = hf.HiggsfieldProvider(api_key="a:b")

    result = await provider.generate("a face", out_path=tmp_path / "still")

    assert result.path.read_bytes() == PNG
    assert result.meta["request_id"] == "r1"


async def test_a_timed_out_poll_keeps_waiting_instead_of_abandoning_the_job(tmp_path,
                                                                           monkeypatch):
    """The job is running on their side and will be billed either way.

    Giving up on the first slow poll throws away something already paid for, so a timeout
    mid-poll backs off and asks again.
    """
    state = {"polls": 0}

    def poll(request: httpx.Request) -> httpx.Response:
        state["polls"] += 1
        if state["polls"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"status": "completed",
                                         "images": [{"url": ASSET}]})

    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        poll,
        poll,
        httpx.Response(200, content=PNG),
    ])
    _no_sleep(monkeypatch)
    provider = hf.HiggsfieldProvider(api_key="a:b")

    result = await provider.generate("a face", out_path=tmp_path / "still")

    assert result.path.exists()
    assert state["polls"] >= 2, "the first timeout must not have ended the wait"


async def test_a_refused_prompt_is_reported_as_a_refusal_not_a_failure(tmp_path,
                                                                      monkeypatch):
    """`nsfw` is a moderation decision, and the fix is a rewritten prompt.

    Calling it a failure sends someone to check their key, their network and their balance
    for something none of those will explain.
    """
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "nsfw"}),
    ])
    _no_sleep(monkeypatch)
    provider = hf.HiggsfieldProvider(api_key="a:b")

    with pytest.raises(ProviderError) as caught:
        await provider.generate("something", out_path=tmp_path / "still")

    message = str(caught.value)
    assert "declined" in message and "Rewrite the prompt" in message
    assert "failed" not in message


async def test_a_real_failure_carries_the_vendors_detail(tmp_path, monkeypatch):
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "failed", "detail": "model overloaded"}),
    ])
    _no_sleep(monkeypatch)

    with pytest.raises(ProviderError, match="model overloaded"):
        await hf.HiggsfieldProvider(api_key="a:b").generate(
            "x", out_path=tmp_path / "still")


async def test_running_past_the_budget_says_the_job_was_not_cancelled(tmp_path,
                                                                     monkeypatch):
    """Because it may still finish, and paying for a second one would be the mistake."""
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "in_progress"}),
    ])
    _no_sleep(monkeypatch)
    provider = hf.HiggsfieldProvider(api_key="a:b")

    job = await provider.submit(hf.SOUL_STANDARD, {"prompt": "x"})
    with pytest.raises(ProviderTimeout) as caught:
        await provider.wait(job, budget_seconds=5.0)

    assert "not been cancelled" in str(caught.value)
    assert "r1" in str(caught.value)


async def test_a_completed_job_with_no_asset_is_an_error(tmp_path, monkeypatch):
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "queued"}),
        httpx.Response(200, json={"status": "completed"}),
    ])
    _no_sleep(monkeypatch)

    with pytest.raises(ProviderError, match="no asset"):
        await hf.HiggsfieldProvider(api_key="a:b").generate(
            "x", out_path=tmp_path / "still")


# ------------------------------------------------------------------- the request


async def test_the_model_id_is_the_path(tmp_path, monkeypatch):
    """Not a body field. A wrong id is a 404 on a URL, which is why it is named as one."""
    recorder: dict = {}
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "completed",
                                  "images": [{"url": ASSET}]}),
        httpx.Response(200, content=PNG),
    ], recorder)

    await hf.HiggsfieldProvider(api_key="a:b").generate("x", out_path=tmp_path / "s")

    assert str(recorder["calls"][0].url).endswith(f"/{hf.SOUL_STANDARD}")


async def test_an_unknown_model_says_it_is_a_model_id_problem(tmp_path, monkeypatch):
    _serve(monkeypatch, [httpx.Response(404, text="Not Found")])

    with pytest.raises(ProviderError) as caught:
        await hf.HiggsfieldProvider(api_key="a:b", model="nope/nope").generate(
            "x", out_path=tmp_path / "s")

    assert "no such model" in str(caught.value)
    assert "higgsfield model list" in str(caught.value)


async def test_extra_parameters_pass_through_untouched(tmp_path, monkeypatch):
    """The mechanism that makes a Soul identity reachable without guessing its field name.

    Per-model parameters are not publicly documented, so inventing one — `soul_id` when the
    API wants `character_id` — produces a request the service silently ignores and a bill
    for a picture of the wrong person. Passing them through verbatim moves that decision to
    the caller, who can read the real schema from `higgsfield model`.
    """
    recorder: dict = {}
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "completed",
                                  "images": [{"url": ASSET}]}),
        httpx.Response(200, content=PNG),
    ], recorder)

    result = await hf.HiggsfieldProvider(api_key="a:b").generate(
        "the inventor", out_path=tmp_path / "s",
        params={"soul_id": "abc-123", "seed": 7})

    body = recorder["calls"][0].read().decode()
    assert '"soul_id":"abc-123"' in body
    assert '"seed":7' in body
    # Recorded on the artefact, so a run that used an identity can be told apart from one
    # that did not without re-reading the request.
    assert result.meta["params"] == ["seed", "soul_id"]


async def test_a_caller_parameter_overrides_the_derived_default(tmp_path, monkeypatch):
    """`params` is merged *over* the three documented fields, not under them."""
    recorder: dict = {}
    _serve(monkeypatch, [
        httpx.Response(200, json={"request_id": "r1", "status": "completed",
                                  "images": [{"url": ASSET}]}),
        httpx.Response(200, content=PNG),
    ], recorder)

    await hf.HiggsfieldProvider(api_key="a:b").generate(
        "x", out_path=tmp_path / "s", width=1920, height=1080,
        params={"resolution": "480p"})

    body = recorder["calls"][0].read().decode()
    assert '"resolution":"480p"' in body
    assert '"aspect_ratio":"16:9"' in body


@pytest.mark.parametrize(("width", "height", "ratio"), [
    (1920, 1080, "16:9"), (1080, 1920, "9:16"), (1024, 1024, "1:1"),
    (1200, 900, "4:3"),
])
def test_the_aspect_ratio_is_one_of_the_names_the_api_accepts(width, height, ratio):
    """`aspect_ratio` is an enumerated string on their side.

    A computed `"1.7777:1"` is not a value, so sending one is a rejected request for the
    sake of arithmetic nobody asked for.
    """
    assert hf._ratio(width, height) == ratio


def test_the_video_shape_of_the_response_is_read_too():
    """One endpoint returns `images` or `video` depending on the model.

    Reading only `images` works until someone points this at Kling.
    """
    assert hf._first_asset({"video": {"url": "https://x.invalid/a.mp4"}}) \
        == "https://x.invalid/a.mp4"
    assert hf._first_asset({"images": [{"url": ASSET}]}) == ASSET
    assert hf._first_asset({"status": "completed"}) == ""


# -------------------------------------------------------------------- the routing


def test_higgsfield_is_never_fallen_back_to():
    """It bills per generation, so it is chosen or it is not used."""
    assert "higgsfield" not in DEFAULT_ROUTING[Capability.image]
    assert "fal" in DEFAULT_ROUTING[Capability.image]


def test_but_naming_it_resolves_to_it():
    capability, klass, key_name = CATALOGUE["higgsfield"]
    assert capability is Capability.image
    assert klass is hf.HiggsfieldProvider
    # Its own key name — it cannot be satisfied by the fal credential.
    assert key_name == "higgsfield"

    registry = ProviderRegistry(mode="live", user_keys={"higgsfield": "a:b"},
                                overrides={"image": "higgsfield"})
    assert isinstance(registry.image(), hf.HiggsfieldProvider)
