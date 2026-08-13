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

## 2026-08-13

### Observation 2: Automating a chat workflow must preserve why its friction exists

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** Building a scriptwriting automation to replace a 2-3 hour chat-based process. The stated problem was "it asks me questions and I have to go back and forth". The first design removed the questions entirely.
**Skill:** New skill candidate: workflow-automation-intake
**Type:** open-source
**Phase/Area:** requirements gathering before automating an existing manual process

**Issue:** The user described back-and-forth questioning as the thing costing hours, so the natural reading was "remove the questions". Mid-build the user clarified the questions were deliberate — they exist to stop the output drifting from intent. Had that not been volunteered, the automation would have removed a control the user had installed on purpose, and the failure would have surfaced only as bad output much later, looking like a quality problem rather than a design error. The real cost was never the questions; it was the number of round trips they were spread across.

**Suggested improvement:** Before automating away any step of an existing manual workflow, separate the step's COST from its FUNCTION and ask which is being complained about. Cost is round trips, latency, repetition. Function is control, verification, alignment. The automation should collapse the cost while preserving the function — typically by batching many scattered decisions into one up-front checkpoint with pre-filled defaults, rather than deleting the checkpoint.

**Principle:** Friction a user built on purpose is a control, not a defect. When automating a manual process, ask what each piece of friction is protecting against before removing it; the goal is to reduce the cost of a control, not to delete the control.

### Observation 3: Verify a quality metric against a deliberately failing input, not only a passing one

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** Building a deterministic quality gate that scores draft scripts, including a "fact density" measure counting numbers and proper nouns per 100 words.
**Skill:** test-driven-development
**Type:** open-source
**Phase/Area:** testing measurement and scoring code

**Issue:** The fact-density and hook-specificity gates were implemented with a naive capitalised-word regex. Run against a deliberately content-free draft, they PASSED — sentence-initial capitals ("The", "It") were counted as proper nouns, inflating the measured density more than threefold. The gate existed to catch exactly that kind of empty prose and instead certified it. A test using only a well-formed draft would have shown plausible numbers and hidden the defect completely.

**Suggested improvement:** When adding a metric or scoring gate, the first fixture must be an input the gate is supposed to REJECT, and the assertion is that it rejects it. Testing a scorer on good input only proves it produces a number, not that the number discriminates.

**Principle:** A detector is only validated by input it must reject. Passing input proves the code runs; failing input proves the measurement means something.

### Observation 4: Inventory the user's existing tooling before building a replacement for it

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** Asked to automate a scriptwriting workflow. Built a measurement gate, a channel profile and a calibration tool across two commits before the user supplied their project files, which contained a mature SOP, a channel skill, and a far better-calibrated lint tool covering most of the same ground.
**Skill:** New skill candidate: workflow-automation-intake
**Type:** open-source
**Phase/Area:** discovery, before any building

**Issue:** The user described a painful manual process and the natural response was to build the missing tool. They already had it. Worse than the wasted work, the invented version CONTRADICTED theirs in three places that would have caused real damage: a uniform per-section word budget where their documented system deliberately varies section length (their own rule: "never uniform"), a guessed 180 wpm where they had a measured 185, and a required hook/outro section where their format explicitly has neither. Shipping it would have produced a gate that fails their correct scripts. The user had twice offered the files before they were requested; the offer was acknowledged but building continued in parallel rather than pausing for it.

**Suggested improvement:** When a user describes an established manual workflow, inventory what they already have BEFORE building — ask for their existing docs, tools and SOPs as the first action, not after a prototype exists. An established workflow that produces real output almost always has accumulated tooling, and any constant invented to fill a gap (rates, thresholds, target lengths) is likely already measured somewhere in their files. Treat every self-chosen constant as a question to ask rather than a default to ship. When a user offers project files, stop and take them; parallel building against assumptions produces work that must be discarded, and its contradictions are invisible until they fire on real input.

**Principle:** A user with a working process has tooling, and invented constants will contradict their measured ones. Inventory before building — the cost is not the wasted work, it is that an invented default silently overrides a measured one and fails the user's correct work.

### Observation 5: Test extraction tools against the user's own logged failures

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** Building a scanner to extract high-risk factual claims from a draft for verification. The user's SOP carried an appendix logging eight real errors that had reached video comments, each with its claim type.
**Skill:** test-driven-development
**Type:** open-source
**Phase/Area:** choosing test fixtures for detection and extraction tools

**Issue:** Building a fixture from those eight logged real-world failures caught three misses in the first implementation that invented test data would not have: a fabricated scene detail was excluded because a place name was treated as a sourcing anchor; a statistic written as "half the armies" was missed by a pattern expecting "half of"; and a percentage spelled out as "four percent" was missed by a digits-only pattern, which is the COMMON case in narration written to be read aloud. All three were exactly the shapes the scanner existed to find.

**Suggested improvement:** When a user's documentation contains a log of past failures — a corrections log, an incident list, a bug postmortem table — build the first test fixture directly from it and require every logged instance to be caught. It is the highest-value fixture available: real, already classified by the user, and drawn from the exact distribution the tool will run against.

**Principle:** A user's log of past failures is a ready-made regression suite. Where one exists, it outranks any fixture that could be invented, because every entry is a real instance of the thing being detected.

### Observation 6: Verify an enforcement claim by running it, before reporting it as enforced

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** The user stated a hard rule twice ("ExplainTory is not 2nd person", then "Do not write explaintory in 2nd person"). Their existing linter contained a second-person check, and it had already been reported back to them as enforced.

**Skill:** doubt-driven-development
**Type:** open-source
**Phase/Area:** verifying that a rule is actually enforced by the tooling that appears to enforce it

**Issue:** The linter's second-person check was real but conditional: it produced a hard failure only when an optional `--overlay` flag was passed, and a warning otherwise. Reading the code showed a check existed; running it on a deliberately failing draft showed the rule did not hold in the default invocation, so a script could address the viewer throughout and exit 0. The claim "this is enforced" had already been made on the strength of having seen the check in the source. The gap was only found because the user repeated the rule, prompting an execution test rather than another read.

**Suggested improvement:** When reporting that a rule is enforced, run the enforcing tool against an input that violates the rule and confirm the failure, using the exact invocation the workflow actually uses. Reading the check is not verification: checks are routinely conditional on flags, modes, config or environment, and the conditional path is invisible when scanning for the rule's presence. Where a rule is unconditional in policy, assert it is unconditional in code — grep the check for flag-dependence specifically.

**Principle:** Presence of a check is not enforcement of a rule. Verify by executing the violating case through the real invocation path; a conditional guard looks identical to an unconditional one when you are only reading for whether the rule exists.

### Observation 7: Composite scores must exclude the criteria that are pass/fail

**Status:** OPEN
**Date:** 2026-08-13
**Session context:** Asked to add a numeric score to a quality-checking pipeline that already had hard gates and graduated profile metrics.
**Skill:** New skill candidate: quality-gate-design
**Type:** open-source
**Phase/Area:** designing scoring and ranking for quality systems

**Issue:** The natural implementation of "make it score" is one number over every measured dimension. That silently converts hard constraints into soft ones: a draft violating an absolute rule can still score highly because conforming dimensions outweigh it, and the headline number is what a reader acts on. A first pass at the comparison output showed the same failure in miniature — it ranked two candidates by score and printed "but blocking failures decide first" underneath, which is a verdict arguing with its own caveat while the headline wins.

**Suggested improvement:** Split the output into blocking criteria and scored criteria, and never blend them. Score only quantities that are legitimately a matter of degree; list absolute constraints separately, unweighted and unaveraged, and tie the exit code to those rather than to the score. Where a verdict or ranking is printed, the verdict logic must itself implement the precedence rule, not state it in adjacent prose.

**Principle:** Averaging a hard constraint into a score converts it into a soft one. Blocking and scored criteria must be reported separately, and any headline verdict must implement the precedence it claims — a caveat printed beneath a contradicting headline is not read.
