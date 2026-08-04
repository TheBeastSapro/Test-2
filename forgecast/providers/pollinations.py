"""Pollinations: still image generation with no key, no account, and no charge.

## Why this is in the tree

Every other generative provider here needs a credential before it does anything, so a
fresh install renders nothing until somebody has signed up for something. This one does
not: it serves FLUX over a plain GET with no key, no signup and no billing relationship,
which makes it the only provider in the catalogue that works on the first run of a fresh
install.

That matters most for the styles that are built from stills rather than from generated
video. `motion/paper.py` composites paper, cut-outs and type and animates them locally —
it needs source images and no video at all, so on this provider the generation cost of a
paper-collage video is zero rather than the $15 to $98 an image-to-video batch costs.

## What it is not

Not a replacement for the paid image path. Two honest limits, both measured rather than
assumed:

* **It queues rather than refusing.** Three requests go through in about a second each;
  the fourth blocks for the better part of a minute. It does not return 429 — it holds
  the connection open until it is ready. A client with an ordinary thirty-second read
  timeout therefore reports the service as broken on the fourth image of every run, which
  is why the timeout below is minutes and why `_pace` exists.
* **No guarantees.** It is a free public service with no contract behind it. It can be
  slow, it can be down, and nothing is owed to anyone using it. Anything with a deadline
  belongs on the paid path.

## Determinism

The seed is derived from the prompt rather than left to the server, so the same prompt
returns the same image on a re-run. Two reasons, and the second is the one that matters:
a re-render after an unrelated failure should not silently change a picture an operator
already approved, and a collage style whose every element is a different generation stops
looking like one artifact. Callers wanting variation vary the prompt, which is what they
were going to do anyway.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .base import ImageProvider, MediaResult, ProviderError, ProviderTimeout

log = logging.getLogger("forgecast.providers.pollinations")

# Minutes, not seconds. The service throttles by holding the connection rather than by
# refusing, so a short read timeout turns a queued request into a reported outage. This
# is the one adapter here where a long read timeout is correct rather than lazy.
_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)

# Requests that go straight through before the queue starts. Measured at three.
_BURST = 3

# What the queue costs once it starts, so the pacer can wait deliberately instead of
# discovering it. Conservative: the fourth request measured at 45 seconds, and a pacer
# that under-waits gets no benefit from pacing at all.
_PACE_SECONDS = 15.0

_BASE_URL = "https://image.pollinations.ai/prompt"

# Big enough that the aspect ratio survives and small enough not to sit in the queue for
# longer than it has to. Callers asking for more get it; this is only the floor.
_MIN_EDGE = 256


class PollinationsProvider(ImageProvider):
    """FLUX stills over a keyless GET.

    Satisfies the `ImageProvider` contract exactly, so it drops in wherever the paid
    image provider goes and no node knows the difference — except in the ledger, where
    it charges nothing.
    """

    name: str = "pollinations"
    base_url: str = _BASE_URL
    # Named so the catalogue and the settings page can say why there is no key box.
    keyless: bool = True

    def __init__(self, api_key: str = "", model: str = "flux") -> None:
        super().__init__(api_key)
        self.model = model or "flux"
        # Per-instance rather than per-call, because the registry caches one provider for
        # the life of a run. A pacer that reset every call would pace nothing.
        self._sent = 0
        self._last = 0.0
        self._gate = asyncio.Lock()

    def available(self) -> tuple[bool, str]:
        """Always configured, because there is nothing to configure.

        Deliberately not a reachability check. `resolve` calls this while choosing a
        vendor, and a network round trip there would put a live request in front of every
        capability lookup — including the ones that end up choosing a different provider.
        Whether the service is *up* is answered by the request, and its failure is
        retryable.
        """
        return True, ""

    def _seed_for(self, prompt: str, width: int, height: int) -> int:
        """A stable seed for a prompt, so a re-run returns the picture already approved.

        Includes the dimensions: the same prompt at a different size is a different image
        anyway, and sharing a seed across sizes gives two near-identical compositions
        cropped differently, which looks like a bug rather than a set.
        """
        material = f"{self.model}|{prompt.strip()}|{width}x{height}".encode()
        return int.from_bytes(hashlib.sha256(material).digest()[:4], "big") % 2_000_000_000

    async def _pace(self) -> None:
        """Wait before the request that would otherwise wait for us.

        The difference is not cosmetic. Waiting here is cancellable and loggable; waiting
        inside an open HTTP request is neither, and it is indistinguishable from the
        service having hung.
        """
        async with self._gate:
            self._sent += 1
            if self._sent <= _BURST:
                self._last = time.monotonic()
                return
            since = time.monotonic() - self._last
            if since < _PACE_SECONDS:
                delay = _PACE_SECONDS - since
                log.debug("pacing pollinations for %.1fs", delay)
                await asyncio.sleep(delay)
            self._last = time.monotonic()

    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720
    ) -> MediaResult:
        text = (prompt or "").strip()
        if not text:
            raise ProviderError("pollinations needs a prompt", provider=self.name)

        wide = max(_MIN_EDGE, int(width))
        tall = max(_MIN_EDGE, int(height))
        seed = self._seed_for(text, wide, tall)

        out_path = Path(out_path).with_suffix(".jpg")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # `safe=""` so slashes and colons inside a prompt are escaped rather than becoming
        # path separators — a prompt containing "16:9" otherwise addresses a URL nobody
        # meant, and the service answers it with something unrelated instead of failing.
        url = (
            f"{self.base_url}/{quote(text, safe='')}"
            f"?width={wide}&height={tall}&seed={seed}&model={self.model}&nologo=true"
        )

        await self._pace()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                f"pollinations did not answer within {_TIMEOUT.read:.0f}s — it queues "
                f"under load rather than refusing, so this is usually congestion",
                provider=self.name,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

        if not response.is_success:
            raise ProviderError(
                f"pollinations returned {response.status_code}",
                provider=self.name,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )

        body = response.content
        # A short body from an endpoint that returns image bytes is an error page served
        # with a 200, which is a shape free services fall into under load. Writing it
        # would put a file on disk that every later stage treats as a picture.
        if len(body) < 2048 or not body.startswith((b"\xff\xd8", b"\x89PNG")):
            raise ProviderError(
                f"pollinations returned {len(body)} bytes that are not an image",
                provider=self.name, retryable=True,
            )
        out_path.write_bytes(body)

        return MediaResult(
            path=out_path,
            mime="image/jpeg",
            # Zero, and it has to be a real zero rather than the one-credit floor the
            # paid adapters round up to. A provider that costs nothing and bills one
            # credit a shot is an eighty-credit charge per video for nothing, and the
            # operator has no way to tell it apart from a real one.
            credits=0,
            provider=self.name,
            meta={
                "model": self.model,
                "prompt": text[:300],
                "seed": seed,
                "width": wide,
                "height": tall,
                "usd": 0.0,
                # Said explicitly, because "free" is the whole reason to pick this and
                # the reason not to depend on it are the same fact.
                "method": "keyless_generation",
                "guarantee": "none — free public service, no contract",
            },
        )
