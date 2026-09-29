#!/usr/bin/env python3
"""make_fixture.py — build a tiny synthetic job so RUN.md's test needs no assets.

The noise sources are SEEDED. Without a seed the fixture renders slightly
differently every run (true peak moved 0.2 dB between two runs), which makes
the documented expected output useless as a reference.

Produces, in the directory given as the first argument (default ./fixture):

  video.mp4    20 s, 24 fps, 320x180, with hard cuts at 4/8/12/16 s so
               visual_redraw.py has real events to find
  vo.wav       20 s of amplitude-modulated noise standing in for narration,
               mastered to -14.5 LUFS to match a real ExplainTory VO stem
  assets/m1.wav, m2.wav    two 12 s "music" beds (different pitches)
  pal/*.wav + pal/palette_manifest.json   six one-shot "SFX"
  cues.json    a hand-written sheet: 2 music sections, 6 SFX cues, 1 bed

Nothing here is real audio content -- it is shaped so every stage of the
pipeline has something valid to chew on and the output is deterministic.
"""
import json, os, subprocess, sys

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "fixture")
FF = "ffmpeg"


def run(cmd):
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    os.makedirs(f"{OUT}/assets", exist_ok=True)
    os.makedirs(f"{OUT}/pal", exist_ok=True)

    # --- picture: five 4 s blocks of different colours = four hard cuts -----
    parts = []
    for i, col in enumerate(("black", "white", "gray", "white", "black")):
        p = f"{OUT}/_v{i}.mp4"
        run([FF, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"color=c={col}:s=320x180:r=24:d=4",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", p])
        parts.append(p)
    with open(f"{OUT}/_parts.txt", "w") as fh:
        for p in parts:
            fh.write(f"file '{p}'\n")
    run([FF, "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", f"{OUT}/_parts.txt", "-c", "copy", f"{OUT}/video.mp4"])
    for p in parts + [f"{OUT}/_parts.txt"]:
        os.remove(p)

    # --- voice: modulated noise, mastered to -14.5 LUFS --------------------
    # Two passes would be more exact; one pass is within ~0.1 LUFS and keeps
    # the fixture fast. The test asserts a range, not an exact figure.
    run([FF, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
         "-i", "anoisesrc=d=20:c=pink:r=48000:a=0.5:seed=1",
         "-af", "tremolo=f=3:d=0.85,loudnorm=I=-14.5:TP=-1.5:LRA=11,"
                "aformat=sample_rates=48000:channel_layouts=stereo",
         "-c:a", "pcm_s16le", f"{OUT}/vo.wav"])

    # --- music: two 12 s tones with a slow swell, so energy_onset has work --
    for i, hz in enumerate((110, 165), start=1):
        run([FF, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"sine=frequency={hz}:duration=12:sample_rate=48000",
             "-af", "afade=t=in:st=0:d=3,volume=-6dB,"
                    "aformat=sample_rates=48000:channel_layouts=stereo",
             "-c:a", "pcm_s16le", f"{OUT}/assets/m{i}.wav"])

    # --- sfx: six short front-loaded clicks + one 6 s bed ------------------
    pal, anchors, fronts, rms = {"hit": [], "amb": []}, {}, {}, {}
    for i in range(1, 7):
        n = f"hit_{i:02d}"
        run([FF, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"sine=frequency={400 + i * 130}:duration=0.25:sample_rate=48000",
             "-af", "afade=t=out:st=0.02:d=0.23,volume=-3dB,"
                    "aformat=sample_rates=48000:channel_layouts=stereo",
             "-c:a", "pcm_s16le", f"{OUT}/pal/{n}.wav"])
        pal["hit"].append(n)
        anchors[n], fronts[n], rms[n] = 0.0, 1.0, -12.0
    run([FF, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
         "-i", "anoisesrc=d=6:c=brown:r=48000:a=0.3:seed=2",
         "-af", "volume=-20dB,aformat=sample_rates=48000:channel_layouts=stereo",
         "-c:a", "pcm_s16le", f"{OUT}/pal/amb_01.wav"])
    pal["amb"].append("amb_01")
    anchors["amb_01"], fronts["amb_01"], rms["amb_01"] = 0.0, 0.0, -26.0
    pal.update({"_anchors": anchors, "_frontload": fronts, "_rms": rms})
    json.dump(pal, open(f"{OUT}/pal/palette_manifest.json", "w"), indent=1)

    # --- the cue sheet -----------------------------------------------------
    sfx = []
    for j, t in enumerate((4.0, 6.5, 8.0, 11.0, 12.0, 16.0), start=1):
        tier = "hero_boom" if t in (4.0, 12.0) else "impact"
        sfx.append({"id": f"s{j}", "at": t, "kind": f"test beat {j}",
                    "tier": tier, "cat": "hit",
                    "gain_db": -5.0 if tier == "hero_boom" else -8.0,
                    "pre_trimmed": True, "anchor": 0.0,
                    "asset": f"{OUT}/pal/hit_{j:02d}.wav"})
    cues = {
        "schema": "sound-designer/cue-sheet@1",
        "video": f"{OUT}/video.mp4", "vo": f"{OUT}/vo.wav", "duration": 20.0,
        # anchor the master to the voice: sum at unity, limit, ship
        "loudness_target_lufs": None, "true_peak_ceiling_dbtp": -1.0,
        "measured": {},
        "music_sections": [
            {"id": "m1", "role": "intro", "start": 0.0, "end": 10.0, "dur": 10.0,
             "energy": 0.5, "energy_label": "first half", "track": "fixture tone A",
             "under_voiceover": True, "duck_db": -9,
             "fade_in": 0.4, "fade_out": 1.2,
             "asset": f"{OUT}/assets/m1.wav", "gain_db": 0.0},
            {"id": "m2", "role": "outro", "start": 10.0, "end": 20.0, "dur": 10.0,
             "energy": 0.6, "energy_label": "second half", "track": "fixture tone B",
             "under_voiceover": True, "duck_db": -9,
             "fade_in": 1.2, "fade_out": 1.2,
             "asset": f"{OUT}/assets/m2.wav", "gain_db": 0.0},
        ],
        "sfx_cues": sfx,
        "amb_beds": [{"id": "b1", "hand": True, "at": 2.0, "dur": 6.0,
                      "gain_db": -16.0, "fade": 1.0, "rms_target_dbfs": -42,
                      "why": "fixture room tone",
                      "asset": f"{OUT}/pal/amb_01.wav"}],
        "mute_windows": [],
    }
    json.dump(cues, open(f"{OUT}/cues.json", "w"), indent=1)
    print(f"fixture ready in {OUT}")
    print("  video.mp4  20 s, 24 fps, cuts at 4/8/12/16 s")
    print("  vo.wav     20 s, mastered to ~-14.5 LUFS")
    print("  cues.json  2 music sections, 6 sfx cues, 1 bed")


if __name__ == "__main__":
    main()
