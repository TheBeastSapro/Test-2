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

## 2026-08-07

### Observation 2: Declared plugin/tool config is not evidence of installation

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** User asked whether `claude plugin install superpowers@claude-plugins-official` had installed. The repo's `.claude/settings.json` contained an `enabledPlugins` block listing three plugins, which reads as "these are installed" — but the runtime state (`~/.claude/plugins/installed_plugins.json`, `claude plugin list`, `ListPlugins`) showed zero plugins installed and zero marketplaces configured.
**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Evidence gathering — distinguishing declared config from runtime state

**Issue:** Declarative configuration files (`enabledPlugins`, lockfiles, dependency manifests, feature flags in source control) describe intent, not state. A declared-but-never-installed component is indistinguishable from an installed one if you only read the config. Answering an "is X installed / enabled / working?" question from the config alone produces a confident wrong answer, and the failure is silent — nothing errors, the config just sits there being aspirational.

**Suggested improvement:** Add a rule to the evidence-gathering section: for any "is X installed/active/configured?" question, read runtime state first (the tool's own status command, its installed-state file, the live process), and treat declarative config as a separate claim to be reconciled against it. Report both when they disagree — the disagreement is usually the actual finding.

**Principle:** Configuration declares intent; runtime state records fact. When asked whether something is in effect, verify against runtime state — and when the two disagree, the divergence is the answer, not an inconvenience.

### Observation 3: Confirm a negative result with a differently-shaped command before reporting its cause

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Diagnosing why `claude plugin install superpowers@claude-plugins-official` failed. The CLI returned: `Plugin "superpowers" not found in marketplace "claude-plugins-official"` — phrasing that presupposes the marketplace exists and merely lacks the plugin. Running a second, differently-shaped command (`claude plugin marketplace update claude-plugins-official`) returned the real cause: `Marketplace 'claude-plugins-official' not found. Available marketplaces: superpowers-dev`. The first message would have led to reporting the wrong cause ("wrong plugin name") instead of the right one ("that marketplace does not exist").

**Issue:** Error messages are written for the expected failure mode and routinely mis-attribute unexpected ones. A message naming an entity ("not found *in* X") is not evidence that X exists — the tool may never have resolved X at all. Taking the message's framing at face value silently narrows the diagnosis to the wrong layer.

**Suggested improvement:** Add a rule to the root-cause section: before reporting the cause of a failure, re-probe with a command that targets a *different layer* of the same operation (here: query the container rather than the item inside it). Confirm the failing layer independently instead of inheriting the error message's assumption about which layer failed.

**Principle:** An error message is a hypothesis authored by someone who did not anticipate your failure. Independently confirm which layer actually failed before reporting a cause — especially when the message's grammar presupposes that an upstream entity resolved successfully.
