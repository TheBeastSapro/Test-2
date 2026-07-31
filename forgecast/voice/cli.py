"""CLI for voice discovery and casting.

    forgecast-voice sync                     # build the catalogue from your account
    forgecast-voice sync --shared            # include the public shared library
    forgecast-voice cast --pitch 132 --accent british --register documentary
    forgecast-voice list --band low_mid
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from ..config import get_settings
from .casting import VoiceTarget, casting_summary, shortlist
from .discover import (
    DEFAULT_CACHE,
    gather_all,
    load_catalogue,
    measure_many,
    measured_summary,
    prerank,
    save_catalogue,
)


def _provider():
    from ..providers.media import ElevenLabsProvider

    key = get_settings().elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        print(
            "error: no ElevenLabs key. Set FORGECAST_ELEVENLABS_API_KEY (or "
            "ELEVENLABS_API_KEY) to sync a real catalogue.",
            file=sys.stderr,
        )
        return None
    return ElevenLabsProvider(key)


def cmd_sync(args) -> int:
    provider = _provider()
    if provider is None:
        return 1
    cache = Path(args.cache or DEFAULT_CACHE)

    async def run():
        voices = await gather_all(
            provider,
            include_shared=args.shared,
            language=args.language,
            max_shared=args.max_shared,
        )
        print(f"gathered {len(voices)} voices", file=sys.stderr)
        if args.measure_all:
            # Only sane for an account-sized list; the shared library is thousands.
            measure_many(voices)
        save_catalogue(voices, cache)
        print(measured_summary(voices))
        print(f"cached to {cache}")

    asyncio.run(run())
    return 0


def cmd_cast(args) -> int:
    cache = Path(args.cache or DEFAULT_CACHE)
    target = VoiceTarget(
        pitch_hz=args.pitch,
        pitch_band=args.band,
        pace=args.pace,
        energy=args.energy,
        accent=args.accent,
        register=args.register,
        evidence=[f"target pitch {args.pitch:.0f}Hz"] if args.pitch else [],
    )

    pool = load_catalogue(cache)
    if pool and args.measure:
        # Two-stage: pre-rank on free metadata, then measure only the finalists.
        pool = measure_many(prerank(target, pool, limit=args.measure))

    for line in casting_summary(
        target, shortlist(target, limit=args.limit, measured=pool or None, cache_path=cache)
    ):
        print(line)
    return 0


def cmd_list(args) -> int:
    voices = load_catalogue(Path(args.cache or DEFAULT_CACHE))
    if not voices:
        print("no cached catalogue — run `forgecast-voice sync` first", file=sys.stderr)
        return 1

    rows = [
        voice for voice in voices
        if (not args.band or voice.pitch_band == args.band)
        and (not args.accent or args.accent.lower() in (voice.accent or "").lower())
    ]
    rows.sort(key=lambda voice: voice.pitch_hz or 0)
    print(f"{'voice':<22}{'Hz':>6}  {'band':<9}{'accent':<14}{'energy':<10}use_case")
    for voice in rows:
        hz = f"{voice.pitch_hz:.0f}" if voice.pitch_hz else "-"
        print(f"{voice.name[:21]:<22}{hz:>6}  {voice.pitch_band or '-':<9}"
              f"{(voice.accent or '-')[:13]:<14}{voice.energy:<10}{voice.use_case or '-'}")
    print(f"\n{len(rows)} of {len(voices)} voices")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgecast-voice", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--cache", default=None, help="catalogue cache path")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="build the catalogue from the live account")
    sync.add_argument("--shared", action="store_true", help="include the shared library")
    sync.add_argument("--language", default="en")
    sync.add_argument("--max-shared", type=int, default=1200)
    sync.add_argument("--measure-all", action="store_true",
                      help="measure every voice's pitch (slow on large libraries)")
    sync.set_defaults(func=cmd_sync)

    cast = sub.add_parser("cast", help="shortlist voices for a target")
    cast.add_argument("--pitch", type=float, default=None, help="reference median Hz")
    cast.add_argument("--band", default=None,
                      choices=["low", "low_mid", "mid", "high"])
    cast.add_argument("--pace", default=None,
                      choices=["slow", "measured", "brisk", "fast", "very_fast"])
    cast.add_argument("--energy", default=None,
                      choices=["calm", "measured", "warm", "energetic"])
    cast.add_argument("--accent", default=None)
    cast.add_argument("--register", default=None)
    cast.add_argument("--limit", type=int, default=3)
    cast.add_argument("--measure", type=int, default=20,
                      help="measure this many pre-ranked finalists (0 to skip)")
    cast.set_defaults(func=cmd_cast)

    listing = sub.add_parser("list", help="show the cached catalogue")
    listing.add_argument("--band", default=None)
    listing.add_argument("--accent", default=None)
    listing.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
