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

## 2026-08-14

### Observation 2: Locked voice profile has no persistent home on an ephemeral container

**Status:** OPEN
**Date:** 2026-08-14
**Session context:** Voicing an ExplainTory script ("Every Failed Weapon in History Explained") on Claude Code on the web. The pipeline hard-stops without a voice id, and no `voiceover_profile.json` existed anywhere on the machine.
**Skill:** explaintory-voiceover
**Type:** open-source
**Phase/Area:** SKILL.md — "Setup — two things, once" / `--profile`

**Issue:** Setup says the profile is copied across from Voiceover Studio "once". On a per-session ephemeral container there is no "once" — the file dies with the container every time, `check_profile()` raises, and the run stops before generating anything. The settings were only recoverable because a sample `--plan` output inside SKILL.md happens to print the real voice id and its four numbers as illustrative prose. That is an accident of documentation, not a source of truth: a reader who reformatted that example, or an author who genericised the id, would silently destroy the only surviving copy of the locked calibration. HANDOFF.md already names the container problem for audio files and the toolchain, but not for the profile.

**Suggested improvement:** Treat the profile as version-controlled project state, not machine-local config: commit `voiceover_profile.json` (no api_key — the key stays in the environment) to the repo, and have the setup section point `--profile` at the committed copy with the studio export as the way to UPDATE it rather than the way to obtain it. Add a line to the setup section naming the ephemeral-container case explicitly, and stop relying on an example block to carry the real calibration.

**Principle:** A skill that depends on a machine-local config file needs a committed fallback wherever the runtime is ephemeral — and settings that only exist inside a documentation example are undocumented, because nothing marks them as load-bearing.

### Observation 3: Pronunciation-guide stripper is anchored to the tail, and production docs append material after it

**Status:** OPEN
**Date:** 2026-08-14
**Session context:** The source Google Doc held the script, then the pronunciation guide, then a full animator note (~1,400 words of shot direction) after it. The animator note had to be removed by hand before the guide would be at the tail.
**Skill:** explaintory-voiceover
**Type:** open-source
**Phase/Area:** `scripts/script_prep.py` — `split_pronunciation_guide`

**Issue:** Guide detection deliberately examines only the tail of the script, which is what keeps a mid-script line like "The corvus — a boarding bridge — decided the battle" from being read as an entry. But a real production document is a container for several documents: script, then guide, then animator note / shot list / research links. With anything appended after the guide, the guide is no longer at the tail, detection misses, and the video closes by reciting its own glossary AND the animator note — the exact failure the feature exists to prevent, arriving silently as extra billed characters.

**Suggested improvement:** Keep the tail anchor as the fast path, but fall back to a section-anchored search: locate the guide by its heading anywhere in the document and take everything from that heading to the next H1, then treat the remainder as non-narration too. Failing that, have `--plan` state where the narration ENDS (last spoken sentence) so a trailing production note is visible before any credits are spent, rather than only visible in the finished audio.

**Principle:** A detector anchored on a document's position breaks as soon as the document becomes a container for several appended documents. Anchor on the section's own identity and use position only as a tiebreak.

### Observation 4: --suggest-breaks emits candidate pairs whose left token is a comma

**Status:** OPEN
**Date:** 2026-08-14
**Session context:** Curating clause breaks before the mastering pass. Two candidates were printed; one was `,|the` for "The better a submariner aimed, the more likely his torpedo was to strike the hull".
**Skill:** explaintory-voiceover
**Type:** open-source
**Phase/Area:** `scripts/voiceover.py` — `suggest_breaks`

**Issue:** The function already has an "already punctuated — nothing to add" guard, but it only tests the token AFTER the modifier (`nxt.is_punct`). When the fronted modifier's own subtree ENDS on its comma, `last.text` is `,` and `nxt` is an ordinary word, so the guard passes and a pair is emitted for a clause that is already punctuated. It is noise in a list whose whole purpose is to be short enough to read by hand, and a `,|word` pair cannot match anything downstream.

**Suggested improvement:** Apply the same punctuation guard to the left edge — skip when `last.is_punct` — or walk `last` back to the previous non-punct token before emitting. One-line change in `suggest_breaks`.

**Principle:** A guard that exists to test "is this boundary already marked?" has to be applied to both edges of the boundary, not just the one the bug was first noticed on.

### Observation 5: Google Docs export splits decimals, and the artifact changes what the voice says

**Status:** OPEN
**Date:** 2026-08-14
**Session context:** The exported script contained "it was fed British. 303 made to loosen ones". The pronunciation guide in the same document listed ".303 — read as three-oh-three", which is what identified it as an export artifact rather than the writer's sentence.
**Skill:** explaintory-voiceover
**Type:** open-source
**Phase/Area:** script prep, before `--plan`

**Issue:** A decimal-leading token (".303", ".22", ".50") comes out of the Docs export with the period detached and attached to the preceding word. Left alone, the voice reads a sentence boundary mid-clause and then says "three hundred and three". Nothing in the pipeline flags it: it is well-formed text, the read-check would diff the ASR against the same broken script and find agreement, and the only reason it was caught was a human reading the script against the guide. The script's own pronunciation guide is a machine-readable answer key that is currently used only downstream, for checking the audio.

**Suggested improvement:** Add a pre-flight pass over the narration text that cross-references the extracted pronunciation guide against the script BEFORE generation: every guide entry whose headword does not appear verbatim in the narration is either an export artifact, a spelling drift, or a stale guide entry, and all three are worth one line in `--plan`. Include a specific rule for orphaned decimal points (`\w\.\s+\d{2,3}\b`).

**Principle:** When a document ships its own answer key, check the source against it before spending anything — an artifact that leaves the text well-formed is invisible to every downstream check, because every downstream check is comparing against the same corrupted source.
