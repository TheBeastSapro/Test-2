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

### Observation 5: Environment-conditional setup scripts create an invisible capability gap on the other environment

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** User asked which of their installed skills need a local install to reach full power. The repo's `.claude/hooks/session-start.sh` opens with an early `exit 0` unless `CLAUDE_CODE_REMOTE=true`, so on a local machine it installs nothing — correctly, since it is written to rebuild a throwaway container and should not mutate a real system. The consequence is that eight skills silently run at reduced capability locally, and nothing anywhere tells the user which eight or why.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Capability inventory across environments

**Issue:** A setup script guarded by an environment check is the standard, correct pattern — but it splits a project's capabilities into two tiers with no visible marker of which tier you are in. The skills all *load* in both places, because loading only requires the markdown file. They simply fail, or silently degrade, at the point of use. Answering "which of these work here" required reading the hook's guard, then the installer it calls, then every skill's own scripts for undeclared binary dependencies (ffmpeg, espeak-ng, yt-dlp, a CLI, an MCP server) — none of which is declared in any manifest. There is no way to answer the question by inspection of the skills alone.

**Suggested improvement:** In the cross-environment-handoff skill, add a capability-inventory procedure: locate environment guards in setup scripts first, since they define the tier boundary; then resolve each skill to its concrete external dependencies (binaries, API keys, MCP servers, running applications) by reading its scripts rather than its description; then classify each as works-everywhere / needs-install / environment-locked, and state which tier the current environment is in. Recommend that projects declare per-skill external dependencies in a manifest so the inventory is readable rather than reconstructed.

**Principle:** A conditional setup script partitions a project's capabilities into tiers that are invisible at load time and only surface at use time. Any skill that ships external dependencies needs those dependencies declared somewhere a reader can find them, or the only way to learn what is missing is to trigger the failure.

### Observation 6: `set -e` turns a non-matching `[ a ] || [ b ] && fn` dispatch into a silent early exit

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Writing an installer with selectable groups (`all`, `audio`, `cli`). The group dispatch was written as two lines of `[ "$G" = all ] || [ "$G" = cli ] && install_cli`.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Shipped-script correctness

**Issue:** That line parses as `([ a ] || [ b ]) && fn`, so when the group does not match, the whole and-or list evaluates to false, and under `set -e` the script exits at that line. Running the installer with an explicit group would perform the requested work and then terminate before the summary, with exit status 1 — reporting failure after succeeding. The bug is invisible in the most-tested path: with the default group everything matches, every list is true, and the script runs to completion. It only fires on the explicitly-selected paths, which are the ones a hurried test skips. Caught by reading, not by running.

**Suggested improvement:** Add a rule to the shipped-script checklist: never use `a || b && c` for dispatch — write an explicit `if`, because the C-like precedence readers expect is not what the shell does, and `set -e` converts the misreading into a wrong exit status rather than a visible error. More generally, when a script has selectable modes, exercise every mode, not just the default; the default is the path most likely to mask a dispatch bug.

**Principle:** Under `set -e`, any bare and-or list is also a conditional exit. Constructs whose value is discarded in ordinary shell become control flow under `set -e`, and the failure mode is a wrong exit status rather than an error message — so the default code path passing proves the least about the branches.

### Observation 7: A directory listing cannot tell you whether a directory is load-bearing

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** Documenting a repo's skills for local use. Two sibling directories, `.agents/skills/` and `agent/skills/`, held near-identical names to `.claude/skills/`. On the strength of `ls` output alone this was written up as duplicate dead weight the user should clean up. A later check showed 26 of the 36 entries in `.claude/skills/` are symlinks into `.agents/skills/` — so that directory is the storage backing most of the skill set, and deleting it would have broken 26 skills. `agent/skills/` genuinely is unreferenced; the two look identical from a listing and could not be more different in consequence.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Repository inventory — before recommending deletion

**Issue:** The advice was destructive, confidently stated, and derived from a listing that could not support it. `ls` renders a symlink and a real directory near-identically, and `find -type d` skips symlinked directories entirely, so a naive comparison shows "same names in both places" and reads as duplication. Nothing about the observable surface distinguished the load-bearing directory from the dead one. The error was not a missing check so much as a category error: a name comparison was used to answer a reachability question.

**Suggested improvement:** Add a rule to the inventory procedure: never recommend deleting or consolidating a path without first establishing what references it. Concretely — resolve symlinks (`find -type l` plus `readlink`) before comparing directory trees; grep the repo for the path; and check whether anything resolves *into* the candidate. State the evidence for "unreferenced" alongside the recommendation, so a wrong call is visible rather than implicit. Treat "these look like duplicates" as a hypothesis requiring a reachability check, never as a finding.

**Principle:** Deletion advice needs positive evidence that nothing references the target, not the absence of evidence that something does. Two paths can be indistinguishable in a listing and opposite in consequence — the observable surface of a filesystem hides exactly the relationship that makes removal safe or catastrophic.

### Observation 8: `cmd && ok "..."` makes an installer report success it never had

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** An installer script whose stated design goal, in its own comment, was "track what could not be done so the summary is honest." Three install sites were written as `npm install -g defuddle && ok "installed"`, with no failure branch. Adversarial testing with a deliberately failing `npm` and `pipx` on PATH showed the script printing "Done." and exiting 0 while installing neither tool. The same file's `pkg_install` helper handled the identical situation correctly, so the bug was inconsistency within one script rather than ignorance of the pattern.
**Skill:** New skill candidate: cross-environment-handoff
**Type:** open-source
**Phase/Area:** Shipped-script correctness — reporting

**Issue:** `set -e` does not abort on the left side of an `&&` list, which is exactly why the idiom is convenient — and exactly why a failure there vanishes. No success message prints, but nothing else does either: no warning, no entry in the skipped list, no non-zero exit. The user is told the install succeeded, and the failure only resurfaces later as a skill that mysteriously does not work. This is worse than crashing, because the false success is durable and misattributed. Notably, the happy path and the "tool already present" path both behaved perfectly; only the failing-install path was wrong, and it is the path least likely to be exercised, since testing an installer usually means testing that it installs.

**Suggested improvement:** Add a rule: any command whose failure should be reported must be the *condition* of an `if`, never the left operand of `&&`. Add a self-check to the shipped-script checklist — for each thing the script claims to install, force it to fail and confirm three outcomes: a warning printed, the item in the skipped list, and a non-zero exit. Related: a partial install should exit non-zero, since callers and CI read the exit code, not the prose.

**Principle:** A script's honesty is a property of its failure paths, not its success paths, and `&&` is where failure paths go to die under `set -e`. Verify a reporting mechanism by forcing the failures it claims to report — a summary that has never seen a failure has never been tested.

### Observation 9: Platform requirements stated from memory go stale silently

**Status:** OPEN
**Date:** 2026-08-06
**Session context:** A setup guide asserted "On Windows, run all of this inside WSL" — written from recall, never checked. When the user turned out to be on Windows and new to all of it, reading the official setup page showed Claude Code installs natively on Windows via a PowerShell one-liner, WSL explicitly optional. The recalled requirement had been true at some point and had silently stopped being true. Acting on it would have sent a beginner through an unnecessary WSL install and into a *worse* configuration, since the desktop app's WSL sessions drop file mentions, connectors and plugins entirely.
**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Trigger conditions — platform and prerequisite claims

**Issue:** This is the same failure the same session already logged as Observation 3, recurring in a different form and getting further: it reached a written deliverable and a user-facing message before being caught. Platform support is the most perishable category of fact — it changes without any signal in the artefact that repeats it, no compiler rejects it, and it reads as settled background knowledge rather than as a claim needing a citation. The cost is asymmetric: an unnecessary prerequisite is invisible as an error, because the user completes the extra work and everything appears to function. Nothing about the outcome reveals that the requirement was never real.

**Suggested improvement:** Extend the skill's grounding rule to name platform requirements and prerequisites explicitly — "requires WSL", "needs Xcode", "only on 64-bit", "install Node first" — as claims to verify rather than recall, with the same standing as API signatures. Add the asymmetry as the reason: a *missing* prerequisite fails loudly at the user's first command, while a *fabricated* one costs time silently and can leave the user in a worse configuration than the correct path. When a guide targets a platform the author is not on, verifying its prerequisites is not optional diligence — it is the only check available.

**Principle:** Prerequisites are perishable facts that decay without notice and cannot be falsified by the artefact working. A superfluous requirement is invisible to the person who follows it, so it must be caught by verification before shipping — it will never be caught by use.
