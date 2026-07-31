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
        f"{provider} returned {response.status_code}: {response.text[:400]}",
        provider=provider,
        retryable=retryable,
    )


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
                _check(response, self.name)
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


class FalVideoProvider(VideoProvider):
    """Text/image-to-video through FAL — covers Kling, Minimax, LTX and friends."""

    name = "fal-video"
    base_url = "https://fal.run"
    usd_per_second = 0.09

    def __init__(self, api_key: str = "", model: str = "fal-ai/kling-video/v1/standard/text-to-video") -> None:
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
        body: dict = {
            "prompt": prompt,
            "duration": str(int(max(5, min(10, round(seconds))))),
            "aspect_ratio": "16:9" if width >= height else "9:16",
        }
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
            credits=_credits(self.usd_per_second * seconds),
            provider=self.name,
            duration_seconds=seconds,
            meta={"model": self.model, "prompt": prompt[:300]},
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
