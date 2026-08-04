"""Media vendor adapters: ElevenLabs (voice), FAL (image), Runway/Kling (video),
HeyGen (avatar).

A caution worth keeping in the code: generative-media APIs change shape more often
than LLM APIs do. Endpoints, model slugs and polling contracts below reflect the
documented public shapes at the time of writing — verify each against current vendor
docs before you switch `FORGECAST_PROVIDER_MODE=live`, and keep `mock` as the way
you develop. Every adapter isolates its vendor quirks behind the same small
interface, so a breaking change costs you one file, not the pipeline.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..credits import USD_PER_CREDIT
from .base import (
    AvatarProvider,
    ImageProvider,
    MediaResult,
    ProviderError,
    ProviderTimeout,
    VideoProvider,
    VoiceProvider,
)

_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)
_MARKUP = 2.0  # charge the user 2x provider cost


def _credits(usd: float) -> int:
    return max(1, round(usd * _MARKUP / USD_PER_CREDIT))


def _check(response: httpx.Response, provider: str) -> None:
    if response.is_success:
        return
    retryable = response.status_code == 429 or response.status_code >= 500
    raise ProviderError(
        f"{provider} returned {response.status_code}: {_body(response)}",
        provider=provider,
        retryable=retryable,
    )


async def _acheck(response: httpx.Response, provider: str) -> None:
    """`_check` for a streaming response.

    A streamed response has no body until it is read, and `response.text` raises
    `ResponseNotRead` instead of returning one. That turned every ElevenLabs API
    error into an httpx exception about streaming, which says nothing about what the
    API actually objected to — a wrong voice id and an expired key looked identical,
    and neither message named the real problem.
    """
    if response.is_success:
        return
    with contextlib.suppress(httpx.HTTPError):
        await response.aread()
    _check(response, provider)


def _body(response: httpx.Response) -> str:
    """The error body, or an explanation of why there is not one."""
    try:
        return response.text[:400]
    except httpx.ResponseNotRead:  # pragma: no cover - guarded by _acheck
        return "<streaming body not read>"


async def _download(client: httpx.AsyncClient, url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with client.stream("GET", url) as response:
        _check(response, "download")
        with out_path.open("wb") as handle:
            async for chunk in response.aiter_bytes(65536):
                handle.write(chunk)
    return out_path


# ------------------------------------------------------------------------- voice


class ElevenLabsProvider(VoiceProvider):
    name = "elevenlabs"
    base_url = "https://api.elevenlabs.io/v1"
    # Creator-tier effective rate; adjust to your contract.
    usd_per_1k_chars = 0.15

    def __init__(self, api_key: str = "", model: str = "eleven_multilingual_v2") -> None:
        super().__init__(api_key)
        self.model = model

    async def list_voices(self) -> list[dict]:
        """Voices available on this account, for resolving catalogue names to IDs.

        Casting works from names because IDs vary per account and cannot be verified
        offline; this is where a name becomes something synthesizable.
        """
        key = self._require_key()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/voices", headers={"xi-api-key": key}
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        _check(response, self.name)

        voices = response.json().get("voices") or []
        return [
            {
                "voice_id": entry.get("voice_id"),
                "name": entry.get("name"),
                "category": entry.get("category"),
                "labels": entry.get("labels") or {},
                "preview_url": entry.get("preview_url"),
            }
            for entry in voices
        ]

    async def list_shared_voices(
        self,
        *,
        language: str = "en",
        page_size: int = 100,
        max_voices: int = 3000,
        use_cases: tuple[str, ...] = (),
    ) -> list[dict]:
        """Page through the public shared voice library.

        There are ~15,000 shared voices, so this filters server-side and caps the
        walk. Metadata only — measuring every preview would mean 15,000 downloads,
        which is why casting measures pitch for a pre-ranked shortlist instead.
        """
        key = self._require_key()
        collected: list[dict] = []
        page_index = 0

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            while len(collected) < max_voices:
                # Paging is `page`/`page_size`. The response also carries a
                # `last_sort_id`, which is not a request parameter — passing it as one
                # is silently ignored and every request returns page 0, capping the
                # walk at 100 voices.
                params: dict = {"page": page_index, "page_size": min(page_size, 100)}
                if language:
                    params["language"] = language
                if use_cases:
                    params["use_cases"] = list(use_cases)

                response = await client.get(
                    f"{self.base_url}/shared-voices",
                    headers={"xi-api-key": key},
                    params=params,
                )
                _check(response, self.name)
                payload = response.json()
                page = payload.get("voices") or []
                if not page:
                    break

                for entry in page:
                    collected.append(
                        {
                            "voice_id": entry.get("voice_id"),
                            "name": entry.get("name"),
                            "category": entry.get("category") or "shared",
                            # Explicit, because BOTH endpoints return `category`
                            # and only /voices implies the account owns it. The
                            # shared endpoint reports category="professional" for
                            # community pro-cloned voices, which would otherwise
                            # read as "your professional voice".
                            "provenance": "library",
                            "labels": {
                                "gender": entry.get("gender"),
                                "accent": entry.get("accent"),
                                "age": entry.get("age"),
                                "use_case": entry.get("use_case"),
                                "descriptive": entry.get("descriptive"),
                                "language": entry.get("language"),
                            },
                            "preview_url": entry.get("preview_url"),
                            "cloned_by_count": entry.get("cloned_by_count") or 0,
                            "featured": bool(entry.get("featured")),
                        }
                    )

                if not payload.get("has_more"):
                    break
                page_index += 1

        return collected[:max_voices]

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        key = self._require_key()
        if not voice_id:
            raise ProviderError("no voice_id set on the channel", provider=self.name)
        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        body = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "speed": speed},
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client, client.stream(
                "POST",
                f"{self.base_url}/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "accept": "audio/mpeg"},
                json=body,
            ) as response:
                await _acheck(response, self.name)
                with out_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes(65536):
                        handle.write(chunk)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        from ..render import ffmpeg as ff

        duration = await asyncio.to_thread(ff.ffprobe_duration, out_path)
        usd = len(text) / 1000 * self.usd_per_1k_chars
        return MediaResult(
            path=out_path,
            mime="audio/mpeg",
            credits=_credits(usd),
            provider=self.name,
            duration_seconds=duration,
            meta={"characters": len(text), "voice_id": voice_id, "model": self.model},
        )


class MiniMaxVoiceProvider(VoiceProvider):
    """MiniMax T2A v2, as the second narration vendor.

    ## Why it exists next to ElevenLabs rather than instead of it

    Both are wanted, and which one a run uses is the operator's choice per channel. The
    reason to say that out loud is that the two are paid for differently and neither one
    can be made to look like the other:

    * **ElevenLabs** issues an API key against the subscription, so narration comes out of
      the plan's character allowance that is already paid for.
    * **MiniMax** bills text-to-speech against the API balance. The MiniMax *subscription*
      covers the agent and the chat CLI, not T2A — there is no token, no CLI subcommand and
      no OAuth scope that routes speech through the plan. That was checked before this
      class was written, and the honest answer went into the docstring instead of a
      hopeful implementation.

    So enabling MiniMax voice spends MiniMax credit and enabling ElevenLabs spends the
    ElevenLabs allowance, which is exactly the behaviour asked for. What this class must
    not do is quietly stand in for a missing ElevenLabs key, because that would move
    someone's spend from a plan they have to a balance they are drawing down; it is
    therefore absent from `DEFAULT_ROUTING` and reachable only by being chosen.

    ## The trap in this API

    A failure arrives as **HTTP 200** with `base_resp.status_code` non-zero. Trusting the
    status line means writing an empty file, calling it a voiceover, and finding out at the
    render when a 13-minute video has silence where the narration goes. `_check` cannot see
    that, so the body is inspected here as well.
    """

    name = "minimax-voice"
    # The global endpoint. `api-uw` is the lower-latency US alias of the same service and
    # `api.minimaxi.chat` is the mainland-China deployment — a key issued for one region is
    # rejected by the other, so this is settable rather than baked in.
    base_url = "https://api.minimax.io/v1"

    # $100 per million characters for the HD models, $60 for turbo. HD is the default
    # because narration is the use case: turbo exists for sub-250 ms conversational
    # latency, which a pre-rendered voiceover has no use for and pays for in quality.
    usd_per_1k_chars = 0.10
    TURBO_USD_PER_1K_CHARS = 0.06

    # A single request's ceiling, from the API reference. A 10,000-character script is
    # about 11 minutes of speech, so long videos need splitting — checked here so the
    # failure is a sentence rather than a rejected request halfway through a run.
    MAX_CHARACTERS = 10_000

    def __init__(self, api_key: str = "", model: str = "speech-2.6-hd",
                 base_url: str = "") -> None:
        super().__init__(api_key)
        self.model = model
        if base_url:
            self.base_url = base_url.rstrip("/")

    def _rate(self) -> float:
        return (self.TURBO_USD_PER_1K_CHARS if "turbo" in self.model
                else self.usd_per_1k_chars)

    async def list_voices(self) -> list[dict]:
        """MiniMax's system voices, in the shape the casting code already reads.

        The catalogue is static per model rather than per account — there is no
        `GET /voices` for the built-in set — so it is returned from here instead of
        fetched. Cloned voices live on the account and are used by passing their id
        straight through as `voice_id`, which is why this list is not a whitelist.
        """
        return [
            {"voice_id": voice_id, "name": label, "category": "premade",
             "labels": {"gender": gender, "language": "en"}, "preview_url": ""}
            for voice_id, label, gender in (
                ("English_Graceful_Lady", "Graceful Lady", "female"),
                ("English_ConfidentWoman", "Confident Woman", "female"),
                ("English_Trustworth_Man", "Trustworthy Man", "male"),
                ("English_CalmWoman", "Calm Woman", "female"),
                ("English_Deep-VoicedGentleman", "Deep-Voiced Gentleman", "male"),
                ("English_ReservedYoungMan", "Reserved Young Man", "male"),
                ("English_PatientMan", "Patient Man", "male"),
                ("English_Wiselady", "Wise Lady", "female"),
            )
        ]

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        key = self._require_key()
        if not voice_id:
            raise ProviderError("no voice_id set on the channel", provider=self.name)
        if len(text) > self.MAX_CHARACTERS:
            raise ProviderError(
                f"{len(text)} characters is over this API's {self.MAX_CHARACTERS} limit "
                f"for one request — split the script by section and concatenate",
                provider=self.name)

        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        body = {
            "model": self.model,
            "text": text,
            "stream": False,
            "language_boost": "auto",
            # Hex rather than a URL: a returned URL expires and would need a second
            # request that can fail on its own, for a file this already has in hand.
            "output_format": "hex",
            "voice_setting": {"voice_id": voice_id,
                              # 0.5 to 2.0. Clamped rather than passed through, because
                              # out-of-range is a rejected request and the caller's speed
                              # comes from a style profile that knows nothing about it.
                              "speed": min(2.0, max(0.5, speed)),
                              "vol": 1.0, "pitch": 0},
            # 44.1 kHz/128 kbps mono. The voiceover is mastered downstream and mixed
            # against beds, so this is the last place to be stingy about the source.
            "audio_setting": {"sample_rate": 44100, "bitrate": 128000,
                              "format": "mp3", "channel": 1},
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/t2a_v2",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        _check(response, self.name)

        payload = response.json()
        status = (payload.get("base_resp") or {})
        if int(status.get("status_code") or 0) != 0:
            # The 200-with-an-error case. Raised rather than logged: a caller that gets a
            # MediaResult back has been told there is a voiceover on disk.
            raise ProviderError(
                f"{status.get('status_msg') or 'rejected'} "
                f"(code {status.get('status_code')})", provider=self.name)

        audio_hex = ((payload.get("data") or {}).get("audio") or "")
        if not audio_hex:
            raise ProviderError("the response carried no audio", provider=self.name)
        try:
            audio = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise ProviderError(f"the audio was not valid hex: {exc}",
                                provider=self.name) from exc
        out_path.write_bytes(audio)

        extra = payload.get("extra_info") or {}
        # `audio_length` is milliseconds and is the vendor's own measurement, so it is
        # preferred over probing the file — but it is not trusted blindly, because a
        # missing field would otherwise become a zero-length voiceover that the render
        # silently drops.
        duration = float(extra.get("audio_length") or 0) / 1000.0
        if duration <= 0:
            from ..render import ffmpeg as ff
            duration = await asyncio.to_thread(ff.ffprobe_duration, out_path)

        characters = int(extra.get("usage_characters") or len(text))
        usd = characters / 1000 * self._rate()
        return MediaResult(
            path=out_path,
            mime="audio/mpeg",
            credits=_credits(usd),
            provider=self.name,
            duration_seconds=duration,
            meta={"characters": characters, "voice_id": voice_id, "model": self.model,
                  "billing": "minimax api balance"},
        )


# ------------------------------------------------------------------------- image


class FalImageProvider(ImageProvider):
    """FAL runs many image models behind one queue API; the slug picks the model."""

    name = "fal"
    base_url = "https://fal.run"
    usd_per_image = 0.04

    def __init__(self, api_key: str = "", model: str = "fal-ai/flux/dev") -> None:
        super().__init__(api_key)
        self.model = model

    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720
    ) -> MediaResult:
        key = self._require_key()
        out_path = out_path.with_suffix(".png")
        body = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "output_format": "png",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/{self.model}",
                    headers={"Authorization": f"Key {key}"},
                    json=body,
                )
                _check(response, self.name)
                payload = response.json()
                images = payload.get("images") or []
                if not images or not images[0].get("url"):
                    raise ProviderError(
                        f"{self.name} returned no image", provider=self.name, retryable=True
                    )
                await _download(client, images[0]["url"], out_path)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        return MediaResult(
            path=out_path,
            mime="image/png",
            credits=_credits(self.usd_per_image),
            provider=self.name,
            meta={"model": self.model, "prompt": prompt[:300]},
        )


# ------------------------------------------------------------------------- video


class RunwayVideoProvider(VideoProvider):
    """Async task API: submit, then poll until the task reports SUCCEEDED."""

    name = "runway"
    base_url = "https://api.dev.runwayml.com/v1"
    api_version = "2024-11-06"
    usd_per_second = 0.05

    def __init__(self, api_key: str = "", model: str = "gen4_turbo") -> None:
        super().__init__(api_key)
        self.model = model

    async def generate_clip(
        self,
        prompt: str,
        *,
        out_path: Path,
        seconds: float = 5.0,
        width: int = 1280,
        height: int = 720,
        image_path: Path | None = None,
    ) -> MediaResult:
        key = self._require_key()
        out_path = out_path.with_suffix(".mp4")
        headers = {
            "Authorization": f"Bearer {key}",
            "X-Runway-Version": self.api_version,
            "content-type": "application/json",
        }
        # Runway's video models are image-conditioned: a still plate is required.
        if image_path is None or not Path(image_path).exists():
            raise ProviderError(
                "runway image_to_video needs a source still — generate the plate first",
                provider=self.name,
            )
        body = {
            "model": self.model,
            "promptImage": _data_uri(Path(image_path)),
            "promptText": prompt[:1000],
            "duration": int(max(5, min(10, round(seconds)))),
            "ratio": f"{width}:{height}",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/image_to_video", headers=headers, json=body
                )
                _check(response, self.name)
                task_id = response.json().get("id")
                if not task_id:
                    raise ProviderError("runway did not return a task id", provider=self.name)
                url = await self._poll(client, task_id, headers)
                await _download(client, url, out_path)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        return MediaResult(
            path=out_path,
            mime="video/mp4",
            credits=_credits(self.usd_per_second * seconds),
            provider=self.name,
            duration_seconds=seconds,
            meta={"model": self.model, "prompt": prompt[:300]},
        )

    async def _poll(
        self, client: httpx.AsyncClient, task_id: str, headers: dict, *, limit: int = 120
    ) -> str:
        for attempt in range(limit):
            await asyncio.sleep(min(2 + attempt * 0.5, 10))
            response = await client.get(f"{self.base_url}/tasks/{task_id}", headers=headers)
            _check(response, self.name)
            payload = response.json()
            status = (payload.get("status") or "").upper()
            if status == "SUCCEEDED":
                outputs = payload.get("output") or []
                if outputs:
                    return outputs[0]
                raise ProviderError("runway succeeded with no output", provider=self.name)
            if status in {"FAILED", "CANCELLED"}:
                raise ProviderError(
                    f"runway task {status}: {payload.get('failure', '')}",
                    provider=self.name,
                    retryable=status == "FAILED",
                )
        raise ProviderTimeout(f"runway task {task_id} never finished", provider=self.name)


# --------------------------------------------------------------- the video catalogue
#
# Image-to-video prices span forty times across the models this app routes to: $0.03 a
# second and $0.40 a second are both normal. A single flat rate therefore makes every
# estimate wrong in one direction or the other, and the direction that hurts is the cheap
# one — a reserve taken at $0.09/sec against a $0.40/sec model promises credits the ledger
# does not hold, and the run dies partway through a batch having already spent.
#
# Each entry also carries the shortest duration the endpoint will accept, because that is
# what the Sample Gate in `forgecast/skills/data/image-to-video.md` renders its one sample
# at. Hard-coding five seconds there quietly overspends on every model whose minimum is
# six, and fails outright on the ones that refuse it.
#
# PRICES DRIFT, AND THESE ARE ALREADY EVIDENCE OF IT. Checked against fal's own model
# pages on 2026-08-03, the operational skill's own table was out by more than 3x in both
# directions — it had Kling v3 Pro at $0.40/sec against a published $0.112, and WAN 2.2
# A14B at $0.02/sec against a published $0.08. Re-check before trusting a quote, and treat
# the numbers below as a floor for reserving rather than as a contract.
PRICES_CHECKED = "2026-08-03"


@dataclass(frozen=True)
class VideoModel:
    """One i2v endpoint's price, duration envelope, and how to spell a request to it.

    `sample_seconds` is the shortest submittable duration, not a recommendation: it is
    what the sample gate costs on this model, and the gate is priced before it runs.

    ## Why the call shape lives beside the price

    There is no convention across these endpoints and assuming one costs money three
    separate ways. Verified against each endpoint's own OpenAPI schema on the date in
    `PRICES_CHECKED`:

    * Kling wants `"5"`, LTX wants `6`, Veo wants `"6s"`, WAN takes no duration at all.
      One hardcoded `str(seconds)` served exactly two of the six families.
    * Durations are an **enum**, not a range. Six seconds is inside Sora's 4–20 envelope
      and Sora rejects it, because Sora accepts 4, 8, 12, 16, 20 and nothing between.
      Clamping to the ends of a range is not the same as choosing a value the endpoint
      will take.
    * Native audio defaults to **on** everywhere it exists, and it is separately billed —
      double the rate on Kling and Veo. This pipeline records narration on its own vendor
      and mixes it in the render, so every one of those seconds was paid for and
      discarded. The flag has to be sent; not sending it is not "leaving the default".

    So the table carries all three facts together. Whoever next re-checks a price is
    already looking at the row where the call shape lives.
    """

    usd_per_second: float
    # Every duration this endpoint accepts, ascending. Not a range — see the class
    # docstring. Where an endpoint takes no duration, its single natural clip length.
    durations: tuple[float, ...]
    note: str = ""
    # How this endpoint spells a duration in the request body:
    #   "string"   — "5"      (Kling, Hailuo)
    #   "integer"  — 6        (LTX, Sora)
    #   "suffixed" — "6s"     (Veo 3 and 3.1)
    #   "absent"   — the endpoint has no duration field, and sending one is an unknown
    #                key on a paid submission (WAN)
    spelling: str = "string"
    # The request field that turns native audio off, where the endpoint has one. Empty
    # means it has none and the quoted rate is already the only rate.
    audio_flag: str = ""

    @property
    def sample_seconds(self) -> float:
        """The shortest clip this endpoint will make, which is what a sample costs."""
        return min(self.durations)

    @property
    def max_seconds(self) -> float:
        return max(self.durations)

    def submittable(self, seconds: float) -> float:
        """The nearest duration this endpoint accepts, rounding up.

        Up rather than down, and it is not a close call. A shot rendered shorter than
        its scene leaves the timeline holding a frozen frame under live narration, which
        a viewer sees; a shot rendered longer is trimmed in assembly and costs the
        difference, which nobody sees. Content loss is the more expensive of the two
        even when it is the cheaper one.
        """
        wanted = float(seconds or 0.0)
        longer = [option for option in self.durations if option >= wanted]
        return longer[0] if longer else self.max_seconds


# Keyed by the fal slug. Resolutions matter to the price on several of these, so the tier
# the figure belongs to is named — a 720p price quoted for a 4K render under-reserves by
# the same mechanism a flat rate does.
VIDEO_MODELS: dict[str, VideoModel] = {
    # Kling. The workhorse for B-roll and dialogue close-ups; audio off, which is how
    # this pipeline uses it — narration is recorded separately and mixed in the render.
    "fal-ai/kling-video/v2.6/pro/image-to-video": VideoModel(
        0.07, (5.0, 10.0), "audio off; $0.14/s with native audio",
        audio_flag="generate_audio"),
    # No audio on this one, so its rate has no second tier and no flag to send.
    "fal-ai/kling-video/v2.5-turbo/pro/image-to-video": VideoModel(
        0.07, (5.0, 10.0), "$0.35 for the first 5s, then $0.07/s"),
    # The only model here that takes an arbitrary whole number of seconds, and the only
    # one that will go past ten — up to fifteen.
    "fal-ai/kling-video/v3/pro/image-to-video": VideoModel(
        0.112, tuple(float(n) for n in range(3, 16)),
        "audio off; $0.168/s with audio, $0.196/s with voice control",
        audio_flag="generate_audio"),
    # WAN, open weights. Priced per resolution tier; 720p is what this app renders at.
    # It has no duration field at all: the clip length is a property of the model, and a
    # `duration` key on the submission is an unrecognised field on a paid request.
    "fal-ai/wan/v2.2-a14b/image-to-video": VideoModel(
        0.08, (5.0,), "720p; $0.06/s at 580p, $0.04/s at 480p, seconds at 16fps. "
                      "Fixed clip length — the endpoint takes no duration",
        spelling="absent"),
    # Hailuo. The reason `sample_seconds` exists: its shortest generation is six
    # seconds, so its sample costs six seconds, not five.
    "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video": VideoModel(
        0.0317, (6.0, 10.0), "768p; $0.19 per 6s clip, $0.32 per 10s clip"),
    # LTX, the volume workhorse. Integer durations, not strings, and the fast variant
    # will run to twenty seconds where the standard one stops at ten.
    "fal-ai/ltx-2.3/image-to-video": VideoModel(
        0.06, (6.0, 8.0, 10.0), "1080p; $0.12/s at 1440p, $0.24/s at 2160p",
        spelling="integer", audio_flag="generate_audio"),
    "fal-ai/ltx-2.3/image-to-video/fast": VideoModel(
        0.04, tuple(float(n) for n in range(6, 21, 2)),
        "1080p; $0.08/s at 1440p, $0.16/s at 2160p",
        spelling="integer", audio_flag="generate_audio"),
    # Veo 3.1 — the model under Google Flow, which has no API of its own. Flow is a web
    # product; asking how to call it is the wrong question, and the right one is which
    # endpoint serves the same engine. These are it, and the rates are the audio-off ones
    # because this pipeline records narration separately and mixes it in the render.
    "fal-ai/veo3.1/lite/image-to-video": VideoModel(
        0.03, (4.0, 6.0, 8.0),
        "720p audio off; $0.05/s with audio, $0.05/s at 1080p audio off. Cheaper per "
        "second than every other model here, Hailuo included",
        spelling="suffixed", audio_flag="generate_audio"),
    "fal-ai/veo3.1/fast/image-to-video": VideoModel(
        0.10, (4.0, 6.0, 8.0),
        "720p/1080p audio off; $0.15/s with audio, $0.30/s at 4K audio off",
        spelling="suffixed", audio_flag="generate_audio"),
    "fal-ai/veo3.1/image-to-video": VideoModel(
        0.20, (4.0, 6.0, 8.0),
        "720p/1080p audio off; $0.40/s with audio, $0.40/s at 4K audio off",
        spelling="suffixed", audio_flag="generate_audio"),
    # The 3.0 endpoints, kept because runs made on them are still in the database and
    # their costs have to price correctly when a run is re-read. Not worth choosing: 3.1
    # lite is a fifth of the standard 3.0 rate and a later model.
    "fal-ai/veo3/image-to-video": VideoModel(
        0.20, (4.0, 6.0, 8.0), "superseded by veo3.1; audio off, $0.40/s with audio",
        spelling="suffixed", audio_flag="generate_audio"),
    "fal-ai/veo3/fast/image-to-video": VideoModel(
        0.10, (4.0, 6.0, 8.0),
        "superseded by veo3.1/fast; audio off, $0.15/s with audio",
        spelling="suffixed", audio_flag="generate_audio"),
    # Sora. The widest envelope here and the sparsest — twenty seconds available, but
    # only at 4, 8, 12, 16 and 20. Six seconds is inside the range and is rejected.
    "fal-ai/sora-2/image-to-video": VideoModel(
        0.10, (4.0, 8.0, 12.0, 16.0, 20.0),
        "720p standard; Pro is $0.30-$0.70/s", spelling="integer"),
}

# Kling v2.6 Pro rather than the v1 *text*-to-video slug this defaulted to before. Two
# reasons: every caller here passes a conditioning still, and a text-to-video endpoint
# handed an `image_url` either ignores it — billing for a clip of the wrong thing — or
# rejects the submission. And it is the model the i2v skill names as the reliable
# workhorse, at $0.07/sec against the $0.09 flat rate that used to be assumed.
DEFAULT_VIDEO_MODEL = "fal-ai/kling-video/v2.6/pro/image-to-video"


# ------------------------------------------------------------------------- shot tiers
#
# What a planned shot asks for, and the only vocabulary the planner is given. A shot names
# a *tier* and the app names the endpoint, which is not a stylistic preference: asked for a
# model directly, a language model invents slugs that do not exist and quotes prices for
# them, and both of those reach the operator as fact. A tier is a claim about the beat —
# this one is the hook, that one is the twelfth cutaway — and that is a claim the planner
# is actually in a position to make.
HERO_TIER = "hero"
STANDARD_TIER = "standard"
VIDEO_TIERS: tuple[str, ...] = (HERO_TIER, STANDARD_TIER)


def video_tier(value: str) -> str:
    """What a planner's word for a tier means, as one of `VIDEO_TIERS`.

    Read loosely, and in one place, because the field is written by a language model:
    "Hero", "  hero " and "hero shot" all mean the same thing, and only an exact match
    would make the difference between them cost money. Anything else is standard — see
    `model_for_tier` for why the unrecognised case falls that way rather than the other.
    """
    return (HERO_TIER if str(value or "").strip().lower().startswith(HERO_TIER)
            else STANDARD_TIER)


def model_for_tier(tier: str, *, standard: str = "", hero: str = "") -> str:
    """The slug a shot of this tier renders on, given a channel's two choices.

    Two fallbacks, and the direction of each one is the whole safety of this feature.

    An empty hero slug falls through to the standard one rather than to some shipped
    premium default. A channel that has not chosen a hero model therefore costs exactly
    what it cost before this existed — down to the cent, because every shot resolves to
    the same endpoint it already used. The opposite default would raise the bill on every
    existing channel at once, silently, in return for a decision nobody made.

    An unrecognised tier resolves to standard for the same reason it resolves at all: the
    planner is a language model, so "premium", an omitted field and a misspelling all have
    to land somewhere, and the cheap tier is the safe place to land. Landing on the dear
    one would make a typo in a JSON field the most expensive thing in the run.
    """
    if video_tier(tier) == HERO_TIER:
        return hero or standard or DEFAULT_VIDEO_MODEL
    return standard or DEFAULT_VIDEO_MODEL

# What an unrecognised slug is priced at: the top of the observed range, not the middle
# and certainly not the cheapest. An estimate that is too high is released back to the
# operator when the node settles; one that is too low is a run that stops mid-batch with
# work already paid for, which no later correction recovers.
UNPRICED_MODEL = VideoModel(
    0.40, (8.0, 10.0),
    f"unrecognised model — reserved at the ceiling of the range priced on "
    f"{PRICES_CHECKED}")

# Families, so an unrecognised variant of a known vendor is priced from its own siblings
# rather than from the global ceiling. fal adds and renames variants faster than any table
# tracks, and `kling-video/v3.1/pro` arriving tomorrow should cost about what Kling costs.
_FAMILIES = ("kling", "hailuo", "wan", "ltx", "veo", "sora")


def _family(slug: str) -> str:
    lowered = slug.lower()
    return next((name for name in _FAMILIES if name in lowered), "")


def video_model(slug: str) -> VideoModel:
    """Price and duration envelope for a slug, erring expensive when unsure."""
    key = (slug or "").strip().lower()
    if key in VIDEO_MODELS:
        return VIDEO_MODELS[key]

    family = _family(key)
    siblings = [model for name, model in VIDEO_MODELS.items() if _family(name) == family]
    if family and siblings:
        # The dearest sibling's rate, the longest sample, the shortest ceiling: three
        # conservative picks rather than one sibling's row, because guessing which
        # sibling an unknown variant resembles is how the guess comes in under cost.
        #
        # The call shape is taken from the dearest sibling rather than being mixed the
        # same way, because spelling is not a quantity — a new Veo variant spells
        # durations the way the other Veo variants do, and blending "suffixed" with
        # "integer" produces a request no endpoint accepts.
        dearest = max(siblings, key=lambda model: model.usd_per_second)
        return VideoModel(
            dearest.usd_per_second,
            tuple(sorted({max(model.sample_seconds for model in siblings),
                          min(model.max_seconds for model in siblings)})),
            f"unrecognised {family} variant — priced from the dearest known {family}",
            spelling=dearest.spelling,
            audio_flag=dearest.audio_flag,
        )
    return UNPRICED_MODEL


def video_usd(slug: str, seconds: float) -> float:
    """What one clip of this length costs on this model, billed the way it is billed.

    Through `submittable` rather than `rate x seconds`, because the endpoint charges for
    the duration it accepted and not for the one the scene wanted: a six-second scene on
    Kling is a ten-second submission. Priced the naive way, a plan mixing two models
    reports a saving that the invoice does not contain — and the whole point of routing
    per shot is that somebody is going to check that number.
    """
    priced = video_model(slug)
    return priced.usd_per_second * priced.submittable(max(0.0, float(seconds or 0.0)))


def video_reserve_credits(model: str, seconds: float, *, samples: int = 0) -> int:
    """Credits to hold for `seconds` on `model`, plus `samples` sample renders.

    `samples` is counted rather than folded into the duration because a sample and a full
    render are separate provider submissions, each billed on its own `request_id`. A
    reserve that quietly added five seconds to the shot would be the "rolled in" framing
    the i2v skill forbids, expressed as money.
    """
    priced = video_model(model)
    total = priced.usd_per_second * (
        max(0.0, float(seconds)) + priced.sample_seconds * max(0, int(samples)))
    return _credits(total)


# A shot list shaped like a real long-form video: eighty shots, scenes running three to
# nine seconds and clustering around five or six. Used only to price the catalogue for
# whoever is choosing from it.
#
# The per-second rate on its own is misleading and the size of the error is not small.
# Durations are enums, so a model's granularity decides how much of each billed second
# survives into the video: Kling offers five seconds or ten and nothing between, so a
# six-second scene is billed at ten and 36% of the spend never reaches the screen. Ranked
# on rate alone Kling looks like the middle of this table. Ranked on what a video costs it
# is near the top.
_TYPICAL_SHOTS: tuple[float, ...] = tuple(
    float(n) for n in [3, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 8, 9] * 5)

# How many of those eighty shots are hero beats. Four roles earn the upgrade — the opening
# hook, the reveal the video is built around, the payoff, and the closing shot — and five
# is that list with one spare, which is what a real script tends to want.
#
# It is deliberately a small number and the arithmetic is why. Upgrading five shots of
# eighty from Veo 3.1 Lite to Veo 3.1 costs about seven dollars; upgrading forty costs
# about sixty, which is the all-hero bill with extra steps. The saving is not "use a
# cheaper model", it is "use the dear one where it is looked at".
TYPICAL_HERO_SHOTS = 5


def _split_typical(hero_shots: int = TYPICAL_HERO_SHOTS) -> tuple[list[float], list[float]]:
    """The typical shot list as (hero durations, batch durations).

    The hero shots are the *longest* entries rather than a slice off the front, and that
    is both the conservative reading and the true one: the beats worth upgrading are the
    beats you let run, so they are the expensive seconds. Split here rather than at each
    call site so the figure on a dropdown row and the figure in the blend below it cannot
    be computed from two different five shots.
    """
    count = max(0, min(int(hero_shots), len(_TYPICAL_SHOTS)))
    ranked = sorted(_TYPICAL_SHOTS, reverse=True)
    return ranked[:count], ranked[count:]


def video_catalogue(chosen: str = "", *, default: str = DEFAULT_VIDEO_MODEL) -> list[dict]:
    """Every selectable i2v model, priced as a whole video rather than per second.

    For the channel settings page and for the agent, from one function, so the operator
    and the assistant cannot be looking at two different tables. Cheapest first — the
    order the decision is usually made in.

    `default` is what an empty choice means, and it is a parameter because the two tiers
    disagree about it. Nothing chosen for the batch model means `DEFAULT_VIDEO_MODEL`;
    nothing chosen for the hero model means *no upgrade at all*, which is not a model and
    so cannot be marked on a row. Passing `default=""` says that honestly instead of
    lighting up a row the channel has not picked.
    """
    rows: list[dict] = []
    for slug, model in VIDEO_MODELS.items():
        if "superseded" in model.note:
            # Kept in the table so old runs still price correctly when they are re-read,
            # but not offered: choosing one is choosing an older model at a higher rate.
            continue
        billed = sum(model.submittable(shot) for shot in _TYPICAL_SHOTS)
        hero_billed = sum(model.submittable(shot) for shot in _split_typical()[0])
        rows.append({
            "slug": slug,
            "label": _video_label(slug),
            "usd_per_second": model.usd_per_second,
            "typical_video_usd": round(model.usd_per_second * billed, 2),
            # What this model costs on the hero beats alone, which is the only figure a
            # hero pick can honestly be shown against: nobody is proposing to run the
            # whole video on it, so `typical_video_usd` next to a hero option would be a
            # true number answering a question nobody asked.
            "hero_shots_usd": round(model.usd_per_second * hero_billed, 2),
            # How much of what this model bills for survives into the finished video.
            # 1.00 means its durations match how scenes actually run.
            "billed_ratio": round(billed / sum(_TYPICAL_SHOTS), 2),
            "durations": [int(option) for option in model.durations],
            "sample_usd": round(model.usd_per_second * model.sample_seconds, 2),
            "note": model.note,
            "chosen": slug == (chosen or default),
            "is_default": slug == default,
        })
    return sorted(rows, key=lambda row: row["typical_video_usd"])


def video_blend(standard: str = "", hero: str = "",
                *, hero_shots: int = TYPICAL_HERO_SHOTS) -> dict:
    """What a typical video costs with the hero beats on one model and the rest on another.

    The number the two-model decision actually turns on, and it is not derivable from the
    two rows in `video_catalogue` — a reader given "$14.70" and "$98.00" and asked to
    picture five-of-eighty will not arrive at $21.50, and the gap between what they guess
    and what it is decides whether the premium model gets used at all.
    """
    standard_slug = model_for_tier(STANDARD_TIER, standard=standard, hero=hero)
    hero_slug = model_for_tier(HERO_TIER, standard=standard, hero=hero)

    upgraded, batch = _split_typical(hero_shots)
    count = len(upgraded)

    blended = (sum(video_usd(hero_slug, seconds) for seconds in upgraded)
               + sum(video_usd(standard_slug, seconds) for seconds in batch))
    standard_only = sum(video_usd(standard_slug, seconds) for seconds in _TYPICAL_SHOTS)
    hero_only = sum(video_usd(hero_slug, seconds) for seconds in _TYPICAL_SHOTS)

    return {
        "standard": standard_slug,
        "hero": hero_slug,
        "standard_label": _video_label(standard_slug),
        "hero_label": _video_label(hero_slug),
        # False when the channel has chosen no hero model, or chose the same one twice.
        # The page needs to know, because "$43.75 a video, saving $0.00" reads as a broken
        # calculation rather than as a channel that has not opted in.
        "upgraded": hero_slug != standard_slug,
        "shots": len(_TYPICAL_SHOTS),
        "hero_shots": count,
        "usd": round(blended, 2),
        "standard_only_usd": round(standard_only, 2),
        "hero_only_usd": round(hero_only, 2),
        # Against all-hero rather than against all-standard. Routing per shot never beats
        # putting everything on the cheap model and was never meant to; what it beats is
        # the video you would have made if you wanted the opening to look expensive.
        # Floored, so two identical models produce "$0.00" rather than the "-$0.00" that
        # summing the same seconds in two orders leaves behind.
        "saved_usd": round(max(0.0, hero_only - blended), 2),
    }


def _video_label(slug: str) -> str:
    """A name an operator recognises, from a slug written for a URL router."""
    known = {
        "fal-ai/kling-video/v2.6/pro/image-to-video": "Kling 2.6 Pro",
        "fal-ai/kling-video/v2.5-turbo/pro/image-to-video": "Kling 2.5 Turbo Pro",
        "fal-ai/kling-video/v3/pro/image-to-video": "Kling 3 Pro",
        "fal-ai/wan/v2.2-a14b/image-to-video": "WAN 2.2 (open weights)",
        "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video": "Hailuo 2.3 Fast",
        "fal-ai/ltx-2.3/image-to-video": "LTX 2.3",
        "fal-ai/ltx-2.3/image-to-video/fast": "LTX 2.3 Fast",
        # Named for what it is rather than for its slug. An operator looking for the
        # thing they saw in Google Flow will not search for "veo3.1/lite".
        "fal-ai/veo3.1/lite/image-to-video": "Veo 3.1 Lite (Google Flow's model)",
        "fal-ai/veo3.1/fast/image-to-video": "Veo 3.1 Fast (Google Flow's model)",
        "fal-ai/veo3.1/image-to-video": "Veo 3.1 (Google Flow's model)",
        "fal-ai/sora-2/image-to-video": "Sora 2 (OpenAI)",
    }
    return known.get(slug, slug.rsplit("/", 2)[0].split("/")[-1].replace("-", " ").title())


class FalVideoProvider(VideoProvider):
    """Image-to-video through FAL — covers Kling, Hailuo, WAN, LTX, Veo and Sora.

    The per-second cost and the duration envelope come from `VIDEO_MODELS` rather than
    from an attribute on this class, because they are properties of the model chosen per
    shot and this one adapter serves all of them.
    """

    name = "fal-video"
    base_url = "https://fal.run"

    def __init__(self, api_key: str = "", model: str = DEFAULT_VIDEO_MODEL) -> None:
        super().__init__(api_key)
        self.model = model

    @property
    def pricing(self) -> VideoModel:
        return video_model(self.model)

    @property
    def usd_per_second(self) -> float:
        return self.pricing.usd_per_second

    @property
    def sample_seconds(self) -> float:
        """What one Sample Gate clip on this model is generated at, and costs."""
        from ..skills.gates import sample_seconds_for

        return sample_seconds_for(self.pricing.sample_seconds,
                                  longest_supported=self.pricing.max_seconds)

    def clamp_seconds(self, seconds: float) -> int:
        """The duration this endpoint will actually accept, nearest to what was asked.

        Snapped to the model's own set of durations rather than clamped into its range.
        Those are different operations and only one of them works: six seconds is inside
        Sora's four-to-twenty envelope and Sora rejects it, because the durations it
        accepts are 4, 8, 12, 16 and 20 with nothing in between. Clamping produced a
        number that was in range and not on the list.
        """
        priced = self.pricing
        wanted = float(seconds) or priced.sample_seconds
        return int(priced.submittable(wanted))

    def reserve_credits(self, seconds: float, *, samples: int = 0) -> int:
        return video_reserve_credits(self.model, self.clamp_seconds(seconds),
                                     samples=samples)

    def sample_and_full_quote(self, seconds: float):
        """The two charges this shot owes, priced from the catalogue.

        Returned as a `gates.Quote` so the gate that surfaces it and the ledger that
        settles it read the same arithmetic — a second implementation of "sample plus
        full" is how one of them ends up quoting a discount that does not exist.
        """
        from ..skills.gates import quote

        priced = self.pricing
        return quote(model=self.model, usd_per_second=priced.usd_per_second,
                     full_seconds=self.clamp_seconds(seconds),
                     shortest_supported=priced.sample_seconds,
                     longest_supported=priced.max_seconds)

    async def generate_clip(
        self,
        prompt: str,
        *,
        out_path: Path,
        seconds: float = 5.0,
        width: int = 1280,
        height: int = 720,
        image_path: Path | None = None,
    ) -> MediaResult:
        key = self._require_key()
        out_path = out_path.with_suffix(".mp4")
        billed_seconds = self.clamp_seconds(seconds)
        priced = self.pricing
        body: dict = {
            "prompt": prompt,
            "aspect_ratio": "16:9" if width >= height else "9:16",
        }
        # Spelled the way this endpoint spells it. There is no convention — see
        # `VideoModel` — and a duration in the wrong shape is a 422 on a submission that
        # has already been queued, or worse, silently replaced by the endpoint's default,
        # which on Veo is eight seconds and twice what most shots asked for.
        if priced.spelling == "integer":
            body["duration"] = billed_seconds
        elif priced.spelling == "suffixed":
            body["duration"] = f"{billed_seconds}s"
        elif priced.spelling == "string":
            body["duration"] = str(billed_seconds)

        # Native audio is on by default on every endpoint that has it, and it is billed
        # separately — double the rate on Kling and on Veo. This pipeline narrates on its
        # own voice vendor and mixes in the render, so a generated audio track is paid
        # for and then discarded. Turning it off is not an optimisation; leaving it on
        # was the quoted rate being wrong by 100% on the default model.
        if priced.audio_flag:
            body[priced.audio_flag] = False

        if image_path and Path(image_path).exists():
            body["image_url"] = _data_uri(Path(image_path))
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/{self.model}",
                    headers={"Authorization": f"Key {key}"},
                    json=body,
                )
                _check(response, self.name)
                payload = response.json()
                url = (payload.get("video") or {}).get("url")
                if not url:
                    raise ProviderError(
                        f"{self.name} returned no video", provider=self.name, retryable=True
                    )
                await _download(client, url, out_path)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        return MediaResult(
            path=out_path,
            mime="video/mp4",
            # Billed on the duration submitted, not the one requested. A shot asked for at
            # four seconds against a six-second minimum is charged for six, and settling
            # the cheaper number puts the difference on the house every clip.
            credits=_credits(self.usd_per_second * billed_seconds),
            provider=self.name,
            duration_seconds=float(billed_seconds),
            meta={"model": self.model, "prompt": prompt[:300],
                  "usd_per_second": self.usd_per_second,
                  "billed_seconds": billed_seconds},
        )


# ------------------------------------------------------------------------- avatar


class HeyGenAvatarProvider(AvatarProvider):
    name = "heygen"
    base_url = "https://api.heygen.com"
    usd_per_minute = 0.60

    async def generate(
        self,
        *,
        audio_path: Path,
        avatar_id: str,
        out_path: Path,
        width: int = 1280,
        height: int = 720,
    ) -> MediaResult:
        key = self._require_key()
        if not avatar_id:
            raise ProviderError("no avatar_id set on the channel", provider=self.name)
        out_path = out_path.with_suffix(".mp4")
        headers = {"X-Api-Key": key, "content-type": "application/json"}

        # HeyGen needs the narration reachable by URL; upload it to your own bucket
        # and pass the public link. `audio_url` is resolved by the storage layer.
        audio_url = _public_url(audio_path)
        body = {
            "video_inputs": [
                {
                    "character": {"type": "avatar", "avatar_id": avatar_id,
                                  "avatar_style": "normal"},
                    "voice": {"type": "audio", "audio_url": audio_url},
                }
            ],
            "dimension": {"width": width, "height": height},
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/v2/video/generate", headers=headers, json=body
                )
                _check(response, self.name)
                video_id = (response.json().get("data") or {}).get("video_id")
                if not video_id:
                    raise ProviderError("heygen did not return a video id", provider=self.name)
                url = await self._poll(client, video_id, headers)
                await _download(client, url, out_path)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        from ..render import ffmpeg as ff

        duration = await asyncio.to_thread(ff.ffprobe_duration, out_path)
        return MediaResult(
            path=out_path,
            mime="video/mp4",
            credits=_credits(self.usd_per_minute * duration / 60),
            provider=self.name,
            duration_seconds=duration,
            meta={"avatar_id": avatar_id},
        )

    async def _poll(
        self, client: httpx.AsyncClient, video_id: str, headers: dict, *, limit: int = 120
    ) -> str:
        for attempt in range(limit):
            await asyncio.sleep(min(3 + attempt * 0.5, 12))
            response = await client.get(
                f"{self.base_url}/v1/video_status.get",
                headers=headers,
                params={"video_id": video_id},
            )
            _check(response, self.name)
            data = response.json().get("data") or {}
            status = (data.get("status") or "").lower()
            if status == "completed":
                url = data.get("video_url")
                if url:
                    return url
                raise ProviderError("heygen completed with no url", provider=self.name)
            if status == "failed":
                raise ProviderError(
                    f"heygen failed: {data.get('error')}", provider=self.name, retryable=True
                )
        raise ProviderTimeout(f"heygen video {video_id} never finished", provider=self.name)


# ------------------------------------------------------------------------- helpers


def _data_uri(path: Path) -> str:
    import base64
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def _public_url(path: Path) -> str:
    """Map a local artifact to a fetchable URL.

    Local disk works only when FORGECAST_BASE_URL is reachable from the vendor.
    Swap this for a presigned object-store URL before running avatars in production.
    """
    from ..config import get_settings

    settings = get_settings()
    try:
        relative = path.resolve().relative_to(settings.storage_dir.resolve())
    except ValueError:
        raise ProviderError(
            f"{path} is outside the storage dir, cannot expose it to the vendor"
        ) from None
    return f"{settings.base_url.rstrip('/')}/files/{relative.as_posix()}"
