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

### Observation 2: Tool-install instructions assume a persistent home directory

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Installing a third-party agent-harness bundle (ECC) whose documented default install target is the user's home config directory (`~/.claude/`), while the session ran in a whole-container-ephemeral environment (Claude Code on the web). The home-directory install would have been correct-looking and completely gone at container teardown; the install only persisted because the tool happened to offer a project-scoped target that lands inside the git working tree, which was then committed.
**Skill:** New skill candidate: install-persistence-check (or an addition to task-observer's references/environments.md)
**Type:** open-source

**Phase/Area:** Pre-install target selection for any third-party tooling

**Issue:** Third-party install docs overwhelmingly default to a home-directory or global target and say nothing about environments where the home directory does not outlive the session. Following the documented default in an ephemeral container produces an install that verifies green in-session and silently ceases to exist afterwards — an especially bad failure mode because nothing errors. Catching it required manually enumerating the installer's targets and picking a project-scoped one, then committing the result to git.

**Suggested improvement:** Before running any install command, resolve where the artifacts will land and check that path against the environment's persistence model; if the target does not survive the session, prefer a project-scoped/in-repo target and commit it, and state the substitution to the user. Worth a short reusable skill, or a subsection in task-observer's environments reference alongside the existing workspace-folder guidance.

**Principle:** Persistence of an install target is a property of the environment, not of the tool's documentation — verify where artifacts land against the environment's lifetime before accepting any documented default.

### Observation 3: Presence of installed files was nearly mistaken for the component being active

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** After a project-scoped install of an agent-harness bundle, all payload files (skills, agents, commands, rules, hooks) copied successfully and the installer reported done. The hook runtime, however, was written to a config file the host does not auto-load in project scope, and its runtime path resolution pointed at a home directory that has no install — so 50+ hooks were present on disk and entirely inert. A file-count verification would have reported full success.
**Skill:** cross-cutting principle candidate (applies to any skill with an install/setup/deploy phase)
**Type:** open-source

**Phase/Area:** Post-install verification

**Issue:** The natural verification after an install is "did the files land" — counts, directory listings, no errors. That check cannot distinguish an active component from a dormant one. Components that require registration with a host (hooks, plugins, daemons, extensions, cron entries) are activated by a wiring step separate from the copy, and that wiring is exactly what an installer may deliberately leave alone to avoid clobbering user config.

**Suggested improvement:** In any skill covering install/setup/deploy, make the verification step ask "is it wired in and would it fire", not "is it on disk" — check the host's registration surface (settings file, plugin registry, service manager) and, where cheap, trigger the component once. Report inert-but-installed components explicitly to the user rather than reporting a clean install.

**Principle:** File presence is not activation — verify a component at its registration surface, not at its installation path.
