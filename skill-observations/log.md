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
