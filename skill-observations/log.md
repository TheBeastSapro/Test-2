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

### Observation 2: Merging JSON config by "keeping both sides" produces silent duplicate keys

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Installing a Claude Code plugin required editing `.claude/settings.json`. The file contained the same top-level `hooks` key twice — identical content — left behind by earlier merge commits whose messages were literally "Merge base branch, keeping both settings blocks" and "Merge base branch: run both session-start halves".
**Skill:** git-workflow-and-versioning
**Type:** open-source
**Phase/Area:** Conflict resolution

**Issue:** "Keep both sides" is the right instinct for a conflict in an *additive list* (two sets of skills, two hook scripts) and the wrong one for a conflict in a *keyed object*. Applied to JSON, it emits a duplicate key. Most JSON parsers accept this silently and take the last occurrence, so one side's changes are discarded with no error, no warning, and a merge commit whose message claims both were kept. Here the two blocks happened to be identical so nothing was lost, but the same resolution on divergent blocks loses one side invisibly. Detection required opening the file for an unrelated reason.

**Suggested improvement:** In the conflict-resolution guidance, distinguish list-shaped conflicts (concatenate) from key-shaped conflicts (merge entries into a single key; if both sides set the same key to different values, that is a real conflict needing a decision). Add a post-merge verification step for structured-config files: parse the merged file and assert the parsed result contains both sides' contributions — a clean `git merge` exit and a passing syntax check both succeed on a duplicate-key JSON file, so neither is evidence the merge preserved anything.

**Principle:** For structured-data files, "the merge succeeded" and "the merge preserved both sides" are different claims. Verify the second by parsing the result and asserting the expected entries are present — never infer it from the absence of conflict markers.

### Observation 3: Tool-local installs don't survive on whole-container-ephemeral platforms

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Ran `claude plugin install <plugin>@<marketplace>` on Claude Code on the web. The CLI reported success at `scope: user`, writing to `~/.claude/settings.json` and a cache under `~/.claude/plugins/` — both inside a container that is discarded when the session ends.
**Skill:** update-config
**Type:** open-source
**Phase/Area:** Where a configuration change is written

**Issue:** A CLI that installs or configures something at "user scope" reports unqualified success, because from its point of view the write did succeed. On a platform where the entire session container is ephemeral, that success is real but worthless — the next session starts without the change, and nothing in the success message hints at this. The durable location is the committed repo config (here `.claude/settings.json`, already carrying three other plugins via `extraKnownMarketplaces` + `enabledPlugins`), so the install has to be mirrored there and committed. A related trap: the install command's failure message for an unregistered marketplace suggested updating that marketplace, which then failed too; the actual missing step was registering it first. An error that names a remedy is not the same as an error that diagnosed the cause.

**Suggested improvement:** Add a rule that before treating any configuration change as done, resolve where the tool actually wrote it and whether that path outlives the session. If it does not, mirror the change into the version-controlled project config and commit it. Where a repo already configures the same class of thing declaratively, follow that existing pattern rather than leaving the change only in tool-local state.

**Principle:** A tool reporting success only attests that the write happened, not that it will still be there next session. On ephemeral platforms, durability is a separate property that has to be established deliberately — by writing to version control — and verified, not inferred from the tool's exit status.
