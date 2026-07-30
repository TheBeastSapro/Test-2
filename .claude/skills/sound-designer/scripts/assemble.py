#!/usr/bin/env python3
"""assemble.py — the Sound Designer "hands".

Takes a cue sheet (with assets resolved) + the mastered VO and renders the
final mix: music bed (fit + faded + placed), SFX hits, sidechain-ducked under
the voice, then mastered to the YouTube loudness target.

Asset resolution per cue, in order:
  1. cue["asset"]                      (explicit path, e.g. filled by the Epidemic MCP)
  2. <assets>/<cue id>.<ext>           (manual-drop convenience: m1.mp3, s3.wav, ...)
  3. skip (warn)

Usage:
  assemble.py --cues cues.json --vo vo.mp3 --out "Title (mixed).mp3"
              [--assets ./assets] [--stems ./stems] [--mux-into in.mp4]
              [--music-db 0] [--sfx-db 0] [--no-duck]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import tempfile

from common import FFMPEG, run, media_info, fmt_ts

SR = 48000
CH = "stereo"


def resolve_asset(cue: dict, assets_dir: str | None) -> str | None:
    if cue.get("asset") and os.path.exists(cue["asset"]):
        return cue["asset"]
    if assets_dir:
        hits = glob.glob(os.path.join(assets_dir, cue["id"] + ".*"))
        if hits:
            return sorted(hits)[0]
    return None


def dur_of(path: str) -> float:
    return media_info(path)["duration"]


_PEAK = {}


def transient_offset(path: str) -> float:
    """Seconds from file start to the sound's ATTACK, via librosa onset detection.

    Placing a hit by its file start is not synchronisation: the audible
    transient is later. The loudest *sample* is not the right anchor either --
    a whoosh peaks well after it starts, and the ear locks to the attack. So
    take the first onset librosa reports, and fall back to peak amplitude only
    if onset detection finds nothing.
    """
    if path in _PEAK:
        return _PEAK[path]
    import numpy as np
    off = 0.0
    try:
        import librosa
        y, sr = librosa.load(path, sr=22050, mono=True)
        if y.size:
            on = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
            if len(on):
                off = float(on[0])
            else:
                off = float(np.argmax(np.abs(y))) / sr
    except Exception:
        from common import decode_mono_pcm
        x, sr = decode_mono_pcm(path, 22050)
        off = float(np.argmax(np.abs(x))) / sr if x.size else 0.0
    _PEAK[path] = off
    return off


def energy_onset(path: str, db: float = -12.0, limit: float = 30.0) -> float:
    """Seconds until the file first reaches `db` below its own peak.

    Library tracks often open on a long ambient swell. Starting a section at
    sample 0 then means the new cue is inaudible for several seconds and the
    era change reads as 'the music never changed' -- measured at 8-17 s on
    five of seventeen tracks in one video.
    """
    import numpy as np
    from common import decode_mono_pcm
    x, sr = decode_mono_pcm(path, 22050)
    if x.size == 0:
        return 0.0
    n = int(0.05 * sr)
    seg = x[:int(sr * limit)]
    e = np.array([np.sqrt(np.mean(seg[i:i + n].astype(np.float64) ** 2))
                  for i in range(0, len(seg), n)])
    if e.size == 0 or e.max() <= 0:
        return 0.0
    i = int(np.argmax(e >= e.max() * 10 ** (db / 20)))
    return max(0.0, i * 0.05 - 0.25)          # land just before it blooms


def render_music_seg(asset, start, dur, fin, fout, gain_db, work, idx, skip=0.0) -> str:
    """Fit an asset to `dur`, fade, gain, delay to `start`; write a wav."""
    out = os.path.join(work, f"m_{idx}.wav")
    loop = dur_of(asset) < dur + skip - 0.1
    if loop:
        skip = 0.0
    fout_st = max(0.0, dur - fout)
    delay_ms = int(round(start * 1000))
    af = (
        f"aformat=sample_rates={SR}:channel_layouts={CH},"
        f"atrim={skip:.3f}:{skip + dur:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fin:.3f},"
        f"afade=t=out:st={fout_st:.3f}:d={fout:.3f},"
        f"volume={gain_db:.2f}dB,"
        f"adelay={delay_ms}:all=1"
    )
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", asset, "-filter:a", af, "-ac", "2", "-ar", str(SR), out]
    run(cmd)
    return out


def render_sfx_seg(asset, at, gain_db, work, idx, vary: float = 0.0) -> str:
    """Place one SFX. `vary` in [0,1) detunes and re-levels it.

    A dense track re-using a handful of sources reads as repetitive fast. Real
    designers never drop the identical file twice; shifting pitch a few percent
    and trimming a decibel or two makes the same hit feel like a family of hits.
    """
    out = os.path.join(work, f"s_{idx}.wav")
    delay_ms = int(round(at * 1000))
    chain = f"aformat=sample_rates={SR}:channel_layouts={CH},"
    if vary:
        # deterministic spread: ~-15%..+15% pitch, -2.5..0 dB
        k = 0.86 + 0.30 * vary
        gain_db += -2.5 * ((vary * 7.0) % 1.0)
        chain += f"asetrate={int(SR * k)},aresample={SR},"
    chain += (f"afade=t=in:st=0:d=0.005,volume={gain_db:.2f}dB,"
              f"adelay={delay_ms}:all=1")
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", asset,
         "-filter:a", chain, "-ac", "2", "-ar", str(SR), out])
    return out


def render_sfx_short(asset, gain_db, work, idx, vary: float = 0.0) -> str:
    """One SFX at its own length — no delay padding. See build_sfx_bus."""
    out = os.path.join(work, f"sh_{idx}.wav")
    chain = f"aformat=sample_rates={SR}:channel_layouts={CH},"
    if vary:
        # rubberband shifts pitch and leaves the duration alone; asetrate was a
        # varispeed, which also moved the transient and broke the alignment.
        semis = -3.0 + 6.0 * vary
        gain_db += -2.5 * ((vary * 7.0) % 1.0)
        chain += f"rubberband=pitch={2 ** (semis / 12):.4f},"
    chain += f"afade=t=in:st=0:d=0.005,volume={gain_db:.2f}dB"
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", asset,
         "-filter:a", chain, "-ac", "2", "-ar", str(SR), out])
    return out


def build_sfx_bus(items, out: str, total: float, work: str, batch: int = 24):
    """Sum many positioned SFX without one padded file per cue.

    Delaying each hit into its own full-length wav costs total_duration per
    cue: at 231 cues on a 13-minute video that is ~17 GB of intermediates and
    it fills the disk. Instead each hit is rendered at its own length, then
    positioned with adelay inside batched filter graphs, so the number of
    full-length files is len(items)/batch rather than len(items).
    """
    if not items:
        run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"anullsrc=r={SR}:cl={CH}", "-t", f"{total:.3f}", out])
        return
    buses = []
    for bi in range(0, len(items), batch):
        chunk = items[bi:bi + batch]
        inputs, parts, labels = [], [], []
        for i, (path, at) in enumerate(chunk):
            inputs += ["-i", path]
            parts.append(f"[{i}]adelay={int(round(at * 1000))}:all=1[d{i}]")
            labels.append(f"[d{i}]")
        fc = ";".join(parts) + ";" + "".join(labels)
        fc += (f"amix=inputs={len(chunk)}:normalize=0:dropout_transition=0[m];"
               f"[m]apad=whole_dur={total:.3f},atrim=0:{total:.3f}[o]")
        b = os.path.join(work, f"sbus_{bi}.wav")
        run([FFMPEG, "-hide_banner", "-v", "error", "-y", *inputs,
             "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), b])
        buses.append(b)
    mix_bus(buses, out, total)
    for b in buses:
        try:
            os.remove(b)
        except OSError:
            pass


def mix_bus(segments: list[str], out: str, total: float):
    """Sum segments (no auto-normalize) into one bus of length `total`."""
    if not segments:
        # silent bus
        run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"anullsrc=r={SR}:cl={CH}", "-t", f"{total:.3f}", out])
        return
    if len(segments) == 1:
        inputs = ["-i", segments[0]]
        fc = f"[0:a]apad=whole_dur={total:.3f},atrim=0:{total:.3f}[o]"
    else:
        inputs = []
        for s in segments:
            inputs += ["-i", s]
        mixin = "".join(f"[{i}:a]" for i in range(len(segments)))
        fc = (f"{mixin}amix=inputs={len(segments)}:normalize=0:"
              f"dropout_transition=0[m];[m]apad=whole_dur={total:.3f},"
              f"atrim=0:{total:.3f}[o]")
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", *inputs,
         "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), out])


def to_wav(src: str, out: str, total: float | None = None):
    af = f"aformat=sample_rates={SR}:channel_layouts={CH}"
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", src,
           "-filter:a", af, "-ac", "2", "-ar", str(SR)]
    if total:
        cmd += ["-t", f"{total:.3f}"]
    run(cmd + [out])


def integrated_lufs(path: str) -> float | None:
    """Integrated loudness of a file, or None if it can't be measured."""
    res = run([FFMPEG, "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"])
    hits = re.findall(r"I:\s*(-?[0-9.]+) LUFS", res.stderr)
    return float(hits[-1]) if hits else None


def calibrate_bed(music_bus: str, vo_wav: str, target_db: float):
    """Return the trim that puts the music bus `target_db` under the VO.

    A flat --music-db trim is not a *relative* level: the VO is a hot mastered
    file while library tracks arrive at their own levels, so the same trim
    lands somewhere different on every video. Measured on a real job, a -10 dB
    trim produced a bed 21.6 dB under the voice. Measure both, then solve.
    """
    m, v = integrated_lufs(music_bus), integrated_lufs(vo_wav)
    if m is None or v is None:
        print("[assemble] could not measure loudness — leaving the trim as given")
        return None
    trim = target_db - (m - v)
    print(f"[assemble] bed calibration: music {m:.1f} LUFS, vo {v:.1f} LUFS "
          f"({m - v:+.1f} dB) -> target {target_db:+.0f} dB needs {trim:+.1f} dB")
    return trim


def mean_db(path: str, a: float, b: float):
    res = run([FFMPEG, "-hide_banner", "-i", path,
               "-af", f"atrim={a:.3f}:{b:.3f},volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume: (-?[0-9.]+)", res.stderr)
    return float(m.group(1)) if m else None


def bed_ratio(music: str, vo: str, silence: list) -> float | None:
    """Measured music-bed-vs-voice: the bed inside the VO's gaps, against the
    voice during speech.

    Measured on the STEMS, and on the music stem specifically. Both of those
    are corrections of earlier versions that landed in the wrong place:

      * An integrated-LUFS ratio is not this quantity at all -- it folds the
        ducking and the VO's own gaps together, and calibrating on it put the
        bed 5.5 dB under the voice instead of 13.
      * Measuring the finished master is worse once the SFX are doing their job.
        The master's gaps contain music AND effects AND ambience, so loud
        effects inflate the reading and the loop compensates by pulling the
        *music* down. On the v3 render that misread the bed as -5.6 dB and
        trimmed the music 7.4 dB when the true error was about 3. "Bed" means
        the music bed; the effects are foreground and are levelled by tier.
    """
    import statistics as st
    gaps = [(a, b) for a, b in silence if b - a >= 0.30][:40]
    if len(gaps) < 4:
        return None
    bed = [x for x in (mean_db(music, a + 0.05, b - 0.02) for a, b in gaps)
           if x and x > -70]
    prog = [x for x in (mean_db(vo, a - 2.0, a - 0.3) for a, b in gaps[:25] if a > 3)
            if x and x > -70]
    if len(bed) < 3 or len(prog) < 3:
        return None
    return st.median(bed) - st.median(prog)


def make_ir(work: str, seconds: float = 0.55) -> str:
    """A small synthetic room impulse, so hits sit in a space.

    Dry hits pasted at full level are the thing that reads as cheap: they have
    no relationship to the picture's space. A short diffuse tail, mixed low,
    makes the same sample sound placed rather than dropped on top.
    """
    import numpy as np
    import wave
    n = int(SR * seconds)
    rng = np.random.RandomState(7)
    t = np.arange(n) / SR
    decay = np.exp(-t * 7.5)
    ir = np.stack([rng.randn(n) * decay, rng.randn(n) * decay])
    ir[:, :int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))   # soften the front
    ir /= np.abs(ir).max()
    path = os.path.join(work, "_ir.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((ir.T.reshape(-1) * 0.5 * 32767).astype("<i2").tobytes())
    return path


def polish_sfx(src: str, out: str, work: str, wet: float = 0.16):
    """Make the SFX bus sit with the voice instead of fighting it.

    Three things separate 'satisfying' from 'irritating', and all three are
    measurable rather than matters of taste:

      * A dip through the speech band. Consonant intelligibility lives around
        1.5-4 kHz; effects with energy there mask the narration and the ear
        reads the result as noise even at a modest level.
      * A tamed top end. Everything above ~9 kHz is what makes repeated hits
        fatiguing over thirteen minutes.
      * A little weight and a little room. A low shelf gives impacts body, and
        a short tail places them in the scene.
    """
    ir = make_ir(work)
    fc = (
        "[0:a]equalizer=f=2400:t=q:w=1.1:g=-4,"          # out of the way of consonants
        "equalizer=f=3600:t=q:w=1.3:g=-3,"
        "highshelf=f=9000:g=-3,"                          # stop the long-run fatigue
        "lowshelf=f=120:g=2.5,"                           # body under the impacts
        "highpass=f=45[eq];"                              # no inaudible rumble
        f"[eq]asplit=2[dry][pre];"
        f"[pre][1:a]afir=dry=0:wet=1[wetsig];"
        f"[dry][wetsig]amix=inputs=2:weights='{1-wet} {wet}':normalize=0,"
        "volume=2.8dB[o]"                                 # makeup: the dips and
    )                                                     # the wet mix cost that

    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", src, "-i", ir,
         "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), out])


def duck(music: str, vo: str, out: str):
    """Sidechain-compress the music bus, keyed by the voice."""
    fc = (
        "[1:a]aformat=sample_rates=%d:channel_layouts=%s[key];"
        "[0:a][key]sidechaincompress=threshold=0.03:ratio=6:attack=5:"
        "release=300:makeup=1[o]" % (SR, CH)
    )
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", music, "-i", vo,
         "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), out])


def final_master(music, sfx, vo, out, lufs, tp, is_mp3):
    inputs, idx, labels = [], 0, []
    for src in (music, sfx, vo):
        if src:
            inputs += ["-i", src]
            labels.append(f"[{idx}:a]")
            idx += 1
    mixin = "".join(labels)
    # loudnorm's own true-peak limiter is not tight in single-pass mode, and the
    # mp3 encoder adds overshoot after it: a master asked for -1.0 dBTP came out
    # at -0.2 once the SFX were levelled as foreground. An explicit limiter after
    # loudnorm holds the ceiling the cue sheet actually specifies.
    ceiling = 10 ** (tp / 20.0)
    fc = (f"{mixin}amix=inputs={len(labels)}:normalize=0:dropout_transition=0[mx];"
          f"[mx]loudnorm=I={lufs}:TP={tp}:LRA=11,"
          f"alimiter=limit={ceiling:.4f}:attack=5:release=50:level=disabled[o]")
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y", *inputs,
           "-filter_complex", fc, "-map", "[o]"]
    if is_mp3:
        cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
    else:
        cmd += ["-c:a", "pcm_s16le"]
    run(cmd + [out])


def mux(video, audio, out):
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", video, "-i", audio,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-shortest", out])


def parse_time(s: str) -> float:
    """'90', '1:30', '1:02:03.5' -> seconds."""
    parts = str(s).strip().split(":")
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        raise SystemExit(f"[assemble] bad time value: {s!r}")
    sec = 0.0
    for v in vals:
        sec = sec * 60 + v
    return sec


def parse_window(spec: str, total: float) -> tuple[float, float]:
    """'0:30-1:00' -> (30.0, 60.0), clamped to the timeline."""
    if "-" not in spec:
        raise SystemExit("[assemble] --preview needs START-END, e.g. 0:30-1:00")
    a, b = spec.split("-", 1)
    start, end = parse_time(a), parse_time(b)
    start = max(0.0, min(start, total))
    end = max(start + 0.5, min(end, total))
    return start, end


def extract_preview(src: str, dst: str, start: float, end: float, is_video: bool):
    """Cut an excerpt out of the finished master, with short fades so it
    doesn't click. The audio is the real master -- only excerpted."""
    dur = end - start
    fade = min(0.05, dur / 10)
    af = f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={dur - fade:.3f}:d={fade:.3f}"
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y",
           "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src, "-af", af]
    if is_video:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "256k"]
    elif dst.lower().endswith(".mp3"):
        cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
    run(cmd + [dst])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True)
    ap.add_argument("--vo", help="mastered voiceover (sidechain key + anchor)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--assets", help="dir with files named by cue id (m1.mp3, s2.wav)")
    ap.add_argument("--stems", help="dir to also write music/sfx/vo stems")
    ap.add_argument("--mux-into", help="video to remux the final mix into (-> mp4)")
    # -10 dB is measured, not guessed: across two StickTory full mixes the bed
    # floor sits 8.2 and 12.6 dB under programme level. See SKILL.md.
    ap.add_argument("--music-db", type=float, default=0.0,
                    help="extra manual music trim on top of the calibration")
    ap.add_argument("--bed-target-db", type=float, default=-13.0,
                    help="put the bed this many dB under the VO, measured (default -13, "
                         "the level measured on a StickTory mix against its own VO stem). "
                         "Pass 'none' via --no-bed-calibration to disable.")
    ap.add_argument("--no-bed-calibration", action="store_true",
                    help="skip the measured calibration and use --music-db verbatim")
    ap.add_argument("--sfx-db", type=float, default=0.0,
                    help="global sfx trim on top of each cue's own gain (-6..-9)")
    ap.add_argument("--no-sfx-polish", action="store_true",
                    help="skip the SFX bus EQ/room chain (see polish_sfx)")
    ap.add_argument("--no-duck", action="store_true")
    ap.add_argument("--preview", metavar="START-END",
                    help="also write a short excerpt of the finished master, "
                         "e.g. --preview 0:30-1:00 (for fast ear-checking)")
    args = ap.parse_args()
    if args.no_bed_calibration:
        args.bed_target_db = None

    with open(args.cues) as f:
        cue = json.load(f)
    total = cue["duration"]
    lufs = cue.get("loudness_target_lufs", -14.0)
    tp = cue.get("true_peak_ceiling_dbtp", -1.0)

    work = tempfile.mkdtemp(prefix="sd_assemble_")
    music_segs, sfx_segs = [], []
    placed_m = placed_s = missing = 0

    for m in cue.get("music_sections", []):
        asset = resolve_asset(m, args.assets)
        if not asset:
            missing += 1
            print(f"[assemble]   music {m['id']} ({fmt_ts(m['start'])}) — NO ASSET, skipped")
            continue
        skip = m.get("intro_skip")
        if skip is None:
            skip = energy_onset(asset)
        seg = render_music_seg(
            asset, m["start"], m["dur"], m.get("fade_in", 1.0),
            m.get("fade_out", 1.5), m.get("gain_db", 0.0) + args.music_db,
            work, m["id"], skip)
        if skip > 0.4:
            print(f"[assemble]     skipped {skip:.1f}s of soft intro on {m['id']}")
        music_segs.append(seg)
        placed_m += 1
        print(f"[assemble]   music {m['id']} <- {os.path.basename(asset)} "
              f"@ {fmt_ts(m['start'])} for {m['dur']}s")

    for s in cue.get("sfx_cues", []):
        asset = resolve_asset(s, args.assets)
        if not asset:
            missing += 1
            continue
        vary = float(s.get("vary", 0.0))
        seg = render_sfx_short(asset, s.get("gain_db", -8.0) + args.sfx_db,
                               work, s["id"], vary)
        # A palette prepared by palette.py already starts on its attack, so the
        # transient search must NOT run again -- doing both compensates twice
        # and throws slow-blooming files (whooshes especially) hundreds of ms
        # early. Prepared cues instead carry a measured anchor: the file is
        # placed so its *perceived* moment lands on the beat, which for a pop
        # is its first sample and for a whoosh is ~400 ms in.
        if s.get("pre_trimmed"):
            lead = float(s.get("anchor", 0.0))
        else:
            lead = transient_offset(asset)
        at = max(0.0, s["at"] - lead)
        sfx_segs.append((seg, at))
        placed_s += 1
        print(f"[assemble]   sfx {s['id']} <- {os.path.basename(asset)} @ {fmt_ts(s['at'])}")

    # Ambience beds. "Most of the areas has no SFX" is not answered by more
    # hits -- it is answered by the scene having a room. A bed at -28 dB is
    # never consciously heard and its absence is, which is exactly the point.
    bed_segs = []
    for b in cue.get("amb_beds", []):
        asset = resolve_asset(b, args.assets)
        if not asset:
            missing += 1
            continue
        fade = float(b.get("fade", 2.0))
        bed_segs.append(render_music_seg(asset, b["at"], b["dur"], fade, fade,
                                         b.get("gain_db", -28.0), work,
                                         f"amb_{b['id']}"))
    if bed_segs:
        print(f"[assemble] {len(bed_segs)} ambience beds under the sections")

    print(f"[assemble] placed {placed_m} music + {placed_s} sfx · {missing} cues had no asset")

    vo_wav = None
    if args.vo:
        vo_wav = os.path.join(work, "vo.wav")
        to_wav(args.vo, vo_wav)

    if not music_segs and not sfx_segs and not vo_wav:
        raise SystemExit("[assemble] nothing to render: no assets and no VO.")

    music_bus = os.path.join(work, "music_bus.wav")
    sfx_bus = os.path.join(work, "sfx_bus.wav")
    mix_bus(music_segs, music_bus, total)
    build_sfx_bus(sfx_segs, sfx_bus, total, work)

    # Polish the hits, then lay the beds under them. The beds are deliberately
    # NOT convolved -- a room tone already is a room, and running it through the
    # impulse just smears it into mush.
    if sfx_segs and not args.no_sfx_polish:
        pol = os.path.join(work, "sfx_pol.wav")
        polish_sfx(sfx_bus, pol, work)
        sfx_bus = pol
        print("[assemble] polished the SFX bus (speech-band dip, tamed top, room)")
    if bed_segs:
        amb_bus = os.path.join(work, "amb_bus.wav")
        mix_bus(bed_segs, amb_bus, total)
        merged = os.path.join(work, "sfx_amb.wav")
        mix_bus([sfx_bus, amb_bus] if sfx_segs else [amb_bus], merged, total)
        sfx_bus = merged
        sfx_segs = sfx_segs or bed_segs

    ducked = music_bus
    if vo_wav and music_segs and not args.no_duck:
        ducked = os.path.join(work, "ducked.wav")
        duck(music_bus, vo_wav, ducked)
        print("[assemble] sidechain-ducked music under VO")

    # Calibrate AFTER ducking. Calibrating the raw bus is wrong whenever the VO
    # is dense: the compressor then pulls the bed below the level we just set,
    # and with a 93%-voiced VO it never comes back up. Measure what actually
    # reaches the master.
    #
    # Closed loop on the STEMS, not on the finished file. Measuring the master
    # cannot separate the music bed from the effects, so once the effects are
    # levelled as foreground they inflate the reading and the loop pulls the
    # music down to compensate. Iterating here also means the correction is
    # verified before mastering rather than by re-rendering it afterwards.
    if vo_wav and music_segs and args.bed_target_db is not None:
        silence = cue.get("measured", {}).get("silence")
        for attempt in range(2):
            got = bed_ratio(ducked, vo_wav, silence) if silence else None
            if got is None:                      # no VO gaps to measure in
                trim = calibrate_bed(ducked, vo_wav, args.bed_target_db)
                if trim is None or abs(trim) <= 0.2:
                    break
            else:
                trim = args.bed_target_db - got
                print(f"[assemble] measured bed {got:+.1f} dB vs target "
                      f"{args.bed_target_db:+.1f} dB")
                if abs(trim) <= 1.0:
                    break
            cal = os.path.join(work, f"music_cal{attempt}.wav")
            run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", ducked,
                 "-filter:a", f"volume={trim:.2f}dB", "-ac", "2", "-ar", str(SR), cal])
            ducked = cal
            print(f"[assemble] trimmed the bed {trim:+.1f} dB")
            if got is None:
                break

    is_mp3 = args.out.lower().endswith(".mp3")
    audio_out = args.out if not args.mux_into else os.path.join(work, "final.wav")
    final_master(ducked if music_segs else None,
                 sfx_bus if sfx_segs else None,
                 vo_wav, audio_out, lufs, tp, is_mp3 and not args.mux_into)

    if args.stems:
        os.makedirs(args.stems, exist_ok=True)
        for name, src in (("music", ducked if music_segs else None),
                          ("sfx", sfx_bus if sfx_segs else None),
                          ("vo", vo_wav)):
            if src:
                dst = os.path.join(args.stems, f"{name}.wav")
                to_wav(src, dst, total)
                print(f"[assemble] stem -> {dst}")

    if args.mux_into:
        mux(args.mux_into, audio_out, args.out)
        print(f"[assemble] muxed into video -> {args.out}")

    if args.preview:
        start, end = parse_window(args.preview, total)
        stem, ext = os.path.splitext(args.out)
        prev = f"{stem} (preview {fmt_ts(start)}-{fmt_ts(end)}){ext}"
        extract_preview(args.out, prev, start, end, bool(args.mux_into))
        print(f"[assemble] preview -> {prev}")

    # loudness verification
    res = run([FFMPEG, "-hide_banner", "-i", args.out,
               "-filter:a", "ebur128=peak=true", "-f", "null", "-"])
    tail = [l for l in res.stderr.splitlines() if "I:" in l or "Peak" in l or "LRA:" in l]
    print(f"[assemble] wrote {args.out}")
    for l in tail[-6:]:
        print("   " + l.strip())


if __name__ == "__main__":
    # The work dir holds a full-length wav per batch plus one file per cue --
    # 2-4 GB for a 13-minute video. Ten leaked runs filled a 252 GB disk and
    # the next render died mid-mix with "No space left on device", so it is
    # removed even when the render raises.
    try:
        main()
    finally:
        for d in glob.glob(os.path.join(tempfile.gettempdir(), "sd_assemble_*")):
            shutil.rmtree(d, ignore_errors=True)
