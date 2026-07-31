#!/usr/bin/env python3
"""Pace metrics, schema validation, and batch prevalence for the analyse skill.

Three subcommands:

    pace      words + duration -> WPM and pace band
    validate  check a per-video analysis JSON against the output contract
    batch     tally hook types, formats, CTAs, alignment across many JSONs

Why a script rather than doing it inline: word counts done by eye drift, WPM is the
number people actually act on, and batch prevalence counted from memory is how
imaginary patterns get into reports. Stdlib only — no install step.

Examples:
    python3 scripts/metrics.py pace --words 231 --duration 47
    python3 scripts/metrics.py pace --duration 47 --transcript-file t.txt
    python3 scripts/metrics.py validate analysis/instagram-DZU1D_8OI62.json
    python3 scripts/metrics.py batch analysis/*.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Bands from references/frameworks.md §7. Keep the two in sync.
PACE_BANDS: list[tuple[float, str]] = [
    (110, "slow"),
    (150, "measured"),
    (180, "brisk"),
    (210, "fast"),
    (float("inf"), "very_fast"),
]

VALID_PLATFORMS = {"instagram", "tiktok", "youtube", "other"}
VALID_STATUS = {"analysed", "unavailable", "partial"}

HOOK_TYPES = {
    "contrarian", "capability_reveal", "transformation", "result_proof",
    "curiosity_gap", "authority", "callout", "pain_naming", "warning",
    "in_medias_res", "question", "list_promise", "story_cold_open",
    "stakes_number", "other",
}
FORMATS = {
    "talking_head", "screen_recording", "voiceover_broll", "tutorial_walkthrough",
    "listicle", "case_study", "pov_skit", "interview_clip", "podcast_clip",
    "text_on_screen", "react_commentary", "greenscreen", "day_in_life",
    "product_demo", "ugc_ad", "compilation", "other",
}
CTA_TYPES = {
    "comment_keyword", "follow", "link_in_bio", "dm_keyword", "save_share",
    "watch_next", "subscribe", "purchase", "none",
}
SECTIONS = [
    "hook_promise", "credibility", "context_stakes", "mechanism", "proof",
    "objection", "cta",
]

# Filler tokens that inflate a word count without being spoken content. Kept short
# on purpose: over-stripping understates WPM, which is the error that matters here.
_FILLER = {"uh", "um", "erm", "mm", "hmm"}


# ----------------------------------------------------------------------- pace


def count_words(text: str, *, strip_filler: bool = False) -> int:
    """Spoken-word count. Hyphenated words count once; '/analyze' counts as one."""
    cleaned = re.sub(r"\[[^\]]*\]", " ", text)          # [Music], [inaudible]
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", cleaned)  # timestamps
    tokens = re.findall(r"[\w/’'-]+", cleaned)
    tokens = [t for t in tokens if any(ch.isalnum() for ch in t)]
    if strip_filler:
        tokens = [t for t in tokens if t.lower().strip("'’-") not in _FILLER]
    return len(tokens)


def pace_band(wpm: float) -> str:
    for threshold, name in PACE_BANDS:
        if wpm < threshold:
            return name
    return "very_fast"


def cmd_pace(args: argparse.Namespace) -> int:
    if args.transcript_file:
        text = Path(args.transcript_file).read_text(encoding="utf-8")
        words = count_words(text, strip_filler=args.strip_filler)
    elif args.transcript:
        words = count_words(args.transcript, strip_filler=args.strip_filler)
    elif args.words is not None:
        words = args.words
    else:
        print("give --words, --transcript, or --transcript-file", file=sys.stderr)
        return 2

    duration = args.duration
    if duration <= 0:
        print("--duration must be greater than 0", file=sys.stderr)
        return 2

    # A silent video is a real case: report null WPM rather than 0, which would
    # read downstream as "spoke very slowly".
    if words == 0:
        result = {
            "word_count": 0,
            "duration_seconds": duration,
            "words_per_minute": None,
            "pace_band": None,
            "note": "no speech detected — analyse on-screen text as the script",
        }
    else:
        wpm = words / (duration / 60)
        result = {
            "word_count": words,
            "duration_seconds": duration,
            "words_per_minute": round(wpm),
            "pace_band": pace_band(wpm),
        }
        if args.hook_seconds:
            result["hook_duration_seconds"] = args.hook_seconds
            result["hook_share_of_runtime"] = round(args.hook_seconds / duration, 3)

    print(json.dumps(result, indent=2))
    return 0


# ------------------------------------------------------------------- validate


def _require(obj: dict, path: str, errors: list[str], warnings: list[str]) -> object:
    """Walk a dotted path, recording a hard error when a required key is absent."""
    current: object = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            errors.append(f"missing required field: {path}")
            return None
        current = current[part]
    return current


def validate_analysis(data: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != "1.0":
        warnings.append(
            f"schema_version is {data.get('schema_version')!r}, expected '1.0'"
        )

    for path in (
        "source.url", "source.platform", "source.video_id", "source.status",
        "metrics.duration_seconds", "metrics.word_count",
        "transcript.full_text", "format.primary", "topic_and_angle.topic",
        "hook.verbatim", "hook.types", "visual_layout.framing",
        "storytelling_structure.sections", "confidence.transcript",
    ):
        _require(data, path, errors, warnings)

    source = data.get("source", {})
    if source.get("platform") not in VALID_PLATFORMS and "platform" in source:
        errors.append(f"source.platform {source['platform']!r} not in {sorted(VALID_PLATFORMS)}")
    status = source.get("status")
    if status is not None and status not in VALID_STATUS:
        errors.append(f"source.status {status!r} not in {sorted(VALID_STATUS)}")
    if status in {"unavailable", "partial"} and not source.get("unavailable_reason"):
        errors.append(f"source.status is {status!r} but unavailable_reason is empty")

    fmt = data.get("format", {})
    if fmt.get("primary") and fmt["primary"] not in FORMATS:
        errors.append(f"format.primary {fmt['primary']!r} not in the format taxonomy")

    hook = data.get("hook", {})
    types = hook.get("types")
    if isinstance(types, list):
        unknown = [t for t in types if t not in HOOK_TYPES]
        if unknown:
            errors.append(f"unknown hook.types: {unknown}")
        if not types:
            warnings.append("hook.types is empty")
    alignment = (hook.get("payoff_alignment") or {}).get("score")
    if alignment is not None and not (isinstance(alignment, int) and 1 <= alignment <= 5):
        errors.append(f"hook.payoff_alignment.score must be an integer 1-5, got {alignment!r}")
    if alignment is not None and not (hook.get("payoff_alignment") or {}).get("reasoning"):
        errors.append("hook.payoff_alignment.score given with no reasoning")
    if hook.get("pattern") and "<" not in hook["pattern"]:
        warnings.append(
            "hook.pattern has no <PLACEHOLDER> — it may be the verbatim line rather "
            "than a reusable template"
        )

    cta = data.get("cta", {})
    if cta.get("type") and cta["type"] not in CTA_TYPES:
        errors.append(f"cta.type {cta['type']!r} not in the CTA taxonomy")
    if cta.get("present") and not cta.get("verbatim"):
        warnings.append("cta.present is true but verbatim is empty")

    metrics = data.get("metrics", {})
    words = metrics.get("word_count")
    duration = metrics.get("duration_seconds")
    wpm = metrics.get("words_per_minute")
    if isinstance(words, (int, float)) and words == 0 and wpm not in (None,):
        errors.append("word_count is 0 so words_per_minute must be null, not a number")
    if all(isinstance(v, (int, float)) for v in (words, duration, wpm)) and duration:
        expected = words / (duration / 60)
        if wpm and abs(expected - wpm) > max(8, expected * 0.06):
            warnings.append(
                f"words_per_minute {wpm} disagrees with word_count/duration "
                f"({expected:.0f}) — recompute with `pace`"
            )
    for key in ("views", "likes", "comments", "engagement_rate"):
        if key in metrics and metrics[key] in ("", "unknown", "n/a"):
            errors.append(f"metrics.{key} uses a placeholder string; use null instead")

    structure = data.get("storytelling_structure", {})
    sections = structure.get("sections")
    if isinstance(sections, list):
        names = [s.get("name") for s in sections if isinstance(s, dict)]
        unknown = [n for n in names if n not in SECTIONS]
        if unknown:
            errors.append(f"unknown storytelling section names: {unknown}")
        completeness = structure.get("completeness")
        if completeness and re.fullmatch(r"\d+/7", str(completeness)):
            claimed = int(str(completeness).split("/")[0])
            present = len([s for s in sections
                           if isinstance(s, dict) and s.get("strength") != "absent"])
            if claimed != present:
                warnings.append(
                    f"completeness says {completeness} but {present} sections are present"
                )

    return errors, warnings


def cmd_validate(args: argparse.Namespace) -> int:
    failed = 0
    for path_str in args.paths:
        path = Path(path_str)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"✗ {path}: cannot read — {exc}")
            failed += 1
            continue

        errors, warnings = validate_analysis(data)
        if errors:
            failed += 1
            print(f"✗ {path}")
            for error in errors:
                print(f"    ERROR   {error}")
        else:
            print(f"✓ {path}")
        for warning in warnings:
            print(f"    warn    {warning}")

    return 1 if failed else 0


# ---------------------------------------------------------------------- batch


def cmd_batch(args: argparse.Namespace) -> int:
    loaded: list[tuple[str, dict]] = []
    skipped: list[str] = []
    for path_str in args.paths:
        path = Path(path_str)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped.append(path.name)
            continue
        # Batch files have video_count; per-video files don't. Don't tally a summary.
        if "video_count" in data:
            skipped.append(f"{path.name} (batch file)")
            continue
        loaded.append((path.name, data))

    if not loaded:
        print("no per-video analysis files found", file=sys.stderr)
        return 2

    analysed = [d for _, d in loaded if (d.get("source") or {}).get("status") == "analysed"]
    unavailable = [d for _, d in loaded
                   if (d.get("source") or {}).get("status") != "analysed"]
    total = len(analysed)

    hooks: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    ctas: Counter[str] = Counter()
    bands: Counter[str] = Counter()
    caption_styles: Counter[str] = Counter()
    missing_sections: Counter[str] = Counter()
    platforms: Counter[str] = Counter()
    creators: Counter[str] = Counter()
    alignments: list[int] = []
    durations: list[float] = []
    wpms: list[float] = []

    for data in analysed:
        source = data.get("source") or {}
        platforms[source.get("platform") or "unknown"] += 1
        if source.get("creator_handle"):
            creators[source["creator_handle"]] += 1

        for hook_type in (data.get("hook") or {}).get("types") or []:
            hooks[hook_type] += 1
        alignment = ((data.get("hook") or {}).get("payoff_alignment") or {}).get("score")
        if isinstance(alignment, int):
            alignments.append(alignment)

        fmt = data.get("format") or {}
        if fmt.get("primary"):
            formats[fmt["primary"]] += 1
        if fmt.get("production_tier"):
            tiers[fmt["production_tier"]] += 1

        cta_type = (data.get("cta") or {}).get("type")
        if cta_type:
            ctas[cta_type] += 1

        metrics = data.get("metrics") or {}
        if metrics.get("pace_band"):
            bands[metrics["pace_band"]] += 1
        if isinstance(metrics.get("duration_seconds"), (int, float)):
            durations.append(float(metrics["duration_seconds"]))
        if isinstance(metrics.get("words_per_minute"), (int, float)):
            wpms.append(float(metrics["words_per_minute"]))

        style = ((data.get("visual_layout") or {}).get("captions") or {}).get("style")
        if style:
            caption_styles[style] += 1

        structure = data.get("storytelling_structure") or {}
        present = {s.get("name") for s in (structure.get("sections") or [])
                   if isinstance(s, dict) and s.get("strength") != "absent"}
        for section in SECTIONS:
            if section not in present:
                missing_sections[section] += 1

    def show(title: str, counter: Counter[str]) -> None:
        if not counter:
            return
        print(f"\n{title}")
        for key, count in counter.most_common():
            bar = "█" * count
            print(f"  {key:<24} {count}/{total}  {bar}")

    def span(title: str, values: list[float], unit: str = "") -> None:
        if not values:
            return
        values = sorted(values)
        mid = values[len(values) // 2]
        print(f"\n{title}")
        print(f"  min {values[0]:.0f}{unit} · median {mid:.0f}{unit} · "
              f"max {values[-1]:.0f}{unit} · mean {sum(values) / len(values):.0f}{unit}")

    print(f"BATCH TALLY — {total} analysed"
          + (f", {len(unavailable)} unavailable" if unavailable else ""))
    if skipped:
        print(f"skipped: {', '.join(skipped)}")
    for data in unavailable:
        source = data.get("source") or {}
        print(f"  unavailable: {source.get('video_id', '?')} — "
              f"{source.get('unavailable_reason') or 'no reason recorded'}")

    print("\nScope")
    print(f"  platforms   {dict(platforms)}")
    if creators:
        print(f"  creators    {len(creators)} distinct")
        if len(creators) == 1:
            print("  ⚠ single creator — patterns describe this creator's style, "
                  "not the niche")
    if total < 4:
        print(f"  ⚠ only {total} videos — prevalence counts are weak evidence")

    show("Hook types (a hook can have several)", hooks)
    show("Format (primary)", formats)
    show("Production tier", tiers)
    show("CTA type", ctas)
    show("Pace band", bands)
    show("Caption style", caption_styles)
    show("Sections MISSING (higher = more often absent)", missing_sections)
    span("Duration", durations, "s")
    span("Words per minute", wpms)

    if alignments:
        counts = Counter(alignments)
        print("\nHook-payoff alignment")
        for score in sorted(counts, reverse=True):
            print(f"  {score}/5{'':<19} {counts[score]}/{total}  {'█' * counts[score]}")
        print(f"  mean {sum(alignments) / len(alignments):.1f}/5")

    # The floor is two videos, not a percentage — with a tiny set that floor is
    # nearly everything, which is itself the finding.
    if total < 3:
        print(f"\nReminder: with only {total} analysed, the 2-video floor for a "
              "pattern means almost nothing here qualifies. Report these as "
              "observations and say the sample is too small.")
    else:
        print(f"\nReminder: a claim needs to hold in at least 2 of {total} videos to "
              "be a pattern. Below that, it goes in outliers.")
    print("Trends need publish dates and a spread of them — check before claiming one.")
    return 0


# ----------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metrics.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pace = sub.add_parser("pace", help="words + duration -> WPM and band")
    pace.add_argument("--words", type=int)
    pace.add_argument("--transcript")
    pace.add_argument("--transcript-file")
    pace.add_argument("--duration", type=float, required=True, help="seconds")
    pace.add_argument("--hook-seconds", type=float, default=0.0)
    pace.add_argument("--strip-filler", action="store_true",
                      help="drop uh/um before counting")
    pace.set_defaults(func=cmd_pace)

    validate = sub.add_parser("validate", help="check JSON against the contract")
    validate.add_argument("paths", nargs="+")
    validate.set_defaults(func=cmd_validate)

    batch = sub.add_parser("batch", help="tally taxonomies across analyses")
    batch.add_argument("paths", nargs="+")
    batch.set_defaults(func=cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
