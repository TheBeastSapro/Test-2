# Which skills need a local install, and how

Short version: **29 of the 36 skills in this repo work the moment you clone.**
Seven need something installed. The reason is one line in your own hook.

## Why anything is missing at all

`.claude/hooks/session-start.sh` starts with this:

```bash
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
```

On a local machine that hook **does nothing, on purpose** — so it never
mutates your system the way it rebuilds a throwaway container. Everything it
installs in the cloud (Agent Reach, yt-dlp, the `tweet` shim, and the whole
audio toolchain) is therefore absent locally until you install it once by
hand. Once. It persists; containers are what needed it every session.

## Read this before you tidy anything

`.claude/skills/` holds 36 entries, but only **10 are real directories**. The
other **26 are symlinks into `.agents/skills/`**:

```
.claude/skills/interview-me -> ../../.agents/skills/interview-me
```

So `.agents/skills/` is **load-bearing**. Deleting it breaks 26 of your 36
skills. All 26 links currently resolve.

`agent/skills/` — same name, no dot, 24 directories — is the one that is
genuinely unreferenced: nothing symlinks to it, and it's already drifted (it's
missing `frontend-design` and `web-design-guidelines`, and no file in it is
byte-identical to its `.agents/skills/` counterpart). That's the one to clean
up, and only that one.

---

## Group A — work immediately, nothing to install (29)

Pure instruction skills. `git clone` is the install.

`api-and-interface-design` · `ci-cd-and-automation` · `code-review-and-quality`
· `code-simplification` · `context-engineering` · `debugging-and-error-recovery`
· `deprecation-and-migration` · `documentation-and-adrs`
· `doubt-driven-development` · `frontend-design` · `frontend-ui-engineering`
· `git-workflow-and-versioning` · `idea-refine` · `incremental-implementation`
· `interview-me` · `json-canvas` · `obsidian-bases` · `obsidian-markdown`
· `observability-and-instrumentation` · `performance-optimization`
· `planning-and-task-breakdown` · `security-and-hardening` · `shipping-and-launch`
· `source-driven-development` · `spec-driven-development` · `task-observer`
· `test-driven-development` · `using-agent-skills` · `web-design-guidelines`

## Group B — need a local install (7)

Dependencies below are what each skill's **code actually imports or shells
out to**, not what the shared installer happens to install.

| Skill | What it actually needs | Install |
|---|---|---|
| `defuddle` | `defuddle` CLI | `npm install -g defuddle` |
| `tweet` | the `tweet` shim the hook symlinks | installer, group `cli` |
| `explaintory-vo-master` | numpy, scipy, torch, torchaudio (`MMS_FA` forced alignment), ffmpeg | installer, group `audio` |
| `explaintory-voiceover` | elevenlabs, faster-whisper, jiwer, whisper-normalizer, spacy + `en_core_web_sm`, numpy, scipy, torch, torchaudio, ffmpeg | installer, group `audio` |
| `sound-designer` | scenedetect, librosa, opencv, ffmpeg, yt-dlp, Epidemic Sound MCP | installer, group `audio`; MCP below |
| `browser-testing-with-devtools` | chrome-devtools MCP server | `claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --isolated` |
| `obsidian-cli` | the Obsidian desktop app, running | install Obsidian; the skill drives a **running** instance |

Three notes on that table, because the shared installer is broader than the
skills are:

- **`faster-whisper` belongs to `explaintory-voiceover` only.** Its
  `readcheck.py` and `orphans.py` import it. `explaintory-vo-master` never
  does — `humanize.py` is its only file and it uses torchaudio for alignment.
- **espeak-ng, phonemizer, panphon and allosaurus are not used by any skill.**
  They belong to `vo-studio/vostudio/pronounce_check.py`, a separate tool.
  `explaintory-voiceover`'s own `pronounce.py` deliberately rejects the
  phoneme approach in favour of respelling. `HANDOFF.md` still lists the
  pronunciation check under "Still broken / not built" — install them for
  vo-studio, not expecting the voiceover skill to use them.
- **silero-vad is not used by `sound-designer`.** `analyze.py` detects speech
  with ffmpeg's `silencedetect` filter. It's in the package list because the
  repo's `install-audio-tools.sh` verification block requires all 17 imports.

### The one-shot installer

```bash
cd ~/claude-repos/Test-2
./local-setup/install-skills-local.sh          # everything
./local-setup/install-skills-local.sh audio    # just the voiceover/sound stack
./local-setup/install-skills-local.sh cli      # just defuddle, yt-dlp, tweet
```

It installs the same 17 packages as `.claude/scripts/install-audio-tools.sh`,
so that script's own verification block passes. Idempotent — re-running skips
what's present. Python goes into a project `.venv`, not your system Python;
`torch` comes from the CPU wheel index (~200 MB, not the 2.5 GB CUDA build).

**Activate the venv before launching Claude Code**, or the skill scripts'
`python3` will resolve to your system Python and report the packages missing:

```bash
source .venv/bin/activate && claude
```

### System packages it can't install for you

`ffmpeg` and `espeak-ng` are OS packages. The installer detects and installs
them via `brew` or `apt` when it can, and tells you if it can't:

```bash
brew install ffmpeg espeak-ng          # macOS
sudo apt install ffmpeg espeak-ng      # Debian/Ubuntu
```

`ffmpeg` is **hard-required** — `install-audio-tools.sh` exits 1 without it,
and every measurement in the sound-design and mastering pipeline is an ffmpeg
call. `espeak-ng` is soft: it only warns, and only vo-studio's pronunciation
check is affected.

### API keys

```bash
export ELEVENLABS_API_KEY="..."     # explaintory-voiceover; generation only
```

Put it in your shell profile, not in the repo. `.gitignore` already blocks
`**/voiceover_profile.json` because a profile can carry a key.

## Not in this repo: your personal skills

`analyse` is **not a repo skill** — it lives in your global
`~/.claude/skills/`, alongside `pdf`, `docx`, `canvas-design`, `morning` and
the rest of your personal set. Cloning this repo does not bring it, and none
of the above installs it. If you want those on the new machine too, copy your
global `~/.claude/skills/` across separately. (`analyse` additionally wants
the NexLev MCP and yt-dlp.)

Worth knowing: `.claude/skills/explaintory-vo-master/` in this repo contains
only `scripts/humanize.py` — no `SKILL.md`. The description lives in your
global copy. Locally, the repo alone gives you the script but not the skill
definition.

## Group C — MCP servers (account-level, not repo-level)

Six MCP servers are live in your cloud sessions: **github, NexLev,
Epidemic-Sound, Google-Drive, Claude-Code-Remote, Idea-Phantom**. These are
attached to your cloud environment, so a local checkout starts with none of
them. They aren't in the repo and cloning won't bring them.

Add the ones tied to skills:

```bash
# sound-designer — music and SFX
claude mcp add --transport http epidemic-sound <server-url>

# analyse — YouTube/TikTok/Instagram research
claude mcp add --transport http nexlev <server-url>

# browser-testing-with-devtools
claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --isolated
```

Two caveats worth knowing before you spend time on it:

- **The URLs aren't recoverable from inside a container.** Read them off
  claude.ai → Settings → Connectors, where you added them.
- **OAuth connectors re-authenticate per machine.** Google Drive and anything
  you signed into interactively will prompt again locally. That's expected,
  not a broken setup.
- `github` is redundant locally — use `gh`, which the CLI already prefers.

## Group D — plugins

`.claude/settings.json` enables three: `claude-mem@thedotmack`,
`superpowers@superpowers-dev`, `ui-ux-pro-max@ui-ux-pro-max-skill`. They
install from their marketplaces on your first local `claude` run in this repo.

These get **better** locally: `/plugin` is one of the commands that doesn't
run in cloud sessions at all, so managing them is only possible from a
terminal.

## Verify

```bash
source .venv/bin/activate
bash .claude/scripts/install-audio-tools.sh    # its own import check
```

Ending in `[audio-tools] all 17 packages present` means the voiceover and
sound-design skills are at full power. Then, in Claude Code, `/context` lists
the skills actually loaded.

## What stays cloud-only

`Claude-Code-Remote` MCP — routines, triggers, `send_later`, spawning cloud
sessions. It's the bridge *to* the cloud, so it has no local equivalent beyond
`claude --cloud`. Nothing else in your setup is cloud-locked.

## One thing to fix while you're in there

`.claude/settings.json` declares `"hooks"` **twice**. Both blocks are
identical so nothing breaks today — the second silently wins — but the first
edit that changes only one block will produce a confusing no-op. Collapse
them.
