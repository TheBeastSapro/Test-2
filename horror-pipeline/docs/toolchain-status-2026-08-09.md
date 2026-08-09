# Toolchain status — 2026-08-09

Setup and verification of the editing toolchain in this container. Every claim
below was produced by running the command shown and reading its output. Where
something failed, the failure is recorded rather than worked around silently.

**Environment:** Linux 6.18.5, Node v22.22.2, npm 10.9.7, Python 3.11.15,
ffmpeg 6.1.1-3ubuntu5, 4 cores / 15.7 GB RAM / 24.5 GB free disk.
All outbound HTTPS goes through the agent proxy at `http://127.0.0.1:37685`.
No TLS verification was disabled and no proxy setting was changed at any point.

**Status summary**

| # | Item | Status |
|---|------|--------|
| 1 | Pillow + imagehash | VERIFIED |
| 2 | Cutout extraction (HyperFrames vs rembg) | PARTIAL |
| 3 | Remotion install + still render | VERIFIED |
| 4 | Remotion Studio | VERIFIED |
| 5 | ffmpeg capabilities | VERIFIED |
| 6 | HyperFrames `doctor` | VERIFIED |

---

## 1. Python imaging deps — VERIFIED

Installed `Pillow 12.3.0` and `imagehash 4.3.2` (which pulled `PyWavelets 1.9.0`;
`numpy 2.4.6` and `scipy 1.17.1` were already present).

```bash
pip3 install pillow imagehash
```

Verified by import:

```
Pillow 12.3.0
imagehash 4.3.2
numpy 2.4.6
cv2 5.0.0
```

Both import cleanly. The perceptual-dedupe path the asset crawler needs
(`imagehash` over `PIL.Image`) has its dependencies satisfied.

*Note:* pip runs as root and emits a "use a virtual environment" warning on every
install. Harmless here (ephemeral container), but worth knowing it is not an error.

---

## 2. Cutout extraction — PARTIAL

Two background removers were installed and run on the **same** real source image,
and the results differ in an important way. Neither is unconditionally good on
this material.

### Test source

```bash
curl -sSL --fail -o /tmp/heiscoming.jpg \
  "https://static.wikia.nocookie.net/trevor-henderson-inspiration/images/9/96/Heiscoming.jpg/revision/latest?cb=20200806142613&format=original"
```

`HTTP 200`, 888,674 bytes, JPEG 1536x2048 RGB. The `&format=original` suffix is
required — without it the CDN returns WebP. The download went through the proxy
with no TLS problems.

This is a hard case on purpose: a very dark, motion-blurred night photograph of a
tall black humanoid creature (Cartoon Cat) standing on an unlit road, with lit
buildings and streetlights behind it. The creature has **two thin outstretched
arms** — these are the detail that separates a usable cutout from a bad one.

### Option A — HyperFrames `remove-background` (recommended, with a caveat)

```bash
npx --yes hyperframes@latest remove-background /tmp/heiscoming.jpg \
  -o /home/user/Test-2/horror-pipeline/assets-example/cutout-hyperframes.png
```

Ran in **11.1 s wall total** (2.4 s of actual inference on CPU) including a
one-time **~168 MB** download of `u2net_human_seg` weights, which succeeded
through the proxy and is cached at
`/root/.cache/hyperframes/background-removal/models/u2net_human_seg.onnx`.

**Output:** `cutout-hyperframes.png`, 7,916,168 bytes, **RGBA 1536x2048**.

| alpha | pixels | share |
|-------|--------|-------|
| `a == 0` (fully transparent) | 3,077,729 | 97.84% |
| `a == 255` (fully opaque) | 13,037 | 0.41% |
| `0 < a < 255` (soft edge) | 54,962 | 1.75% |

Alpha bounding box `(625, 487) → (965, 1102)`, i.e. 340 x 615.

**Honest quality assessment.** The matte is *clean* — visibly the best of the
four runs. It isolates the head (both ears resolved), the torso and both long
legs with a plausible soft edge, and it drops essentially all of the lit
background that defeated rembg. Composited over magenta it reads as a usable
cutout.

**But it amputates both arms.** The model is `u2net_human_seg` — a *human*
segmentation model, and the CLI exposes no way to choose a different one
(`--help` offers only `--device`, `--quality`, `--info`, `--json`). Measuring
alpha inside the horizontal band that contains the arms (`y` 620–860):

```
left of x=625  :     0 px
x 625–965      : 27,882 px
right of x=965 :     0 px
```

Zero. Both outstretched limbs are gone, and a side-by-side crop of the
gamma-brightened source against the cutout confirms it visually — the source
clearly shows both arms, the cutout shows a bare torso. The tight bounding box
that initially reads as a *quality* signal is in fact the symptom.

This matters for the channel's craft: creature cutouts are frequently defined by
thin limbs (spider legs, elongated arms). Expect this failure class and check for
it per asset.

### Option B — rembg (installed, kept for comparison)

```bash
pip3 install "rembg[cpu]"     # installs rembg 2.0.78 + onnxruntime 1.28.0
```

First run downloaded `u2net.onnx` (**176 MB**) from GitHub releases to
`/root/.u2net/` — **the download succeeded through the proxy**, no TLS or
403/405/407 issues. `onnxruntime 1.28.0`, providers
`['AzureExecutionProvider', 'CPUExecutionProvider']`.

One real cost worth recording: **`import rembg` took 79.8 s** on the first import
in this container (cold module graph — scikit-image, scipy, onnxruntime). Session
build was 5.0 s, inference 16.4 s with alpha matting / 1.0 s without.

Three configurations were run on the same image:

| Run | `a==0` | `a==255` | partial | alpha bbox | verdict |
|-----|--------|----------|---------|-----------|---------|
| `u2net` + alpha matting (240/20/erode 8) | 94.97% | 1.88% | 3.15% | 589 x 607 | keeps one arm, but drags a large slab of lit background |
| `u2net` plain | 93.73% | 0.03% | 6.24% | 700 x 633 | keeps arms, drags **more** background; almost no fully-opaque pixels |
| `isnet-general-use` plain | 92.08% | 0.00% | 7.92% | full frame | **failed** — output is a faint ghost, zero fully-opaque pixels, stray alpha across the whole frame |

**Honest quality assessment.** rembg retains the arms — the thing HyperFrames
loses — but on this dark, low-contrast source every rembg configuration also
retains a large, clearly visible region of the lit background (buildings,
streetlights, roadway) fused to the subject. That is not a soft-edge artifact you
can feather away; it is a segmentation error. `isnet-general-use` is worse still:
it produced a translucent ghost with **no fully opaque pixels at all**, which is
unusable.

### Comparison verdict

| | HyperFrames (`u2net_human_seg`) | rembg (`u2net`) |
|---|---|---|
| Background rejection | **Clean** | Poor — large lit region retained |
| Thin limbs | **Lost entirely** | Retained |
| Soft edge | Plausible | Plausible but noisy |
| Speed (warm) | 2.4 s inference | 1.0 s (plain) / 16.4 s (alpha matting) |
| Cold start | ~11 s incl. 168 MB model | 79.8 s import + 176 MB model |
| Model choice | **Locked** to human seg | Selectable |
| Disk | 168 MB | 176 MB + ~1 GB of deps |

**Recommendation:** use **HyperFrames `remove-background`** as the default — it is
faster to cold-start, far cleaner, and one command. Keep rembg installed as the
escape hatch for subjects where limb geometry matters more than background
cleanliness, and because it lets you swap models.

**This is marked PARTIAL, not VERIFIED**, because the requirement was "cut a
creature out as a transparent PNG" and the best available tool measurably drops
part of the creature. Neither tool is safe to run unattended on creature art; the
matte needs a per-asset check (see below).

### Suggested acceptance check for the crawler

Global transparent/opaque counts are **not** sufficient — amputation and
background bleed move those numbers in the same direction. Check the regions the
cutout exists to preserve:

```python
from PIL import Image; import numpy as np
a = np.array(Image.open(p))[:, :, 3]
assert (a > 0).any() and (a == 0).mean() > 0.5        # tier 1: alpha is real
band = a[y0:y1, :]                                     # tier 2: limb band
assert (band[:, :x_torso_left] > 10).sum() > 0         # left limb survived
assert (band[:, x_torso_right:] > 10).sum() > 0        # right limb survived
```

### Output files

| File | Source |
|------|--------|
| `assets-example/cutout-hyperframes.png` | HyperFrames `remove-background` |
| `assets-example/cutout-rembg.png` | rembg `u2net` + alpha matting |
| `assets-example/cutout-test.png` | identical to `cutout-rembg.png` (the originally-requested filename, kept) |

---

## 3. Remotion — VERIFIED

### Install

```bash
cd /home/user/Test-2/horror-pipeline/engine/remotion-engine
npm install --no-audit --no-fund
```

**Completed, exit 0, in 15 s** — far faster than the "several minutes" expected.
255 packages, `node_modules` is 418 MB. No errors, no peer-dependency warnings.
`npx remotion versions` reports every `remotion` / `@remotion/*` package on
**4.0.507** with "All packages have the correct version".

### Browser — Remotion downloads its own; the pre-installed Chromium does *not* work

This needs stating precisely, because the intuitive answer is wrong.

`npx remotion browser ensure` reports:

```
Has browser at /home/user/Test-2/horror-pipeline/engine/remotion-engine/node_modules/.remotion/chrome-headless-shell/linux64/chrome-headless-shell-linux64/chrome-headless-shell
```

Remotion **silently downloaded its own `chrome-headless-shell` into
`node_modules/.remotion/`** on the first render. It did *not* pick up
`/opt/pw-browsers`. (A first search missed this because the path is deeper than
`find -maxdepth 8`.)

Pointing Remotion at the pre-installed **full Chromium** fails outright:

```bash
npx remotion still SewerSpider out/x.png \
  --browser-executable=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
```
```
Error: Failed to launch the browser process!
Old Headless mode has been removed from the Chrome binary. Please use the new
Headless mode or the chrome-headless-shell ...
```

Pointing it at the pre-installed **headless shell** in the same tree **works**:

```bash
npx remotion still SewerSpider out/still-pwshell.png --frame=200 \
  --props='{"withAudio":false}' \
  --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```
Exit 0 → `out/still-pwshell.png`, 2,312,614 bytes.

**Bottom line:** `npx remotion browser ensure` is not *required* — the pre-installed
`chromium_headless_shell-1194/chrome-linux/headless_shell` can be used via
`--browser-executable` and avoids a redundant download. But Remotion will fetch
its own copy on first use unless you pass that flag every time, and the *full*
Chromium binary is unusable with Remotion 4.0.507. Both Chromium builds report
version `141.0.7390.37`.

### Composition

`remotion.config.ts` sets: PNG image format, h264, **14 Mbps ABR** (explicitly not
CRF), `yuv420p`, x264 preset `slow`, overwrite on, concurrency 2, OpenGL renderer
`swangle`, web security disabled.

`src/Root.tsx` registers exactly **one** composition, id **`SewerSpider`**
(1920x1080, `defaultProps: {withAudio: true}`). It calls `assertSheet()` at module
scope as a hard build-time gate — that gate **passed**, so the sheet is valid.

### Still render — VERIFIED

Rendered three stills. The clean one:

```bash
cd /home/user/Test-2/horror-pipeline/engine/remotion-engine
npx remotion still SewerSpider out/verify-frame300.png --frame=300 --props='{"withAudio":false}'
```

**Exit 0 in 7.3 s** → `out/verify-frame300.png`, **2,973,648 bytes, PNG RGB
1920x1080**, mean RGB `[56.2 58.3 64.6]`, std 62.7 (i.e. real image content, not a
blank frame). Visual check confirms a fully composited frame: title bar "THE SEWER
SPIDER" with the red accent rule, the grainy background plate, two stick-figure
cutouts, and the slot tag `PLATE 03 · CUT 03/06 · CLOSE · PLACEHOLDER · TUNNEL
MOUTH AT STREET LEVEL, TWO WORKERS IN HI-VIS`.

Two things are needed to get a *clean* still and both are non-obvious:

1. **`--props='{"withAudio":false}'`.** `public/audio/mix.wav` does not exist (only
   a README placeholder), and the composition's default is `withAudio: true`.
2. **The plate assets must be generated first** — see the defect below. Without
   them the render still succeeds but logs eight 404s for
   `public/plates/slot*.png` and `public/plates/card.png`, and those regions come
   out empty.

### DEFECT FOUND — `npm run plates` is broken (hardcoded paths)

```bash
npm run plates
# ModuleNotFoundError: No module named 'plates'
```

`scripts/export_plates.py` hardcodes two paths from a different machine:

- `sys.path.insert(0, "/home/claude/hp/engine")` — should be
  `/home/user/Test-2/horror-pipeline/engine/ffmpeg-engine`
- `ROOT = "/home/claude/hp/remotion/public"` — should be
  `<repo>/horror-pipeline/engine/remotion-engine/public`

The same class of hardcoded path appears in `package.json` (`mux` writes to
`/home/claude/hp/assets/out/...`), in `scripts/stills.mjs` (default outDir
`/home/claude/hp/remotion/out/stills`), and in `ffmpeg-engine/cutouts.py`'s
`__main__` default. **These are not fixed** — flagging rather than editing, since
the brief was to verify the toolchain, not refactor it.

The script logic itself is fine: running an equivalent with corrected paths
generated all 17 plates + `card.png`, 6 cutouts and `tex/grain.png` successfully,
which is what made the clean still above possible. Those generated assets are now
present in `public/`.

---

## 4. Remotion Studio — VERIFIED

```bash
cd /home/user/Test-2/horror-pipeline/engine/remotion-engine
npx remotion studio --no-open           # default port 3000
npx remotion studio --port 3010 --no-open   # custom port also verified
```

Both were started, probed and stopped.

- **Default port is 3000.** Log: `Server ready - Local: http://localhost:3000,
  Network: http://192.0.2.2:3000`, then `Built in 4041ms`.
- `curl http://localhost:3000/` → **HTTP 200**, `content-type: text/html`,
  `Content-Length: 7327`, body contains `<title>Remotion Studio</title>`.
  Reachable **4 s** after launch.
- `--port 3010` also verified: HTTP 200, same title, reachable in 1 s, built in
  6780 ms.
- Stopped cleanly; after the stop `curl` returns exit 7 (connection refused) and
  no `remotion studio` process remains.

Use `--no-open` — there is no browser to open in this container, and without it
the CLI will try.

**Operational warning (cost me a shell).** Do **not** stop it with
`pkill -f "remotion studio"`. `pkill -f` matches full command lines, and the
agent's own shell command line contains that string, so it kills the calling
shell (exit 144) and silently drops the rest of the command. Capture the PID at
launch and kill by PID, or put the pattern-kill in a separate script file.
A working stop helper is included in the known-good commands below.

---

## 5. ffmpeg capabilities — VERIFIED

`ffmpeg version 6.1.1-3ubuntu5`, built with gcc 13, `--enable-gpl
--enable-libx264 --enable-libvpx --enable-libopus` (also x265, aom, svtav1, vorbis,
mp3lame, webp, zimg, librsvg).

**Encoders — all required present:**

| Required | Present | Line |
|---|---|---|
| libx264 | yes | `V....D libx264  libx264 H.264 / AVC / MPEG-4 AVC (codec h264)` |
| aac | yes | `A....D aac      AAC (Advanced Audio Coding)` (native encoder) |

`libx264rgb` is also available. `libfdk_aac` is **not** present — the native `aac`
encoder is the only AAC path. Muxers `mp4`, `ipod`, `matroska`, `wav` all present.

**Filters — all four required present**, plus the rest of the audio chain the
pipeline uses:

```
PRESENT  sidechaincompress   PRESENT  loudnorm    PRESENT  apad      PRESENT  atrim
PRESENT  asetpts   PRESENT  adelay   PRESENT  amix   PRESENT  volume
PRESENT  aformat   PRESENT  highpass PRESENT  lowpass PRESENT  acompressor
PRESENT  aresample
```

Presence in `-filters` was not treated as proof. The four required filters were
executed together in one real graph:

```bash
ffmpeg -y -f lavfi -i "sine=f=220:d=6:r=48000" \
       -f lavfi -i "anoisesrc=d=6:c=pink:r=48000:a=0.3" \
  -filter_complex "[0:a]atrim=start=0.5:end=4.5,asetpts=PTS-STARTPTS[vo];\
[1:a]apad=pad_dur=2[bed];\
[bed][vo]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=250[duck];\
[duck]loudnorm=I=-14:TP=-1.0:LRA=11[out]" \
  -map "[out]" -c:a aac -b:a 192k out.m4a
```

Exit 0. `ffprobe` on the result: `codec_name=aac`, `duration=4.000000`.
libx264 was proven the same way (`testsrc2` → `codec_name=h264, 320x180`).

**Gotcha worth recording:** the probe reports `sample_rate=96000`, not 48000.
`loudnorm` resamples internally and does not restore the input rate. Append
`,aresample=48000` after `loudnorm` in the real mix graph or the muxed audio will
be at the wrong rate.

---

## 6. HyperFrames `doctor` — VERIFIED

`npx --yes hyperframes@latest --version` → **0.7.102** (reported as latest).

```bash
npx --yes hyperframes@latest doctor
```

**Found (✓):** Version 0.7.102 · Node v22.22.2 (linux x64) · CPU 4 cores Xeon
@2.80GHz · Memory 15.7 GB total / 14.4 GB available · Disk 24.5 GB free · Frames
cache `/tmp/hyperframes-extract-cache-0` · Archive extractor `unzip` · `/dev/shm`
16075 MB · Environment non-TTY · **FFmpeg** 6.1.1-3ubuntu5 at `/usr/bin/ffmpeg` ·
**FFprobe** 6.1.1-3ubuntu5 at `/usr/bin/ffprobe` · **Chrome** (see below) ·
**Docker** 29.3.1.

**Missing (✗):**

| Item | Doctor's note | Impact |
|------|---------------|--------|
| `whisper-cpp` | Not found (optional — needed for transcription) | `hyperframes transcribe` will not work. Doctor suggests building from source (needs cmake + a C compiler). **Not attempted.** |
| TTS (Kokoro) | Not installed (optional — local voice fallback) | `hyperframes tts` unavailable. Fix per doctor: `pip install kokoro-onnx soundfile`. **Not attempted.** |
| BGM (MusicGen) | Not installed (optional — local music fallback) | Fix per doctor: `pip install transformers torch soundfile numpy`. **Not attempted** (torch is a large install). |
| Docker running | "Not running" | Docker binary exists but the daemon is down. Only matters for containerised render paths. |

Doctor's overall verdict: `Some checks failed — see hints above`. All four
failures are marked **optional** by the tool itself; nothing required is missing.

### Chrome — HyperFrames also brings its own, but it *can* be pointed at the pre-installed one

By default doctor reports:

```
✓ Chrome  cache: /root/.cache/hyperframes/chrome/chrome-headless-shell/linux-152.0.7928.2/chrome-headless-shell-linux64/chrome-headless-shell
```

It downloaded its own `chrome-headless-shell` 152.0.7928.2 (197 MB) rather than
using `/opt/pw-browsers`. It does **not** need one it cannot find — but the
redundant download is avoidable. Testing the override env vars found in the
package:

| Env var | Result |
|---|---|
| `HYPERFRAMES_BROWSER_PATH` | **Works** — doctor reports `✓ Chrome  env: /opt/pw-browsers/...` |
| `CHROME_PATH` | **Ignored** — falls back to the downloaded cache copy |
| `PUPPETEER_EXECUTABLE_PATH` | present in the bundle; not tested |

Exact working invocation:

```bash
export HYPERFRAMES_BROWSER_PATH=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
npx --yes hyperframes@latest doctor
```

Note this points at the **headless shell**, not the full `chromium` binary —
consistent with the Remotion finding in item 3, where the full Chromium fails
because old headless mode was removed. Only the doctor check was verified with
this override; a full HyperFrames **render** under it was **not** tested.

---

## Known-good commands

```bash
# ---- Python imaging -------------------------------------------------------
pip3 install pillow imagehash
python3 -c "import PIL, imagehash; print(PIL.__version__, imagehash.__version__)"

# ---- Cutout: preferred path (clean matte, loses thin limbs) ----------------
npx --yes hyperframes@latest remove-background INPUT.jpg -o OUT.png
npx --yes hyperframes@latest remove-background --info      # list execution providers

# ---- Cutout: fallback (keeps thin limbs, drags background) -----------------
pip3 install "rembg[cpu]"
python3 - <<'PY'
from PIL import Image
from rembg import remove, new_session          # NOTE: first import takes ~80s
s = new_session("u2net")                        # do NOT use isnet-general-use here
Image.open("INPUT.jpg").convert("RGB")
out = remove(Image.open("INPUT.jpg").convert("RGB"), session=s,
             alpha_matting=True, alpha_matting_foreground_threshold=240,
             alpha_matting_background_threshold=20, alpha_matting_erode_size=8)
out.convert("RGBA").save("OUT.png", "PNG")
PY

# ---- Verify a cutout's alpha is real --------------------------------------
python3 - <<'PY'
from PIL import Image; import numpy as np
im = Image.open("OUT.png"); a = np.array(im)[:, :, 3]
print(im.mode, im.size, "bbox", im.getbbox())
print("transparent %.2f%%  opaque %.2f%%  soft %.2f%%" % (
    100*(a==0).mean(), 100*(a==255).mean(), 100*((a>0)&(a<255)).mean()))
PY

# ---- Remotion -------------------------------------------------------------
cd /home/user/Test-2/horror-pipeline/engine/remotion-engine
npm install --no-audit --no-fund
npx remotion versions
npx remotion browser ensure            # prints the resolved browser path

# generate plate/cutout assets FIRST (npm run plates is broken — see item 3)
python3 - <<'PY'
import os, sys
ENGINE = "/home/user/Test-2/horror-pipeline/engine/ffmpeg-engine"
ROOT   = "/home/user/Test-2/horror-pipeline/engine/remotion-engine/public"
sys.path.insert(0, ENGINE)
import numpy as np
from PIL import Image
import plates as P, cutouts as C, sheets.sewer_spider as M
P.PW, P.PH = 2600, 1600
os.makedirs(f"{ROOT}/plates", exist_ok=True)
for slot, desc, kl in M.PLATES:
    P.make_plate(slot, desc, slot*977+13, key_light=kl).save(f"{ROOT}/plates/slot{slot:02d}.png", "PNG")
P.make_plate(99, M.CARDS[0]["desc"], 4242, key_light=0.62).save(f"{ROOT}/plates/card.png", "PNG")
C.export_all(f"{ROOT}/cutouts")
os.makedirs(f"{ROOT}/tex", exist_ok=True)
rng = np.random.default_rng(7); g = rng.normal(0.5, 0.16, (512, 512)).clip(0, 1)
a = (abs(g-0.5)*2*255).astype("uint8"); v = np.where(g > 0.5, 255, 0).astype("uint8")
Image.fromarray(np.stack([v, v, v, (a*0.55).astype("uint8")], -1), "RGBA").save(f"{ROOT}/tex/grain.png")
PY

# single still (audio is absent, so withAudio MUST be false)
npx remotion still SewerSpider out/verify.png --frame=300 --props='{"withAudio":false}'

# same, reusing the pre-installed headless shell instead of Remotion's copy
npx remotion still SewerSpider out/verify.png --frame=300 --props='{"withAudio":false}' \
  --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell

# ---- Remotion Studio ------------------------------------------------------
cd /home/user/Test-2/horror-pipeline/engine/remotion-engine
setsid nohup npx remotion studio --no-open > /tmp/studio.log 2>&1 < /dev/null &
echo $! > /tmp/studio.pid
curl -s -o /dev/null -w "%{http_code}\n" --noproxy '*' http://localhost:3000/   # expect 200

# stop it — NEVER `pkill -f "remotion studio"` from an interactive/agent shell
cat > /tmp/stop-studio.sh <<'EOF'
#!/bin/bash
PAT=$(printf 'remotion\x20studio')
for p in $(pgrep -f "$PAT"); do
  cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
  case "$cmd" in *stop-studio*) continue;; esac
  kill "$p" 2>/dev/null
done
sleep 3
for p in $(pgrep -f "$PAT"); do
  cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
  case "$cmd" in *stop-studio*) continue;; esac
  kill -9 "$p" 2>/dev/null
done
EOF
chmod +x /tmp/stop-studio.sh && /tmp/stop-studio.sh

# ---- HyperFrames ----------------------------------------------------------
npx --yes hyperframes@latest doctor
npx --yes hyperframes@latest doctor --json
export HYPERFRAMES_BROWSER_PATH=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell

# ---- ffmpeg capability check ---------------------------------------------
ffmpeg -hide_banner -encoders | grep -E ' (libx264|aac) '
for f in sidechaincompress loudnorm apad atrim; do
  ffmpeg -hide_banner -filters 2>/dev/null | awk '{print $2}' | grep -qx "$f" \
    && echo "PRESENT $f" || echo "MISSING $f"
done
# remember: loudnorm changes the sample rate — append ,aresample=48000
```

---

## What failed or is unavailable

| Thing | Status | Detail |
|---|---|---|
| `npm run plates` | **BROKEN** | `scripts/export_plates.py` hardcodes `/home/claude/hp/...`. Not fixed — flagged only. Same pattern in `package.json:mux`, `scripts/stills.mjs`, `ffmpeg-engine/cutouts.py`. |
| Remotion + full Chromium | **UNUSABLE** | `--browser-executable=.../chromium-1194/chrome-linux/chrome` → "Old Headless mode has been removed". Use the `chromium_headless_shell-1194` binary instead. |
| Reusing `/opt/pw-browsers` by default | **NO** | Both Remotion and HyperFrames download their own `chrome-headless-shell` unless explicitly pointed at it (`--browser-executable` / `HYPERFRAMES_BROWSER_PATH`). |
| HyperFrames arm/limb retention | **FAILS** | Both thin arms dropped; model locked to `u2net_human_seg`, no override flag. |
| rembg background rejection | **FAILS** | Every config retains a large lit background region on this dark source. |
| rembg `isnet-general-use` | **FAILS** | Ghost output, 0.00% fully-opaque pixels. Do not use. |
| `whisper-cpp` | **ABSENT** | HyperFrames transcription unavailable. Not installed. |
| Kokoro TTS | **ABSENT** | HyperFrames local TTS unavailable. Not installed. |
| MusicGen BGM | **ABSENT** | Not installed. |
| Docker daemon | **NOT RUNNING** | Binary present (29.3.1), daemon down. |
| `libfdk_aac` | **ABSENT** | Native `aac` encoder only. |
| `public/audio/mix.wav` | **ABSENT** | Placeholder README only — always render with `withAudio: false` until a mix exists. |
| Full video render | **NOT ATTEMPTED** | Out of scope per brief; only stills were rendered. |
| HyperFrames render under `HYPERFRAMES_BROWSER_PATH` | **NOT TESTED** | Only `doctor` was verified with the override. |
| `CHROME_PATH` for HyperFrames | **IGNORED** | Silently falls back to the cached download. |
