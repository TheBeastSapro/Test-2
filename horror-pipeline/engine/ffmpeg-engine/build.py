import json, math, os, subprocess, sys, importlib
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S
from render import Renderer

# Repo-relative, not machine-specific. HP_ROOT overrides if assets live elsewhere.
ROOT = os.environ.get(
    "HP_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
A    = os.environ.get("HP_ASSETS", f"{ROOT}/assets")

def build_sheet(mod):
    sheet = {"title": mod.TITLE, "duration": mod.DURATION,
             "cards": mod.CARDS,
             "shots": [{"t0": a, "t1": b, "desc": c, "kb": k} for a, b, c, k in mod.SHOTS],
             "pops":  [{"text": t, "t0": t0, "t1": t0+d, "where": w, "accent": ac, "size": sz}
                       for t, t0, d, w, ac, sz in mod.POPS],
             "icons": [{"kind": k, "t0": a, "t1": b, "x": x, "y": y, "size": s}
                       for k, a, b, x, y, s in mod.ICONS],
             "shakes":[{"t0": a, "dur": d, "amp": m} for a, d, m in mod.SHAKES],
             "glitches":[{"t0": a, "dur": d, "amp": m} for a, d, m in mod.GLITCHES]}
    return sheet

def validate(sheet):
    """Pacing guardrails from the editing brief, enforced BEFORE a frame is rendered."""
    errs, warns = [], []
    shots = sheet["shots"]
    for i, s in enumerate(shots):
        L = s["t1"]-s["t0"]
        if L > 8.0:  errs.append(f"shot {i+1} is {L:.1f}s (>8s hard limit)")
        elif L > S.MAX_SHOT_LEN: warns.append(f"shot {i+1} is {L:.1f}s (> {S.MAX_SHOT_LEN}s house limit)")
    for i in range(len(shots)-1):
        if abs(shots[i]["t1"]-shots[i+1]["t0"]) > 1e-6: errs.append(f"gap/overlap between shot {i+1} and {i+2}")
    # "something changes every 2-4s" -> merge cuts + pop-ins + icon-ins into one change track
    ch = sorted([s["t0"] for s in shots] + [p["t0"] for p in sheet["pops"]] + [i["t0"] for i in sheet["icons"]])
    gaps = [b-a for a, b in zip(ch, ch[1:])]
    for a, g in zip(ch, gaps):
        if g > 4.5: warns.append(f"{g:.1f}s with no new on-screen event at t={a:.1f}")
    dens = len(sheet["pops"])/(sheet["duration"]/60.0)
    return errs, warns, dens

def render_video(sheet, out):
    r = Renderer(sheet)
    n = int(round(sheet["duration"]*S.FPS))
    p = subprocess.Popen(
        ["ffmpeg","-nostdin","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24",
         "-s",f"{S.W}x{S.H}","-r",str(S.FPS),"-i","-","-an","-c:v","libx264","-preset","medium",
         "-crf","17","-pix_fmt","yuv420p","-x264-params","keyint=60","-movflags","+faststart", out],
        stdin=subprocess.PIPE)
    for i in range(n):
        t = i/S.FPS
        p.stdin.write(r.render(t).convert("RGB").tobytes())
        if i % 150 == 0: print(f"  frame {i}/{n}", flush=True)
    p.stdin.close(); p.wait()
    return out

def build_audio(mod, out):
    """Two-stage: build the raw mix WITHOUT any limiting, measure it, then apply a
    LINEAR loudnorm. Dynamic (single-pass) loudnorm + a pre-limiter is what crushed
    LRA to 1.9 on the editor cut we QC'd; linear mode preserves range."""
    dur = mod.DURATION
    ins  = ["-i", f"{A}/vo/vo_raw.mp3", "-i", f"{A}/music/bed.wav"]
    fc   = [f"[0:a]adelay={int(mod.VO_OFFSET*1000)}|{int(mod.VO_OFFSET*1000)},aresample=48000,"
            f"highpass=f=80,acompressor=threshold=-12dB:ratio=1.6:attack=15:release=280,"
            f"aformat=channel_layouts=stereo[vo]",
            f"[1:a]aresample=48000,atrim=0:{dur},apad=whole_dur={dur},"
            f"afade=t=in:st=0:d=1.2,afade=t=out:st={dur-2.0}:d=2.0,"
            f"volume={S.BED_GAIN_DB}dB,aformat=channel_layouts=stereo[bed0]"]
    auto = [("whoosh", s[0], -15) for s in mod.SHOTS[1:]] + [("whoosh", p[1], -12) for p in mod.POPS]
    allsfx = auto + [(f, t, g) for f, t, g in mod.SFX]
    labels = []
    for k, (name, t, g) in enumerate(allsfx):
        idx = 2+k
        ins += ["-i", f"{A}/sfx/{name}.wav"]
        fc.append(f"[{idx}:a]aresample=48000,volume={g+S.SFX_GAIN_DB}dB,"
                  f"adelay={int(t*1000)}|{int(t*1000)},aformat=channel_layouts=stereo[s{k}]")
        labels.append(f"[s{k}]")
    fc.append("".join(labels)+f"amix=inputs={len(labels)}:normalize=0:duration=longest[sfx]")
    fc.append("[vo]asplit=2[vo1][vokey]")
    fc.append(f"[bed0][vokey]sidechaincompress=threshold=0.02:ratio={S.DUCK_RATIO}:attack=20:release=520:makeup=1[bed]")
    fc.append(f"[vo1][bed][sfx]amix=inputs=3:normalize=0:duration=longest,"
              f"apad=whole_dur={dur},atrim=0:{dur},aresample=48000[out]")
    raw = f"{A}/work/mix_raw.wav"
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y"]+ins+["-filter_complex",";".join(fc),
                    "-map","[out]","-c:a","pcm_s24le", raw], check=True)
    # pass 1 - measure
    r = subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",raw,"-af",
        f"loudnorm=I={S.LUFS_TARGET}:TP={S.TRUE_PEAK}:LRA={S.LRA_TARGET}:print_format=json",
        "-f","null","-"], capture_output=True, text=True)
    blob = r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}")+1]
    m = json.loads(blob)
    print(f"[audio] pre-master  I={m['input_i']}  TP={m['input_tp']}  LRA={m['input_lra']}")
    # pass 2 - LINEAR normalisation, no limiter in the chain
    af = (f"loudnorm=I={S.LUFS_TARGET}:TP={S.TRUE_PEAK}:LRA={S.LRA_TARGET}:linear=true:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:print_format=summary,"
          f"aresample=48000,apad=whole_dur={dur},atrim=0:{dur}")
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",raw,"-af",af,
                    "-c:a","pcm_s16le", out], check=True)
    return out

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "sewer_spider"
    mod = importlib.import_module(f"sheets.{name}")
    sheet = build_sheet(mod)
    errs, warns, dens = validate(sheet)
    print(f"[validate] shots={len(sheet['shots'])} pops={len(sheet['pops'])} "
          f"pop density={dens:.1f}/min")
    for e in errs:  print("  ERROR:", e)
    for w in warns: print("  warn :", w)
    if errs: sys.exit(1)
    os.makedirs(f"{A}/out", exist_ok=True)
    build_audio(mod, f"{A}/work/mix.wav"); print("[audio] ok")
    render_video(sheet, f"{A}/work/video.mp4"); print("[video] ok")
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",f"{A}/work/video.mp4",
                    "-i",f"{A}/work/mix.wav","-c:v","copy","-c:a","aac","-b:a","320k",
                    f"-t",str(sheet["duration"]),f"{A}/out/{name}.mp4"], check=True)
    print("[mux] ->", f"{A}/out/{name}.mp4")
