# Open Generative AI

Setup for [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI)
— an MIT-licensed, self-hostable AI image/video studio. It ships two entry
points from the same source tree: an Electron desktop app and a Next.js web
app. Models come from either MuAPI (cloud, paid per generation) or a local
engine running on your own GPU (free).

## What actually costs money

The app is free. Generating is not, unless you run models locally.

| Part | Cost |
|---|---|
| The app itself — source, desktop builds, self-hosting | Free (MIT) |
| 400+ cloud models (Flux, Kling, Sora, Veo, Midjourney, Seedance…) | Paid — MuAPI access key, billed per generation |
| Local images via bundled `sd.cpp` | Free — desktop app only, runs on your GPU |
| Local video via [Wan2GP](https://github.com/deepbeepmeep/Wan2GP) | Free — you supply a CUDA/ROCm GPU |

The upstream README's "no subscription fees" refers to the software, not to
generating. MuAPI sponsors the project, so the README is promotional about it.

## The free path on an NVIDIA GPU

Both local engines take CUDA, so a cloud key is optional — skip it at first
launch and everything below still works.

**Images — `sd.cpp`, bundled, no separate install.** Open **Settings → Local
Models**, install the engine (one click, auto-downloaded), pull a model, then
hit the **⚡ Local** toggle in Image Studio. SD 1.5 models (Dreamshaper,
Realistic Vision, Anything v5) are ~2.1 GB each; SDXL is 6.9 GB; Z-Image needs
its weights plus 2.7 GB of shared auxiliary files and wants 16 GB RAM.

**Video — Wan2GP, a server you run.** The desktop app is only an HTTP client to
it; it bundles no Python and no weights. Wan2GP's runtime (Sage attention,
flash-attn, AWQ/GGUF kernels) is CUDA-only, which is exactly the hardware you
have.

```bash
git clone https://github.com/deepbeepmeep/Wan2GP
cd Wan2GP
./install.sh                                    # install.bat on Windows
python wgp.py --listen --server-name 0.0.0.0
```

Then **Settings → Local Models → Wan2GP server**, paste the URL
(e.g. `http://192.168.1.42:7860`), **Test**, **Save**. Gets you Flux.1 Dev,
Qwen Image, Wan 2.2 T2V/I2V, Hunyuan Video, and LTX Video.

### Image-to-video, locally and free

Works on the desktop app at v2.0.0. The upstream README still says Video Studio
wiring is "on the roadmap" — that text is stale; the source has it:

- `src/lib/localModels.js:176` splits the Wan2GP catalog into `localI2VModels`
  (entries flagged `needsImage`) — `wan2gp:wan22-i2v`, "Wan 2.2
  (Image-to-Video)".
- `src/components/VideoStudio.js:31` merges those entries into Video Studio's
  image-to-video model list.
- `src/components/VideoStudio.js:173` routes the source-image upload to
  `localAI.uploadFileToWan2gp` instead of MuAPI when the selected model is a
  Wan2GP one, so no cloud round-trip and no key.

So image-to-video runs two ways: cloud models (Kling, Sora, Veo, Seedance…)
against a paid MuAPI key, or Wan 2.2 I2V against your own GPU for free.

The catch is `isLocalAIAvailable()` (`src/lib/localInferenceClient.js:9`), which
tests `window.localAI?.isElectron`. Every local path — images and video — is
**desktop-only**. The web build never shows local models.

Model weights default to Electron's app-data dir
(`~/.config/open-generative-ai/local-ai` on Linux,
`%APPDATA%\open-generative-ai\local-ai` on Windows). Set
`OPEN_GENERATIVE_AI_LOCAL_AI_DIR` before launch to keep multi-GB weights on
another drive.

## Install

**Prebuilt desktop installer — no Node.js, one click.** Upstream publishes
v1.0.9 at [the releases
page](https://github.com/Anil-matcha/Open-Generative-AI/releases): `.exe` for
Windows x64, `.dmg` for macOS (Apple Silicon and Intel), `.AppImage`/`.deb` for
Linux. macOS is not notarized, so Gatekeeper blocks the first launch — clear it
with `xattr -cr "/Applications/Open Generative AI.app"`.

**From source** — `./install.sh` in this directory. Needs Node.js 18+ (22.x
verified) and git. It clones with submodules, runs the upstream `setup` script,
and by default builds the desktop app for the host platform.

```bash
./install.sh                          # clone + setup + desktop build
./install.sh --no-desktop             # skip packaging, dev entry points only
./install.sh --dir ~/apps/ogai        # choose the checkout location
```

Source is at v2.0.0, ahead of the v1.0.9 published installers, so building
yourself gets you a newer app than the download links.

Then start one of:

```bash
npm run electron:dev   # desktop app (Electron + Vite)
npm run dev            # web version → http://localhost:3000
```

`npm install` alone is not enough — the four workspace packages (`studio`,
`workflow-builder`, `agents`, `design-agent`) must be built first, which is what
`npm run setup` does. Skipping it makes `npm run dev` fail with
`Couldn't find a 'pages' directory`.

## Verified

Built and run end-to-end on Linux x64, Node v22.22.2 / npm 10.9.7:

| Step | Result |
|---|---|
| `npm run setup` (submodules + install + 4 workspace builds) | pass |
| `npm run build` — Next.js production build | pass |
| `npm run vite:build` — Electron renderer | pass |
| `electron-builder --linux AppImage deb --x64` | pass — Electron 33.4.11 |
| Packaged binary launch | pass — boots and stays running under Xvfb |

Artifacts were 275 MB (`.AppImage`) and 162 MB (`.deb`). They were built in an
ephemeral container and are not committed here; `install.sh` reproduces them.

Local model inference was not exercised — it needs a GPU and the desktop UI,
neither available in a headless container.
