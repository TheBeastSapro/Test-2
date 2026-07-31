"""YouTube publishing.

Uses the Data API v3 resumable upload endpoint over plain HTTP. Two things worth
knowing before you point this at a real channel:

* An app in Google's unverified/testing state can only upload as `private`. The
  publish node therefore defaults to private and treats "public" as an explicit
  operator choice made at the gate.
* Uploads are quota-expensive (~1,600 units each against a default 10,000/day
  budget), which caps you near six uploads per day per project until you request
  more. Plan channel scale around that, not around render throughput.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import get_settings
from .base import ProviderError, ProviderTimeout

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API_URL = "https://www.googleapis.com/youtube/v3"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]

_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=10.0)
_CHUNK = 8 * 1024 * 1024


@dataclass
class PublishResult:
    video_id: str
    url: str
    privacy_status: str
    provider: str = "youtube"
    meta: dict | None = None


class YouTubePublisher:
    name = "youtube"

    def __init__(self, client_id: str = "", client_secret: str = "") -> None:
        settings = get_settings()
        self.client_id = client_id or settings.youtube_client_id
        self.client_secret = client_secret or settings.youtube_client_secret

    async def _access_token(self, refresh_token: str) -> str:
        if not (self.client_id and self.client_secret):
            raise ProviderError("YouTube OAuth client is not configured", provider=self.name)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if not response.is_success:
            raise ProviderError(
                f"token refresh failed ({response.status_code}): {response.text[:300]}",
                provider=self.name,
            )
        return response.json()["access_token"]

    async def upload(
        self,
        *,
        video_path: Path,
        refresh_token: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str = "27",
        privacy_status: str = "private",
        publish_at: str | None = None,
        thumbnail_path: Path | None = None,
        made_for_kids: bool = False,
    ) -> PublishResult:
        if not video_path.exists():
            raise ProviderError(f"no rendered file at {video_path}", provider=self.name)

        token = await self._access_token(refresh_token)
        status: dict = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        }
        if publish_at:
            # Scheduling requires the video to start private.
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at

        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:30],
                "categoryId": category_id,
            },
            "status": status,
        }

        size = video_path.stat().st_size
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # 1. open a resumable session
            init = await client.post(
                UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "content-type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(size),
                    "X-Upload-Content-Type": "video/*",
                },
                content=json.dumps(metadata),
            )
            if not init.is_success:
                raise ProviderError(
                    f"could not start upload ({init.status_code}): {init.text[:300]}",
                    provider=self.name,
                    retryable=init.status_code >= 500,
                )
            session_url = init.headers.get("location")
            if not session_url:
                raise ProviderError("no resumable session URL returned", provider=self.name)

            # 2. push the bytes
            video_id = await self._send_chunks(client, session_url, video_path, size)

            # 3. thumbnail is a separate call and may not exceed 2MB
            if thumbnail_path and thumbnail_path.exists():
                await self._set_thumbnail(client, token, video_id, thumbnail_path)

        return PublishResult(
            video_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=status["privacyStatus"],
            meta={"bytes": size, "scheduled_for": publish_at},
        )

    async def _send_chunks(
        self, client: httpx.AsyncClient, session_url: str, video_path: Path, size: int
    ) -> str:
        offset = 0
        with video_path.open("rb") as handle:
            while offset < size:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                try:
                    response = await client.put(
                        session_url,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{end}/{size}",
                        },
                        content=chunk,
                    )
                except httpx.TimeoutException as exc:
                    raise ProviderTimeout(str(exc), provider=self.name) from exc

                if response.status_code in (200, 201):
                    return response.json()["id"]
                if response.status_code == 308:
                    # Server tells us how much it actually kept.
                    kept = response.headers.get("range")
                    offset = int(kept.split("-")[1]) + 1 if kept else end + 1
                    handle.seek(offset)
                    continue
                raise ProviderError(
                    f"upload failed ({response.status_code}): {response.text[:300]}",
                    provider=self.name,
                    retryable=response.status_code >= 500,
                )
        raise ProviderError("upload ended without a video id", provider=self.name)

    async def _set_thumbnail(
        self, client: httpx.AsyncClient, token: str, video_id: str, thumbnail_path: Path
    ) -> None:
        if thumbnail_path.stat().st_size > 2 * 1024 * 1024:
            return  # over YouTube's limit; skip rather than fail the publish
        response = await client.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id, "uploadType": "media"},
            headers={"Authorization": f"Bearer {token}", "content-type": "image/png"},
            content=thumbnail_path.read_bytes(),
        )
        if not response.is_success:
            # A missing thumbnail is cosmetic; the video is already live.
            raise ProviderError(
                f"thumbnail rejected ({response.status_code}): {response.text[:200]}",
                provider=self.name,
                retryable=True,
            )

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # force a refresh token on re-auth
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        if not response.is_success:
            raise ProviderError(
                f"code exchange failed: {response.text[:300]}", provider=self.name
            )
        return response.json()


class MockPublisher(YouTubePublisher):
    """Pretends to upload. Returns a stable fake id so the UI has something to show."""

    name = "mock-youtube"

    def __init__(self) -> None:
        self.client_id = "mock"
        self.client_secret = "mock"

    async def upload(self, *, video_path: Path, **kwargs) -> PublishResult:  # type: ignore[override]
        import hashlib

        if not video_path.exists():
            raise ProviderError(f"no rendered file at {video_path}", provider=self.name)
        digest = hashlib.sha256(str(video_path).encode()).hexdigest()[:11]
        return PublishResult(
            video_id=digest,
            url=f"https://www.youtube.com/watch?v={digest}",
            privacy_status=kwargs.get("privacy_status", "private"),
            provider=self.name,
            meta={"mock": True, "bytes": video_path.stat().st_size},
        )


def publisher_for() -> YouTubePublisher:
    return MockPublisher() if get_settings().is_mock else YouTubePublisher()
