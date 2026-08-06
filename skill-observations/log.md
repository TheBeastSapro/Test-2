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

### Observation 5: A repo-root .gitignore silently excluded a required source asset

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Added a video review module to a sub-project. Ships two encodes per clip as source assets. The repo root's `.gitignore` carried `*.mp4` (intended for media artifacts from an unrelated sub-project), so `git add -A` staged the `.webm` files and silently skipped every `.mp4`. Nothing errored. The app would have shipped with the H.264 encode missing, 404ing for exactly the browsers that need it, while passing CI — because the verify browser can only play the `.webm` that did get committed.
**Skill:** git-workflow-and-versioning
**Type:** open-source
**Phase/Area:** Staging / pre-commit verification

**Issue:** `git add -A` reports success whether or not a file was ignored. The failure is invisible at commit time and at build time, and here it was also invisible to the test suite, because the one artifact the test browser could consume was the one that got through. It surfaced only from reading `git diff --cached --stat` and noticing a file count that did not match what was on disk. In a monorepo or any repo with sub-projects, a root ignore rule written for one sub-project applies to all of them, and a broad extension glob is exactly the kind of rule that ages into a trap.

**Suggested improvement:** Add a staging check to the skill: when a commit introduces binary or non-source assets, diff the staged file list against what is on disk in the added directories (`git status --ignored`, or compare `git ls-files <dir>` to `ls <dir>`) before committing. Recommend `git check-ignore -v <path>` as the one-command diagnosis. Note that the fix belongs in the sub-project's own `.gitignore` as a scoped negation, not in the root rule, so the original intent stays intact.

**Principle:** Tooling that silently skips work reports the same success as tooling that did the work. When an operation can partially no-op without erroring — staging under ignore rules, copying with filters, selective sync — verify the output set, not the exit code.

### Observation 6: Test environment codec gaps mislead unless the fix is the portable one

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** A `<video>` element would not load under the verify browser. Diagnosis: Playwright's bundled Chromium is built without proprietary codecs, so `canPlayType('video/mp4; codecs="avc1.42E01E"')` returns empty — H.264 is unplayable there, though fine in real Chrome and Safari.
**Skill:** browser-testing-with-devtools
**Type:** open-source
**Phase/Area:** Environment differences between test and production browsers

**Issue:** The tempting responses are both wrong: re-encode everything to the format the test browser likes (which breaks Safari), or exclude the feature from automated checks (which abandons coverage of the highest-risk module). The correct response was to treat the gap as a genuine portability signal and ship both encodes behind `<source>` elements — which fixed real-browser portability *and* restored test coverage. Worth noting the general shape: a capability the test environment lacks is often a capability *some user's* environment also lacks.

**Suggested improvement:** Add a note on test-vs-production browser capability gaps — bundled Chromium lacking proprietary codecs (H.264/AAC) is the common one, alongside missing fonts and disabled hardware acceleration. Recommend probing capability directly (`canPlayType`, feature detection) rather than inferring from a silent failure, and prefer fixes that make the artifact more portable over fixes that special-case the test environment. Note the React-specific trap that swapping `<source>` children does not re-run source selection — the element needs a `key` to remount.

**Principle:** When the test environment can't do something production can, ask whether some real user shares that limitation before special-casing the test. The portable fix usually satisfies both, and a fix that only satisfies the test is coverage theatre.
