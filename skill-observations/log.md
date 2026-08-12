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

### Observation 3: A user's stated cause for a symptom is a hypothesis to test, not a diagnosis to confirm

**Status:** OPEN
**Date:** 2026-08-12
**Session context:** Immediately after vendoring a large third-party asset collection into a project, the user asked whether that install was the reason their sessions were slow to start. Measurement showed the install cost ~9 ms of file reads and could not be the cause — the real cost was a pre-existing session-start hook doing multi-hundred-megabyte package installs and network probes on every session.
**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Root-cause investigation — handling a user-supplied causal hypothesis

**Issue:** When a user proposes a cause for a symptom, especially the change that just happened, the conversational pull is to confirm it — it is recent, salient, plausibly expensive-looking, and agreeing is the path of least friction. The skill's investigation guidance addresses finding a root cause from symptoms, but does not name the specific failure mode of *inheriting* a cause from the person asking. Two checks resolved it immediately here and neither was prompted by any step: a timeline check (the suspected change landed after the symptom was already being observed, so it cannot be the cause) and a direct measurement of the suspect against the alternatives (milliseconds versus tens of seconds). Without them the answer would have been a confident, wrong yes.

**Suggested improvement:** Add a rule to the investigation phase for user-supplied hypotheses: treat the proposed cause as one candidate among several, never the default. Run two cheap checks before answering — (1) timeline: could the suspected change have been present when the symptom was first observed? (2) magnitude: measure the suspect and at least one alternative candidate in the same units, and compare. Report the measurements, not just the verdict, and say plainly when the user's hypothesis is wrong.

**Principle:** The most recent change is the most suspected and the least likely to have been measured. A causal claim that arrives with the question deserves the same evidence bar as one you would have proposed yourself — confirm it with a timeline check and a measured comparison, or contradict it with them.

### Observation 4: Declared configuration is a request, not a result — verify the runtime state

**Status:** OPEN
**Date:** 2026-08-12
**Session context:** A project settings file declared three plugin marketplaces and marked three plugins as enabled. The user believed they had been running for a long time. None were installed: that settings key is only honoured at user scope, and an entry at project scope is silently dropped — no error, no warning, and the file reads exactly like a working configuration.
**Skill:** context-engineering
**Type:** open-source
**Phase/Area:** Project configuration — verifying that configuration took effect

**Issue:** Configuring a project is treated as finished when the config file says the right thing. But config systems commonly have scope boundaries (user vs project vs local), and the near-universal failure behaviour at a boundary is to ignore the entry rather than reject it. The result is config that is indistinguishable from working config by reading alone, and can sit broken indefinitely — here it survived long enough that the user was surprised, and it also produced a false lead when diagnosing an unrelated performance problem, because the declared-but-absent components looked like plausible suspects. Nothing in the workflow required checking the runtime side: one command listing what was actually installed settled in seconds what reading the file could never have settled.

**Suggested improvement:** Add a verification step to the context-engineering skill's project-configuration guidance: after writing or auditing any config that registers external components (plugins, extensions, marketplaces, MCP servers, hooks), query the runtime for what is actually loaded and diff it against what is declared. Prefer the tool's own list/status command over reading the file back. Note explicitly that scope-boundary rejections are usually silent, so "the file is correct" is not evidence the component is active — and that on ephemeral or per-session environments, a component installed at user scope must be reinstalled by a session-start step or it silently disappears again.

**Principle:** Reading a config file tells you what was requested; only the runtime tells you what was granted. Any configuration whose effect crosses a scope, a process, or a machine boundary must be verified by observing the running system, because the common failure mode there is silence, not an error.
