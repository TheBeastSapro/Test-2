#!/usr/bin/env python3
"""fetch.py — bridge between the Epidemic MCP results and the assembler.

Given a manifest mapping cue id -> asset URL (direct file OR HLS .m3u8 preview,
both of which the Epidemic MCP returns), download/transcode each into
<assets>/<cue id>.wav so assemble.py can pick them up by id.

Also writes the resolved paths back into the cue sheet's `asset` fields if
--cues is given, so the cue sheet becomes a self-contained record of the mix.

Usage:
  fetch.py --manifest manifest.json --assets ./assets [--cues cues.json]

manifest.json:  { "m1": "https://.../track.m3u8", "s1": "https://.../whoosh.mp3" }
"""
from __future__ import annotations

import argparse
import json
import os

from common import FFMPEG, run

SR = 48000


def fetch_one(url: str, dst: str):
    # ffmpeg reads http(s) and HLS natively; always land as 48k stereo wav.
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", url,
         "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", dst])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--cues")
    args = ap.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)
    os.makedirs(args.assets, exist_ok=True)

    resolved = {}
    for cue_id, url in manifest.items():
        dst = os.path.join(args.assets, f"{cue_id}.wav")
        try:
            fetch_one(url, dst)
            resolved[cue_id] = dst
            print(f"[fetch] {cue_id} <- {url[:60]}... -> {dst}")
        except Exception as e:
            print(f"[fetch] {cue_id} FAILED: {e}")

    if args.cues:
        with open(args.cues) as f:
            cue = json.load(f)
        for bucket in ("music_sections", "sfx_cues"):
            for c in cue.get(bucket, []):
                if c["id"] in resolved:
                    c["asset"] = resolved[c["id"]]
        with open(args.cues, "w") as f:
            json.dump(cue, f, indent=2)
        print(f"[fetch] updated asset paths in {args.cues}")


if __name__ == "__main__":
    main()
