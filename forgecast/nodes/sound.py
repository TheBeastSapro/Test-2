"""The sound stage: a bed under the narration, and the accents on top of it.

## Why this is a node of its own rather than part of `finalize.render`

Three reasons, in the order they would have bitten.

**`render` retries and this must not.** Its spec carries `max_attempts=2`, which is
correct for an ffmpeg assembly that can lose a race on a temporary file. It is wrong for a
vendor fetch: a retried render would buy the bed a second time, and on this vendor a
download is not merely a cost — Epidemic's terms make exporting a track into published
content a reportable event, so the second fetch is a second export of a video that ships
once. Every other stage in this graph that spends sits in a node that does not retry
around the spend, and this follows it.

**The mix has to exist before the picture is muxed.** `assemble_video` masters the
finished programme to the platform target as its last pass. Producing the bed here and
handing `render` one audio track means that master measures voice, bed and accents
together — which is the operator's own rule, "calibrate after ducking, not before",
because with dense narration the sidechain pulls the bed below whatever was set before it.
Scoring a *finished* video instead would mean mastering the dry narration, adding music
underneath afterwards, and then re-encoding the whole file a second time to master again.

**A stage that can be skipped should be visible when it is skipped.** No music vendor, or
a vendor that failed, is a fact about the video that an operator should be able to read off
the run. As its own node it has a status, a log line and an output that says which track
played. Folded into `render` it would be four lines in the middle of a node whose output is
about resolutions and shot counts.

It depends on `voice` rather than on `script` alone because both numbers it needs — how
long the bed must run, and how loud it must be — come from the narration that actually
exists, not from the script's estimate of it.

## What it will not do

It will not fetch anything unless the channel named a music vendor. `providers.registry`
lists no default music vendor precisely so that this cannot happen by inheritance, and the
check here is the second lock rather than the only one.

It will not fail the run. Every failure below degrades to what survived plus the named
reason for what did not — because a finished video with no bed is a smaller loss than no
video, and because the alternative failure mode, a run that dies at the last stage after
paying for research, a script, narration and B-roll, is the expensive one. Degrading is
still reported as degrading: a video with accents and no bed says so rather than reporting
itself complete.

It does not place the plan's **ambience** layer. `style.sound.design` puts room tone under
everything, on the grounds that a cut into digital silence reads as a mistake even when the
edit is clean, and that rule is right — but placing it needs a room-tone source, and
choosing one by keyword is exactly the casting-by-keyword error the method warns about
(a "crowd" bed never ducks, so it becomes a second narrator for as long as it runs). Where
a music bed runs, the bed is the floor. Where one does not, this stage leaves the floor
where it found it and the plan's ambience cue stands as an unmet recommendation rather than
as something quietly satisfied.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers.base import MusicTrack, ProviderError
from ..render import RenderError
from ..render import audio as mixing
from ..style import SoundBrief, SoundPlan, brief_from, design, recommend

# The measured figures belong to the sound-designer method and are read from where that
# method documents them, rather than copied into this file. The types and builders above
# are the style package's public API; these are its numbers.
from ..style.sound import (
    BED_UNDER_VOICE_DB,
    DUCK_DB,
    FILE_COOLDOWN_SECONDS,
    MAX_USES_PER_FILE,
)

# Shorter than this and a "bed" is a sting being looped every forty seconds, which the ear
# learns in about two passes. The catalogue holds plenty above it, so the filter costs
# nothing and rules out the one class of track that cannot work.
MIN_SOURCE_SECONDS = 90.0

# How many distinct files to fetch per accent role. Repetition, not density, is what
# "sounds cheap" actually means — the reference render placed 474 cues drawn from seven
# files and one tick played 240 times. Four per role plus the per-file limits below is what
# keeps a whoosh from becoming a tell.
PALETTE_PER_ROLE = 4

# The search word per planned action. Deliberately a free-text term rather than a tag slug:
# a slug that does not exist in the vendor's taxonomy returns an empty page, which reads as
# "the library has no whooshes" rather than as a query that was wrong, and the slugs cannot
# be verified from here without a live credential.
ACCENT_TERMS = {
    "whoosh": "whoosh transition",
    "riser": "riser build up",
    "impact": "deep impact boom",
}

# A one-shot longer than this is not a one-shot, it is a passage. The method's rule is that
# library recordings are *takes* — one "sword on shield" file held four separate blows, and
# placed whole it read as a slam and anchored 695 ms late. Splitting takes into single hits
# is not implemented here, so the length filter is what keeps them out instead.
MAX_ACCENT_SECONDS = 6.0


def bed_levels(brief: SoundBrief) -> tuple[float, float, str]:
    """Where the bed sits, how hard it ducks, and where the first number came from.

    Two quantities that one field name has hidden before, and conflating them makes a bed
    that is either always too quiet or ducks so hard it disappears on every word:

    * **Where it sits** is a level, measured against the narration. The operator's own
      figure is 13 dB under, taken on the music stem. A reference that has actually been
      analysed can improve on that for this channel, so a brief with any evidence behind
      it wins — and a brief with none is the house figure rather than a convention
      dressed up as a measurement.
    * **How hard it ducks** is a compressor depth, and it is always the house figure. Not
      because the reference does not matter but because nothing in a finished video can
      report it: ducking depth and bed level are not separable without the stems, which
      is exactly what the brief says about itself when it flags that unknown.
    """
    if brief.confidence != "none":
        return abs(brief.duck_under_db), abs(DUCK_DB), "measured on this channel's reference"
    return abs(BED_UNDER_VOICE_DB), abs(DUCK_DB), "the house figure — nothing measured"


def chosen_vendor(ctx: NodeContext) -> str:
    """Which music vendor this run is allowed to spend on. Empty means none.

    Four places, most specific first: this run's provider overrides, this run's options,
    the channel's standing choice, and the pipeline's own parameter. Empty at the end of
    all four is not an error — it is a channel that has not asked for music, which is the
    default state and produces a video without any.
    """
    overrides = dict(ctx.options.get("provider_overrides") or {})
    style = ctx.channel.style_profile or {}
    return str(
        overrides.get("music")
        or ctx.options.get("music_vendor")
        or style.get("music_vendor")
        or ctx.params.get("music_vendor")
        or ""
    ).strip()


def brief_for(ctx: NodeContext) -> tuple[SoundBrief, str]:
    """What this video's sound should be, and where that came from.

    A channel that has had a reference analysed carries the measurements on its style
    profile, and those are what `brief_from` reads. A channel that has not gets the niche's
    convention, which labels itself as convention — the brief's own `confidence` field goes
    to "none" and its `unknowns` say so, so the two never read alike in the output.
    """
    style = ctx.channel.style_profile or {}
    measured = style.get("audio") or {}
    if measured:
        return (
            brief_from(measured, style.get("beat_alignment") or {}),
            "measured from this channel's reference video",
        )
    return (
        recommend(ctx.channel.niche),
        "the convention for this niche — no reference video has been analysed, so nothing "
        "here was measured",
    )


def wants_effects(ctx: NodeContext) -> bool:
    """Accents are opt-out, like motion. Three places can turn them off."""
    style = ctx.channel.style_profile or {}
    return False not in (
        ctx.options.get("sound_effects"),
        ctx.params.get("sound_effects"),
        style.get("sound_effects"),
    )


def choose_track(tracks: list[MusicTrack], brief: SoundBrief) -> tuple[MusicTrack, str]:
    """The bed, and one sentence saying why it rather than the others.

    Recorded because a bed nobody can argue with is a bed nobody checked. The order is
    deliberate: a track that sings is refused outright however well it scores otherwise —
    a bed does not duck out of its own vocal, so a vocal bed is a second narrator for as
    long as it runs.
    """
    instrumental = [track for track in tracks if not track.has_vocals]
    if not instrumental:
        raise ProviderError(
            "every candidate bed came back with a vocal stem, and a bed that sings "
            "competes with the narration for the whole video",
            provider="sound",
        )

    def distance(track: MusicTrack) -> float:
        if not brief.tempo_bpm or not track.bpm:
            return 0.0
        return abs(track.bpm - brief.tempo_bpm)

    ranked = sorted(instrumental, key=lambda track: (distance(track),
                                                     -track.duration_seconds))
    best = ranked[0]
    if brief.tempo_bpm and best.bpm:
        why = (f"{best.bpm} BPM against the {brief.tempo_bpm:.0f} BPM measured on the "
               f"reference, the closest of {len(instrumental)} instrumental candidates")
    else:
        why = (f"the longest of {len(instrumental)} instrumental candidates at "
               f"{best.duration_seconds:.0f}s — no usable tempo to match against, so "
               f"length is the only thing worth choosing on")
    return best, why


def assign_files(
    cues: list, palette: dict[str, list[dict]]
) -> tuple[list[tuple[Path, float, float]], list[str], int]:
    """Give every accent cue a file, without letting one file become the video's tell.

    Two limits, both from the method and both measured rather than chosen: no file returns
    inside `FILE_COOLDOWN_SECONDS`, and none is used more than `MAX_USES_PER_FILE` times in
    the whole video. A cue that cannot be served under those limits is dropped and counted,
    not served by repeating something — because the failure being avoided is not "too few
    effects", it is one tick played two hundred and forty times.
    """
    placements: list[tuple[Path, float, float]] = []
    used: list[str] = []
    last_at: dict[str, float] = {}
    counts: dict[str, int] = {}
    dropped = 0

    for cue in sorted(cues, key=lambda item: item.at_seconds):
        options = palette.get(cue.action) or []
        pick = None
        for option in options:
            key = option["effect_id"]
            if counts.get(key, 0) >= MAX_USES_PER_FILE:
                continue
            if cue.at_seconds - last_at.get(key, -1e9) < FILE_COOLDOWN_SECONDS:
                continue
            pick = option
            break
        if pick is None:
            dropped += 1
            continue
        key = pick["effect_id"]
        counts[key] = counts.get(key, 0) + 1
        last_at[key] = cue.at_seconds
        placements.append((Path(pick["path"]), cue.at_seconds, cue.gain_db))
        if key not in used:
            used.append(key)
        # Round-robin rather than always-the-first: leaving the order alone would use file
        # one until its cooldown bit, then file two, which is the same repetition problem
        # spread over a longer window.
        options.append(options.pop(options.index(pick)))

    return placements, used, dropped


async def fetch_palette(ctx: NodeContext, provider, plan: SoundPlan) -> dict[str, list[dict]]:
    """A few distinct files per accent role, each downloaded once and reused by rule.

    Fetched per role rather than per cue. A keyword search per cue is what produces a
    palette of seven files across five hundred placements; searching once and rationing the
    result is what produces a palette at all.
    """
    wanted = {cue.action for cue in plan.at_layer("accent")}
    palette: dict[str, list[dict]] = {}

    for action in sorted(wanted):
        term = ACCENT_TERMS.get(action)
        if term is None:
            continue
        found = await provider.search_sound_effects(
            term=term, seconds_max=MAX_ACCENT_SECONDS, limit=PALETTE_PER_ROLE
        )
        entries: list[dict] = []
        for index, effect in enumerate(found[:PALETTE_PER_ROLE]):
            try:
                result = await provider.fetch_sound_effect(
                    effect.effect_id, out_path=ctx.path_for(f"sfx_{action}_{index}")
                )
            except ProviderError as exc:
                # One missing file is not a missing palette. The cue assignment below
                # rations whatever did arrive and drops what it cannot serve.
                ctx.log(f"could not fetch the {action} '{effect.title}': {exc}",
                        level="warning")
                continue
            entries.append({
                "effect_id": effect.effect_id, "title": effect.title,
                "path": str(result.path), "seconds": round(result.duration_seconds, 2),
                "provider": result.provider,
            })
        if not entries:
            # The method is explicit that a missing palette category must warn rather than
            # be skipped: rebuilding a palette once dropped a category, and every strike
            # silently lost its weight layer for a whole render.
            ctx.log(f"no usable {action} files came back, so every {action} cue in the "
                    f"plan is unplaced", level="warning")
            continue
        palette[action] = entries

    return palette


@node_handler("sound")
async def sound_node(ctx: NodeContext) -> NodeResult:
    voice_output = ctx.output("voice")
    narration = Path(str(voice_output.get("narration_path") or ""))
    segments = sorted(
        (item for item in voice_output.get("segments") or []
         if isinstance(item, dict) and item.get("seconds")),
        key=lambda item: int(item.get("scene_index") or 0),
    )
    scene_seconds = [float(item["seconds"]) for item in segments]
    total = float(voice_output.get("total_seconds") or sum(scene_seconds) or 0.0)

    brief, provenance = brief_for(ctx)
    plan = design(brief, scene_seconds)
    base = {
        "brief": brief.as_dict(),
        "brief_from": provenance,
        "plan": plan.as_dict(),
    }

    if not narration.exists() or total <= 0:
        return _silent(ctx, base,
                       "there is no narration to score — the voice stage produced no "
                       "audio, so there is nothing to sit a bed under")

    vendor = chosen_vendor(ctx)
    if not vendor:
        # The consent gate. Not a degradation and not reported as one: a channel that has
        # not chosen a music vendor gets a video with no music, and the run says so
        # plainly rather than either fetching one or failing.
        return _silent(ctx, base,
                       "no music vendor is set for this channel, so nothing was fetched. "
                       "Choose one on the channel to score its videos")

    accents = plan.at_layer("accent") if wants_effects(ctx) else []
    if not brief.music_bed and not accents:
        return _silent(ctx, base,
                       "this channel's sound is voice and room — "
                       + (brief.reasons[0] if brief.reasons else "no bed was measured"))

    try:
        provider = ctx.registry.music(vendor)
    except ProviderError as exc:
        return _degraded(ctx, base, f"the {vendor} music vendor is not usable: {exc}")

    try:
        return await _score(ctx, provider, brief, plan, base,
                            narration=narration, total=total, accents=accents)
    except (ProviderError, RenderError, OSError) as exc:
        # `_score` guards each half of the design itself, so reaching here means something
        # outside both of them went wrong. Every earlier stage has been paid for and the
        # picture is about to be rendered either way: a named reason on a finished video
        # beats a failed run.
        return _degraded(ctx, base, f"scoring failed and the video is unscored: {exc}")


async def _score(
    ctx: NodeContext, provider, brief: SoundBrief, plan: SoundPlan, base: dict,
    *, narration: Path, total: float, accents: list,
) -> NodeResult:
    """Buy, level, duck and place.

    The bed and the accents are guarded separately, which is the whole reason this is not
    one long try block. A bed that has been fetched has already been *exported* against the
    operator's licence; throwing it away because a whoosh failed would be a reportable
    event spent on a video that then shipped without it. Each half fails on its own and
    whatever survives is what ships.
    """
    output = dict(base)
    mix = narration
    credits = 0
    track_record: dict | None = None
    levels: dict = {}
    failures: list[str] = []

    if brief.music_bed:
        try:
            mix, track_record, levels, credits = await _lay_bed(
                ctx, provider, brief, narration=narration, total=total
            )
        except (ProviderError, RenderError, OSError) as exc:
            # Recorded and carried on rather than raised: the accents below are a separate
            # purchase and a separate piece of the design, and a video with them is better
            # than one with neither.
            failures.append(str(exc))
            ctx.log(f"no bed: {exc}", level="warning")

    placed: list[dict] = []
    dropped = 0
    if accents:
        try:
            mix, placed, dropped = await _lay_accents(ctx, provider, plan, accents, mix)
        except (ProviderError, RenderError, OSError) as exc:
            failures.append(str(exc))
            ctx.log(f"no accents: {exc}", level="warning")

    if mix == narration:
        return _degraded(
            ctx, base,
            "; ".join(failures) or "nothing could be placed: the plan asked for accents "
            "and none of them could be served",
        )

    ctx.emit_artifact("audio", mix, "audio/mp4", role="scored_narration")
    output.update({
        "music": track_record is not None,
        "track": track_record,
        "mixed_path": str(mix),
        "levels": levels,
        "effects": placed,
        "accents_placed": len(accents) - dropped,
        "accents_dropped": dropped,
        # A half-scored video is still a degraded one. "This video has accents" and "this
        # video has the sound it was designed to have" are different claims, and a run
        # that reports the second while delivering the first is how a broken half of a
        # vendor stays broken.
        "degraded": bool(failures),
        "reason": "; ".join(failures),
    })
    if failures:
        ctx.log("scored, but not completely: " + "; ".join(failures), level="warning")
    return NodeResult(output=output, credits=credits,
                      provider=getattr(provider, "name", "music"))


async def _lay_bed(
    ctx: NodeContext, provider, brief: SoundBrief, *, narration: Path, total: float,
) -> tuple[Path, dict, dict, int]:
    """Search, choose, fetch, level and duck. Returns the mix and the licence record."""
    wanted = brief.search_filter().get("bpm") or {}
    tracks = await provider.search_tracks(
        topic=_headline(ctx),
        bpm_min=int(wanted.get("min") or 0),
        bpm_max=int(wanted.get("max") or 0),
        seconds_min=MIN_SOURCE_SECONDS,
        # Always, and not read off the brief. `search_filter` asks for it whenever it asks
        # for anything, and the one format where a vocal is the point — ambient, where the
        # brief ducks by 0 dB — has no narration, which this pipeline always has.
        instrumental_only=True,
        limit=10,
    )

    tempo_dropped = False
    if not tracks and wanted:
        # The tempo window is the tightest thing in the search and the least costly to
        # lose. A bed at the wrong tempo under a narrated video is a mild mismatch; no bed
        # at all is the video having no sound design, so the window is widened once and
        # the fact is recorded rather than the search being reported as a failure.
        tempo_dropped = True
        ctx.log(f"no bed between {wanted['min']} and {wanted['max']} BPM — searching "
                f"again without the tempo window", level="warning")
        tracks = await provider.search_tracks(
            topic=_headline(ctx), seconds_min=MIN_SOURCE_SECONDS,
            instrumental_only=True, limit=10,
        )

    if not tracks:
        raise ProviderError(
            f"no instrumental bed at least {MIN_SOURCE_SECONDS:.0f}s long matched "
            f"{_headline(ctx)!r}",
            provider=getattr(provider, "name", "music"),
        )

    track, why = choose_track(tracks, brief)
    if tempo_dropped:
        why += ", after the measured tempo window returned nothing and was dropped"
    # Only when the vendor handed back a vocal track anyway. A track that already has no
    # vocals gains nothing from stem isolation and loses the length-matched edit, which is
    # the better bed — an edit ends musically where a looped stem fades out.
    stem = track.instrumental_stem if track.has_vocals else ""

    bought = await provider.make_bed(
        track.track_id, out_path=ctx.path_for("bed_source"), seconds=total, stem=stem
    )

    # Run even when the vendor cut the edit to length. `duck_under` mixes for the length of
    # the voice, so an over-long bed would be cut dead on the last word; this is what gives
    # the tail its fade, and it is the guarantee that the two lengths agree rather than an
    # assumption that they do.
    bed = await asyncio.to_thread(
        mixing.loop_to_length, bought.path, ctx.path_for("bed.m4a"), total
    )

    under_db, depth_db, level_source = bed_levels(brief)
    gain, voice_level, bed_level = await asyncio.to_thread(
        mixing.bed_gain_for, narration, bed, under_db=under_db
    )
    mix = await asyncio.to_thread(
        mixing.duck_under, narration, bed, ctx.path_for("mixed.m4a"),
        depth_db=depth_db, music_gain_db=gain,
    )

    levels = {
        "narration_lufs": round(voice_level.integrated_lufs, 2),
        "bed_lufs_before_gain": round(bed_level.integrated_lufs, 2),
        "bed_gain_db": round(gain, 2),
        "bed_under_voice_db": round(under_db, 1),
        "bed_under_voice_from": level_source,
        "duck_depth_db": round(depth_db, 1),
        # The house figures alongside what was applied, so a channel that has drifted away
        # from them is visible rather than merely different.
        "house_bed_under_voice_db": abs(BED_UNDER_VOICE_DB),
        "house_duck_depth_db": abs(DUCK_DB),
    }
    record = {
        # The licence record. An id is what makes a shipped bed traceable, and an
        # untraceable bed in a monetised render is the thing this whole stage was gated on.
        "track_id": track.track_id,
        "title": track.title,
        "artists": track.artists,
        "bpm": track.bpm,
        "seconds": round(track.duration_seconds, 2),
        "stem": stem or "full mix",
        "provider": bought.provider,
        "licence": bought.meta.get("licence", ""),
        "route": bought.meta.get("route", ""),
        "tempo_window_dropped": tempo_dropped,
        "why": why,
    }
    ctx.emit_artifact(
        "audio", bed, "audio/mp4", role="music_bed", track_id=track.track_id,
        title=track.title, licence=bought.meta.get("licence", ""),
    )
    ctx.log(f"bed: {track.title} ({track.track_id}) — {why}; levelled "
            f"{gain:+.1f} dB to sit {under_db:.0f} dB under the voice "
            f"({level_source}), ducking {depth_db:.0f} dB on speech")
    return mix, record, levels, bought.credits


async def _lay_accents(
    ctx: NodeContext, provider, plan: SoundPlan, accents: list, mix: Path,
) -> tuple[Path, list[dict], int]:
    """Fetch a palette, ration it across the planned cues, and mix them over the top."""
    palette = await fetch_palette(ctx, provider, plan)
    placements, used, dropped = assign_files(accents, palette)
    if not placements:
        return mix, [], dropped

    scored = await asyncio.to_thread(
        mixing.place_accents, mix, ctx.path_for("scored.m4a"), placements
    )
    flat = [entry for entries in palette.values() for entry in entries]
    placed = [entry for entry in flat if entry["effect_id"] in used]
    ctx.log(f"{len(placements)} accents placed from {len(placed)} distinct files"
            + (f", {dropped} cues dropped rather than repeat one inside "
               f"{FILE_COOLDOWN_SECONDS:.0f}s" if dropped else ""))
    return scored, placed, dropped


def _headline(ctx: NodeContext) -> str:
    script = ctx.upstream_outputs.get("script") or {}
    return str(script.get("title") or ctx.topic or "").strip()


def _silent(ctx: NodeContext, base: dict, reason: str) -> NodeResult:
    """A video with no music, by decision rather than by failure."""
    ctx.log(f"no music: {reason}")
    return NodeResult(
        output={**base, "music": False, "track": None, "mixed_path": None,
                "levels": {}, "effects": [], "accents_placed": 0, "accents_dropped": 0,
                "degraded": False, "reason": reason},
        credits=0,
        provider="local",
    )


def _degraded(ctx: NodeContext, base: dict, reason: str) -> NodeResult:
    """A video with no music, where music was wanted and could not be had.

    Kept apart from `_silent` in the output as well as in the log. "This channel scores
    nothing" and "this channel scores everything and today's bed failed" are different
    facts, and collapsing them is how a broken connector goes unnoticed for a month.
    """
    ctx.log(f"no music: {reason}", level="warning")
    return NodeResult(
        output={**base, "music": False, "track": None, "mixed_path": None,
                "levels": {}, "effects": [], "accents_placed": 0, "accents_dropped": 0,
                "degraded": True, "reason": reason},
        credits=0,
        provider="local",
    )
