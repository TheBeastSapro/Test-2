"""CLI for the visual analysis engine.

    forgecast-vision analyse clip.mp4
    forgecast-vision analyse clip.mp4 --json profile.json
    forgecast-vision analyse "https://youtube.com/watch?v=..." --max-seconds 120
    forgecast-vision compare a.json b.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from .acquire import AcquireError
from .engine import analyse_file, analyse_reference
from .probe import ProbeError


def cmd_analyse(args) -> int:
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="fcvision-"))
    try:
        if Path(args.reference).exists() and not args.max_seconds:
            profile = analyse_file(
                args.reference, sample_fps=args.sample_fps, max_frames=args.max_frames
            )
        else:
            profile, acquired = analyse_reference(
                args.reference, workdir,
                max_seconds=args.max_seconds,
                sample_fps=args.sample_fps,
                max_frames=args.max_frames,
            )
            if acquired.title:
                print(f"# {acquired.title}"
                      + (f" — {acquired.uploader}" if acquired.uploader else ""),
                      file=sys.stderr)
    except (AcquireError, ProbeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = profile.as_dict(include_shots=not args.no_shots)
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json}", file=sys.stderr)
    if args.quiet:
        return 0
    if args.raw:
        print(json.dumps(payload, indent=2))
    else:
        print(render_report(profile))
    return 0


def render_report(profile) -> str:
    source = profile.source
    spec = profile.render_spec
    rhythm = profile.shot_rhythm
    lines: list[str] = []

    name = source.get("title") or Path(source.get("path", "clip")).name
    lines.append(f"EDIT STYLE — {name}")
    lines.append(
        f"{source.get('duration_seconds', 0):.1f}s · {source.get('width')}x"
        f"{source.get('height')} · {source.get('aspect_ratio')} · "
        f"{source.get('orientation')}"
    )
    lines.append("")

    lines.append("SIGNATURE")
    for item in profile.edit_signature:
        lines.append(f"  · {item}")
    lines.append("")

    length = rhythm.get("shot_length") or {}
    lines.append("RHYTHM")
    lines.append(f"  shots           {rhythm.get('shot_count')}")
    lines.append(f"  cuts/min        {rhythm.get('cuts_per_minute')}")
    lines.append(
        f"  shot length     median {length.get('median')}s  "
        f"(min {length.get('min')}s, max {length.get('max')}s)"
    )
    lines.append(f"  regularity      {rhythm.get('regularity')}")
    lines.append(f"  pacing          {rhythm.get('pacing_trend')}")
    lines.append(f"  transitions     {rhythm.get('transition_mix')}")
    lines.append("")

    lines.append("LOOK")
    colour = profile.colour
    lines.append(f"  grade           {colour.get('grade_label')}")
    lines.append(
        f"  brightness {colour.get('brightness')}  contrast {colour.get('contrast')}  "
        f"saturation {colour.get('saturation')}  warmth {colour.get('warmth')}"
    )
    lines.append("  palette         " + " ".join(
        f"{item['hex']}({item['share']:.0%})" for item in colour.get("palette", [])
    ))
    motion = profile.motion
    lines.append(
        f"  motion          {motion.get('dominant')} / "
        f"{motion.get('dominant_camera_move')}  (mean {motion.get('mean_magnitude')})"
    )
    overlay = profile.overlay
    lines.append(
        f"  on-screen text  {overlay.get('caption_zone')} "
        f"({overlay.get('caption_persistence'):.0%} of frames)"
        if overlay.get("caption_zone") != "none" else "  on-screen text  none detected"
    )
    lines.append("")

    audio = profile.audio
    lines.append("AUDIO")
    if audio.get("present"):
        lines.append(
            f"  loudness        {audio.get('loudness_mean_dbfs')} dBFS mean, "
            f"{audio.get('loudness_peak_dbfs')} peak, "
            f"{audio.get('dynamic_range_db')} dB range"
        )
        lines.append(
            f"  silence         {audio.get('silence_ratio'):.1%} "
            f"(longest {audio.get('longest_silence_seconds')}s)"
        )
        lines.append(
            f"  onsets          {audio.get('onset_count')} "
            f"({audio.get('onsets_per_minute')}/min)  tempo "
            f"{audio.get('tempo_bpm')} BPM [{audio.get('tempo_confidence')}]"
        )
        lines.append(f"  cut-to-beat     {profile.beat_alignment.get('verdict')}"
                     f" ({profile.beat_alignment.get('cuts_on_beat_ratio')})")
    else:
        lines.append("  none")
    lines.append("")

    lines.append("RENDER SPEC — apply this to reproduce the style")
    for key, value in spec.as_dict().items():
        if key == "palette":
            continue
        lines.append(f"  {key:<22} {value}")
    lines.append("")

    lines.append("CONFIDENCE")
    confidence = profile.confidence
    lines.append("  " + "  ".join(
        f"{k}={v}" for k, v in confidence.items() if k != "notes"
    ))
    for note in confidence.get("notes", []):
        lines.append(f"  ! {note}")

    return "\n".join(lines)


def cmd_compare(args) -> int:
    """Diff two style profiles — useful for 'is my edit close to the reference yet'."""
    profiles = []
    for path in args.paths:
        try:
            profiles.append((Path(path).name, json.loads(Path(path).read_text())))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error reading {path}: {exc}", file=sys.stderr)
            return 1

    fields = [
        ("cuts/min", lambda d: (d.get("shot_rhythm") or {}).get("cuts_per_minute")),
        ("median shot", lambda d: ((d.get("shot_rhythm") or {}).get("shot_length") or {}).get("median")),
        ("regularity", lambda d: (d.get("shot_rhythm") or {}).get("regularity")),
        ("pacing", lambda d: (d.get("shot_rhythm") or {}).get("pacing_trend")),
        ("grade", lambda d: (d.get("colour") or {}).get("grade_label")),
        ("brightness", lambda d: (d.get("colour") or {}).get("brightness")),
        ("saturation", lambda d: (d.get("colour") or {}).get("saturation")),
        ("motion", lambda d: (d.get("motion") or {}).get("dominant")),
        ("captions", lambda d: (d.get("overlay") or {}).get("caption_zone")),
        ("cut-to-beat", lambda d: (d.get("beat_alignment") or {}).get("verdict")),
    ]

    width = max(len(name) for name, _ in profiles) + 2
    print(f"{'':<14}" + "".join(f"{name:<{width}}" for name, _ in profiles))
    for label, getter in fields:
        row = "".join(f"{getter(data)!s:<{width}}" for _, data in profiles)
        print(f"{label:<14}{row}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgecast-vision", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    analyse = sub.add_parser("analyse", help="analyse a video's editing style")
    analyse.add_argument("reference", help="local path, media URL, or platform URL")
    analyse.add_argument("--json", help="also write the full profile here")
    analyse.add_argument("--raw", action="store_true", help="print JSON instead of a report")
    analyse.add_argument("--quiet", action="store_true", help="write files only")
    analyse.add_argument("--no-shots", action="store_true", help="omit the per-shot array")
    analyse.add_argument("--max-seconds", type=float, default=None,
                         help="analyse only the first N seconds")
    analyse.add_argument("--sample-fps", type=float, default=4.0)
    analyse.add_argument("--max-frames", type=int, default=1200)
    analyse.add_argument("--workdir", default=None)
    analyse.set_defaults(func=cmd_analyse)

    compare = sub.add_parser("compare", help="diff two saved profiles side by side")
    compare.add_argument("paths", nargs="+")
    compare.set_defaults(func=cmd_compare)
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
