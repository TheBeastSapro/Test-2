# Which skills need a local install, and how

Short version: **29 of your 37 repo skills work the moment you clone.** Eight
need something installed. The reason is one line in your own hook.

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

## Group B — need a local install (8)

| Skill | What's missing locally | Install |
|---|---|---|
| `defuddle` | `defuddle` CLI | `npm install -g defuddle` |
| `tweet` | the `tweet` shim the hook symlinks | symlink `.claude/tools/tweet-read.py` onto your PATH — the installer does it |
| `explaintory-vo-master` | numpy, scipy, torch, torchaudio, faster-whisper, ffmpeg | installer, group `audio` |
| `explaintory-voiceover` | all of the above + elevenlabs, jiwer, whisper-normalizer, spacy + model, espeak-ng, phonemizer, panphon, allosaurus | installer, group `audio` |
| `sound-designer` | audio stack + scenedetect, librosa, silero-vad, opencv + yt-dlp + Epidemic Sound MCP | installer, group `audio`; MCP below |
| `browser-testing-with-devtools` | chrome-devtools MCP server | `claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --isolated` |
| `obsidian-cli` | the Obsidian desktop app, running | install Obsidian, enable its CLI; the skill drives a **running** instance |
| `analyse` (plugin) | NexLev MCP + yt-dlp | MCP below |

### The one-shot installer

```bash
cd ~/claude-repos/Test-2
./local-setup/install-skills-local.sh          # everything
./local-setup/install-skills-local.sh audio    # just the voiceover/sound stack
./local-setup/install-skills-local.sh cli      # just defuddle, yt-dlp, tweet
```

It is idempotent — re-running skips what's present. Python packages go into a
project `.venv`, not your system Python; `torch` comes from the CPU wheel index
(~200 MB, not the 2.5 GB CUDA build).

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

`ffmpeg` is **hard-required** — `install-audio-tools.sh` aborts without it, and
every measurement in the sound-design and mastering pipeline is an ffmpeg call.
`espeak-ng` is soft: without it only the pronunciation check goes dark, which is
the check that would have caught "Quito" (see `HANDOFF.md`).

### API keys

```bash
export ELEVENLABS_API_KEY="..."     # explaintory-voiceover; generation only
```

Put it in your shell profile, not in the repo. `.gitignore` already blocks
`voiceover_profile.json` because a profile can carry a key.

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
  you signed into interactively will prompt again locally. That's expected, not
  a broken setup.
- `github` is redundant locally — use `gh`, which the CLI already prefers.

## Group D — plugins

`.claude/settings.json` enables three: `claude-mem@thedotmack`,
`superpowers@superpowers-dev`, `ui-ux-pro-max@ui-ux-pro-max-skill`. They install
from their marketplaces on your first local `claude` run in this repo.

These get **better** locally: `/plugin` is one of the commands that doesn't run
in cloud sessions at all, so managing them is only possible from a terminal.

## Verify

```bash
source .venv/bin/activate
bash .claude/scripts/install-audio-tools.sh    # its own import check, 17 packages
```

Ending in `[audio-tools] all 17 packages present` means the voiceover and
sound-design skills are at full power. Then, in Claude Code, `/context` lists
the skills actually loaded.

## What stays cloud-only

`Claude-Code-Remote` MCP — routines, triggers, `send_later`, spawning cloud
sessions. It's the bridge *to* the cloud, so it has no local equivalent beyond
`claude --cloud`. Nothing else in your setup is cloud-locked.

## Two things to fix while you're in there

- `.claude/settings.json` declares `"hooks"` **twice**. Both blocks are
  identical so nothing breaks today — the second silently wins — but the first
  edit to that file that changes only one block will produce a confusing
  no-op. Collapse them.
- `.agents/skills/` and `agent/skills/` are near-duplicate copies of the same
  skill set as `.claude/skills/`. Only `.claude/skills/` is loaded. The other
  two are dead weight that will drift out of sync.
