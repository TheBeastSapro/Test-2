#!/usr/bin/env python3
"""
Stage 5: the audio mix. Four buses -- voiceover, ambient bed, SFX, master.

Usage:
    python3 tools/mix_audio.py --vo vo.wav --bed bed.wav --duration 62.6 \
        --sfx whoosh.wav@3.2 --sfx boom.wav@11.8:-6 \
        --out projects/<slug>/audio/mix.wav --work projects/<slug>/work

    # optional: mux straight onto the picture, with -t, never -shortest
    ... --mux out/video.mp4 --mux-out out/<slug>.mp4

Direct port of the chain already working in engine/ffmpeg-engine/build.py
(BUILD-PACKET section 7). The rules below are not style preferences; each one
has already cost this channel a rejected cut.

  NO LIMITER ANYWHERE. A cut was failed at LRA 1.9: over-limited to the point
  that the bed never audibly ducked and the SFX could not punch. The chain is
  checked for limiter-class filters before it is handed to ffmpeg, and the tool
  refuses to run if one appears.

  TWO-PASS LINEAR loudnorm. Pass 1 measures with print_format=json and changes
  nothing. Pass 2 applies with linear=true and ALL FIVE measured_* values, which
  is the only way ffmpeg applies a single constant gain to the whole file. One
  constant gain cannot change the loudness range, so the LRA that comes out is
  the LRA that went in. Single-pass loudnorm is a DYNAMIC normaliser: it rides
  the level over time and destroys LRA, which is the number that gets a cut
  rejected. If any of the five measured values is missing or non-finite this
  tool aborts rather than silently falling back to dynamic mode.

  THE DUCK. sidechaincompress compresses its FIRST input and is keyed by its
  SECOND. First = the bed, second = a copy of the VO via asplit. Backwards and
  the bed swamps the voice.

  aresample=48000 AFTER loudnorm. Bare loudnorm silently resamples 48k to 96k.

  apad then atrim at the end of pass 2, so the mix is EXACTLY the composition
  length. That is what stops the -shortest truncation in the mux (a real cut lost
  the last 0.63 s of picture that way and nothing in the render output warned).

  The mux uses -t <exact_duration>. NEVER -shortest.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys

# Targets (BUILD-PACKET 7.2 / style.py)
LUFS_TARGET = -15.0   # middle of the -14..-16 window; the measured result drifts
TRUE_PEAK = -1.5      # QC fails at -1.0, so aim 0.5 dB inside the line
LRA_TARGET = 9.0      # a CEILING HINT, not a target to squash toward. QC fails <3
BED_GAIN_DB = -19.0
SFX_GAIN_DB = -9.0
DUCK_RATIO = 6
DUCK_THRESHOLD = 0.02
DUCK_ATTACK = 20
DUCK_RELEASE = 520
VO_HIGHPASS = 80
VO_COMP = "acompressor=threshold=-12dB:ratio=1.6:attack=15:release=280"
BED_FADE_IN = 1.2
BED_FADE_OUT = 2.0
LRA_FLOOR = 3.0       # QC fail threshold; reported, not enforced by limiting

# Anything in this list in the filtergraph means the master is being squashed.
BANNED_FILTERS = ("alimiter", "limiter", "compand", "asoftclip", "aexciter",
                  "adynamicsmooth", "speechnorm")

FF_QUIET = ["ffmpeg", "-nostdin", "-loglevel", "error"]
# loudnorm and volumedetect print their statistics at info level, so those two
# calls cannot run at -loglevel error. -nostats is what kills the frame=...
# progress flood that the house rule is actually about.
FF_MEASURE = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-loglevel", "info"]


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"ffmpeg failed ({r.returncode}):\n{' '.join(cmd)}\n{r.stderr[-3000:]}")
    return r


def probe_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", path],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(d["format"]["duration"]),
        "sample_rate": int(a["sample_rate"]) if a else 0,
        "channels": int(a["channels"]) if a else 0,
        "codec": a["codec_name"] if a else None,
    }


def loudnorm_measure(path, I=LUFS_TARGET, TP=TRUE_PEAK, LRA=LRA_TARGET):
    """Pass 1: measure and change NOTHING."""
    r = run(FF_MEASURE + ["-i", path, "-af",
                          f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json",
                          "-f", "null", "-"], check=False)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    if not m:
        sys.exit(f"loudnorm pass 1 produced no JSON block for {path}\n{r.stderr[-2000:]}")
    return json.loads(m.group(0))


def measured_ok(m):
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    bad = []
    for k in keys:
        try:
            v = float(m[k])
        except (KeyError, TypeError, ValueError):
            bad.append(k)
            continue
        if not math.isfinite(v):
            bad.append(f"{k}={m[k]}")
    return bad


def check_no_limiter(chain):
    low = chain.lower()
    hits = [f for f in BANNED_FILTERS if re.search(rf"(^|[;,\[\]]|\s){f}\s*=", low)
            or re.search(rf"(^|[;,\[\]]|\s){f}(\s|$|,|;|\[)", low)]
    if hits:
        sys.exit("REFUSING TO BUILD: limiter-class filter(s) in the chain: "
                 + ", ".join(sorted(set(hits)))
                 + "\nNo limiter anywhere. A cut was failed at LRA 1.9 for exactly this.")


def parse_sfx(specs, sheet_path):
    """--sfx path@time[:gain_db], repeatable. Or a JSON sheet with shots/pops."""
    out = []
    for s in specs or []:
        m = re.match(r"^(.*)@([0-9.]+)(?::(-?[0-9.]+))?$", s)
        if not m:
            sys.exit(f"bad --sfx spec {s!r}; want path@seconds[:gain_db]")
        out.append({"file": m.group(1), "t": float(m.group(2)),
                    "gain": float(m.group(3)) if m.group(3) else 0.0})
    if sheet_path:
        with open(sheet_path) as f:
            sd = json.load(f)
        for h in sd.get("sfx", []):
            out.append({"file": h["file"], "t": float(h["t"]),
                        "gain": float(h.get("gain", 0.0))})
    out.sort(key=lambda h: h["t"])
    return out


def build_raw(vo, bed, sfx, dur, vo_offset, work, bed_gain, sfx_gain, duck_ratio):
    """Bus 1 VO, bus 2 bed, bus 3 SFX, summed to the pre-master. No limiter."""
    ms = int(round(vo_offset * 1000))
    ins = ["-i", vo, "-i", bed]
    fc = [
        # VO: delay to its start offset, high-pass out rumble, gentle levelling only
        f"[0:a]adelay={ms}|{ms},aresample=48000,highpass=f={VO_HIGHPASS},"
        f"{VO_COMP},aformat=channel_layouts=stereo[vo]",
        # BED: trimmed and padded to the exact duration, faded, well below the VO
        f"[1:a]aresample=48000,atrim=0:{dur},apad=whole_dur={dur},"
        f"afade=t=in:st=0:d={BED_FADE_IN},"
        f"afade=t=out:st={max(dur - BED_FADE_OUT, 0)}:d={BED_FADE_OUT},"
        f"volume={bed_gain}dB,aformat=channel_layouts=stereo[bed0]",
    ]
    # SFX: one input per hit, each delayed to its cue and gain-staged
    labels = []
    for k, h in enumerate(sfx):
        ins += ["-i", h["file"]]
        fc.append(f"[{k + 2}:a]aresample=48000,volume={h['gain'] + sfx_gain}dB,"
                  f"adelay={int(round(h['t'] * 1000))}|{int(round(h['t'] * 1000))},"
                  f"aformat=channel_layouts=stereo[s{k}]")
        labels.append(f"[s{k}]")

    # THE DUCK: the bed is compressed, the VO is the key.
    fc.append("[vo]asplit=2[vo1][vokey]")
    fc.append(f"[bed0][vokey]sidechaincompress=threshold={DUCK_THRESHOLD}:"
              f"ratio={duck_ratio}:attack={DUCK_ATTACK}:release={DUCK_RELEASE}:"
              f"makeup=1[bed]")

    if labels:
        fc.append("".join(labels) +
                  f"amix=inputs={len(labels)}:normalize=0:duration=longest[sfx]")
        mixin, n = "[vo1][bed][sfx]", 3
    else:
        mixin, n = "[vo1][bed]", 2
    fc.append(f"{mixin}amix=inputs={n}:normalize=0:duration=longest,"
              f"apad=whole_dur={dur},atrim=0:{dur},aresample=48000[out]")

    chain = ";".join(fc)
    check_no_limiter(chain)
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, "mix_raw.wav")
    run(FF_QUIET + ["-y"] + ins + ["-filter_complex", chain,
                                   "-map", "[out]", "-c:a", "pcm_s24le", raw])
    return raw, chain


def crest_headroom(m, I, TP):
    """How much peak headroom a single constant gain would need.

    ffmpeg honours linear=true only if the one constant gain that lands the
    integrated loudness on target does NOT push the true peak past the TP
    target. If it would, loudnorm SILENTLY falls back to dynamic mode -- the
    riding normaliser that flattens LRA. So predict it before spending the pass.
    """
    offset = I - float(m["input_i"])
    predicted_tp = float(m["input_tp"]) + offset
    crest = float(m["input_tp"]) - float(m["input_i"])
    return {"offset": offset, "predicted_tp": predicted_tp, "crest": crest,
            "budget": TP - I, "linear_possible": predicted_tp <= TP + 1e-9}


def master(raw, out, dur, I, TP, LRA):
    """Two-pass LINEAR loudnorm. Pass 1 measures, pass 2 applies one constant gain."""
    m = loudnorm_measure(raw, I, TP, LRA)
    bad = measured_ok(m)
    if bad:
        sys.exit("loudnorm pass 1 returned unusable measurements: " + ", ".join(bad) +
                 "\nlinear=true is only honoured when all five measured_* values are "
                 "supplied and finite. Refusing to fall back to dynamic (single-pass) "
                 "loudnorm, which would destroy LRA.")
    print(f"[audio] pre-master   I={m['input_i']} LUFS  TP={m['input_tp']} dBTP  "
          f"LRA={m['input_lra']} LU  thresh={m['input_thresh']}  "
          f"offset={m['target_offset']}")

    ch = crest_headroom(m, I, TP)
    print(f"[audio] linear check offset {ch['offset']:+.2f} dB -> predicted TP "
          f"{ch['predicted_tp']:+.2f} dBTP (limit {TP})  "
          f"pre-master crest {ch['crest']:.1f} dB, budget {ch['budget']:.1f} dB")
    if not ch["linear_possible"]:
        print("[audio] WARNING: one constant gain to I=%.1f would peak at %+.2f dBTP, "
              "past the %.1f dBTP target. ffmpeg will REFUSE linear mode and fall back "
              "to DYNAMIC normalisation, which rides the level and destroys LRA.\n"
              "        The fix is gain staging in the PRE-MASTER, never a limiter: the "
              "pre-master crest is %.1f dB and the budget at these targets is %.1f dB, "
              "so the VO stem needs its peaks brought under control upstream (stage 4.5 "
              "VO master), or the bed and SFX need to come down."
              % (I, ch["predicted_tp"], TP, ch["crest"], ch["budget"]))

    af = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:linear=true:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:print_format=summary,"
          # aresample AFTER loudnorm: bare loudnorm silently resamples 48k -> 96k
          f"aresample=48000,"
          # apad then atrim: the mix is EXACTLY the composition length
          f"apad=whole_dur={dur},atrim=0:{dur}")
    check_no_limiter(af)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    # pass 2 runs at info level ONLY so print_format=summary can be read back:
    # "Normalization Type: Linear" is ffmpeg telling us to our face whether the
    # constant-gain path was actually taken. -nostats kills the progress flood.
    r = run(FF_MEASURE + ["-y", "-i", raw, "-af", af, "-c:a", "pcm_s16le", out])
    mt = re.search(r"Normalization Type:\s*(\w+)", r.stderr)
    ntype = mt.group(1) if mt else "unknown"
    print(f"[audio] loudnorm reports Normalization Type: {ntype}")
    return m, ntype, ch


def duck_check(vo, bed, sfx, dur, vo_offset, work, bed_gain, sfx_gain, duck_ratio):
    """Measure how far the bed actually ducks under the voice.

    'Over-limited to the point the bed never audibly ducked' was half of the LRA
    1.9 rejection, and a swapped sidechaincompress argument order produces
    exactly that with no error anywhere. So render the post-sidechain bed and the
    VO separately and measure the bed's level when the VO is speaking against its
    level when the VO is quiet. A correctly wired duck is several dB down under
    speech; zero (or negative) means the key and the target are the wrong way
    round."""
    try:
        import numpy as np
    except ImportError:
        return None
    ms = int(round(vo_offset * 1000))
    fc = [
        f"[0:a]adelay={ms}|{ms},aresample=48000,highpass=f={VO_HIGHPASS},"
        f"{VO_COMP},aformat=channel_layouts=stereo[vo]",
        f"[1:a]aresample=48000,atrim=0:{dur},apad=whole_dur={dur},"
        f"afade=t=in:st=0:d={BED_FADE_IN},"
        f"afade=t=out:st={max(dur - BED_FADE_OUT, 0)}:d={BED_FADE_OUT},"
        f"volume={bed_gain}dB,aformat=channel_layouts=stereo[bed0]",
        "[vo]asplit=2[vo1][vokey]",
        f"[bed0][vokey]sidechaincompress=threshold={DUCK_THRESHOLD}:"
        f"ratio={duck_ratio}:attack={DUCK_ATTACK}:release={DUCK_RELEASE}:makeup=1[bed]",
        f"[vo1]apad=whole_dur={dur},atrim=0:{dur}[voo]",
        f"[bed]apad=whole_dur={dur},atrim=0:{dur}[bedo]",
    ]
    chain = ";".join(fc)
    check_no_limiter(chain)
    vop = os.path.join(work, "_duck_vo.raw")
    bep = os.path.join(work, "_duck_bed.raw")
    run(FF_QUIET + ["-y", "-i", vo, "-i", bed, "-filter_complex", chain,
                    "-map", "[voo]", "-ac", "1", "-ar", "48000", "-f", "s16le", vop,
                    "-map", "[bedo]", "-ac", "1", "-ar", "48000", "-f", "s16le", bep])
    v = np.fromfile(vop, np.int16).astype(np.float32) / 32768.0
    b = np.fromfile(bep, np.int16).astype(np.float32) / 32768.0
    n = min(len(v), len(b)) // 4800          # 100 ms frames
    if n < 10:
        return None
    v = np.sqrt(np.maximum((v[:n * 4800].reshape(n, 4800) ** 2).mean(1), 1e-12))
    b = np.sqrt(np.maximum((b[:n * 4800].reshape(n, 4800) ** 2).mean(1), 1e-12))
    vdb, bdb = 20 * np.log10(v), 20 * np.log10(b)
    gate = vdb.max() - 25.0
    speak, quiet = vdb > gate, vdb <= gate
    for p in (vop, bep):
        if os.path.exists(p):
            os.remove(p)
    if speak.sum() < 5 or quiet.sum() < 5:
        return None
    return {"bed_under_vo_db": float(bdb[speak].mean()),
            "bed_in_gaps_db": float(bdb[quiet].mean()),
            "duck_depth_db": float(bdb[quiet].mean() - bdb[speak].mean()),
            "speaking_frames": int(speak.sum()), "quiet_frames": int(quiet.sum())}


def mux(video, mix, out, dur):
    """-t <exact_duration>, NEVER -shortest. -shortest silently threw away the
    last 0.63 s of picture on a real cut and the A/V length check failed with
    nothing in the render output warning about it."""
    run(FF_QUIET + ["-y", "-i", video, "-i", mix, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "320k", "-t", f"{dur}", out])
    return out


def main():
    ap = argparse.ArgumentParser(description="Stage 5 audio mix (4 buses, no limiter)")
    ap.add_argument("--vo", required=True)
    ap.add_argument("--bed", required=True)
    ap.add_argument("--duration", type=float, required=True,
                    help="EXACT composition length in seconds")
    ap.add_argument("--out", required=True, help="mastered mix.wav")
    ap.add_argument("--work", default=None, help="workdir for mix_raw.wav")
    ap.add_argument("--sfx", action="append", default=[],
                    help="path@seconds[:gain_db], repeatable")
    ap.add_argument("--sfx-json", default=None, help='JSON with {"sfx":[{file,t,gain}]}')
    ap.add_argument("--vo-offset", type=float, default=0.0)
    ap.add_argument("--bed-gain", type=float, default=BED_GAIN_DB)
    ap.add_argument("--sfx-gain", type=float, default=SFX_GAIN_DB)
    ap.add_argument("--duck-ratio", type=float, default=DUCK_RATIO)
    ap.add_argument("--lufs", type=float, default=LUFS_TARGET)
    ap.add_argument("--tp", type=float, default=TRUE_PEAK)
    ap.add_argument("--lra", type=float, default=LRA_TARGET)
    ap.add_argument("--no-duck-check", action="store_true",
                    help="skip the measured bed-duck depth diagnostic")
    ap.add_argument("--mux", default=None, help="video to mux the mix onto")
    ap.add_argument("--mux-out", default=None)
    ap.add_argument("--report", default=None, help="write measurements as JSON")
    args = ap.parse_args()

    dur = round(args.duration, 3)
    work = args.work or os.path.join(os.path.dirname(os.path.abspath(args.out)), "work")
    sfx = parse_sfx(args.sfx, args.sfx_json)
    for p in [args.vo, args.bed] + [h["file"] for h in sfx]:
        if not os.path.exists(p):
            sys.exit(f"missing input: {p}")

    print(f"[audio] buses: VO={os.path.basename(args.vo)} "
          f"bed={os.path.basename(args.bed)} sfx={len(sfx)} "
          f"target duration={dur}s")
    raw, chain = build_raw(args.vo, args.bed, sfx, dur, args.vo_offset, work,
                           args.bed_gain, args.sfx_gain, args.duck_ratio)
    rp = probe_audio(raw)
    print(f"[audio] pre-master file {os.path.basename(raw)} "
          f"{rp['duration']:.3f}s {rp['sample_rate']} Hz {rp['channels']}ch")

    duck = None
    if not args.no_duck_check:
        duck = duck_check(args.vo, args.bed, sfx, dur, args.vo_offset, work,
                          args.bed_gain, args.sfx_gain, args.duck_ratio)
        if duck:
            print(f"[audio] duck         bed {duck['bed_under_vo_db']:.1f} dB under "
                  f"speech vs {duck['bed_in_gaps_db']:.1f} dB in gaps  -> "
                  f"{duck['duck_depth_db']:.1f} dB of duck")

    m, ntype, ch = master(raw, args.out, dur, args.lufs, args.tp, args.lra)

    # ---- verification: measure what actually came out -----------------------
    op = probe_audio(args.out)
    post = loudnorm_measure(args.out, args.lufs, args.tp, args.lra)
    I = float(post["input_i"])
    TP = float(post["input_tp"])
    LRA = float(post["input_lra"])
    lra_in = float(m["input_lra"])
    print("\n[audio] MASTER MEASURED")
    print(f"  integrated   {I:>7.2f} LUFS   (target {args.lufs}, QC window -16..-14)")
    print(f"  true peak    {TP:>7.2f} dBTP   (target {args.tp}, QC fails at -1.0)")
    print(f"  LRA          {LRA:>7.2f} LU     (pre-master {lra_in:.2f} LU, "
          f"QC fails at or below {LRA_FLOOR})")
    print(f"  duration     {op['duration']:>7.3f} s      (composition {dur} s)")
    print(f"  sample rate  {op['sample_rate']:>7d} Hz     (48000 required)")
    print(f"  norm type    {ntype:>7s}        (Linear required; Dynamic rides the "
          f"level and flattens LRA)")

    problems = []
    if ntype.lower() != "linear":
        problems.append(
            f"loudnorm ran in {ntype.upper()} mode, not linear. That is the exact "
            "chain that produced the LRA 1.9 rejection: a dynamic normaliser rides "
            "the level over time. Gain-stage the pre-master (see the linear check "
            "above); do not add a limiter.")
    if op["sample_rate"] != 48000:
        problems.append(f"sample rate is {op['sample_rate']}, not 48000 -- the "
                        "aresample=48000 after loudnorm is missing or ineffective")
    if abs(op["duration"] - dur) > 0.01:
        problems.append(f"duration {op['duration']:.3f}s != composition {dur}s -- "
                        "check apad/atrim")
    if not (-16.0 <= I <= -14.0):
        problems.append(f"integrated {I:.2f} LUFS outside the -16..-14 QC window")
    if TP >= -1.0:
        problems.append(f"true peak {TP:.2f} dBTP at or above -1.0 (QC fail)")
    if LRA <= LRA_FLOOR:
        problems.append(f"LRA {LRA:.2f} LU at or below {LRA_FLOOR} -- there is a "
                        "limiter in the chain or linear mode was not honoured")
    if lra_in > 0 and abs(LRA - lra_in) > 1.0:
        problems.append(f"LRA moved {lra_in:.2f} -> {LRA:.2f} LU; a single constant "
                        "gain cannot do that, so linear=true was not applied")
    if duck and duck["duck_depth_db"] < 1.0:
        problems.append(f"the bed ducks only {duck['duck_depth_db']:.1f} dB under the "
                        "voice. Check the sidechaincompress argument order: the FIRST "
                        "input is compressed (the bed), the SECOND is the key (the VO "
                        "via asplit). Backwards and the bed swamps the voice.")

    if args.mux:
        out_mp4 = args.mux_out or os.path.splitext(args.mux)[0] + "_muxed.mp4"
        mux(args.mux, args.out, out_mp4, dur)
        mp = probe_audio(out_mp4)
        print(f"\n[mux] {out_mp4}  {mp['duration']:.3f}s  (-t {dur}, never -shortest)")

    if args.report:
        with open(args.report, "w") as f:
            json.dump({"pre_master": m, "master": post, "specs": op,
                       "normalization_type": ntype, "linear_check": ch,
                       "duck": duck,
                       "chain": chain, "sfx": sfx, "duration": dur,
                       "problems": problems}, f, indent=2)
        print(f"[audio] report -> {args.report}")

    if problems:
        print("\n[audio] PROBLEMS")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print("\n[audio] OK -> " + args.out)


if __name__ == "__main__":
    main()
