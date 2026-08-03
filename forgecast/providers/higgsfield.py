"""Higgsfield: identity that survives across shots and across episodes.

## Why this vendor, when fal already makes stills

Because it closes a gap rather than adding a fourth way to do something the app already
does. Forgecast's image node runs Flux through fal, and Flux invents a new face on every
call. Thirty shots of "the inventor" in one video are thirty different men, and next
week's episode is a thirty-first. On a channel built around a recurring character — an
animated host, a historical figure who returns, a mascot — that is the most visible defect
in the finished video, and nothing else in this codebase addresses it.

Higgsfield's Soul family is the answer to exactly that: a trained identity referenced by
id, so the same face comes back. It also fronts Kling, Veo and Seedance behind one
credential, which is *useful* but not a gap — fal and Runway already cover generation.
So the reason this file exists is Soul, and the video path is a bonus that costs nothing
extra to expose because it is the same endpoint.

## Why it is opt-in and stays opt-in

It bills against a Higgsfield credit balance, per generation, and the operator said so
before it was built. It is therefore absent from `DEFAULT_ROUTING` — reachable by being
chosen per channel, never by being fallen back to when another key is missing. A vendor
that can start spending because a different vendor's key expired is a vendor that will.

## What is asserted here and what is not

The endpoint shape below is from Higgsfield's own API documentation and was confirmed
against the live service: `POST https://platform.higgsfield.ai/{model_id}` with
`Authorization: Key {key}:{secret}` answers 401 `{"detail":"Invalid credentials"}`
unauthenticated, `GET` on a model path answers 405, and
`/requests/{id}/status` exists and is authenticated. The documented request fields are
`prompt`, `aspect_ratio` and `resolution`; the response carries `status`, `request_id`,
`status_url`, `cancel_url`, and on completion `images[].url` or `video.url`, with statuses
`queued`, `in_progress`, `nsfw`, `failed`, `completed`.

Everything **beyond** those three fields is per-model and is not documented publicly, so
this adapter does not invent names for it: extra parameters pass through verbatim from the
caller in `params`. That is deliberate. Guessing that a Soul reference is called
`soul_id` rather than `character_id` or `reference_id` would produce a request the API
silently ignores, and the symptom is a bill for a picture of the wrong person. The real
names come from `higgsfield model` in their CLI or from the MCP server's own schema, and
they are passed in rather than hard-coded here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .base import Capability, ImageProvider, MediaResult, ProviderError, ProviderTimeout

log = logging.getLogger("forgecast.providers.higgsfield")

BASE_URL = "https://platform.higgsfield.ai"

# One request's ceiling, and the poll loop's. A video generation is minutes, not seconds,
# so the submit timeout and the wait budget are separate numbers — a short submit timeout
# with a long wait is what lets a stuck submit fail fast while a slow render still lands.
SUBMIT_TIMEOUT = 60.0
POLL_TIMEOUT = 30.0
WAIT_SECONDS = 900.0

# Backs off from half a second to eight. A fixed one-second poll on a six-minute video is
# 360 requests for one clip; this is about 30.
POLL_START = 0.5
POLL_MAX = 8.0

# The vendor's own status vocabulary. `nsfw` is a *refusal*, not an error — the request
# was understood, judged and declined — so it is separated from `failed` and reported in
# those words, because "generation failed" sends someone to check their key.
TERMINAL_OK = "completed"
TERMINAL_BAD = ("failed", "nsfw", "cancelled", "canceled")

# Model ids are vendor-namespaced paths, not slugs, and they are the URL. Defaulted to the
# Soul model because that is the reason this provider exists; anything else is one
# constructor argument away.
SOUL_STANDARD = "higgsfield-ai/soul/standard"


@dataclass
class Job:
    """A submitted generation, as the fields worth keeping from the submit response."""

    request_id: str
    status: str = ""
    status_url: str = ""
    cancel_url: str = ""
    # The submit response in full. Kept because a fast model can answer `completed` on
    # submit with the asset already in it, and polling for something already in hand is a
    # wasted round trip per generation.
    payload: dict = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.status.lower() == TERMINAL_OK


class HiggsfieldProvider(ImageProvider):
    """Stills — and, through the same endpoint, clips.

    Registered as an image provider because the identity-consistency case is a still
    problem: the plate is what carries the face, and the i2v step animates a plate that is
    already right. Naming it under `Capability.image` also keeps it out of the video
    routing chain, where fal and Runway are already priced and tested.
    """

    name = "higgsfield"
    capability = Capability.image
    base_url = BASE_URL

    # Higgsfield prices per generation against a credit balance, and does not publish a
    # per-model rate that could be pinned here honestly. So this is the fallback estimate
    # for the ledger, and it is deliberately not pretending to be exact: `account` in
    # their CLI is where the real balance lives, and the meta on every result carries the
    # model so a run can be reconciled against their statement.
    usd_per_generation = 0.08

    def __init__(self, api_key: str = "", model: str = SOUL_STANDARD) -> None:
        # The credential is a pair joined by a colon — `Key {id}:{secret}` — so it is
        # carried as one opaque string rather than split, which keeps it in the same shape
        # as every other provider key in the settings table.
        super().__init__(api_key)
        self.model = model

    # ------------------------------------------------------------------ credential

    def _headers(self) -> dict[str, str]:
        key = self._require_key()
        if ":" not in key:
            raise ProviderError(
                "the Higgsfield credential is a pair — paste it as "
                "`key:secret`, both halves from platform.higgsfield.ai. A single value "
                "is rejected as invalid credentials with no further explanation.",
                provider=self.name)
        return {"Authorization": f"Key {key}", "Content-Type": "application/json"}

    # -------------------------------------------------------------------- the calls

    async def submit(self, model: str, body: dict) -> Job:
        """Start one generation. The model id *is* the path."""
        headers = self._headers()
        url = f"{self.base_url}/{model.strip('/')}"
        try:
            async with httpx.AsyncClient(timeout=SUBMIT_TIMEOUT) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        if response.status_code == 401:
            raise ProviderError(
                "Higgsfield rejected the credential. It is `key:secret` from "
                "platform.higgsfield.ai, and both halves are needed.", provider=self.name)
        if response.status_code == 404:
            # A wrong model id is a 404 on a URL, which reads like an outage rather than a
            # typo unless it is named.
            raise ProviderError(
                f"no such model {model!r}. Model ids are namespaced paths such as "
                f"{SOUL_STANDARD!r} — list them with `higgsfield model list`.",
                provider=self.name)
        if response.status_code >= 500:
            raise ProviderTimeout(f"Higgsfield returned {response.status_code}",
                                  provider=self.name)
        if response.status_code >= 400:
            raise ProviderError(f"{response.status_code}: {response.text[:300]}",
                                provider=self.name)

        payload = response.json()
        request_id = str(payload.get("request_id") or payload.get("id") or "")
        if not request_id:
            raise ProviderError(f"no request_id in the response: {response.text[:200]}",
                                provider=self.name)
        return Job(request_id=request_id,
                   status=str(payload.get("status") or "queued"),
                   status_url=str(payload.get("status_url") or ""),
                   cancel_url=str(payload.get("cancel_url") or ""),
                   payload=payload)

    async def wait(self, job: Job, *, budget_seconds: float = WAIT_SECONDS) -> dict:
        """Poll until terminal, and translate the terminal states into sentences."""
        headers = self._headers()
        url = job.status_url or f"{self.base_url}/requests/{job.request_id}/status"
        delay = POLL_START
        waited = 0.0

        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            while waited < budget_seconds:
                try:
                    response = await client.get(url, headers=headers)
                except httpx.TimeoutException:
                    # A timed-out poll is not a failed generation. The job is still
                    # running on their side, so this backs off and asks again rather than
                    # abandoning something already paid for.
                    response = None

                if response is not None and response.status_code < 400:
                    payload = response.json()
                    status = str(payload.get("status") or "").lower()
                    if status == TERMINAL_OK:
                        return payload
                    if status in TERMINAL_BAD:
                        raise ProviderError(self._why(status, payload),
                                            provider=self.name)
                elif response is not None and response.status_code == 404:
                    raise ProviderError(
                        f"Higgsfield does not know request {job.request_id}",
                        provider=self.name)

                await asyncio.sleep(delay)
                waited += delay
                delay = min(POLL_MAX, delay * 1.6)

        raise ProviderTimeout(
            f"generation {job.request_id} was still running after "
            f"{int(budget_seconds)}s. It has not been cancelled, so it may finish — "
            f"check it with `higgsfield generate get {job.request_id}` before paying for "
            f"another.", provider=self.name)

    def _why(self, status: str, payload: dict) -> str:
        detail = str(payload.get("detail") or payload.get("error") or "").strip()
        if status == "nsfw":
            # Distinct wording on purpose. This is a moderation decision about the
            # prompt, and reporting it as a failure sends the operator to check their key
            # and their network for something only a rewritten prompt will fix.
            return ("Higgsfield declined this prompt on content grounds — it was "
                    "understood and refused, not broken. Rewrite the prompt."
                    + (f" ({detail})" if detail else ""))
        return f"generation {status}{': ' + detail if detail else ''}"

    # ----------------------------------------------------------------- the interface

    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720,
        params: dict | None = None, model: str = "",
    ) -> MediaResult:
        """One still.

        `params` is passed through untouched and merged over the documented three. That is
        the mechanism by which a Soul identity, a preset, a seed or any other per-model
        field reaches the API without this file guessing its name — see the module
        docstring for why guessing would be worse than not supporting it.
        """
        model = model or self.model
        body: dict = {
            "prompt": prompt,
            "aspect_ratio": _ratio(width, height),
            "resolution": _resolution(width, height),
        }
        body.update(params or {})

        job = await self.submit(model, body)
        # Only poll if there is something to wait for. A model that finishes inside the
        # submit call returns the asset with it, and asking again for what is already here
        # is one avoidable request on every single generation.
        payload = job.payload if (job.finished and _first_asset(job.payload)) \
            else await self.wait(job)

        url = _first_asset(payload)
        if not url:
            raise ProviderError(
                f"generation {job.request_id} completed with no asset in the response",
                provider=self.name)

        out_path = out_path.with_suffix(_suffix(url))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await _download(url, out_path)

        return MediaResult(
            path=out_path,
            mime="image/png" if out_path.suffix == ".png" else "image/jpeg",
            credits=_credits(self.usd_per_generation),
            provider=self.name,
            meta={"model": model, "request_id": job.request_id,
                  # Named so a run can be reconciled against a Higgsfield statement,
                  # since the per-generation price is theirs to set and not published.
                  "billing": "higgsfield credit balance",
                  "params": sorted((params or {}).keys())},
        )


# ------------------------------------------------------------------------- helpers


def _ratio(width: int, height: int) -> str:
    """The nearest ratio this API names, rather than a computed fraction.

    `aspect_ratio` is an enumerated string on their side, so `"1.7777:1"` is not a value —
    sending one is a rejected request for the sake of arithmetic nobody asked for.
    """
    if height <= 0:
        return "16:9"
    value = width / height
    known = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4,
             "3:2": 3 / 2, "2:3": 2 / 3}
    return min(known, key=lambda name: abs(known[name] - value))


def _resolution(width: int, height: int) -> str:
    """Their tiers, chosen from the short edge — which is what a tier name means."""
    short = min(width, height) if width and height else 720
    for tier, floor in (("1080p", 1000), ("720p", 700), ("480p", 0)):
        if short >= floor:
            return tier
    return "720p"


def _first_asset(payload: dict) -> str:
    """The URL of whatever came back, image or video.

    Both shapes are documented and one endpoint returns either depending on the model, so
    reading only `images` would work until the day someone points this at Kling.
    """
    images = payload.get("images") or []
    if isinstance(images, list):
        for entry in images:
            if isinstance(entry, dict) and entry.get("url"):
                return str(entry["url"])
    video = payload.get("video")
    if isinstance(video, dict) and video.get("url"):
        return str(video["url"])
    results = payload.get("results") or payload.get("result")
    if isinstance(results, dict) and results.get("url"):
        return str(results["url"])
    return ""


def _suffix(url: str) -> str:
    lowered = url.split("?")[0].lower()
    for candidate in (".png", ".jpg", ".jpeg", ".webp", ".mp4"):
        if lowered.endswith(candidate):
            return candidate
    return ".png"


async def _download(url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=SUBMIT_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            if response.status_code >= 400:
                raise ProviderError(
                    f"the finished asset would not download ({response.status_code})",
                    provider="higgsfield")
            with out_path.open("wb") as handle:
                async for chunk in response.aiter_bytes(65536):
                    handle.write(chunk)


def _credits(usd: float) -> int:
    from .media import _credits as convert

    return convert(usd)
