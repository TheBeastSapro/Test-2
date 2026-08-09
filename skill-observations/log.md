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

### Observation 10: Metered/rate-limited tools need a budget check before the plan is built, not at first call

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Frame-level teardown of a competitor YouTube video. The task plan was built entirely around a metered multimodal tool with a documented "use 5-7 calls" budget.
**Skill:** analyse
**Type:** open-source
**Phase/Area:** Tool selection / pre-flight

**Issue:** The assigned plan allocated 5-7 calls to a metered tool. The very first call timed out server-side after 60s, and the second returned "RATE LIMIT EXCEEDED — 5/5 calls used in the last 24 hours": four calls had already been consumed by other sessions before this one started, and the timed-out call consumed the fifth while returning nothing. The budget was therefore zero before any work began, but this was only discoverable by spending the last unit of it. A parallel agent independently burned wall-clock rediscovering the same wall. Compounding it, the timeout appears related to prompt density — a very long multi-part prompt produced a generation that exceeded the transport's fixed 60s limit — so the "ask many questions per call to save budget" strategy actively increased the chance of losing a call to a timeout and getting nothing back.

**Suggested improvement:** In any workflow built around a metered or rate-limited tool, add a pre-flight step: make one minimal, cheap probe call to establish remaining budget BEFORE committing to a call plan, and treat shared/pooled quota as the default assumption rather than assuming the session owns the full allowance. Pair this with a per-call size rule: when a tool has a fixed transport timeout, cap the output a single call is asked to produce, because a timed-out call typically still decrements quota while returning nothing. Where a workflow's value depends on a metered tool, name the fallback path in the workflow itself so it does not have to be invented under pressure.

**Principle:** Budget is a precondition, not a runtime discovery. Verify remaining quota with a cheap probe before designing a plan around a metered tool, and size individual calls so a transport timeout cannot convert a spent unit into zero returned information.

### Observation 11: When a primary capability is unavailable, look for a lower-fidelity source of the same underlying signal before downgrading the deliverable

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Visual teardown of a video after the multimodal video tool's quota was exhausted and the direct media download was blocked by the platform's bot detection.
**Skill:** analyse
**Type:** open-source
**Phase/Area:** Evidence gathering / fallbacks

**Issue:** With the multimodal tool exhausted, the instinct — and the explicit mid-task steering from the coordinator — was to fall back to text-only sources and label all visual questions as undetermined. That would have answered almost none of the actual question, which was entirely about visual grammar. A third path existed: the platform publishes a low-resolution storyboard track (a sprite sheet of periodic frames) as ordinary image assets on a different host, which was neither quota-metered nor blocked. Fetching it yielded 120 real frames spanning 100% of the runtime at fixed intervals, which could then be measured numerically — background colour sampling, layout classification, element bounding boxes, per-section palette extraction — and read directly. Coverage of the whole runtime at coarse time resolution turned out to be *better* for the questions asked (what percentage of runtime uses layout X, what is the per-section palette, what is the structural grammar) than a single high-resolution window would have been, even though it cannot answer fine-timing questions.

**Suggested improvement:** In the evidence-gathering phase, before declaring a visual question unanswerable, enumerate the *adjacent artifacts* the platform exposes for the same media — periodic frame/storyboard tracks, poster and preview images, chapter thumbnails, generated previews. Record explicitly what each fallback can and cannot support: coarse-interval frames settle proportions, structure, palette and layout, but cannot settle sub-interval cut counts, animation direction and duration, or audio. Note also that low-fidelity frames become high-value evidence when measured programmatically rather than only eyeballed — exact colours, geometry and ratios survive downsampling even when text and fine detail do not.

**Principle:** A blocked primary capability is not the same as a blocked signal. Enumerate lower-fidelity carriers of the same signal before downgrading the deliverable, and state precisely which sub-questions the substitute can and cannot answer instead of applying one confidence label to everything.

### Observation 12: Stored "measured" values need provenance and a re-verification pass before being promoted to config

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Re-deriving a competitor's visual style; the repo already held a profile whose header asserted every number came from watching the real video end to end.
**Skill:** New skill candidate: measurement-provenance
**Type:** open-source
**Phase/Area:** Recording measured findings for downstream machine consumption

**Issue:** A stored profile presented as fully measured contained several values that direct re-measurement contradicted: a background asserted as pure white measured as a near-white off-value on every sampled frame; a roster asserted as 8 cells is 12; an accent list of 5 colours is actually 12, one per section; a layout element described in a way that implied a plain shape is a distinctly different shape. Each individually is small; collectively they would have been wrong renderer config, and the file's own framing ("every number came from watching a real video") discouraged re-checking. The values that proved wrong share a signature: they are the ones a viewer would *estimate* from memory of watching (counts of things, "it looked white") rather than ones that force precision. The values that held up were the structural and behavioural ones.

**Suggested improvement:** When recording measurements that will be consumed as configuration, tag each value with how it was obtained — sampled/computed, counted from a specific frame or timestamp, or estimated by eye — and carry that tag into the config file, not just the prose document. Flag eye-estimated counts and colours as provisional by default, since those are the classes that fail. Before any stored profile is used as authoritative config, run a cheap re-verification pass on exactly those provisional fields. A blanket assertion that a document is "measured" should be treated as a claim about the document's intent, not about any individual value in it.

**Principle:** Provenance belongs on the value, not on the document. A file-level claim of "measured" cannot distinguish computed values from eye estimates, and it is the eye estimates — counts and colours — that quietly become wrong configuration.

### Observation 13: Segmentation quality must be judged by anatomy-region probes, never by global alpha statistics

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Evaluating automatic background-removal models for creature artwork; a prior agent had ranked candidates on global transparent/opaque/soft-edge percentages
**Skill:** New skill candidate: matte-quality-evaluation
**Type:** open-source
**Phase/Area:** Choosing an evaluation metric for a segmentation or extraction output

**Issue:** The candidate with the best-looking global alpha statistics (97.84% transparent, tight bounding box) was in fact the worst matte: it had deleted both of the subject's limbs. Amputation and background bleed move global percentages in OPPOSITE directions, so a single global number cannot separate "clean" from "mutilated" — a tight bounding box reads as precision when it is actually loss. The fix was to hand-place a dozen small probe boxes on the source image, each visually confirmed to sit on a specific anatomical feature (each limb, each extremity) or on unambiguous background, and to report per-region pass/fail. That immediately exposed failures the global numbers had scored as wins, including one region (a gap enclosed by the subject) that every global metric ignored.

**Suggested improvement:** For any task that evaluates a spatial mask, mattes, crop, or region-extraction output, require a per-region probe set derived from the source before any ranking, and forbid ranking on aggregate coverage numbers alone. Probe boxes must be visually verified by rendering them onto a contrast-enhanced copy of the source and looking at it, because a probe placed on the wrong pixels silently invalidates every subsequent comparison. Include at least one probe on an enclosed background region (a gap the subject surrounds), which is the case aggregate metrics are structurally blind to.

**Principle:** An aggregate score over a spatial output cannot distinguish losing the signal from keeping the noise, because both errors move the aggregate the same way. Evaluate spatial outputs at the locations that carry the meaning, and verify the locations by eye before trusting anything measured at them.

### Observation 14: A benchmark must label which inputs are pathological, or one hard case silently picks the winner

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Comparing background-removal models across two source images, one of which is an extreme worst case
**Skill:** New skill candidate: matte-quality-evaluation
**Type:** open-source
**Phase/Area:** Selecting and reporting on a test corpus

**Issue:** Two test inputs were given equal weight in a model comparison. One was a typical, well-separated subject; the other was an extreme outlier where part of the subject is genuinely unrecoverable by any method. Every candidate scored poorly on the outlier, which compressed the spread between them and made a strong general-purpose winner look barely adequate. Worse, it framed the whole exercise as a tooling failure when the real finding was that the outlier is not a valid input for this treatment at all — no tool choice would ever fix it. The correct output was two conclusions, not one: a winner ranked on the representative case, and a separate admission-control rule that keeps inputs like the outlier out of the pipeline.

**Suggested improvement:** When assembling a benchmark corpus, label each input as typical or pathological BEFORE running any candidate, and report per-input results separately rather than as a pooled score. Where an input turns out to be pathological, the deliverable should include an admission-control rule — how to recognise such inputs cheaply up front — as a first-class result alongside the ranking. Never let a single hard case decide a ranking, and never report a pooled average that hides which input drove it.

**Principle:** A pathological input tests the boundary of the problem, not the quality of the solution. Separate "which candidate is best" from "which inputs belong in this pipeline at all" — pooling them produces a ranking that is both pessimistic and unactionable.

### Observation 15: Proxy failure classes must be checked against helper services' own logs, not just the primary tool's output

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Unblocking yt-dlp YouTube downloads behind an agent egress proxy
**Skill:** New skill candidate: proxied-environment-debugging
**Type:** open-source
**Phase/Area:** Diagnosis of network failures in multi-process toolchains

**Issue:** yt-dlp reported only a generic `PoTokenProviderError ... HTTPError 500` from its PO token provider plugin. The real cause was visible only in the *provider server's* own stdout log: a `405 Method Not Allowed` from the egress proxy, which the environment's README explicitly documents as "axios older than 1.16.1". The primary tool's error message flattened a specific, documented, fixable proxy failure class into an opaque upstream 500. Reading the helper process's log turned an apparent dead end into a one-line `npm install axios@latest` fix.

**Suggested improvement:** When a toolchain spans multiple processes (primary CLI + helper daemon/sidecar), and the primary reports a generic upstream 5xx, always read the helper's own log before concluding the approach failed. Additionally, when an environment ships a README enumerating proxy failure classes, grep that README for the *helper's* observed status code, not just the primary tool's.

**Principle:** An error surfaced by process A about process B is a summary, not a diagnosis. In multi-process failures, the authoritative error lives in the log of the process that actually made the failing request — always read it before declaring an approach unworkable.

### Observation 16: Verify whether a gatekeeper error is local-policy or remote before attributing it to the remote service

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Diagnosing HTTP 403 on a CDN behind an agent egress proxy
**Skill:** New skill candidate: proxied-environment-debugging
**Type:** open-source
**Phase/Area:** Root-cause attribution

**Issue:** A 403 was assumed to be remote bot detection. In a proxied environment a 403 can equally be the *egress proxy's* policy denial, and the two demand opposite responses (work the remote problem vs. report the blocked host and stop). The cheap discriminating test — a direct CONNECT to the CDN host, observing whether the tunnel establishes and whether the body is a genuine remote error page — was not run until late, after substantial effort had gone into remote-side fixes. It took one curl to settle and confirmed the remote attribution.

**Suggested improvement:** Add an early, explicit disambiguation step to any network-failure workflow in a proxied environment: before investing in remote-side workarounds, issue a direct request to the failing host and classify the response as (a) proxy tunnel refused/denied, or (b) tunnel established with a genuine remote response. Record which one, then proceed. Cost is one command; it can invalidate an entire line of work.

**Principle:** When two independent gatekeepers can emit the same status code, attribution must be established by test before it is used as a premise. Run the cheapest discriminating experiment first — a wrong premise about *who* rejected you invalidates every subsequent step.

### Observation 17: Enumerate every client/variant of an API before accepting the first response's capability ceiling

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Extracting a YouTube storyboard sprite-sheet track to analyse a video frame-by-frame without a metered multimodal tool
**Skill:** New skill candidate: media-asset-extraction
**Type:** open-source
**Phase/Area:** Source discovery

**Issue:** The same metadata endpoint returned materially different asset inventories depending on which client identity was requested. Three of four working client variants exposed a maximum storyboard tile of 160x90; only the fourth exposed a 320x180 level — a 4x pixel-area difference that decided whether on-screen text could be read at all. Had the first successful client's response been treated as the capability ceiling, the entire analysis would have been done at unusable resolution and several findings (label text, box border presence, corner radius) would have been impossible.

**Suggested improvement:** In any asset-extraction workflow that supports multiple client/user-agent/API-version identities, enumerate ALL of them and diff the returned asset inventories before selecting a source. Treat the union, not the first success, as the available set. Log which variant produced the richest inventory so the next run starts there.

**Principle:** A capability ceiling observed through one client identity is a property of that identity, not of the service. When identity is a free parameter, sweep it before concluding what is available.

### Observation 18: Test the physical/legibility explanation for a stylistic rule before adopting a semantic one

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Deriving the rule that decides which background colour a reference video uses for its non-scene cards
**Skill:** New skill candidate: reference-teardown
**Type:** open-source
**Phase/Area:** Rule inference from samples

**Issue:** A prior pass over ~11% of the runtime produced a semantic trigger rule — one content class routes to a black card, another to a white card — and encoded it as a programmable content-to-canvas mapping. Full-runtime measurement showed the mapping was an artefact of the sample: the identical content classes appeared on BOTH canvas colours elsewhere. The actual predictor was mechanical — subject luminance. Pale subjects went on the dark canvas, dark subjects on the light one, with clean separation on a measured luminance statistic. The semantic rule was a coincidence of which creature happened to occupy the sampled minute.

**Suggested improvement:** When inferring a production rule from observed samples, explicitly generate and test the boring physical hypothesis (contrast, legibility, fit, safe area, file constraints) alongside the interesting semantic one, and prefer the physical one unless the semantic one survives a sample that varies the physical variable independently. Note in the writeup which alternatives were tested and rejected.

**Principle:** Rules inferred from a narrow sample tend to encode the sample's incidental correlations as intent. Before attributing a design choice to meaning, check whether a mechanical constraint predicts it — mechanical explanations generalise, semantic ones invented from small samples usually do not.

### Observation 19: When several installs of a tool coexist, verify which one is executing before trusting any capability result

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Installing a yt-dlp plugin to unblock media downloads
**Skill:** New skill candidate: proxied-environment-debugging
**Type:** open-source
**Phase/Area:** Environment setup / capability verification

**Issue:** Two installs of the same CLI were present: the one first on `PATH` (a `uv`-managed tool install) and a second under system site-packages. `pip install <plugin>` placed the plugin where only the *second* could see it. Running the `PATH` binary reported `Plugin directories: none` and would have silently produced a false negative — "the plugin approach doesn't work" — when in fact the plugin was installed correctly and simply invisible to the binary being invoked. Separately, the same tool's JS-runtime detection ignored `PATH` entirely (it probed the Python scripts directory first and returned on first hit), so a newer runtime that *was* installed kept being reported as an unsupported older version until it was named by absolute path.

**Suggested improvement:** Before concluding that an installed component doesn't work, run the tool's own capability/verbose output and confirm it lists the component as loaded (e.g. a "plugin directories" or "providers" line). Prefer absolute paths to the specific install being configured. Treat `which <tool>` as one candidate among several, not as the answer — enumerate installs when a plugin or extension is involved.

**Principle:** Installing a component and the tool *loading* it are two different facts. Verify the second directly from the tool's own introspection output; otherwise a packaging mismatch masquerades as a failed approach and closes off a line of work that was actually working.

### Observation 20: Define the success signal before running a retry experiment, or the experiment measures the wrong thing

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Testing whether retrying a request could defeat a rotating-egress-IP mismatch
**Skill:** New skill candidate: proxied-environment-debugging
**Type:** open-source
**Phase/Area:** Experiment design

**Issue:** A 25-iteration retry experiment was run to test a hypothesis, but the request client was not configured to follow redirects. Every iteration recorded HTTP 302 — an intermediate hop — which is neither the success nor the failure state. The whole run produced no usable evidence and had to be repeated, and the repeat run was itself lost to a rate limit triggered partly by the wasted first run. The experiment also issued an extra diagnostic request per iteration, doubling the request volume against a rate-limited endpoint for information that was already known.

**Suggested improvement:** Before running any loop-based experiment, write down explicitly what the success observation looks like and what the failure observation looks like, and confirm the measurement actually distinguishes them on a single trial run first. Then run the loop. Also budget requests against rate-limited endpoints: strip per-iteration diagnostics that don't change the conclusion.

**Principle:** An experiment is only worth its request budget if its measurement can distinguish the outcomes it was designed to separate. Validate the measurement on one trial before spending the budget on many — especially against rate-limited resources, where a wasted run also degrades the conditions for the retry.

### Observation 21: Check the pipeline stage's fixed internal resolution before optimising the stage in front of it

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Deciding whether to enlarge an image before or after running it through a model
**Skill:** New skill candidate: matte-quality-evaluation
**Type:** open-source
**Phase/Area:** Ordering stages in a processing chain

**Issue:** A plausible and expensive plan was to enlarge the input before the analysis stage, on the reasoning that more pixels would give the model more to work with. Reading the stage's source showed it resizes every input to a fixed square before inference, so the extra pixels were discarded and the enlargement could not possibly add information. The measurement then confirmed something stronger than "no benefit": doing it first made the result WORSE, because the enlarger denoises, and denoising removed the faint low-contrast signal the analysis stage had been relying on. Ordering the other way also allowed cropping to the region of interest first, which cut the enlarger's work by up to 23x. Twenty lines of reading the dependency's source settled a question that would otherwise have been argued from intuition.

**Suggested improvement:** Before ordering or optimising stages in a processing chain, read each stage's source to find its fixed internal working resolution or other normalisation. Treat any stage that normalises its input as an information ceiling: no upstream stage can raise the information that reaches it, and upstream transforms can only remove signal. State the ceiling explicitly in the analysis, then measure to check for the second-order harm rather than assuming neutrality.

**Principle:** A stage that normalises its input caps what every stage before it can contribute. Find that cap by reading the code, not by benchmarking around it, and remember that an upstream transform which cannot add information can still destroy some.

### Observation 22: A metric that cannot go wrong is a baseline, not a winner

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Ranking image enlargement methods on a reconstruct-the-original fidelity test
**Skill:** New skill candidate: matte-quality-evaluation
**Type:** open-source
**Phase/Area:** Interpreting a reconstruction or round-trip benchmark

**Issue:** A round-trip test (degrade a known input, restore it, compare to the original) ranked the simplest non-generative method first on every fidelity metric. Reported as a ranking that would have been a false conclusion: the simple method wins that test by construction, because it cannot add anything and therefore cannot add anything wrong. It also fails the actual job, producing a visibly unusable result at the target size. The test's real value was a DIFFERENT number in the same run: a high-frequency energy ratio against the original, where above 1.0 means the method emitted more fine detail than the truth contains. That single ratio separated the faithful candidates from the one that was silently restyling the content, and it was confirmed by looking at the outputs, where the offending model had converted photographs into line art.

**Suggested improvement:** When designing a reconstruction benchmark, identify up front which candidates win it trivially and label them as the floor rather than entering them in the ranking. Pair every similarity metric with an at-least-one excess metric that detects output the input did not contain, since similarity scores punish invention and conservatism identically. Always confirm the excess metric against the rendered output, because the mechanism of invention (added texture, restyling, sharpened edges) determines whether it matters.

**Principle:** In a reconstruction benchmark, the method that cannot invent always scores best and is usually not the answer. Rank on what a candidate ADDS that the ground truth does not have, not only on how close it stays.

### Observation 23: A spec that names an artifact's fields and its consumers can still name no producer

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Building a well-specified ingestion stage from a written build packet
**Skill:** New skill candidate: spec-implementation-audit
**Type:** open-source
**Phase/Area:** Reading a specification before implementing it

**Issue:** The build packet described a data file in two separate places: a repo-layout table said the file holds "sections with time ranges", and a later section required those same time ranges as an argument to every lookup, warning that omitting them causes a specific class of wrong result. But the packet's own code sketch for the tool that writes that file never produced the time-range fields, and no other specified tool produced them either. The field had two documented consumers and zero producers. Nothing in the packet flagged this: each section was internally consistent, and the gap was only visible by tracking one field across three sections that were written at different times.

**Suggested improvement:** Before implementing from a spec, build a field-level producer/consumer table for every data artifact the spec defines: for each field, which specified step writes it and which read it. Fields with consumers but no producer are the missing work; fields with producers but no consumers are dead weight worth questioning. Do this as a reading pass, not during implementation, because in the middle of writing a tool the natural move is to invent the missing field silently and never report the gap.

**Principle:** Specs are usually consistent within a section and incomplete across sections. The cheapest defect scan is to follow one data field end to end through the whole document and check that something actually writes it.

### Observation 24: An observation the agent only skims is not a control; the mitigation has to sit where the action happens

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Building a human approval gate for a media pipeline. Needed to stop a background HTTP server and ran `pkill -f "<script>.py serve"`, which killed the agent's own shell because the shell's command line contained the pattern. The session had already read the observation log at start-up and Observation 7 in that same log documents this exact failure mode by name.
**Skill:** task-observer
**Type:** open-source
**Phase/Area:** Session Start Protocol, step 2 ("Scan OPEN observations and active principles; hold them in awareness")

**Issue:** At session start the agent listed the log's `### Observation N:` headers to find the highest number and to see what was open. It read the titles, not the bodies. Observation 7's title names the hazard, but recognising a one-line title as relevant requires already knowing you are about to do the thing it warns about, and the `pkill` was typed forty minutes later in the middle of unrelated work. "Hold them in awareness" is a memory instruction, and memory is exactly what fails under cognitive load, which is the same reason the skill already replaced its soft logging prompts with hard tool-call checkpoints.

**Suggested improvement:** Treat operational hazards differently from methodology insights at review time. When an observation describes a concrete command or tool invocation that fails in a specific way, the review should not leave it as prose in the log: it should be promoted into a place that fires at the moment of use, such as a settings.json hook, a shell alias or wrapper, an entry in the project's CLAUDE.md command notes, or a pre-approved safe alternative in the permission list. Add a `**Mitigation surface:**` field to the observation format for this class, naming where the fix must live for it to actually bind, and have the weekly review refuse to mark such an observation ACTIONED while its only home is the log.

**Principle:** A written warning binds behaviour only if the reader encounters it at the moment of the action. For hazards attached to a specific command or tool call, the durable fix is a control at the point of use; leaving it as narrative in a log that gets skimmed at session start reproduces the failure the log was supposed to prevent.

### Observation 25: A batch API's response order is not the request order, and ordering that carries meaning must be reattached by key

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Running an unrun crawler that enumerated a wiki page's images, then hydrated them through a batched metadata endpoint. Page order was a documented signal in the spec: the first images on the page are the canonical debut images and later ones are variants. The crawler recorded each item's position using the loop index over the batch response.
**Skill:** source-driven-development
**Type:** open-source
**Phase/Area:** integrating a third-party read API

**Issue:** The batch call takes a pipe-joined list of titles and the code assumed the response came back in that order. It does not: the request order began with a screenshot file and the response began with a completely different file, and the two sequences disagreed at nearly every position. Because the resulting field was still a clean ascending integer sequence, the output looked correct in the JSON and in every summary. Nothing failed, nothing warned, and the one signal the spec called out as canon-bearing was silently replaced with an arbitrary internal ordering. It would have been found only by a human noticing the wrong image ranked first, weeks later.

**Suggested improvement:** When hydrating an ordered list through a batch endpoint, never derive position from enumerate() over the response. Build an explicit rank map from the ordered request keys, attach the rank to each returned record by that key, and sort. Add a verification step to the integration checklist: for any batch call, print the request sequence beside the response sequence once and confirm they match before trusting positional data. Note that key matching usually needs the provider's normalisation rules applied first, since responses commonly come back canonicalised rather than verbatim.

**Principle:** Set-shaped APIs make no ordering promise even when they usually look ordered. Any meaning carried by position must be reattached from the request side by key, and a positional field that is silently wrong is more dangerous than one that is missing, because it still validates.

### Observation 26: A regenerator that writes a file humans also edit must merge and must invalidate, never rewrite

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** A crawler wrote a JSON record per downloaded asset, containing both machine fields (path, hash, source URL, dimensions) and human fields (a written description, a review decision, an approval flag). The file was explicitly the durable artifact and the downloaded binaries were a disposable cache. Re-running the crawler rebuilt the file from scratch.
**Skill:** api-and-interface-design
**Type:** open-source
**Phase/Area:** designing the contract of a tool that regenerates a shared artifact

**Issue:** Re-running the fetch step destroyed every human-entered field with no warning and no prompt. The failure is invisible at the moment it happens, because the regenerated file is structurally valid and the counts are identical; the loss only surfaces later when someone opens the review page and finds it blank. The design had inverted its own stated priority: the document said the JSON was the durable artifact and the binaries were rebuildable, but the code treated the JSON as the rebuildable thing.

**Suggested improvement:** For any tool that regenerates a file carrying human-owned fields, make the contract explicit in three parts. (1) Split the schema into machine-owned and human-owned field sets and write them down in the code, not just in comments. (2) Default to merging on a stable identity key, with destructive regeneration behind an explicit flag rather than being the default behaviour. (3) Decide and document what invalidates a human decision: if the underlying artifact's content hash changed, a prior approval refers to something that no longer exists and must be voided and reported, not carried forward, because carrying it forward is worse than losing it.

**Principle:** When one file mixes generated and human-authored fields, the generator owns only its own fields. Regeneration must merge on identity, destructive rewrites must be opt-in, and any human judgement about content must be voided when the content it referred to changes.

### Observation 27: A warning treatment applied in the resting state destroys the signal it exists to carry

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Building a review page where each item carried four blocking-category checkboxes. The brief said the blocking categories had to be shown in red and be impossible to miss, so the checkbox group was given a red border and a red heading on every card.
**Skill:** frontend-design
**Type:** open-source
**Phase/Area:** designing alert and severity states

**Issue:** Rendering the page showed the mistake immediately: every card was red, so red became the page's background condition, and the one item that actually carried a blocking flag was indistinguishable from the twenty-six that did not. The instruction "show these in red and make them impossible to miss" had been implemented literally on the control rather than on the state, which produced the exact opposite of the requirement. It was only caught by screenshotting the built page and looking at it; the code read as though it satisfied the brief.

**Suggested improvement:** Add a rule to the alert-and-severity guidance: severity styling belongs to the state, never to the affordance that can produce the state. The control that sets a flag stays neutral until the flag is set; then the styling escalates on the whole containing element, and preferably adds a marker readable while scrolling past rather than only on close inspection. Add a review question for any severity work: if every item were in this state, would the styling still communicate anything? If not, the styling is on the wrong element. Pair it with a standing instruction to render and look at the result, because this class of error is invisible in source and obvious in a screenshot.

**Principle:** Emphasis is relative. A treatment that appears on every item carries no information, so severity must attach to the exception rather than to the mechanism that creates it, and any design where the alarm state is also the resting state has inverted its own purpose.

### Observation 28: A larger model under degraded input converts omission into fabrication

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Re-checking a suspect window of a machine transcript with a bigger model, as the spec instructed
**Skill:** New skill candidate: machine-transcript-verification
**Type:** open-source
**Phase/Area:** Escalating to a larger model to verify a suspect result

**Issue:** The written procedure said to re-run a suspect window through a larger model before believing the first result. On a deliberately degraded window where the truth was 54 items, the small model returned 8 and the large model returned 47. The large model looked like a recovery and was not: its output was fluent, well-formed and almost entirely invented. The only signal separating the two was the per-item confidence, which was 0.95 on clean input and 0.53 on the degraded window, with half the items below 0.5. Item count moved in the direction that looks like success while correctness moved the other way, so the obvious metric pointed exactly the wrong way.

**Suggested improvement:** When a procedure says to escalate to a larger model to verify something, define in advance which number decides the comparison, and make it a confidence or agreement measure rather than a volume measure. Report mean confidence and the share of low-confidence items alongside any count. Frame the escalation as a second opinion to diff against the first, never as an upgrade that supersedes it, and treat a large jump in output volume from a degraded input as evidence of fabrication until the confidence says otherwise.

**Principle:** Capacity does not become accuracy when the input is bad. A weak model drops what it cannot resolve, a strong one fills the hole with something plausible, so the more capable model can be the less trustworthy witness. Verify with confidence, not with volume.

### Observation 29: Do not derive the location of missing data from the record that lost it

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Locating a genuinely missing stretch of source material by inspecting the derived record
**Skill:** New skill candidate: machine-transcript-verification
**Type:** open-source
**Phase/Area:** Reporting where a detected gap actually is

**Issue:** The natural implementation was to bracket a missing stretch by the surviving records either side of it and report that interval. It produced a zero-width interval: the recogniser does not emit position information for content it never perceived, so the surviving records on both sides were adjacent even though six seconds of source sat between them. The tool correctly detected that something was missing and then reported it at a single instant, which is useless to the person who has to go and re-make the missing part. The fix was to locate the gap in an independent measurement of the raw source rather than in the derived record, which returned the true interval.

**Suggested improvement:** Whenever a tool reports a gap, separate the two questions: which content is missing (answered by the derived record) and where it is in the source (answered only by an independent measurement of the source). Never let the second question be answered by the artifact that lost the data. Add a test with a known removed span and assert that the reported interval matches the real one, since a detector can pass a presence test while failing a location test.

**Principle:** A derived record cannot tell you where its own omissions are. Detection can come from the derivation; localisation has to come from the raw source.

### Observation 30: Machine-read text has its own surface conventions, and both sides of a comparison must be folded onto them

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Matching an authored source document against a machine transcript of a reading of it
**Skill:** New skill candidate: machine-transcript-verification
**Type:** open-source
**Phase/Area:** Normalising before comparing authored text with recognised text

**Issue:** The authored document spelled numbers as words; the recogniser emitted digits. Every number therefore read as a mismatch, and the reference implementation's own worked example, which looked up a spelled-out number, could never succeed against a real transcript. The failure was silent in one direction (a slightly lower match rate that looks like normal noise) and loud in the other (a lookup that raises). Worse, the convention is a property of the model rather than of the content, so a lookup written against one model can break when the model is swapped, which defeated the entire purpose of writing lookups symbolically instead of hardcoding positions. One shared normalisation function, applied to both sides, fixed both symptoms and raised the match rate by more than a percentage point.

**Suggested improvement:** Before comparing authored text with recognised text, enumerate the recogniser's output conventions (numerals, currency, dates, contractions, casing, punctuation attached to tokens) and write a single normalisation function that both sides import. Never let two comparison sites define their own. Treat the convention as part of the recogniser's interface and re-check it when the model version changes.

**Principle:** A recogniser does not return the source, it returns its own rendering of the source. Any comparison against authored text must fold both sides onto one canonical form through one shared function, or the comparison is silently measuring the rendering rather than the content.

### Observation 31: Porting a measurement tool must preserve the exact numeric path, not just the algorithm

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Porting a working image/audio measurement script into a new tool and comparing its output against the original's recorded benchmarks
**Skill:** New skill candidate: measurement-tool-porting
**Type:** open-source
**Phase/Area:** Reproducing a reference implementation's numbers

**Issue:** The reference implementation extracted sample frames to PNG and read them back with the library's grayscale-decode flag. The port streamed the same frames in-process and converted to grayscale with the library's colour-conversion call, which is the obvious equivalent. The pixel data was byte-identical, but the two grayscale paths use different luma coefficients (one uses the modern-primaries weights, the other the legacy ones), giving per-pixel differences up to 62 levels out of 255. Every downstream threshold count shifted, so the new tool's numbers could no longer be compared with the benchmarks the whole pass/fail table was calibrated on. A separate check of the frame-selection filter found a similar trap: the resampling filter's chosen frames were offset by one from naive every-Nth-frame indexing, which moved every reported timestamp.

**Suggested improvement:** When porting a tool whose OUTPUT NUMBERS are compared against recorded historical values, treat the numeric path as part of the contract, not an implementation detail: same decode, same colour conversion, same sampling filter. Before optimising any of them, run both versions on the same input and assert the outputs match to within the tolerance the thresholds need. If an optimisation changes the numbers at all, either keep the slow path or re-derive the benchmarks, and say which.

**Principle:** A measurement is defined by its whole pipeline, not by its formula. Two implementations that are mathematically 'the same' can disagree enough to invalidate every calibrated threshold, and the disagreement is silent.

### Observation 32: Ask the tool what it did, do not infer it from the parameters you passed

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Building an audio master stage where one specific mode of a filter is the whole point of the design
**Skill:** New skill candidate: measurement-tool-porting
**Type:** open-source
**Phase/Area:** Verifying that a requested processing mode was actually taken

**Issue:** The design requires a normaliser to run in constant-gain mode, because the alternative mode rides the level over time and destroys the exact statistic the QC gate measures. The mode is requested with a flag plus five measured values. Supplying all six correctly is NOT sufficient: when the constant gain needed to hit the loudness target would push the peak past the peak target, the filter silently falls back to the other mode. No warning, no non-zero exit, and the output looks plausible because it lands on both targets. The only reliable signal was that the filter's own summary output names the mode it used, which meant running that one call at a higher log level purely so the summary could be read back and asserted on.

**Suggested improvement:** For any processing step whose MODE (not just its parameters) is load-bearing, find the tool's own report of what it did and assert on it. Where no such report exists, assert on an invariant that only the intended mode can produce. Add a pre-flight prediction of the fallback condition so the failure is explained before it happens, with the fix named. Requesting a mode and getting a zero exit code is not evidence the mode was used.

**Principle:** A silent fallback to a different algorithm is indistinguishable from success at the call site. Verification has to come from the tool's own account of its behaviour or from an invariant unique to the intended path, never from the arguments you supplied.

### Observation 33: Count evidence in units of the underlying event, not units of the detector

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Building a text-detection pass that runs two different preprocessing passes over every sampled frame and merges the results
**Skill:** New skill candidate: measurement-tool-porting
**Type:** open-source
**Phase/Area:** Thresholds over multi-detector evidence

**Issue:** Real on-screen events persist across several samples; detector noise does not. So a 'seen on at least two samples' threshold was used to separate them. But two preprocessing passes run over the SAME sample, and the counter was incremented per detection rather than per distinct sample timestamp. Any artefact that both passes happened to read on one frame therefore scored two and cleared a threshold designed to require two frames. The persistence filter silently stopped filtering, and the noise it was meant to remove appeared in the results as real detections with a start time equal to their end time. The zero-width time span was the visible symptom of a counting bug.

**Suggested improvement:** When a threshold means 'this persisted', count DISTINCT values of the dimension it persists along (timestamps, positions, sessions), by accumulating them into a set, never by incrementing a counter per detection. Add an assertion that any event claiming to persist actually spans a non-zero extent, since a zero-width span is the cheap tell that the count came from the wrong axis.

**Principle:** Redundant detectors inflate any count that is not keyed on the thing being counted. A persistence threshold must be expressed as a set of distinct positions, not as a tally of observations.

### Observation 34: A pattern-matching process killer will match the command that is running it

**Status:** OPEN
**Date:** 2026-08-09
**Session context:** Cleaning up a stuck long-running job from a shell command
**Skill:** New skill candidate: shell-safety-notes
**Type:** open-source
**Phase/Area:** Terminating background processes by pattern

**Issue:** A command-line process killer was invoked with a pattern to terminate a stuck job. The pattern also appeared, literally, in the text of the shell command issuing the kill, so the shell matched its own command line and killed itself. The compound command exited before its later parts ran, and, because the later parts included writing a script via a here-document, the next step failed with a confusing 'no such file' that pointed nowhere near the real cause. It cost two extra round trips to diagnose.

**Suggested improvement:** When killing processes by pattern from a shell, never let the pattern appear verbatim in the same command line: anchor it to something specific to the target (a full path, an argument the target has and the shell does not), or resolve PIDs in one step and kill them in another. Also treat a self-kill as a likely explanation whenever a compound command's later steps silently do not run.

**Principle:** Any tool that selects its targets by matching text will match the text that invoked it. Selection patterns need to exclude the selecting context explicitly, or the operation can consume its own caller.
