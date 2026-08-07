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

## 2026-08-07

### Observation 2: Official docs are not authoritative for capability questions — check the source tree

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Installing a third-party open-source app (an Electron + Next.js AI media studio) at the user's request. The user asked whether a specific capability — image-to-video on the desktop build — was available. The project's own README stated that the relevant UI wiring was "on the roadmap", i.e. not yet available.
**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Grounding decisions in official documentation — authority ranking of sources

**Issue:** The skill grounds implementation decisions in official documentation, which is right for API contracts and usage patterns but wrong as a blanket rule for *capability* questions about a fast-moving project. Here the README described an older release (v1.0.9 installers) while the checked-out source was a later version (v2.0.0) that had already implemented the feature. Answering from the README would have told the user the capability did not exist, when three source locations showed it shipped: a catalog filter splitting image-to-video entries, the studio component merging those entries into its model list, and the upload path routing to the local server instead of the cloud API. The README was not wrong when written — it had simply drifted behind the code, which is the normal state of a README in an actively developed repo.

**Suggested improvement:** Add an authority-ranking rule to the skill: documentation is authoritative for *how to use* an interface, but the source tree at the checked-out revision is authoritative for *whether a capability exists*. When a doc claim is negative ("not yet supported", "on the roadmap", "planned") and the answer materially affects the user, verify against the code before repeating it — negative claims age worst, because features get added without the doc being updated. Note the specific tell: a version mismatch between the docs' stated release and the checked-out revision means every capability claim in those docs is suspect. Cite file and line when contradicting a doc, so the correction is checkable.

**Principle:** Documentation and source can disagree, and which one wins depends on the question: docs are authoritative for intended usage, code is authoritative for present capability. Negative capability claims in docs are the highest-risk kind to trust, because nothing forces a doc update when the gap they describe gets closed.

### Observation 3: In ephemeral environments, an "install X" task delivers a reproducible installer, not the installed artifacts

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** A bare "install this <repo URL>" request, executed in a per-session container that is reclaimed after inactivity. The install produced multi-hundred-megabyte desktop packages, and the build was verified end-to-end, but none of it could outlive the session.
**Skill:** New skill candidate: third-party-install
**Type:** open-source
**Phase/Area:** Scoping the deliverable for install requests

**Issue:** "Install X" is ambiguous in a way that only shows up in ephemeral environments. The literal reading — run the install in the current environment — produces something real but worthless, since the artifacts die with the container and the user's own machine is untouched. Nothing in the existing skill set names the reframing: the durable deliverable is a committed, reproducible install path plus a verification record proving the path works, not the artifacts. The verification is what makes the committed script trustworthy — it converts "here is a script that should work" into "this exact sequence was executed and these steps passed" — so the build in the throwaway environment is not wasted, it is the evidence. Separately, the request arrived with the target platform unstated; it emerged only through unprompted mid-task user messages, and platform determines which install route is even applicable.

**Suggested improvement:** Scope a skill for installing third-party software on the user's behalf. Core rules: (1) determine early whether the executing environment is the user's machine or a remote/ephemeral one, and say so plainly when it is not — the user may reasonably assume otherwise; (2) in ephemeral environments, treat a committed install script plus a verification record as the deliverable, and note explicitly that any built artifacts are not persisted; (3) establish target platform and hardware before recommending a route, since prebuilt installer vs build-from-source vs local-GPU paths diverge on both; (4) record what was verified *and what was not* — a headless container cannot exercise a GPU or a desktop UI, and claiming otherwise is the failure mode; (5) surface the real cost model, separating the software's license from what running it actually charges.

**Principle:** When the environment executing a task is not the environment the task is ultimately for, the deliverable shifts from the artifact to the reproducible means of producing it — and the throwaway execution earns its keep as evidence that those means work.
