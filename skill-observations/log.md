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

## 2026-08-06

### Observation 2: No guidance for requests whose target is a machine the agent cannot reach

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** User asked to "clone all cloud repos/chats in to local I want to use it locally" while the session was running inside an ephemeral cloud container (Claude Code on the web). The agent has no path to the user's local filesystem, so the literal request was unexecutable — but the underlying goal was fully achievable by producing a bundle the user runs locally.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Task intake — deliverable-shape selection when execution environment != target environment

**Issue:** Requests phrased as direct actions ("clone X into local", "install this on my machine", "set up my laptop") are routinely issued to agents running in a remote/sandboxed environment that cannot touch the target. No skill covers how to recognise this class or what to deliver instead. The failure modes are predictable: either the agent refuses ("I can't access your machine"), delivering nothing, or it silently performs the action *inside the sandbox* — cloning into a container that is reclaimed at teardown — which looks like success and produces nothing the user keeps. Here the correct deliverable was neither: a committed, tested bundle of scripts plus a document stating precisely which parts transfer, which do not, and why.

**Suggested improvement:** Create a skill covering the recognise → reshape → verify loop: (1) detect the mismatch by asking "does the target of this request exist in the environment I am running in?"; (2) reshape the deliverable into an artefact that executes in the target environment (script, checklist, exported bundle) and persists beyond the current session (committed to the repo, not written to container-local paths); (3) state the boundary explicitly — the parts that cannot be transferred at all, and the supported mechanism for each part that can; (4) verify by exercising every code path reachable from the authoring environment, and naming the paths that could not be tested there.

**Principle:** When the target of a request lies outside the environment the agent runs in, the deliverable changes shape but the scope does not: produce something that executes in the target environment, make it outlive the current session, and state the boundary rather than either refusing or silently acting inside the sandbox.

### Observation 3: source-driven-development is scoped to libraries, not product/platform behaviour

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Writing user-facing instructions for moving Claude Code cloud sessions to a local terminal. Working from memory would have produced a wrong or hedged answer; fetching the official documentation yielded the exact supported mechanism (`--teleport`), its four preconditions, and the explicit fact that no bulk-download exists.
**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Trigger conditions / scope

**Issue:** The skill's framing is about implementation decisions in code — "building with any framework or library where correctness matters." It does not obviously cover the case where the deliverable is *instructions for a human* about a product's or platform's behaviour: exact commands, menu paths, preconditions, and stated limitations. That case has the same failure mode (confident recall of a version-stale or invented detail) with a worse blast radius, because the user follows the instructions directly instead of a compiler rejecting them. In this session, three separate details — the flag name, the four teleport preconditions, and the absence of any bulk export — were all facts only the docs could settle, and the negative fact ("there is no bulk download") is one that recall alone would never surface.

**Suggested improvement:** Extend the skill's trigger conditions to name user-facing procedural instructions — CLI invocations, UI menu paths, preconditions, limits — as a case requiring source grounding, not just code. Add a rule that documented *limitations and absences* be cited alongside capabilities, since a missing constraint reads as an unqualified promise. Add a caution that a menu path or flag stated from memory should be verified or omitted, never approximated.

**Principle:** Instructions a human will execute verbatim need the same source grounding as code, and stated limits deserve equal weight to stated capabilities — an omitted constraint is read as a promise.

### Observation 4: Scripts authored in a Linux container ship to macOS bash 3.2 and break

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Writing shell scripts in a Linux container (bash 5.x) for the user to run on their own machine, likely macOS.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Deliverable verification — target-environment compatibility

**Issue:** The first draft used two constructs that work in the authoring container and fail on the most likely target. `mapfile` does not exist in bash 3.2, which macOS still ships as `/bin/bash`. And under `set -u`, referencing `${#ARR[@]}` on an array declared empty is an unbound-variable error on older bash, so the script's own error-reporting path was the part that would crash. Both passed `bash -n` and both passed a live run in the container, because the container's bash is modern. Neither the syntax check nor the successful execution could have caught them — only knowing the target's interpreter version could.

**Suggested improvement:** In the cross-environment-handoff skill, add a target-compatibility checklist for shipped scripts: assume the oldest interpreter the target platform ships by default, not the authoring environment's; avoid bashisms newer than that baseline or declare the requirement in the shebang and fail fast with a clear message; treat error-handling paths as needing the same compatibility scrutiny as the happy path, since they are the least likely to be exercised in testing.

**Principle:** A green test run in the authoring environment proves nothing about the target environment. For anything shipped to run elsewhere, compatibility is established by knowing the target's baseline, not by the artefact working where it was written — and error paths, being the least exercised, are where the incompatibility survives to production.
