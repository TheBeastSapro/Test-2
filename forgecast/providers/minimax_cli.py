"""MiniMax narration through the subscription, rather than through the API balance.

## What changed, and why the docstring next door used to say this was impossible

`media.MiniMaxVoiceProvider` calls `POST /v1/t2a_v2` with an API key. That key draws
down a pay-as-you-go balance per character, which is real money separate from the
plan — and this app said so, loudly, in three places, because quietly moving someone's
spend from a subscription they hold to an invoice they do not expect is the worst kind
of bug.

What it also said was that there was no way to do otherwise: "there is no token, no CLI
subcommand and no OAuth scope that routes speech through the plan". That was the state
of the investigation at the time and it is wrong now. `mmx`, MiniMax's own CLI, exposes
a `speech` command group beside `text`, `image`, `video` and `music`, and speech sits
under the same Token Plan tiers the rest of the CLI does. Signed in with
`mmx auth login` — the browser flow, no key — narration comes out of the plan.

So there are two routes to the same vendor, and the difference between them is which
account pays:

* **this class** — `mmx speech synthesize`, on the subscription's speech quota;
* **`media.MiniMaxVoiceProvider`** — the HTTP API, on the API balance, per character.

## Why both stay, and why this one does not silently replace the other

A subscription has a quota that resets; an API balance does not. Falling back from one
to the other without saying so is the same failure in the other direction — a render
that quietly starts costing money the moment a daily quota runs out. So the fallback is
a decision the registry makes explicitly and every result records which meter it drew
on, in `meta["billing"]`. If you are reading a run's artifacts and want to know what a
voiceover cost, that field is the answer and it is never inferred.

## What is measured here and what is taken on trust

The CLI reports nothing machine-readable about a synthesis beyond writing the file, so
unlike the HTTP path there is no vendor-supplied duration or character count to read
back. Duration is probed off the file with ffprobe — measured, not claimed — and the
character count is the length of the text that went in, which is what the vendor
charges on anyway.

`credits` is reported as zero, deliberately, and that is not a shortcut. A credit here
means money spent, and a synthesis inside a plan's quota spends none. Booking the API
rate against it would put a number in the ledger that nobody is billed for, and the
ledger is the thing this app asks people to trust about their own spend.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ..agent import minimax_auth
from .base import MediaResult, ProviderError, ProviderTimeout, VoiceProvider

log = logging.getLogger("forgecast.providers.minimax_cli")

# Long enough for a full narration pass. A ten-minute voiceover is a real generation on
# the vendor's side, and a timeout tuned to a short sentence turns the normal case into
# a failure — which then falls back to the paid route and bills someone for a request
# that was going to succeed.
SYNTH_TIMEOUT = 600.0

# The CLI's own default model. Named rather than left implicit so a run's artifacts say
# which model produced the audio, the same way the HTTP path does.
DEFAULT_MODEL = "speech-2.8-hd"

# Matches the HTTP path's limit, which comes from the API reference. The CLI is a client
# of the same service, so the ceiling is the service's, not the transport's — checked
# here so a long script fails as a sentence rather than as a rejected request several
# minutes into a run.
MAX_CHARACTERS = 10_000


class MiniMaxCliVoiceProvider(VoiceProvider):
    """Narration from `mmx speech synthesize`, paid for by the subscription."""

    name = "minimax-voice-cli"
    usd_per_1k_chars = 0.0

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL,
                 root: Path | None = None) -> None:
        # `api_key` is accepted and ignored so the registry can construct every voice
        # provider the same way. Passing it on would be worse than ignoring it: `mmx`
        # takes a key through `auth login --api-key`, and a key supplied there moves the
        # billing back to the balance this class exists to avoid.
        super().__init__("")
        self.model = model or DEFAULT_MODEL
        self._root = root

    # ------------------------------------------------------------------ readiness

    @classmethod
    def available(cls, root: Path | None = None) -> tuple[bool, str]:
        """Whether this route can be used right now, and if not, what is missing.

        Returns (ready, reason). The reason is shown to the operator, so it names the
        fix rather than the internal state — an unusable narration vendor discovered at
        render time has already cost the run everything upstream of it.
        """
        status = minimax_auth.check(root)
        if not status.cli_found:
            return False, (
                "the MiniMax CLI is not installed, so narration cannot go through your "
                f"subscription — install it once ({minimax_auth.INSTALL_HINT}), or "
                "leave a MiniMax API key set and it will bill the API balance instead")
        if not status.signed_in:
            return False, (
                "nobody has signed in to MiniMax on this machine — sign in under "
                "Settings to narrate on your subscription instead of the API balance")
        if getattr(status, "with_api_key", False):
            # Signed in, so it works. It is just signed in the way that bills per
            # character, which is precisely the thing this class exists to avoid, and
            # reporting it as "on the subscription" would be a lie about money.
            return False, (
                "the MiniMax CLI is signed in with an API key rather than your "
                "subscription, so it would bill per character either way — run "
                "`mmx auth logout` and sign in again to use the plan")
        return True, ""

    # ------------------------------------------------------------------ synthesis

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        if not voice_id:
            raise ProviderError("no voice_id set on the channel", provider=self.name)
        if len(text) > MAX_CHARACTERS:
            raise ProviderError(
                f"{len(text)} characters is over the {MAX_CHARACTERS} limit for one "
                "request — split the script by section and concatenate",
                provider=self.name)

        ready, reason = self.available(self._root)
        if not ready:
            raise ProviderError(reason, provider=self.name)

        cli = minimax_auth.find_cli(self._root)
        if not cli:                                                   # pragma: no cover
            raise ProviderError("the MiniMax CLI went missing between the check and the "
                                "call", provider=self.name)

        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # `--text-file -` with the script on stdin, never `--text "…"`. A narration
        # block contains quotes, apostrophes and newlines, and every one of those is a
        # way for an argument list to be parsed into something other than what was
        # written. stdin has no quoting rules to get wrong.
        argv = [cli, "speech", "synthesize",
                "--text-file", "-",
                "--voice", voice_id,
                "--model", self.model,
                # 0.5 to 2.0 at the service. Clamped rather than passed through,
                # because the caller's speed comes from a style profile that knows
                # nothing about this vendor's accepted range.
                "--speed", f"{min(2.0, max(0.5, float(speed))):.2f}",
                "--out", str(out_path)]

        code, output = await self._run(argv, text)
        if code != 0:
            raise ProviderError(
                _explain(output) or f"the MiniMax CLI exited with code {code}",
                provider=self.name)

        # Written, or not. The CLI reports success on its exit code and this is the only
        # check that the audio actually exists — a zero-byte file passed downstream
        # becomes a rendered video with silence where the narration goes, discovered
        # after the render has been paid for.
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise ProviderError(
                "the MiniMax CLI reported success but wrote no audio"
                + (f" — {output.strip()[:200]}" if output.strip() else ""),
                provider=self.name)

        from ..render import ffmpeg as ff
        duration = await asyncio.to_thread(ff.ffprobe_duration, out_path)

        return MediaResult(
            path=out_path,
            mime="audio/mpeg",
            # Nothing was billed. See the module docstring — a credit here means money,
            # and quota inside a plan is not money.
            credits=0,
            provider=self.name,
            duration_seconds=duration,
            meta={"characters": len(text), "voice_id": voice_id, "model": self.model,
                  "billing": "minimax subscription quota"},
        )

    async def _run(self, argv: list[str], stdin_text: str) -> tuple[int, str]:
        """One CLI call with the script on stdin, its console suppressed on Windows."""
        from ..desktop.toolchain import _no_window

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ},
                **_no_window(),
            )
        except OSError as exc:
            raise ProviderError(f"could not start the MiniMax CLI at {argv[0]}: "
                                f"{type(exc).__name__}: {exc}",
                                provider=self.name) from exc

        try:
            out, _ = await asyncio.wait_for(
                process.communicate(stdin_text.encode("utf-8")), timeout=SYNTH_TIMEOUT)
        except TimeoutError as exc:
            # Killed rather than left running. An abandoned synthesis holds a slot in
            # the plan's concurrency limit, so the next attempt fails for a reason that
            # has nothing to do with the next attempt.
            with _suppress_process_errors():
                process.kill()
            raise ProviderTimeout(
                f"the MiniMax CLI did not finish within {SYNTH_TIMEOUT:.0f}s",
                provider=self.name) from exc

        return process.returncode or 0, (out or b"").decode("utf-8", "replace")


def _explain(output: str) -> str:
    """The CLI's failure, as a sentence naming what to do about it.

    Matched on substrings rather than on exit codes: the CLI returns 1 for everything,
    so the code carries no information and the text is all there is. Anything
    unrecognised is passed through whole rather than replaced by a generic message —
    an unfamiliar error is exactly the one worth reading.
    """
    low = output.lower()
    if "quota" in low or ("limit" in low and "rate" in low):
        return ("your MiniMax plan's speech quota is used up for now. It resets on the "
                "plan's own schedule; until then, set the channel's voice vendor to "
                "ElevenLabs, or to minimax-voice to use the API balance instead")
    if "no credentials" in low or "not logged in" in low or "unauthor" in low:
        return ("the MiniMax CLI is not signed in any more — sign in again under "
                "Settings")
    if "voice" in low and ("not found" in low or "invalid" in low):
        return ("MiniMax does not recognise that voice id — pick one from the catalogue, "
                "or check a cloned voice still exists on the account")
    return output.strip()[:400]


def _suppress_process_errors():
    import contextlib

    return contextlib.suppress(OSError, ProcessLookupError)


def cli_voices(root: Path | None = None) -> list[dict]:
    """The voice catalogue as `mmx speech voices` reports it, or an empty list.

    Empty means "could not ask", never "there are none". The caller falls back to the
    static catalogue in `media.MiniMaxVoiceProvider.list_voices`, which is the same
    system voice set — so a machine that cannot run the CLI still casts a voice
    instead of showing an empty picker and looking broken.
    """
    import json
    import subprocess

    cli = minimax_auth.find_cli(root)
    if not cli:
        return []
    try:
        done = subprocess.run([cli, "speech", "voices", "--output", "json"],
                              capture_output=True, text=True, errors="replace",
                              timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    try:
        payload = json.loads(done.stdout or "{}")
    except ValueError:
        return []

    rows = payload if isinstance(payload, list) else (payload.get("voices") or [])
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        voice_id = str(row.get("voice_id") or row.get("id") or "").strip()
        if not voice_id:
            continue
        out.append({"voice_id": voice_id,
                    "name": str(row.get("name") or voice_id),
                    "category": "premade",
                    "labels": {"gender": str(row.get("gender") or ""),
                               "language": str(row.get("language") or "en")},
                    "preview_url": ""})
    return out
