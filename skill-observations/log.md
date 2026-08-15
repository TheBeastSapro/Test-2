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

### Observation 5: Run the product to its output before diagnosing it from source

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Auditing a video-production app the user said was "not doing what I intend". Two prior turns diagnosed it by reading source and screenshotting pages in their default empty state, producing a confident but shallow list of styling defects.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Reproduction — establishing what the software actually does

**Issue:** Static reading and empty-state screenshots surfaced real but minor defects (spacing, column balance, a truncated status word). Driving the product all the way to its actual output — creating an account, a channel, and a run, then waiting out a twelve-minute render — surfaced the defect that mattered: the pipeline wrote a 23 MB finished video to disk and registered it as an artifact, and no screen in the application ever showed it or linked to it. Reading the preview page's source did not reveal this, because the code is correct for what it was written to do (simulate the plan pre-render); the bug is an absence, and absences are invisible in source. It only appeared when a run reached a state the empty app could never show. The user had already named this exact area as their worst friction, and two turns of source-reading had not found it.

**Suggested improvement:** Add an explicit reproduction step before diagnosis on any product with a pipeline or multi-stage output: drive it end to end to a real artifact, including waiting for slow stages, and compare what exists on disk or in the database against what the interface exposes. Diff produced-artifacts against reachable-artifacts as a named check. Treat empty-state inspection as insufficient — most interesting states are the ones only reachable by actually completing the work.

**Principle:** A defect of omission cannot be found by reading the code that omits it, because that code is locally correct. Run the product to its real output and compare what it produced against what it shows; the gap between the two is where this class of bug lives, and it is invisible from both the source and the empty state.

### Observation 6: Reproduce the failing call in isolation before believing its error message

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Diagnosing why a pipeline run died two stages after a human approval gate. The raised exception stated a specific cause: a data structure was empty.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Reading a failure — treating the error text as evidence rather than as fact

**Issue:** The exception said "the shortlist is empty". It was not empty; it held four entries, none of which carried the one field the caller filtered on. The guard was `next((c for c in items if c.get("id")), None)`, so a full list of id-less entries reached the same "nothing found" branch as an absent list, and the message hard-coded one of the two causes. Acting on the message would have meant investigating why the list failed to populate — a question with no answer, because it populated correctly. Calling the producing function directly in a throwaway script resolved it in one step: four candidates, every `voice_id` None. The real defect was upstream and structural (a descriptive catalogue with no vendor ids, offered through an approval gate that could not change the outcome), and none of it was reachable from the error text.

**Suggested improvement:** Add an explicit step when a failure carries a specific stated cause: call the producing function in isolation and inspect what it actually returns before investigating the cause the message names. Treat any error whose text asserts a cause that the raising code did not distinguish — a falsy-filter collapsing "absent" and "present but unusable" into one branch — as an unverified claim. When the reproduction contradicts the message, fixing the message is part of the fix, not a cleanup.

**Principle:** An error message is a hypothesis written by someone who did not have the failing data. Where a guard collapses several distinct conditions into one branch, the message can only name one of them and will name the wrong one whenever the other occurs. Reproduce the call and look at the real values before spending any effort on the cause the text asserts.

### Observation 7: Audit for built-but-unreachable capability, and exclude dispatch-registered symbols first

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** A large agent-built application felt to its author like it was "not doing what I intend". Three separate defects turned out to be the same shape: a capability fully implemented and tested at the library layer, with no caller anywhere in the application.

**Skill:** code-review-and-quality
**Type:** open-source
**Phase/Area:** Auditing a codebase produced largely by agents

**Issue:** Agent-written code is unusually prone to a specific defect: a module is built to a good standard, tested thoroughly, committed with a coherent rationale — and never wired to anything. Each piece passes review in isolation because nothing is wrong with it; the defect is the absent edge between it and the rest of the system, which no file-scoped review can see. Three instances were confirmed here: a 963-line visual style with 655 lines of tests, imported only by its test; a publishing OAuth flow whose two entry points were never called, so the publish stage could only ever succeed in mock mode; and a footage-ingest lane referenced only from tests. The codebase's own history showed the author had already caught a fourth instance by hand, meaning this recurs and is not a one-off. A cheap static sweep — public symbols whose name appears nowhere outside their defining module — surfaced all of them in one pass. The sweep's first version was badly wrong, reporting pipeline stages as unreachable when they are registered by decorator and dispatched by string, which would have been a confident false alarm had it been reported unverified.

**Suggested improvement:** Add a reachability sweep to the review of any large or agent-generated codebase: list public symbols not referenced outside their own module, then subtract every indirection the project actually uses before reporting anything — decorator registries, `__all__` exports, string dispatch tables, subclass overrides of framework hooks, and plugin entry points. Confirm each survivor by tracing one concrete call path by hand. Report survivors ranked by the size of the capability stranded, not by symbol count.

**Principle:** In a codebase assembled incrementally by agents, the likeliest serious defect is not broken code but unreachable code — each part correct, the edge between them never built. Reachability is a whole-program property and is invisible to file-scoped review, so it needs its own explicit pass. Any automated sweep for it must first subtract the project's indirection mechanisms, or it will confidently report the framework's own dispatch as dead code.

### Observation 8: Prefer the cheapest evidence that answers the question, and check what the subject already publishes

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** An application needed to learn a reference video's structure in order to reproduce its format. Its implementation downloaded and decoded the video, which failed against a datacenter IP block.

**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Choosing a measurement method before implementing one

**Issue:** The measurement path was built as full media acquisition and frame analysis — expensive, slow, dependent on a fetch that a platform can refuse, and it did refuse. Considerable effort went into working around the block (alternate extractor clients, format selectors, cookie advice the application had no mechanism to honour) before checking whether the quantity being measured was published directly. It was: the creator lists chapter timestamps in the video description, which yields the segment count and every segment boundary exactly, free, from a metadata call. Two videos read this way gave a complete structural profile — eight segments each, boundaries to the second, no cold open — that the decode path had never once produced. Worse, the answer this cheap path gives is strictly better: chapter marks are the creator's own declaration of where segments begin, whereas frame analysis infers boundaries and can be wrong. The expensive method was not merely a costlier route to the same answer, it was a less reliable one.

**Suggested improvement:** Before building or debugging an expensive measurement path, enumerate what the subject already publishes about itself — metadata, descriptions, chapter marks, sitemaps, feeds, declared schemas — and check whether any of it answers the question directly. Where a cheap declarative source exists, make it the primary path and the expensive inference the fallback for subjects that lack it. When an error message advises a remedy (\"supply cookies\"), verify the codebase actually implements a way to supply it before treating that as the route forward.

**Principle:** Reach for the cheapest evidence that answers the question, and check what the subject declares about itself before inferring it. A declared value is usually both cheaper and more authoritative than a measured one; time spent unblocking an expensive inference path is wasted when the answer is published in plain text. Effort spent circumventing a refusal should first be spent asking whether the refused resource was needed at all.

### Observation 9: Read the project's own design record before proposing a visual direction

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Systematising the front end of an application whose author felt it looked amateur. A design skill was loaded that asks for a distinctive, opinionated visual direction and warns against defaulting to familiar looks.

**Skill:** frontend-design
**Type:** open-source
**Phase/Area:** Establishing the brief before brainstorming a direction

**Issue:** The skill's process starts with brainstorming a palette and typeface pairing. Applied literally here it would have produced the wrong work twice over. The stylesheet already carried a written rationale for its palette, and — critically — a stated engineering reason for its type: no webfont, because the import is a network round-trip on every launch of an application whose purpose is running offline. A brainstormed "characterful display face" would have violated a documented constraint that had nothing to do with taste. Meanwhile the actual defect was invisible to a direction-setting exercise: 23 distinct font sizes including seven half-pixel values, 29 spacing values, and no motion scale. The design was not under-directed, it was un-systematised, and those call for opposite responses. The skill does say the brief's own words win where a direction is pinned — but it treats the brief as the user's prompt, when in a codebase with history the binding brief is often already written into the source as constraints and rationale.

**Suggested improvement:** Add a step before brainstorming: read the existing design record — stylesheet headers, token blocks, design docs, and any comment explaining why a choice was made — and treat documented constraints as part of the brief, ranking equal to the user's prompt. Then decide explicitly whether the work is direction-setting or systematising, and say which. Where a constraint forecloses an axis the skill would normally spend boldness on (no webfonts, a fixed palette, a required density), state what carries the design's character instead.

**Principle:** In a codebase with history, part of the brief is already written into the source. Constraints recorded as rationale are binding, and reading them first distinguishes a design that needs redirecting from one that needs systematising — a distinction worth making early, because treating the second as the first destroys sound work while leaving the real defect untouched.

### Observation 10: Render the artefact and look at it — a successful build is not evidence of a correct one

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Connecting a large, fully-tested rendering module that had no caller, and separately migrating a set of templates onto a design scale. Both changes produced output that passed every check.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Verifying work whose output is visual

**Issue:** Two defects in one session survived a green build, a green test suite, a clean linter and a plausible-looking file size, and both were obvious within two seconds of looking at the rendered result. A helper returning a dataclass was passed where a path was expected, so one compositing layer silently dropped out of every frame — the video still encoded, at very nearly the expected size, because the module's designed behaviour is to skip a layer it cannot source. And a page migrated onto a type scale rendered correctly while still carrying the structural defects the migration was supposed to be a step toward fixing: a two-column grid splitting evenly for content that was not evenly split, and the page's primary action styled as a secondary. In both cases the mechanical check confirmed the mechanical change and said nothing about whether the result was right. Extracting one frame, and taking one screenshot, found what neither the suite nor the size nor the diff could.

**Suggested improvement:** When a change produces something visual — a rendered frame, a composited video, a page, a chart, a document — add an explicit step that produces the artefact and inspects it, and treat that as part of the change rather than as optional confirmation. Do it before writing the summary, not after. Prefer inspecting the artefact to inspecting a proxy for it: a byte count, an exit code, or a passing assertion about structure can all be satisfied by output that is visibly wrong. Where degradation is designed in — a layer that skips, a fallback that substitutes — the proxy is especially weak, because the failure path is built to look like success.

**Principle:** For visual output, a successful build is evidence the code ran, not evidence it produced the right thing. Look at the artefact. This matters most in code designed to degrade gracefully, where the failure path is deliberately indistinguishable from the success path by every signal except the output itself.

### Observation 11: A workaround repeated in three places is evidence about the shared rule, not about the three places

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** A pass over an app's templates for control styling and action hierarchy, driven by screenshots rather than by reading the stylesheet.

**Skill:** code-review-and-quality
**Type:** open-source
**Phase/Area:** Deciding where a fix belongs

**Issue:** Three separate templates each carried `style="width:auto"` on a checkbox. Read one at a time, each looks like a reasonable local nudge and invites a local fix — tidy the inline style into a class, move on. Read together, they are a measurement of the shared rule: the stylesheet's text-field skin selected on the bare `input` tag, so it was landing on checkboxes too, and every page that rendered one had had to escape it by hand. The same session had a second instance of the pattern. A checkbox rendered as a bright white rectangle on a near-black page, and the obvious reading — "the accent colour is not set" — was half right; `accent-color` had been added and the box was still white, because that property only tints the *checked* fill. The real cause was one level up again: no `color-scheme: dark` on `:root`, which is also why the select popups and scrollbars were light. Both fixes were one declaration in the shared layer, and both were invisible from any single call site.

**Suggested improvement:** When about to apply a local override, first search for that same override elsewhere. Two occurrences is a coincidence worth noting; three is a finding about the shared rule, and the fix belongs there. Before writing the workaround, state what rule it is escaping and whether that rule should have applied here at all — a selector that is too broad, a default that is wrong, a base class doing two jobs. Where a symptom persists after the obvious targeted fix, treat the persistence as information: it usually means the cause sits one layer above where the fix was aimed.

**Principle:** Repeated local workarounds are a distributed bug report about a shared rule. Counting them costs one search and converts N scattered patches into one correct change — and the version of the defect nobody worked around yet is fixed at the same time, which the N patches would each have missed.

### Observation 12: A fixture that supplies the happy path hides the branch every new user takes

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Driving an application end to end by hand, in the state a fresh install is in, against a suite of 2,400 passing tests.

**Skill:** code-review-and-quality
**Type:** open-source
**Phase/Area:** Judging what a green suite actually covers

**Issue:** A pipeline refused to run past its fifth of fifteen stages on a newly created account, making two thirds of the product unreachable and contradicting what the app's own interface promised on the page the user starts from. Every relevant test passed, including one named for driving a run to completion. The cause was a shared fixture: it set an optional field that the real creation paths — the CLI and the web form — both leave empty, and a guard downstream refused only when that field was absent. So every end-to-end test drove the one configuration a new user never has, and the failure was reachable in about ninety seconds by hand and not at all by the suite. The same session found the mirror image: a second copy of the guard, in another module with different wording, which the first fix did not touch and which the by-hand run surfaced immediately.

**Suggested improvement:** When a shared fixture populates an optional field, check what the real creation paths do with it — if they leave it empty, the fixture is asserting a configuration the product may never be in, and at least one end-to-end test should be built from the constructor a user actually reaches rather than from the fixture. More generally: before trusting an end-to-end suite as coverage of "it works", run the thing by hand once from the state a new install is in. Treat "all tests pass" as evidence about the paths the fixtures describe, not about the paths users take. When a defect is found this way, search for other copies of the same guard before declaring it fixed — a rule worth stating once is usually stated twice.

**Principle:** Fixtures encode assumptions, and the most expensive ones are the fields they helpfully fill in. A suite can be green, thorough, and entirely about a configuration no user is in — so the first run should be done by hand, from the default state, before the suite is believed.

### Observation 13: A graceful fallback makes a broken wiring indistinguishable from a working one

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Connecting several measured-but-unread settings to the code that should act on them, in a codebase whose lookups are all written to degrade rather than raise.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Verifying that a newly connected path actually took effect

**Issue:** Three times in one session I wired a measurement to its consumer, ran the code, got a result with entirely plausible numbers, and had produced nothing. Each time the cause was a well-written fallback. A lookup documented as "never raises — a name from a newer build should give the quietest possible output rather than stopping work that has already been paid for" returned the default when handed a name from a *different vocabulary*, so the new path produced byte-identical output to the old one. The output's duration, size and structure were all correct; only the pixels differed, and they differed by being unchanged. The same shape appeared in a settings lookup that defaulted to "on" and a section matcher that fell back to a sibling alias — in the last case the live sample I was testing against happened to contain the sibling, so the code appeared to work for a reason unrelated to what I had written, and only a hand-built fixture exposed it.

**Suggested improvement:** When connecting a new path through a lookup that degrades rather than raises, assert on the *effect*, not on the call succeeding or on the shape of the result. Sample the output where the change should show — the pixels at the boundary, the field on the row, the branch in the log — and assert it differs from the unchanged case. Where two components use different vocabularies for the same concept, the mapping between them is the thing to test first, because a defaulting lookup will silently absorb every unmapped name. And treat a passing check against one live sample as untested until a second sample or a hand-built fixture agrees: a fallback can be satisfied by a coincidence in the data.

**Principle:** Graceful degradation is correct behaviour and it destroys the signal that tells you whether new code ran. The more carefully a lookup is written to never fail, the less its success proves — so a newly connected path must be verified by the difference it makes, never by the absence of an error.

### Observation 14: Check who calls it before you commit it, not after

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** A long autonomous session adding several modules to a codebase whose own documentation names "built but unreachable" as its most common defect.

**Skill:** code-review-and-quality
**Type:** open-source
**Phase/Area:** The moment work is declared finished

**Issue:** I shipped five new modules across one session. Four of them had no production caller at the moment I committed them — including in the commits whose messages quoted the project's rule about exactly this failure. Each was individually reasonable: the module was complete, tested against real data, and obviously about to be used by the next piece. The next piece was another module. Twice I caught it a commit later and wired it; once I caught three at the same time only because I finally ran a mechanical sweep — one grep per new module, asking who imports it, excluding the module itself and its tests. That sweep takes under a minute and would have caught every instance. The reason it kept happening is that "is this finished?" reads as a question about the code in front of you, and reachability is the one property that cannot be seen from there.

**Suggested improvement:** Before committing a new module, run an explicit reachability check: grep for its import across the production tree, excluding the file itself and the test directory, and confirm a real caller exists. If none does, either wire it in the same commit or say plainly in the message that it is unreachable and name the commit that will connect it. Add the check to the definition of done for new files, alongside tests passing — and treat a caller that is only a test as no caller at all. Where the codebase already names this defect, assume you are about to commit it rather than assuming you are the exception.

**Principle:** Reachability is invisible from inside the file being written, so it has to be checked from outside by a mechanical sweep rather than by judgement. Knowing a project's most common defect does not protect you from it; the sweep does, and it is cheap enough that there is no case for skipping it.

### Observation 15: Relaxing an over-strict filter can delete the intent it was protecting

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Fixing a planner that reused three images across eight shots while nine sat unused, in a codebase whose named failure mode is exactly that kind of repetition.

**Skill:** code-simplification
**Type:** open-source
**Phase/Area:** Fixing an over-constraint

**Issue:** A selection step filtered a pool down to one shape of asset, and on real data that left it cycling three items across eight slots with nine candidates untouched. The fix looked obvious: stop excluding, widen the pool, order it so the preferred shape comes first. Every item now reached the output and the repetition was gone. But the filter had been encoding two things at once — an exclusion, which was the bug, and a preference for what should come *first*, which was the point. With a cursor that carried across calls, ordering the pool only shifted the phase of a modulo cycle, so the preference decided nothing at all and the output opened on whatever the arithmetic happened to land on. The relaxation had quietly deleted the intent along with the defect, and it looked completely correct: the metric I had set out to fix was fixed. What caught it was writing the assertion for the surviving intent — "it still leads on the preferred shape" — and watching it fail.

**Suggested improvement:** When removing a constraint that turned out to be too strict, name what the constraint was *for* before deleting it, and write a separate assertion for that intent in the same change. A constraint usually encodes at least two things — what must not happen, and what should be preferred — and relaxing it addresses the first while silently dropping the second. If the intent cannot be restated as its own testable rule, that is the signal that the relaxation has removed a behaviour rather than a restriction. Assert on the intent, not only on the metric that prompted the fix.

**Principle:** An over-strict filter is doing two jobs, and loosening it only ever fixes one of them. The preference a constraint enforced has to be re-expressed explicitly, or it disappears in the fix and takes the design decision with it.

### Observation 16: Consult your own measurements before making the choice they already answer

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Building a compositing step whose design question had already been measured and written into a reference document in an earlier session of the same project.

**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Choosing between plausible implementations

**Issue:** I needed a background for a composited subject and picked the source that was nearest to hand — other images from the same page. It was defensible, it cost nothing, and it was wrong. Rendering one frame and *looking at it* showed why: those images were gameplay screenshots, so the finished shot carried a heads-up display along the bottom and a player avatar in the corner. The correct answer had been measured weeks earlier and written into this project's own reference document as a plain table of asset provenance — roughly seventy per cent sourced artwork against ten per cent generated background plates — with a paragraph explaining that generation is used only for the plate. I had written that table. I did not re-read it before choosing, because the choice felt like an implementation detail rather than a question the research had covered, and no test would ever have caught the difference.

**Suggested improvement:** When a project carries its own measured reference for a domain, re-read the relevant section at the moment of each design choice inside that domain, not only at the start of the work. Treat a decision that *feels* like a local implementation detail as the most likely place to have skipped the reference, because those are the choices made without looking anything up. And for anything whose output is visual or otherwise perceptual, render one and look at it before committing: the defect here was obvious in under a second by eye and invisible to every automated check, including the ones written specifically for that code path.

**Principle:** Research already done is only worth what it is re-read for. A measurement written down in an earlier session does not reach the decision it was made for unless it is deliberately consulted at that decision — and for perceptual output, looking at one artefact is a stronger check than any assertion about it.

### Observation 17: A fixture written by whoever wrote the matcher validates it against itself

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Testing a text-extraction module against twenty real inputs after it had passed a full suite of examples I had written myself.

**Skill:** test-driven-development
**Type:** open-source
**Phase/Area:** Choosing what a matcher is tested against

**Issue:** A module that pulls requests out of user-written text had a green suite of hand-written examples covering every pattern it matched. Pointed at twenty real inputs for the first time, one pass found three defects. The extractor required a word that half the real phrasings omit — every example I had invented happened to include it, because I wrote the examples while thinking about the pattern. A cleanup step stripped a token from both ends of a phrase, which is right at the front and wrong at the back, and it silently turned a real proper noun into something nobody had asked for and no search would find. And with nothing occurring twice, the summary reported that nothing had been asked for at all, to a reader whose users had just named three things — a false statement rather than a quiet one, on the module's single most important output. None of the three was subtle. All three were invisible to a suite whose inputs and whose matcher came out of the same head, in the same hour.

**Suggested improvement:** For any component that parses text people wrote — comments, queries, free-form fields, scraped prose — get real samples into the test suite before believing the hand-written ones, and paste them verbatim rather than tidying them. Twenty is enough to be worth more than fifty invented ones. Treat a suite whose fixtures were authored alongside the matcher as a consistency check on your own assumptions, not as evidence about the input domain. When real samples do arrive, read what the component *missed* as carefully as what it caught: the misses are where the assumption lives. And check the summary line the same way as the extraction — a report that says "nothing found" when the parser found things is a defect in the output nobody thinks to test.

**Principle:** A fixture and the code it exercises, written by the same person in the same sitting, share every assumption. Only inputs from outside that head can falsify them, so real samples are not a nice-to-have for a text matcher — they are the first test that carries any information.

### Observation 18: A wired path can still do nothing, and only counting the output shows it

**Status:** OPEN
**Date:** 2026-08-07
**Session context:** Connecting a planner to a renderer, where both had passing tests and the combination produced nothing.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Verifying an integration after both sides are connected

**Issue:** Two rules I had written, each correct alone, selected disjoint sets. One rationed an expensive treatment to a particular category of item; the other guaranteed that category always led with the one *kind* of item the treatment cannot be applied to. So the plan reported two items marked for the treatment, the renderer silently declined both, and the finished output had none. Nothing errored. The planner's tests passed — it marked what it was told to mark. The renderer's tests passed — it handled a markable item correctly. The defect existed only in the intersection, and neither module could see it, because each was individually behaving exactly as specified. I found it by running both stages against real input and *counting the files that came out*: sixteen planned, two marked, zero produced. Reading either module's code, or its logs, or its test suite, would not have surfaced it, and a reachability sweep would have called the path connected — because it was.

**Suggested improvement:** After connecting two stages, do not stop at "the call happens". Run the pair on real input and count the artifacts each promised: N planned versus N produced, and compare the two numbers explicitly. Where one stage marks items for special handling and another consumes those marks, check that the selection criteria on both sides can actually overlap — write the intersection down as a sentence and see whether it is empty. And when a downstream stage silently degrades an item it cannot handle, that degradation should be counted and logged, not just performed; a stage that quietly returns the ordinary result for an unhandleable input is a stage that makes this class of defect invisible by design.

**Principle:** Reachability is not effect. Two components can be connected, individually correct, individually tested, and jointly useless — when their selection criteria do not intersect. Only an end-to-end run that counts what came out against what was promised can tell the difference, so that count is the integration test, not the call.

### Observation 19: Measure the effect without the correction, or you will credit the wrong part

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Adding a small geometric correction to a visual effect, and finding my model of which part did the work was exactly inverted.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Attributing an effect to the component that causes it

**Issue:** I built an effect in two parts: a primitive transform, and a correction that moved its pivot to the physically right place. My mental model was that the primitive produced the effect and the correction refined it — so I wrote it that way, documented it that way, and would have shipped it that way. Measuring the primitive *alone* showed it produced essentially nothing: the two ends of the object moved in opposite directions by similar small amounts and cancelled, landing within noise of the do-nothing baseline. The correction was not a refinement, it was the entire effect. The numbers were unambiguous once separated — barely above the floor without it, four times the floor with it — and completely invisible while both ran together, because the combined result looked right and "looks right" is exactly what stops the investigation. The same session had already produced a measurement I could not read at all because a second, larger motion was running at the same time and swamping it; I only got a usable number by turning that one off.

**Suggested improvement:** When an effect is built from a primitive plus a correction, measure three configurations, not one: neither, primitive only, and both. The primitive-only run is the one that tells you where the effect actually comes from, and it is the one nobody runs because the finished version already looks correct. Where two effects are active at once, disable one before measuring the other — a small signal under a large one is not a weak measurement, it is no measurement. And when the ablation contradicts your description of the mechanism, rewrite the description: a comment that credits the wrong component is worse than no comment, because it tells the next person which part is safe to simplify away.

**Principle:** "It looks right" attributes an outcome to whatever you believe caused it. Only removing a component tells you what it contributed, and the component you assumed was cosmetic is as likely to be load-bearing as the reverse.

### Observation 20: A negative result is a deliverable, and belongs in the code

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Looking for a signal in source data that would let a feature choose automatically, and finding the data does not carry one.

**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** Deciding whether a heuristic is supportable

**Issue:** I wanted a feature to select its own behaviour from the source material rather than being told, which would have been the better product. Before building the selector I checked whether the signal was there: I sampled nine real documents across three sources and counted. Three contained any relevant term at all, and each contained it exactly once — one occurrence in thirteen thousand characters in the strongest case. That is a passing word, not a signal, and a selector built on it would have been the system inventing facts about somebody else's material while looking like inference. So I built the feature as an explicit choice instead, and wrote the counts and the sample size into the module's docstring. The temptation both ways was strong: to build the clever version because a threshold could be tuned until the sample "worked", and to drop the finding silently once I had decided against it. The second is the more expensive one — without the note, the next person has the same good idea, and there is nothing in the code to tell them it was checked and how.

**Suggested improvement:** Before building a heuristic that infers behaviour from data, sample the real data and count — a dozen instances is usually enough to tell a signal from a coincidence. If the count does not support it, do not build it, and do not delete the measurement: write the numbers and the sample size into the module where the heuristic would have gone, with enough specificity that somebody could repeat it. Be suspicious of a threshold you had to tune to make a sample pass; that is the shape of fitting to noise. And treat "I checked and it is not there" as a result to record rather than a dead end to hide, because the alternative is the same investigation done again by someone with less context.

**Principle:** Checking whether the data supports a heuristic is real work whether or not the answer is yes. A negative result left out of the code is an invitation to redo it — and a heuristic built on a signal that is not there is worse than the explicit choice it replaced, because it fails invisibly and looks like intelligence.

### Observation 21: A capability claim can be true of the code and false of the deployment

**Status:** OPEN
**Date:** 2026-08-15
**Session context:** Reviewing an application's own copy and finding it promising a feature that cannot work where the application is actually running.

**Skill:** documentation-and-adrs
**Type:** open-source
**Phase/Area:** Interface copy that describes what the software can do

**Issue:** Three separate surfaces told the user that a particular operation needed no credentials, because the software falls back to an unauthenticated route. That statement was accurate about the code and false about the machine: the upstream service refuses that route from datacentre addresses, so on any hosted install the feature was present, correctly implemented, and refused every time. The failure mode was the worst kind — a fetch that returned nothing, no error, and copy on the same screen insisting no setup was required. The user's only available conclusion was that they had pasted the wrong thing, which was the one thing that was fine. What made this hard to see is that the copy is *right* in the environment where it was written, so reading the code or running it locally confirms it. I only caught it because I had independently hit the block earlier in the session and recognised the claim when I read it back.

**Suggested improvement:** When copy states that something works, ask where — a claim about capability is implicitly a claim about the environment, and those diverge whenever the software ships to somewhere other than a developer's machine. For any path that depends on an external service tolerating you (unauthenticated scraping, rate-limited endpoints, IP-reputation-sensitive APIs), write the caveat as a *condition* alongside the claim: what to do if nothing comes back, and both fixes. Phrase it conditionally rather than as a prediction, because the code cannot know where it is running and the same build genuinely works elsewhere. And keep the sentence in the module that owns the path rather than on each page: I found three surfaces describing one failure, which is exactly the arrangement where two of them keep saying something the third has stopped saying.

**Principle:** "It works" is a statement about an environment, not about code. Copy written where it is true will be shipped where it is not, and the resulting failure looks like user error — so the environment-dependence belongs beside the claim, phrased as a condition.

### Observation 22: Sweep the rendered output for internal identifiers, not the source

**Status:** OPEN
**Date:** 2026-08-15
**Session context:** Looking for internal names leaking into a user interface, across pages whose templates I had not read.

**Skill:** frontend-ui-engineering
**Type:** open-source
**Phase/Area:** Reviewing an interface for polish

**Issue:** Enum values, tool names and pipeline slugs were reaching users verbatim — machine identifiers with underscores, sitting in tables and prose beside sentences in plain English. I had already fixed several by reading templates, which found the ones I happened to look at. What found the rest was mechanical: render each page in a browser, take `document.body.innerText`, and regex it for `snake_case`. That is a two-line check, it covers every page including the ones nobody thought to inspect, and it reads what the user sees rather than what the template says — so it catches identifiers that arrive through data, through JavaScript, or through a helper three layers down, none of which a source grep for the template would find. It also produced a clean signal on pages that were fine, which is what let me stop looking. One hit it returned was on a page I would not have reviewed at all.

**Suggested improvement:** Add a rendered-output sweep to interface review: load each page, extract the visible text, and search it for the shapes internal names take — `snake_case`, `SCREAMING_CASE`, `camelCase` in prose, bare enum values, class or module names. Do it against the running application rather than the templates, because the leak is often in data rather than markup. Then decide each hit deliberately rather than renaming on sight: an identifier is correct where the subject *is* the identifier — a tool-call log should name the tool — and wrong where the subject is the product. Where you do translate, put the mapping in one place and have the live-updating parts of the page use the same one, or the page will render the friendly word and then replace it with the raw one on its next refresh.

**Principle:** What leaks into an interface is visible in the output and often invisible in the source. Grep what the user sees.

### Observation 23: Render the intermediate representation, not just the output

**Status:** OPEN
**Date:** 2026-08-15
**Session context:** Building a shape detector whose output feeds a visual effect, where two plausible implementations were both wrong on real inputs.

**Skill:** debugging-and-error-recovery
**Type:** open-source
**Phase/Area:** Verifying a computed intermediate before anything consumes it

**Issue:** I needed to identify which pixels of a shape were its appendages. The first implementation walked the shape's skeleton from each free end back to the first junction — a standard, correct-sounding decomposition. Its summary statistics looked healthy: it reported three regions on one input, one on another, plausible sizes. Only when I tinted each detected region on the image and looked did I see it had found a single *finger* of a claw and missed both arms entirely, because an arm ending in three fingers has the fingers as branches and the arm as an internal segment. The second implementation — threshold the shape by thickness — also produced believable counts, and the picture showed why it was wrong too: every silhouette has a thin rim, so the rim connected both arms into one region. Neither failure was visible in the numbers. Both were obvious in about a second once drawn. The eventual method was found by testing the *third* idea against the picture before building anything on it.

**Suggested improvement:** When a step computes a structured intermediate — a segmentation, a clustering, a parse tree, a matched set — render it before writing the code that consumes it, and render it *on real inputs* rather than on a fixture built to match your mental model. For anything spatial, tint the regions and overlay the anchors on the source image; the check costs a few lines and it is the only view in which "found three regions" and "found the right three regions" are different statements. Summary counts are compatible with almost any wrong answer, so treat them as a smoke test rather than as evidence. And when the picture contradicts the method, prefer changing the method to tuning it: both wrong versions here had parameters that could be adjusted, and no setting of them would have been right.

**Principle:** A count tells you the algorithm ran. A picture tells you what it found. For a structured intermediate those are different questions, and only the second one is the one you care about.

### Observation 24: Building on an assumption is what finally tests it

**Status:** OPEN
**Date:** 2026-08-15
**Session context:** Starting a feature that depended on inputs being a particular kind of thing, and discovering that half of them were not.

**Skill:** doubt-driven-development
**Type:** open-source
**Phase/Area:** Beginning work that rests on an earlier classification

**Issue:** A pipeline I had built classified its inputs into two kinds and treated them differently. The classifier used a cheap proxy available before the data was fetched, and I had noted in its own docstring that the proxy was a heuristic. It shipped, the tests passed, and the outputs were plausible. Weeks later I began a feature that needed one of those kinds specifically — and the first thing that feature does is examine the data closely. Within minutes it was obvious that a third of the inputs classified as kind A were kind B: the proxy separated them by a property both kinds happen to share. Rendering one showed the consequence immediately, and it was ugly and had been shipping the whole time. The new feature did not cause the bug or reveal it by accident; it revealed it because building on a classification is the first activity that actually depends on the classification being right. Everything before that had only depended on it being *plausible*.

**Suggested improvement:** When starting work that rests on an existing classification, inference, or heuristic — especially one you wrote and labelled as approximate — spend the first few minutes verifying it on real data rather than assuming the earlier self did. Treat a docstring that says "this is a heuristic" as an open ticket rather than as a disclosure that settles the matter. And when the new work needs to look closely at data an earlier stage only glanced at, run that closer look across the whole input set first: the cheap proxy is usually right on the examples that motivated it and wrong on a class nobody sampled. Fix the classification before building on it — a feature layered on a wrong split inherits the wrongness and makes it harder to see.

**Principle:** A heuristic is only tested by something that depends on it being correct rather than merely reasonable. Until then it is an assumption with a passing test suite, and the moment you start building on it is the cheapest moment you will ever have to check it.
