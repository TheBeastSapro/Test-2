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

### Observation 2: Inherited handoffs need their stated limits and stated status re-verified before planning

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Taking over an existing multi-stage media production pipeline delivered as a handoff bundle (spec + docs + working code). The handoff's central premise was that one pipeline stage had to move to a new environment because the previous environment could not reach a required external API.
**Skill:** New skill candidate: handoff-intake
**Type:** open-source
**Phase/Area:** Orientation phase, before any planning or code is written

**Issue:** Two claims carried in the handoff docs turned out to be stale, and both would have distorted the plan if taken at face value. (1) The environment claim: the entire reason the work was relocated was "this environment cannot reach the source API". A 40-second connectivity probe in the new environment showed the API, the asset CDN, and full-resolution downloads all working — so the stated blocker was not a property of the tooling but of the specific previous environment, which changes what is worth building and where it can run. (2) The status claim: the standing instructions file stated a config refactor was "partially landed" in one of the renderers. A single grep showed zero code paths read the config file at all — the refactor was spec-only. Neither claim was dishonest; both were simply written at a different time than they were read. Planning on either without checking would have produced a plan aimed at the wrong problem.

**Suggested improvement:** Add an explicit intake step for inherited work, before planning: extract every load-bearing claim in the handoff docs into two buckets, environment/capability claims and implementation-status claims, then verify each with the cheapest available probe (a live request for the first, a grep or an import for the second). Report which claims held and which did not as part of the plan, since a falsified claim usually changes the plan's shape rather than just its details. Budget this as minutes, not as a phase.

**Principle:** A handoff document describes the world as it was when written, not as it is when read. Claims that determine what gets built — what the environment can reach, and what is already implemented — must be re-verified by direct probe at intake, because both decay silently and both are cheap to test and expensive to assume.

### Observation 3: A curated digest of a source is a map, not a substitute, when decisions hinge on specifics

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Orienting on an inherited production pipeline. The bundle included a curated findings document explicitly created by mining a long chat log for material that had never been written to a project doc. Partway through the session the owner supplied the underlying 35,000-word log itself.
**Skill:** New skill candidate: handoff-intake
**Type:** open-source
**Phase/Area:** Orientation phase, source material triage

**Issue:** The digest was accurate and well made, and reading it first was the right call: it surfaced conflicts, specs and decisions efficiently. But reading the primary source afterwards changed two things the digest had flattened in ways that mattered for the design about to be proposed. First, a rule the digest recorded as a binary policy conflict turned out in the source to be a deliberate owner decision with a stated reason, which inverts how a tool should treat that case (surface and let the human decide, rather than block). Second, a failure the digest recorded at category level appeared in the source at a finer granularity that changed the required data model. A digest is lossy in exactly the direction that hurts: it preserves conclusions and drops the distinctions that constrain implementation.

**Suggested improvement:** Treat digest-then-source as the standard order rather than an either/or, and make the second pass explicitly targeted: after reading a digest, re-read the source filtered to the decisions actually about to be made, looking specifically for granularity the digest collapsed and for stated reasons behind rules the digest recorded only as rules. Where the source is large, that targeted second pass is cheap. Where a digest and a source disagree, the source wins and the digest should be updated.

**Principle:** Read the digest to orient, read the source before deciding. Summaries preserve conclusions and lose the distinctions that determine how something must be built, so any decision that turns on specifics needs the primary source, not the summary of it.
