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

### Observation 4: Metered-tool budget must be probed before a sampling plan is committed to

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Frame-level teardown of a competitor video. The task brief specified an expensive multimodal video-watching tool and budgeted "roughly 5-7 calls, each covering a 60-120 second window", with five suggested windows.

**Skill:** New skill candidate: metered-tool-research
**Type:** open-source
**Phase/Area:** Planning, before the first expensive call

**Issue:** The first call succeeded and returned an excellent 60-second teardown. The second call returned RATE LIMIT EXCEEDED: 5 of 5 calls used in the last 24 hours. Four had been consumed by earlier sessions, so the real budget was one call, not five to seven. Because the plan assumed a five-window budget, that single call was spent on the deepest possible read of the FIRST window (0-60s) rather than on the window with the highest information value, and the resulting coverage was 11% of the source. Had the true budget been known, the one call would have been aimed at a window straddling a section boundary and a number-dense passage, or asked a coverage-maximising question across a wider span. The cost of the mistake was not the failed call, it was that the successful call was pointed at the wrong target.

**Suggested improvement:** Before committing to any sampling plan built on a metered or rate-limited tool, establish the actual remaining budget, and treat it as a rolling shared quota that earlier sessions may already have spent rather than a per-session allowance. Where no quota-introspection endpoint exists, order the plan so the single highest-value call runs first and each subsequent call is a refinement, so that truncation at any point still leaves the most valuable observation made. State the assumed budget explicitly in the plan so a mismatch surfaces immediately rather than after the budget is gone.

**Principle:** A sampling plan is a bet on how many observations you will get. When the budget is metered, shared across sessions, and not visible up front, order the samples by information value rather than by source order, so that being cut off early costs coverage but never costs the most important measurement.

### Observation 5: Exhaust cheap sources before spending an expensive one, then re-scope the expensive call

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Same teardown. The brief named an expensive multimodal tool as the required instrument because "transcripts cannot answer visual questions", and listed nine question areas.

**Skill:** New skill candidate: metered-tool-research
**Type:** open-source
**Phase/Area:** Source triage, before the first expensive call

**Issue:** The framing that transcripts cannot answer the question was true for some of the nine areas and false for others, and this was not separated before spending. After the budget ran out, the cheap text sources were pulled as a fallback and turned out to answer a large share of the brief outright: the video description carried an official chapter list that gave exact section boundaries for all eight sections; the timestamped transcript gave section durations, per-section word counts and narration rate, the exact placement and script of both calls to action, and a complete map of every numeric utterance, which is precisely the input the central visual question was about. Roughly a third of the deliverable came from sources that cost almost nothing and were consulted only after the expensive budget was exhausted. Had they been pulled first, the expensive call could have been narrowed to what is genuinely visual-only and aimed at the passage the cheap data identified as most information-dense.

**Suggested improvement:** Make cheap-source exhaustion a required first step whenever a brief mandates an expensive instrument. Split the question list into what the cheap sources can answer, what they can partly answer, and what is genuinely exclusive to the expensive tool, then scope the expensive call to the third bucket only, and use the cheap data to CHOOSE the sampling window rather than accepting the windows suggested in the brief. Note that a brief naming an expensive tool as required is a statement about the hardest questions, not about every question in the list.

**Principle:** Cheap sources do double duty: they answer part of the question and they tell you where to point the expensive instrument. Spending the expensive budget first forfeits the second benefit entirely, so cheap-first is a sequencing rule, not a cost-saving preference.

### Observation 6: Measured config values need provenance and coverage metadata, or later sessions cannot adjudicate conflicts

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Producing a fresh measurement of a reference video that an earlier session had already measured into a machine-readable style profile used by a renderer. The profile's header asserted that every number came from watching a real video end to end on a stated date.

**Skill:** New skill candidate: measured-config-provenance
**Type:** open-source
**Phase/Area:** Writing and consuming measured configuration

**Issue:** The fresh pass contradicted the stored profile on five fields and found one whole concept missing from it: the reference uses three distinct non-scene frame backgrounds, the stored profile modelled only one, and the trigger condition it recorded for that one was mapped to the wrong background. When the conflict surfaced there was no way to adjudicate it, because neither side carried the metadata needed: the stored values recorded a date and a claim of full coverage but not the sampling method or per-field evidence, and the fresh values covered only 11% of the source. Two of the conflicts are plausibly not conflicts at all but different counting rules for the same quantity, and one is plausibly a context-dependent value that flips between frame types, but none of that is decidable from what either record stores. A downstream renderer reading the profile has no signal that some fields are firm and others are single-sample estimates.

**Suggested improvement:** Require every measured configuration value to carry provenance alongside the value: what fraction of the source was actually observed, by what method, on what date, and the counting rule for any counted quantity. Where a value is an estimate from partial coverage, mark it as such in the file rather than only in the accompanying prose, so consumers can distinguish a firm constant from a provisional one. When a fresh measurement contradicts a stored one, record both with their coverage rather than silently overwriting, and state what observation would settle it.

**Principle:** A measured value without its coverage and its counting rule is not reproducible and cannot be adjudicated against a later measurement. Provenance is part of the measurement, not commentary on it, so it belongs in the same record as the number.

### Observation 7: `pkill -f <pattern>` kills the agent's own shell, because the shell's cmdline contains the pattern

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Verifying a video toolchain. A dev server had been started in the background and needed to be stopped after confirming it was reachable.
**Skill:** New skill candidate: background-process-lifecycle
**Type:** open-source
**Phase/Area:** Stopping a background process started earlier in the session

**Issue:** The obvious cleanup command — `pkill -f "remotion studio"` — killed the agent's own bash invocation and returned exit 144, losing the rest of the compound command (the default-port test never ran). The cause is structural, not incidental: `pkill -f` matches against full command lines, and the agent's own shell process carries the pattern in its cmdline because the pattern is literally part of the command being run. Any agent that starts a process by name and later stops it by the same name hits this. It is silent in the sense that the failure looks like an unrelated crash, not like a self-kill.

**Suggested improvement:** Codify a lifecycle rule for background processes: capture the PID at launch (`setsid nohup … & echo $! > pidfile`) and stop by PID, never by name. When stopping by name is unavoidable, put the pattern-matching kill in a separate script file and execute the script — the invoking shell's cmdline then contains only the script path, not the pattern — and additionally skip any PID whose `/proc/<pid>/cmdline` matches the helper itself. Verify the stop by probing the port and expecting a connection-refused, not by trusting the kill's exit status.

**Principle:** A process-management command that selects targets by matching command-line text will also match the command line that is issuing it. Select by identity (PID) rather than by description, and when matching by description is unavoidable, ensure the matcher cannot see itself.

### Observation 8: Global alpha statistics hide categorical matte failures; measure the region that carries the meaning

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Evaluating two automatic background-removal tools on the same source photograph, to choose one for a production cutout workflow.
**Skill:** New skill candidate: cutout-quality-evaluation
**Type:** open-source
**Phase/Area:** Verifying the output of an automatic segmentation/matting step

**Issue:** The agreed acceptance evidence was "is the alpha channel present and non-trivial — count transparent vs opaque pixels". Both candidates passed that test convincingly, and on the headline numbers the cleaner-looking tool won decisively: far less retained background, a tight bounding box, a plausible soft edge. Those aggregates were true and still misleading. A targeted check — counting alpha pixels inside the horizontal band where the subject's thin outstretched limbs sit — returned exactly zero on either side of the torso: the tool had amputated both limbs and the "tight bounding box" that read as a quality signal was in fact the symptom. The competing tool retained the limbs but dragged background with them. Neither the transparent/opaque ratio nor the soft-edge percentage could distinguish "clean cut" from "cut too much", because both failures move the same aggregate in the same direction.

**Suggested improvement:** Make the verification step two-tier. Tier one is the cheap global check (alpha present, not all-or-nothing). Tier two is a subject-aware check derived from the source before looking at the output: identify the regions the cutout exists to preserve — thin limbs, hair, protrusions, anything narrow or low-contrast — and assert non-zero alpha inside each, plus a visual composite over a high-contrast ground. Record the failure mode by name (amputation vs background bleed vs ghosting) rather than a single quality score, since the two failure directions call for different remedies.

**Principle:** An aggregate quality metric that both failure directions push the same way cannot adjudicate between them. Derive the acceptance regions from what the artifact is *for*, check those specifically, and report the failure mode rather than a scalar.

### Observation 9: A pre-provisioned dependency is not the dependency the tool will use — resolve the actual path before claiming reuse

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Standing up a renderer in an environment whose documentation stated that a browser was pre-installed at a specific path, with an instruction not to download another one.
**Skill:** task-observer
**Type:** open-source
**Phase/Area:** Environment verification, before reporting what a tool depends on

**Issue:** A render succeeded on the first attempt with no visible download step, which read as confirmation that the tool had picked up the pre-provisioned binary as intended. It had not: the tool had quietly fetched its own copy into a nested project directory, and a first search missed it only because the path sat deeper than the search's depth limit. Asking the tool itself where its dependency lived returned the real path immediately. Separately, when the pre-provisioned binary was explicitly forced, it failed outright for a version-compatibility reason — so the intended reuse was not merely unused, it was not viable, and a nearby variant of the same binary had to be used instead. Reporting "it uses the pre-installed one" would have been wrong twice over, and the evidence for it was the *absence* of a symptom.

**Suggested improvement:** When an environment claims a dependency is pre-provisioned, verify by resolution rather than by outcome: ask the tool to print the path it resolved, or locate the binary with a depth-unbounded search, before describing the dependency in a report. Then separately test the forced-path invocation, because "the tool works" and "the tool works via the provisioned artifact" are independent claims. Treat a silent success as evidence of nothing in particular.

**Principle:** Absence of a failure symptom is not evidence that the intended mechanism was used. Verify which artifact a tool actually resolved, not merely that the tool succeeded — and treat "it works" and "it works the way we intended" as two claims needing two tests.
