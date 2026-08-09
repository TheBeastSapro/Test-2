# Start here

You are looking at the handoff bundle for a faceless analog-horror YouTube pipeline.

## Setup, once

1. Unzip this folder somewhere sensible, for example `~/horror-pipeline`.
2. Install Claude Code: https://code.claude.com/docs/en/setup
   - Desktop app if you would rather not use a terminal.
   - Or `curl -fsSL https://claude.ai/install.sh | bash` on macOS/Linux, `irm https://claude.ai/install.ps1 | iex` in Windows PowerShell.
3. Open a terminal in this folder and run `claude`. In the Desktop app, open this folder as the project.
4. Reconnect your tools as MCP servers if you want them: Epidemic Sound, Google Drive, NexLev. Ask Claude Code to help, it can edit `.mcp.json` for you.

Claude Code reads `CLAUDE.md` automatically on every session, so the house rules load themselves. You do not have to re-explain the channel.

## What is in here

- `CLAUDE.md` - the standing instructions. Loads automatically.
- `docs/` - 36 project docs, the whole operating standard. `docs/INDEX.md` describes each one.
- `spec/BUILD-PACKET.md` - the full build spec, 11.5k words, including the asset-sourcing stage that has to run on your machine.
- `spec/style-profiles.json` - measured style configs for M Simplified, Ficknime, Darkly, and the house profile.
- `engine/remotion-engine/` - the primary renderer (React/Remotion).
- `engine/ffmpeg-engine/` - the fallback renderer plus `qc.py`, the measured QC pass.

## What is deliberately missing

- `node_modules` - run `npm install` inside `engine/remotion-engine/`.
- The finished audio mix and the rendered video. Both regenerate.
- Real creature art. Every shot renders a placeholder tagged `ASSET SLOT NN`. Building the approved-image library is Stage 1 of the packet and it is the actual bottleneck.

## First thing to do

Paste the kickoff message (in the chat where you got this) into Claude Code. It orients itself, then builds the asset sourcing you cannot do anywhere else.
