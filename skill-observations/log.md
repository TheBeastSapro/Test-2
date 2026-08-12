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

---

## 2026-08-12

### Observation 2: Bulk agent/skill installs need a provenance lock and a stated context cost

**Status:** OPEN
**Date:** 2026-08-12
**Session context:** Installing a 270-agent third-party roster (a public GitHub collection of subagent definitions) into a project's agent directory on a platform where the session container is ephemeral and persistence rides on git.
**Skill:** context-engineering
**Type:** open-source
**Phase/Area:** Configuring project context — installing third-party agent/skill collections

**Issue:** Installing a large third-party collection of agents (or skills) into a project is treated as a file-copy task, but it has two consequences no step in the workflow currently forces you to handle. First, provenance: a flat copy of hundreds of vendored files carries no record of which upstream repo and commit they came from, so there is no way to diff, update, or audit them later — and no way to distinguish vendored files from locally authored ones sitting in the same directory. Second, context cost: every installed agent's name and description is loaded into the session's agent roster on every future session in that project, so a 270-agent install silently adds a fixed per-session context tax that the user never chose and is never told about. Both were handled here only because they were noticed ad hoc — a lock file was written and the cost was flagged in the summary — not because any step required it.

**Suggested improvement:** Add a rule to the context-engineering skill covering bulk installs of third-party agents/skills into a project: (a) write a lock file recording source repo, pinned commit, install path, and a per-file hash, and keep an idempotent re-install script alongside it so updates are a diff rather than a re-copy; (b) never overwrite or lock locally authored files that share the install directory — identify vendored files by their presence upstream, not by directory; (c) state the per-session context cost of the install to the user in concrete terms (how many entries load every session) and name the narrower alternative (install only the subsets they need) even when the user asked for everything.

**Principle:** Vendoring third-party context into a project is a dependency decision, not a copy operation: it needs pinned provenance, a reproducible update path, a boundary that protects local files, and an explicit statement of the recurring cost it imposes on every future session.
