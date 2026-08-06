# Skill Observation Log

Observations captured during task-oriented work.

**Status key:** OPEN = not yet actioned | ACTIONED (YYYY-MM-DD) = skill
updated/created | DECLINED (YYYY-MM-DD) = user decided not to pursue —
resolved statuses always carry their resolution date

---

## 2026-08-05

### Observation 1: Workspace-folder guidance misses whole-container-ephemeral platforms

**Status:** OPEN
**Date:** 2026-08-05
**Session context:** Installing task-observer into a repo running on Claude Code on the web (remote execution environment). Each session runs in a fresh, ephemeral container that is reclaimed after inactivity, and the repo is cloned fresh each time.
**Skill:** task-observer
**Type:** open-source
**Phase/Area:** references/environments.md — workspace folder resolution

**Issue:** The workspace-folder guidance (SKILL.md and references/environments.md) names ephemeral checkouts — a git worktree under `.claude/worktrees/`, a temporary clone — as the failure mode to detect and re-anchor away from. It doesn't name a distinct failure mode: platforms where the *entire session container* is ephemeral per session, not just a checkout subdirectory within an otherwise-persistent environment. On such platforms even the "stable" path (`~/.claude/projects/<project-id>/`) doesn't outlive a session, so the default guidance would silently write a log that vanishes at container teardown. This had to be caught manually and worked around with a CLAUDE.md override pinning the workspace folder to the git repo root and committing the observation files so persistence rides on git instead of the local filesystem.

**Suggested improvement:** Add a named pattern to references/environments.md for "whole-container-ephemeral" platforms (e.g. cloud/web coding environments that clone fresh per session), distinct from the worktree/temp-clone case already covered. Recommend anchoring the workspace folder inside the git repository itself and committing `skill-observations/` so persistence is git-backed rather than filesystem-backed, and suggest checking for this pattern during the Session Start Protocol's config-detection step.

**Principle:** Any skill instruction that assumes a persistent local filesystem needs an explicit fallback for platforms where the whole session container is ephemeral, not only for ephemeral subdirectories within an otherwise-persistent environment.

## 2026-08-06

### Observation 2: No skill covers reverse-engineering a product from a screen recording

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** User linked a 21-minute X video demoing a SaaS product (kloudboard/kloudie) and asked for the product's built-in apps to be enumerated and a working clone built. No skill matched; the whole method was improvised.
**Skill:** New skill candidate: product-teardown-from-video
**Type:** open-source
**Phase/Area:** Whole workflow

**Issue:** The task needed a repeatable method that did not exist as a skill: download the video, sample frames at a fixed rate, assemble contact-sheet montages so hundreds of frames can be scanned in a handful of vision calls instead of one call per frame, read only the frames that show the product, transcribe audio for narration-only facts, then cross-reference the vendor's public pages to convert visual guesses into cited fact. Each step was rediscovered mid-task. The contact-sheet step in particular was the difference between ~7 vision calls and ~213.

**Suggested improvement:** Create a skill covering: frame sampling rate selection by video length; `ffmpeg tile` contact sheets as the cheap scanning primitive before targeted full-resolution reads; region-crop-and-upscale for unreadable UI chrome (icon rails, small labels); ASR for narration-only claims; and a mandatory public-source cross-reference pass before any finding is stated as fact. Include an explicit observed-vs-inferred labelling convention in the output.

**Principle:** When the evidence is a long video, the scanning strategy dominates cost — build a cheap low-resolution index first and spend high-resolution attention only where the index says something is there.

### Observation 3: A vendor's comparison and roadmap pages outrank its homepage as reverse-engineering sources

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Same teardown. The homepage yielded positioning copy; `/compare` yielded 42 pages naming the exact product cloned per module, `/roadmap` yielded 19 dated shipped/planned items, `/mcp` yielded a full 19-tool API surface with descriptions, and `/product/*` yielded per-module feature detail the homepage omitted entirely (client portal, custom fields, version history, Zapier/webhooks).
**Skill:** New skill candidate: product-teardown-from-video
**Type:** open-source
**Phase/Area:** Cross-reference pass

**Issue:** The instinct is to fetch the homepage and stop. The homepage is the least informative page a SaaS vendor publishes — it is written to be vague. The high-yield pages are the ones written to convert or to inform existing users: comparison pages (which name competitors module by module, effectively confirming the lineage of each feature), public roadmaps (which reveal what is *not* built, and the team's own framing of each feature), integration/MCP/API docs (which expose the real data model), and per-product marketing pages.

**Suggested improvement:** Add an explicit source-priority checklist to the cross-reference phase: `/compare` or `/vs/*` → `/roadmap` or `/changelog` → `/mcp`, `/api`, `/docs`, `/integrations` → `/product/*` or `/features` → `/pricing` → homepage last. Note that a comparison page answers "what did they take inspiration from" directly and with the vendor's own words, which is otherwise a speculative question.

**Principle:** When reverse-engineering any product, prefer the pages written for readers who already know the product over the pages written to attract readers who don't — informational intent correlates with information density.

### Observation 4: A passing type-check was treated as evidence the UI works

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** After `tsc -b && vite build` went green on a 15-screen React app, the next instinct was to report it as done. Driving it in a headless browser instead caught issues a compile cannot see: incoherent seed data surfacing as a $15.60 RPM against figures that should have produced $13.05, and a chart whose spikes rendered as unreadable needles.
**Skill:** frontend-ui-engineering
**Type:** open-source
**Phase/Area:** Verification / definition of done

**Issue:** For UI work, a green build proves the code compiles, not that anything renders, that state flows between screens, or that displayed numbers agree with each other. The gap was closed with a short Playwright script that visited every route asserting zero console errors, then drove the primary state loop end to end (agent proposes a write → user approves → the created records appear in a different app → a counter decrements → the change survives reload). That script found real defects; the build did not.

**Suggested improvement:** Add a verification rule to the skill: UI work is not done at a green build. Require (a) a headless pass over every route asserting no console/page errors, (b) at least one end-to-end drive of the app's primary state loop across more than one screen, and (c) a visual read of the rendered screenshots — including a check that displayed figures are mutually consistent, since seed and mock data drift silently and only ever fails in the rendered output.

**Principle:** A compiler validates the code you wrote; only execution validates the thing the user sees. For any visual deliverable, the definition of done must include looking at it.
