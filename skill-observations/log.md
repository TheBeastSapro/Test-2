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

### Observation 2: Test-suite health reported from an auditor-broken environment, not the code

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** First-pass audit of an unfamiliar 55k-LOC Python application (FastAPI + Jinja) that the user believed was low quality. Ran the test suite to establish a baseline of actual health.
**Skill:** code-review-and-quality
**Type:** open-source
**Phase/Area:** Establishing a baseline before assessing an unfamiliar codebase

**Issue:** The repo was installed with `pip install -e .` plus a bare `pip install pytest`. The suite reported 103 failures, which was relayed to the user as a finding about their code. Every one of those failures was `async def functions are not natively supported` — the project declares `dev = ["pytest-asyncio>=0.23", ...]` in `pyproject.toml` and sets `asyncio_mode = "auto"` in its own pytest config. Installing the declared dev extra turned all 103 into passes (129 passed, 0 failed on the affected files). The defect was entirely in the auditor's environment setup, but it was reported as a property of the code — and to a user already primed to believe their app was badly built, a false "103 failing tests" is a damaging and self-confirming error.

**Suggested improvement:** Add an explicit precondition to the baseline/assessment step: before running or reporting on an unfamiliar project's test suite, install the project's own declared dev/test extra (`.[dev]`, `.[test]`, `requirements-dev.txt`, lockfile dev group) and read its test-runner configuration (`[tool.pytest.ini_options]`, `pytest.ini`, `tox.ini`, `setup.cfg`). Treat any homogeneous failure signature — the same error text across many tests — as an environment fault to be ruled out before it is reported, never as a code finding.

**Principle:** A test run measures the code and the environment together. Before attributing failures to the code, reproduce the project's own declared environment; a single failure signature repeated across many tests is evidence of a harness fault, not many independent defects. Reporting an environment artefact as a code defect is worst precisely when the user already expects bad news, because it confirms a belief that the evidence does not actually support.

### Observation 3: Establish which prior context is reachable before the user spends turns pointing at it

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Continuing work an earlier set of Claude Code sessions had started, in an ephemeral cloud container. The user referred in turn to a session branch, then two more branches, then "read the claude code chats" — expecting each to carry the history of ideas they had given.

**Skill:** context-engineering
**Type:** open-source
**Phase/Area:** Session start — inventorying available context

**Issue:** Three consecutive user turns pointed at prior context that did not exist in the environment: two of three named branches were absent from the only reachable remote, and no prior session transcripts survived at all (`~/.claude/projects/` held only the current session). Each absence was discovered reactively, one turn at a time, after the user had already spent a turn asking. Nothing was checked up front, so the user kept offering pointers into a void and learning one at a time that they led nowhere. The durable record of their intent did exist — in commit messages and committed design docs — but that was found incidentally rather than by deliberately inventorying what history was actually reachable.

**Suggested improvement:** Add an explicit first step when picking up work started elsewhere: enumerate what historical context is actually reachable before consuming it or asking the user for more — remote branches (`git ls-remote`, not `git branch -a`, which shows only stale local tracking refs), transcript directories, and committed design documents. Report the inventory to the user in one pass, naming both what exists and what does not, so they can redirect once instead of discovering gaps serially.

**Principle:** When resuming work whose history lives somewhere else, inventory what is reachable before asking the user to point at it. Discovering absent context reactively costs a turn per gap and pushes the user to keep supplying pointers that cannot resolve; one upfront inventory converts an indefinite series of dead ends into a single accurate statement of what survived. Where transcripts are gone, artefacts committed to the repository — commit messages, design docs — are the surviving record of intent and should be read as such.

### Observation 4: Quantify design-token entropy to convert "it looks amateur" into an actionable diagnosis

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** A user reported their app "feels like it's done by a noobie, not like an app built by top coders" and asked for a UI/UX overhaul. The complaint was entirely subjective and named no specific defect.

**Skill:** frontend-design
**Type:** open-source
**Phase/Area:** Diagnosis — before proposing any visual direction

**Issue:** The instinctive response to an "it looks amateur" report is to propose a new visual direction, which risks discarding work that is actually sound and leaves the user unable to judge the proposal. Counting the distinct values the stylesheet and templates actually use turned the subjective complaint into a measurement in one command: 23 distinct font sizes (including 9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5px), 29 distinct spacing values (nearly every integer from 1–18px), and 234 inline `style=` attributes. That is a precise mechanism — every size was chosen individually by eye rather than drawn from a scale — and it named what to fix without touching the palette, which measurement showed was coherent and deliberate. It also protected work that was good: the same pass revealed a considered token block and a documented design rationale that a "redesign" would have destroyed.

**Suggested improvement:** Add a diagnostic step before proposing visual direction: count distinct values per property class across the stylesheet and templates (font-size, spacing, transition duration, radius, colour) and count inline style attributes. Report the counts to the user. High cardinality in size and spacing with low cardinality in colour indicates a systematisation problem, not an art-direction problem — and those call for opposite responses. Use the measurement to decide which, rather than assuming a redesign.

**Principle:** Subjective aesthetic complaints have measurable correlates. Counting how many distinct values a design actually uses distinguishes a system that needs systematising from one that needs redirecting — and the distinction matters, because treating the first as the second destroys sound work while leaving the real defect in place.
