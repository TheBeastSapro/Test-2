#!/usr/bin/env python3
"""rebuild_palette.py — rebuild the sword video's SFX palette exactly.

The prepared palette is 243 MB of wav, too big to carry around, but every byte
of it is derived from a 3.7 KB list of Epidemic ULIDs plus four deterministic
steps. This script is those steps, so a fresh session reproduces the identical
palette (and the identical palette_manifest.json) in a couple of minutes instead
of re-choosing 104 sounds and re-deriving the levels.

Run it from the directory holding ulids.txt:

  rebuild_palette.py --scripts /path/to/skills/sound-designer/scripts

Steps, in order, and why each exists:
  1. Download each ULID from the CDN as lqmp3.
  2. palette.py -- peak-normalise the hits, trim their leading silence, measure
     each file's anchor and front-load ratio. amb and march are beds: left
     un-normalised and un-trimmed, but their rms is measured so beds can be
     levelled to a target instead of trimmed by a constant.
  3. impact_13..16 are punch/kick/flesh recordings, not metal. They move to
     body_01..04 so they can serve as the weight layer under a strike.
  4. impact_11 is "Weapons, Armor, Medieval Shield, Impact, Hit, Block, Sword
     Attack" -- a 3.23 s take holding several blows. oneshot.py splits it into
     single sword-on-shield clashes (shield_01..03); dropped whole it reads as a
     slam, and its energy accumulates across all the blows so its anchor lands
     695 ms in and the cluster is placed early.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

CDN = "https://audiocdn.epidemicsound.com/lqmp3/{}.mp3"
# vox_yell is a crowd held under a shot, not a hit: it is levelled from
# measured rms like the other beds, never peak-normalised.
BEDS = ("amb", "march", "vox_yell", "crowd")


def sh(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scripts", required=True,
                    help="the skill's scripts/ dir (palette.py, oneshot.py)")
    ap.add_argument("--ulids", default="ulids.txt")
    ap.add_argument("--raw", default="pal_raw")
    ap.add_argument("--out", default="pal")
    ap.add_argument("--skip-download", action="store_true",
                    help="reuse an existing --raw dir")
    args = ap.parse_args()
    sys.path.insert(0, os.path.abspath(args.scripts))

    entries = [ln.split() for ln in open(args.ulids) if ln.strip()]
    os.makedirs(args.raw, exist_ok=True)

    if not args.skip_download:
        # The CDN resets a connection every so often across a hundred fetches,
        # and one reset used to abort the whole rebuild at file 27. Retry, and
        # skip anything already on disk so a resumed run costs nothing.
        got = 0
        for name, ulid in entries:
            dst = os.path.join(args.raw, f"{name}.mp3")
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                continue
            for attempt in range(4):
                try:
                    sh(["curl", "-sS", "-f", "--retry", "3", "--retry-all-errors",
                        "-o", dst, CDN.format(ulid)])
                    got += 1
                    break
                except subprocess.CalledProcessError:
                    if attempt == 3:
                        raise SystemExit(f"[rebuild] {name} ({ulid}) failed after "
                                         f"4 attempts — CDN or key problem")
                    time.sleep(2 ** attempt)
        print(f"[rebuild] downloaded {got} files ({len(entries) - got} already present)")

    sh([sys.executable, os.path.join(args.scripts, "palette.py"),
        "--raw", args.raw, "--out", args.out,
        "--bed-prefix", ",".join(BEDS)], stdout=subprocess.DEVNULL)
    print(f"[rebuild] prepared {args.out}/")

    man = os.path.join(args.out, "palette_manifest.json")
    m = json.load(open(man))

    # 3. the flesh recordings become their own layer
    moved = []
    for i, src in enumerate([f"impact_{n}" for n in ("13", "14", "15", "16")], 1):
        s = os.path.join(args.out, f"{src}.wav")
        if not os.path.exists(s):
            continue
        d = f"body_{i:02d}"
        shutil.move(s, os.path.join(args.out, f"{d}.wav"))
        for key in ("_anchors", "_frontload"):
            if src in m.get(key, {}):
                m[key][d] = m[key].pop(src)
        moved.append((src, d))
    if moved:
        m["impact"] = [x for x in m["impact"] if x not in dict(moved)]
        m["body"] = [d for _, d in moved]
        print(f"[rebuild] {len(moved)} flesh recordings -> body_*")

    # 4. split the multi-hit takes into single hits. Both of these are takes
    # rather than samples, and dropped whole each reads as a cluster:
    #   impact_11  sword-on-shield, several blows in 3.23 s
    #   voxsrc_01  "Voices, Efforts, Male, Attack, Grunt, Breath, Short,
    #              Multiple 02" -- three grunts in 3.56 s, so one swing would
    #              have played all three.
    import palette
    for src, name in (("impact_11", "shield"), ("voxsrc_01", "vox_effort"),
                      # "Wood, Break, Wood Chop, Split, Barn 04" is 3 splits in
                      # 2.97 s; "Sword, Axe, Heavy, Whoosh, Blade Impact 06" is a
                      # whoosh into an impact, and its energy anchor straddles
                      # both at 190 ms. Split so the impact lands on the frame and
                      # place.py supplies its own anticipation.
                      ("woodsrc_01", "cut"), ("chopsrc_01", "chop"),
                      ("slashsrc_01", "slash"), ("gunsrc_01", "gun")):
        srcp = os.path.join(args.out, f"{src}.wav")
        if not os.path.exists(srcp):
            continue
        sh([sys.executable, os.path.join(args.scripts, "oneshot.py"), srcp,
            "--out", args.out, "--name", name], stdout=subprocess.DEVNULL)
        hits = sorted(os.path.basename(f)[:-4]
                      for f in glob.glob(os.path.join(args.out, f"{name}_*.wav")))
        m[name] = hits
        for n in hits:
            p = os.path.join(args.out, f"{n}.wav")
            m.setdefault("_anchors", {})[n] = round(palette.anchor_offset(p), 4)
            m.setdefault("_frontload", {})[n] = round(palette.front_loaded(p), 3)
        print(f"[rebuild] {len(hits)} single hits from {src} -> {name}_*")
        # the source take itself is not a usable cue
        m[src.rsplit("_", 1)[0]] = [x for x in m.get(src.rsplit("_", 1)[0], [])
                                    if x != src]
        os.remove(srcp)

    # 5. crowd recordings leave the auto-assigned ambience pool.
    #
    # place.py lays one `amb` bed under every music section by rotation, and two
    # of these recordings are crowds with human voices in them:
    #   amb_06  Crowds, Battle, Medieval, Savages Battle Ambience, Voices, Yells
    #   amb_07  Crowds, Battle, Medieval, Village Battle Ambience, Voices, Yells
    # amb_07 drew the Renaissance section and yelled under the narration for its
    # whole 44.8 s -- reported as "unnecessary vocals in the background", and it
    # was never the music track, which is tagged no-vocals.
    #
    # Room tone under a voice must not contain a second voice. These stay in the
    # palette as `crowd`, which nothing auto-assigns, so a hand-written bed can
    # still call one where a crowd is actually on screen.
    crowds = []
    for i, src in enumerate(("amb_06", "amb_07"), 1):
        sp = os.path.join(args.out, f"{src}.wav")
        if not os.path.exists(sp):
            continue
        d = f"crowd_{i:02d}"
        shutil.move(sp, os.path.join(args.out, f"{d}.wav"))
        for key in ("_anchors", "_frontload", "_rms"):
            if src in m.get(key, {}):
                m[key][d] = m[key].pop(src)
        crowds.append((src, d))
    if crowds:
        m["amb"] = [x for x in m["amb"] if x not in dict(crowds)]
        m["crowd"] = [d for _, d in crowds]
        print(f"[rebuild] {len(crowds)} crowd recordings -> crowd_* "
              f"(out of the auto-assigned ambience pool)")

    # beds are levelled from measurement, so their rms must be present
    lv = m.setdefault("_rms", {})
    for cat in BEDS:
        for n in m.get(cat, []):
            lv[n] = round(palette.rms_db(os.path.join(args.out, f"{n}.wav")), 2)

    json.dump(m, open(man, "w"), indent=1)
    cats = {k: len(v) for k, v in m.items() if not k.startswith("_")}
    print(f"[rebuild] {sum(cats.values())} files across {len(cats)} categories")
    for k in sorted(cats):
        print(f"  {k:<9}{cats[k]:>4}")


if __name__ == "__main__":
    main()
