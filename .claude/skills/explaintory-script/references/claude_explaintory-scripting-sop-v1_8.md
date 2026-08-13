# ExplainTory Scripting SOP — v1.7
*Standard Operating Procedure for producing one publishable script, from title to VO handoff.*
*Grounded in: explaintory-channel-skill **v6.7**, the Subject-Type Law v1, Title Scan SOP v1.4, FacelessOS master, retention-mechanics, variety-rotation, authenticity-audit, punchy-dark-wit-overlay v1.0. Confirmed against channel data through August 2026.*

> **v1.8 change (2026-08-13):** battery tool pointer moves to
> **`explaintory-lint-v3_2.py`**, and the reason is a rule change rather than a
> rename. v3.1 failed second person only under `--overlay`; a base-voice or
> dry-wit script could address the viewer throughout and exit 0. v3.2 makes it
> an unconditional hard fail, because the ban belongs to the channel and not to
> the overlay. Channel skill **v6.7** records the doctrine. **Stages 1 through 7
> are otherwise byte-identical to v1.7** and no other constant changed. v3.1 is
> superseded and should not be run.
>
> **v1.7 change (2026-08-13):** pointer-alignment pass and one Stage 0.5
> correction. **Stages 1 through 7 are byte-identical to v1.6** — no research,
> outline, drafting, battery, 5A, 5B, versioning or handoff rule moved, and no
> constant changed.
>
> (1) **Channel skill pointers updated v6.4 → v6.6.** v6.5 added a third voice
> state; v6.6 records the dramatic overlay's provenance.
>
> (2) **Stage 0.5 question 1 offered two voice states and there are three.**
> Channel skill v6.5 notes this exact failure — that a drafting session "asks
> 'base or dry wit?' and never offers the dramatic option." This SOP was one of
> the places causing it. Question 1 now names all three.
>
> (3) **Gate 7's standing reconciliation note is discharged.** Title Scan SOP
> §0.2 listed the `From Every Era` wrapper as BURNED while this file's Gate 7
> read it as a validated house engine. v1.6 required both be edited in the same
> pass; Title Scan SOP **v1.4** now carries the correction and the note is
> removed here.
>
> (4) **The overlay's AVD figure is recorded with its owner.** 50–55% AVD
> belongs to **StickTory**, the channel the dramatic overlay is derived from —
> it is **not** a measured ExplainTory result. ExplainTory's own post-overlay
> AVD is unmeasured. Recorded in channel skill v6.6 and repeated here because
> citing a source channel's retention as your own is the precise error the
> Subject-Type Law and v6.4 exist to prevent.
>
> **v1.1 changes:** (1) VO rate corrected to the measured **185 WPM** everywhere — the 165–170 figure was a planning estimate and made every runtime ~10% long. (2) New **Stage 0.5 — Pre-flight**, four questions asked at title lock before research begins. (3) Superlative-verdict check added to the Stage 5 battery. (4) Versioning discipline tightened in Stage 6: never edit a version file in place.
>
> **v1.2 change:** **deadzone scan** added to the Stage 5 battery, after video QC found stretches where the animator had nothing to put on screen.
>
> **v1.6 change (2026-08-06):** two corrections to v1.5, both of them corrections to the writer rather than to the process.
>
> (1) **Gate 7 was rewritten on a stem status that had already been overturned.** v1.5 marked `The [Superlative] [X] From Every Era Explained` as BURNED, copied from Title Scan SOP v1.3 §0.2. The weekly scan of the *same date* (`claude/titlescan-weekly-2026-08-06.md` §8.1) re-ran G6 and reversed it: only two genuine third-party attempts exist, neither cleared 50K, and the wrapper carries four in-house instances at 513,087 · 145,008 · 135,779 · 32,119@57h. The two corpses (Battles 1,390; Military Units 3,094) failed **G0 on subject class**, not on packaging. Attributing their failure to the wrapper was the same error the Subject-Type Law exists to correct. Gate 7 now reads the stem as a validated house engine with a variant-occupancy check. **[v1.7] Reconciled: Title Scan SOP v1.4 §0.2 now reads the wrapper as a validated house engine, with the variant-occupancy check as the live constraint.**
>
> (2) **The v1.5 changelog line below said "no scripting rule changed." That was inaccurate and has been corrected in place.** Stages 1–7 were byte-identical, but Stage 0 gained a rejection gate and had gate 7 rewritten, and Stage 0 is a scripting rule — it decides whether a topic gets written at all. Per Stage 5B rule 1, the description of the work has to match the work.
>
> **v1.5 change (2026-08-06):** pointer-alignment pass plus two Stage 0 gate changes. **Stages 1 through 7 are byte-identical to v1.4** — nothing in research, entry confirmation, outline, drafting, the audit battery, Stage 5A, Stage 5B, versioning or handoff moved, and no constant changed. **Stage 0 did change:** it gained a gate and had one rewritten. This SOP still cited **channel skill v6.3**, which v6.4 superseded, and Stage 0 still recommended a title stem that the Title Scan SOP has since **burned**. Three corrections: (1) all v6.3 pointers updated to **v6.4**; (2) **Gate 0 — Subject class** added at the top of Stage 0, since v6.4 makes the Subject-Type Law doctrine principle #0 and it outranks every other gate; (3) Stage 0 gate 7 no longer offers `The Deadliest [X] From Every Era Explained` as a house skeleton — it is BURNED (clone swarm plus our own two corpses); the era-block *structure* is untouched, only the wrapper.
>
> **v1.4 change (2026-08-06):** written immediately after running Stage 5A for the first time on a finished script. It found **three further errors that the mechanical battery had passed**, all introduced during drafting rather than research. Consequences: a **seventh claim type (invented connective detail)**, the **cadence heuristic** (verify the lines that sound best), the **dossier re-read rule**, and **Stage 5B — Reporting Discipline**, because the deeper failure was not the errors themselves but describing a partial battery to the channel owner as a full one.
>
> **v1.3 change (2026-08-06):** new **Stage 5A — High-Risk Claim Verification**, a named taxonomy of the claim types that survive every mechanical check and then get corrected in the comments. Added because a published video drew top-level accuracy complaints on three claim types at once (weapon lineage, blade anatomy, composite metallurgy), from viewers who timestamped them. The mechanical battery cannot catch any of these: they are fluent, confident, plausible sentences that are wrong. Also adds the **comment-police pre-mortem** to Stage 5 and the **Audience Corrections Log** appendix.
>
> **Tool pointer correction (2026-07-30):** the deadzone scan and the fact-density floor were documented here as automated, but `explaintory-lint-v3.py` never implemented either. They now live in **`explaintory-lint-v3_1.py`** (project doc `claude/explaintory-lint-v3_1.py`), which is the current battery tool. v3.0 is superseded and should not be run. This note is a reference correction only — no rule in this SOP changed.

---

## PURPOSE & SCOPE

This SOP covers the full scripting pipeline for ExplainTory long-form videos (Listicle default, ENTIRE History secondary). It is a repeatable checklist: any session, any Claude instance, same output quality. Production downstream (human VO artist + separate animator) is covered only at the handoff stage.

**Non-negotiable process rule:** Stages run in order. No full script is ever written before Stage 2 sign-off.

---

## STAGE 0 — TITLE & TOPIC SELECTION

**Input:** A candidate title or topic idea.
**Output:** A go/no-go decision.

**GATE 0 — SUBJECT CLASS (runs before everything below).** Classify what the candidate is *about*. **OBJECT** (a physical thing that can be drawn and that did something) and **SYSTEM** (a repeatable method or structure) are GO. **PEOPLE** (rosters of humans, units, commanders, ranks) and **EVENT** (battles, campaigns, sieges-as-events) are STOP, and advance only on a written override in which the video is about a *thing* with people present as its operators. The channel is 5-for-5 on objects and systems and 0-for-3 on people and events; the worst object video beats the best people video by 19x. **High AVD is not a green light** — Military Units holds the channel's best AVD at 41.9% and did 2,800 views. Watch the word, not the vibe: "Every Failed Siege in History" is an EVENT, "Every Siege Engine Explained" is an OBJECT. Full reasoning in `claude/explaintory-subject-type-law-v1.md`; gate wording in Title Scan SOP v1.3 G0.

Gates (all must pass):
1. **Within niche** — weapons, military tech, forces, tactics, or military history.
2. **Search demand exists** — verify via YouTube autocomplete or NexLev search.
3. **Short-form competition is sparse** — no dominant existing 15–25 min version.
4. **Format fit** — natural list (Listicle) or chronological arc (ENTIRE History). Ambiguous → default Listicle.
5. **Vein check** — "mine each vein once." If the subject repeats an already-mined vein (Weapons, Rome, Naval) without a genuinely new angle, reject or reframe.
6. **Flop-pattern check** — no modern-only subjects (WW2-only, nuclear-only). Cross-era sweeps that fold famous modern items into a historical arc are fine; modern-only is not.
7. **Title words** — prefer validated stems, and check the stem's *current* status in Title Scan SOP §0.2 before committing, because that list moves faster than this file.

   **Validated house engines:** `The [Superlative] [X] From Every Era Explained` · `Every Genius [X] Explained` · `The Weirdest [X] Explained`.

   **HOT imports:** `Every [X] Explained` (7 independent channels) · `Every Failed [X]` (15+ channels across 10+ niches; failure outperforms success 3-6x on the same channels).

   **BURNED, do not build on:** `Explained in 10 Minutes` (odd runtimes outperform round ones) · `Met Their End` · `Every Single [X]`.

   **On the From Every Era wrapper specifically.** It was listed as burned and is not. The G6 re-run of 2026-08-06 found two genuine third-party attempts, neither above 50K, against four in-house instances at 513,087 · 145,008 · 135,779 and 32,119 in 57 hours. **The wrapper works on OBJECT subjects and fails on PEOPLE/EVENT subjects, which is Gate 0 doing its job, not the stem decaying.** The one live constraint is **variant occupancy**: run exact-match on the precise `[X] from every era` string and take an unoccupied noun. `"sword from every era"` returned zero results, which is why that variant was available.

If a proven skeleton just performed, the Pt 2 / sequel is the next obvious candidate.

---

## STAGE 0.5 — PRE-FLIGHT (ASK AT TITLE LOCK, BEFORE RESEARCH)

Four questions, asked once, as tappable options, the moment the title is locked. Never defaulted silently. These are the decisions that are cheap to answer now and expensive to reverse after a draft exists.

1. **Voice** — **three states, not two**: base channel skill · punchy dark-wit overlay (DRY WIT) · punchy dark-wit overlay (DRAMATIC). The dramatic mode is the StickTory-derived one. Never present this as a two-way choice; channel skill v6.5 records sessions defaulting past the dramatic option because the question only ever offered two. [v1.7]
2. **Era headers** — only if the title carries "From Every Era": all spoken, or at most two with the rest as on-screen cards. (Default per channel skill v6.6 Fix 2 is at most two; all-spoken costs ~2–3 AVD points and is the channel owner's call to make.)
3. **Target word count / runtime.**
4. **Write mode** — section-by-section with mini-audits, or full draft then one battery.

**Then keep asking.** Pre-flight is not a gate that licenses silence afterwards. Forks that emerge during research and drafting — roster swaps, entries to cut, closer choice, tone shifts — get surfaced at the moment they become live, not batched and not decided unilaterally. Reversible craft calls (tier assignment, sentence-level choices) stay with the writer and are flagged, not asked.

---

## STAGE 1 — RESEARCH & CANDIDATE ENTRY POOL

**Input:** Approved title. Research tools enabled.
**Output:** A rated candidate pool. **NO script. NO drafting.**

1. Research up front, not while drafting. Reach past first-page Google/Wikipedia results.
2. Build a pool **larger than the script needs** (target 14–18 candidates for an 8–12 entry script). Deliberately hold back 4–6 strong entries to seed a Pt 2.
3. For each candidate, capture a mini fact-card:
   - One date/year
   - One named individual (inventor, commander, engineer)
   - One hard number (range, weight, casualties, cost)
   - Outcome type (failed / almost worked / surprise success / endured)
   - A real sourced quote or exchange, if one exists
4. Rate each candidate (e.g., ★–★★★) on: recognition, weirdness/hook value, explanatory richness, visual potential for the animator.
5. Flag sourcing quality. Single late sources get rejected or soft-flagged (precedent: Cambyses' cat shields — one source, 688 years after the event — rejected).
6. Deliver to Sapro: rated pool + recommended selection and order + which candidates are held for Pt 2.

---

## STAGE 2 — ENTRY CONFIRMATION (SAPRO GATE)

**Input:** Rated pool.
**Output:** Locked entry list and order.

- Sapro confirms, swaps, or adjusts entries.
- Any lines Sapro flags as preserve-verbatim are logged and honored exactly through all future versions.
- Claude confirms understanding of any structural instructions before executing.
- Only after this sign-off does drafting begin.

---

## STAGE 3 — STRUCTURE & OUTLINE

**Input:** Locked entries.
**Output:** A position-and-tier outline (not prose).

1. **Ordering — Paint Explainer 5-position model:**
   - Position 1 (OPENER): most visually shocking / strongest 0:30 subject — not necessarily most famous.
   - Rehook position (~40–55%): explicit open loop, most famous entry, or most ironic story.
   - CLOSER: the most devastating or resonant entry, not necessarily the most famous.
   - Chronological signal in the title wins for ordering when present.
2. **Tier budget (variable entry length — never uniform):**
   - HEAVY ~250–320 words: opener, rehook, closer (fixed) + max 2 more (complex/obscure/twist/full-arc entries).
   - MEDIUM ~170–220 words.
   - LIGHT ~110–160 words: famous self-explanatory subjects, one-beat weirdness, deliberate pace-troughs. Every LIGHT entry still clears the fact-density floor.
   - ~9 entries / ~1,800 words ≈ 3 HEAVY + 3–4 MEDIUM + 2–3 LIGHT. Alternate weights; avoid back-to-back HEAVIES.
   - A HEAVY that can't fill its band with substance gets demoted, not padded.
3. **Outcome-type map:** assign each entry's outcome now; force at least 1–2 pattern-breakers (surprise success / endured) so not everything resolves as rise-and-fall failure.
4. **Duplication check:** no battle/event is the primary example in more than one entry; no entry re-describes another's mechanic.
5. Optional deliberate shape: undulating entry lengths (trough before the rehook peak) as used in Weirdest Tactics v5.

---

## STAGE 4 — DRAFT

**Input:** Approved outline.
**Output:** Full draft (internal — not yet presented).

**Global rules:**
- Length: **1,600–2,000 words** (~8:40–10:50 at the measured **185 WPM**; 2,000 ≈ 10:50 VO). Longer is permitted when the channel owner sets a higher target; if over budget, identify cuttable **beats** rather than shaving sentences everywhere, because even shaving flattens the HEAVY/MEDIUM/LIGHT tier variation that the tier system exists to create.
- No extracted hook section. No outro — the final entry's last sentence ends the script.
- Section headers written **without numbers from the start**.
- Zero em dashes anywhere in the body.

**Entry #1 mechanics (carries the 0:30 metric):**
1. Concrete sensory/specific detail in sentence 1 — name the subject and something physical.
2. Counter-intuitive claim by sentence 2.
3. Specific number by sentence 4.
4. Never open abstract ("Throughout history…").

**Voice:**
- Serious-but-conversational, dry-restrained. ~1 dry observation per 250–300 words, clustered near transitions, never two casual lines back-to-back.
- Tonal-restraint test on every humor line: works read by a serious narrator with a slightly raised eyebrow, or cut.
- One **comprehension analogy** per unfamiliar/abstract entry, placed at introduction — clarity job, doesn't count against humor density, no meme register.
- Gary Provost rhythm: after 2–3 long sentences, drop a short punch.
- 1–2 real sourced quotes max per script; never invented or misattributed.

**Transitions:**
- Open-loop transitions are load-bearing for abstract/similar entries. Famous distinct subjects with built-in arcs may close on a summary kicker — recognition carries the gap.
- No announcement transitions. No "and then" — But/Therefore logic throughout.
- Each entry's first line resolves the previous open loop where one exists.

---

## STAGE 5 — FULL AUDIT BATTERY (MANDATORY BEFORE PRESENTING)

Run all components. A "full battery" is not just the anti-slop grep.

**Tool:** `python3 explaintory-lint-v3_1.py script.md --format listicle [--overlay] [--punchline WORD ...]`. It covers items 1–4, 9, and the mechanical half of item 8. It cannot cover 5, 6, 7, or whether a fact is TRUE. A clean run is not a pass; it is the floor.

1. **Anti-AI-slop scan:** em dashes (zero), "No X. No Y. No Z." fragments, "Most people…" openers, colon crutch phrases (max 2–3 colons total), suspicious percentages, empty words (powerful / game-changing / transformational), "Let that sink in."
2. **Superlative-verdict scan:** grep `weird|strange|bizarre|odd|peculiar|insane|crazy|incredible`. The title already promises the superlative; narration that repeats it states a verdict the viewer should reach alone, and reads as a script unsure its subject landed. The paradox hook states a **contradiction** ("warships do not have roofs"), never a **verdict** ("this was the strangest ship"). Legitimate only when quoting a source or judging the historical record rather than the subject. Automated in `explaintory-lint-v3_1.py`.
3. **Deadzone scan:** every sentence must answer "what is on screen while this is being said." Flag any sentence that leans on a reporting or abstract verb while naming no physical object. The three highest-debt types, in order: **sourcing and attribution** ("X wrote it down, Y quoted him"), **historiography** ("the historian went through the records and found"), and **institutional aftermath** ("the details were classified"). These naturally land at entry *endings*, which is exactly where the next entry's pull should be working, so deadzones cost retention as well as animation time.

   **Two or more consecutive deadzones is the serious failure** — that is seconds of screen time with nothing to cut to, and it is what surfaced in QC.

   The fix is always to write the visual INTO the sentence, never to hand the animator a cue sheet covering a passage that should not exist. A historian reading a service record becomes the ship anchored off a shoreline firing inland. A classified file becomes a drawer that stays shut for seventy years. Automated in `explaintory-lint-v3_1.py`: singles print as REVIEW with the debt type and an ENTRY-END marker, consecutive runs are a hard fail.

4. **ExplainTory pattern thresholds (grep):** basically ≤3, genuinely ≤2, actually ≤4, literally ≤2, honestly ≤1, "Here's [reveal]" ≤3, "Which is/was" aside ≤2, single punchline word ≤1, "and then" transitions = 0. Exactly **one** negate-contrast ("It's not X, it's Y") device per script.
5. **Retention/cadence check:** rehook placement, tier alternation, entry-length shape matches the outline.
6. **Variety Rotation Log:** required output block — confirms device rotation across entries.
7. **Formal Authenticity Audit output block:** required — not optional.
8. **Fact verification pass:** every entry has its date, named individual, and hard number; unverifiable claims softened or flagged. The *presence* of each is now a hard-fail check in `explaintory-lint-v3_1.py` (fact-density floor, per channel skill v6.6), which also warns on filler paragraphs. Whether each fact is CORRECT is still a human/Claude pass — the Bushnell dimension error in Warships v2.0 cleared every mechanical check.
9. Word count verified against 1,600–2,000.

Present the script only after all components pass, with the audit summary block attached.

---

## STAGE 5A — HIGH-RISK CLAIM VERIFICATION (MANDATORY, AFTER THE BATTERY)

Item 8 of the battery confirms a date, a name, and a number are *present*. This stage asks whether the sentences are *true*. It exists because the errors that reach the comments are never slop — they are fluent, confident, plausible sentences that pattern-match to something true. They pass every grep. The audience for this channel timestamps them.

**Method:** walk the script entry by entry. For each entry, find every sentence that makes one of the six claim types below and verify it against a real source. Not memory. Not the research dossier's summary of a source — dossiers compress, and compression is where these errors are born.

### The six high-risk claim types

1. **Lineage / descent** — "X evolved from Y," "the ancestor of Z." Weapons rarely descend from what they resemble. *Verified failure: the khopesh was called sword-shaped when it descends from the epsilon axe; the falcata gets called the gladius's ancestor when the gladius comes from the straight Celtiberian sword.* **Rule: if a weapon has a documented ancestor, name it in the entry.** The lineage fact is almost always more interesting than the line it replaces, so this rule pays for itself.

2. **Anatomy / which-part-does-what** — which edge cuts, which curve hooks, which end is weighted, what a named component is for. **The specific trap is merging two parts into one action.** *Verified failure: writing that a khopesh's sharpened outer edge hooks a shield, when the outer edge cuts and the blunt inner curve hooks.* Any sentence that gives a weapon two functions in one clause gets checked twice.

3. **Composite materials described as one material** — laminated, differentially hardened, forge-welded, or graded constructions written as if the object were homogeneous. *Verified failure: "tamahagane folded to purge its flaws," which collapses a sorted, two-metal, laminated blade into one lump of steel and drops the reason the construction exists.* **Rule: if the object is a composite, the narration must say which material does which job.**

4. **Function inferred from shape** — asserting how something was used because of how it looks, where no source documents the use. **Rule: shape does not testify.** If the technique is not attested, the sentence says so and turns the gap into a beat ("no Egyptian ever wrote the technique down"). This converts the single most common comment correction into a trust signal.

5. **Statistics where datasets disagree** — a precise share ("swords caused four percent of wounds") when different registers, centuries, or scholars give different numbers. **Rule: attribute the source in the narration and state the shape of the finding, not a bare percentage,** unless one figure is genuinely canonical. A named historian plus a directional claim is unfalsifiable-in-the-good-sense; a naked number invites the correction.

6. **Superlatives about material or performance** — hardest, sharpest, strongest, unbreakable, centuries ahead. These invite the counter-example, and the counter-example always exists. Keep the material's *documented* property and drop the ranking.

7. **Invented connective detail** — the scene-making sentence that no source supports, written to give an entry a concrete image or to smooth a seam. *Verified failure: "captured sabers traveled home in the baggage of half the armies of Europe" — plausible, vivid, and fabricated; the documented fact was the slower adoption of the design over the following century.* This is the most dangerous type because it is invisible to verification-by-reading: there is no wrong fact to catch, only a fact that was never there. **Rule: every concrete detail in a scene must trace to a source, including detail that merely decorates a true event.** If a scene needs an image the record does not supply, the entry uses a different image or states the gap.

### Two drafting-side rules (these prevent the errors rather than catching them)

- **The cadence heuristic.** Verify hardest the sentences that sound best. Every error found in the first Stage 5A run had arrived as an improvement to rhythm: a tricolon that merged two functions of a weapon into one action, a compression that flattened a laminated material into one metal, a callback that invented a lineage to complete a thread, an invented detail that gave a seam a picture. **Fluency is the tell, not the defence.** Any sentence that felt satisfying to write gets checked against a source before it ships.
- **The dossier re-read.** Before Stage 5A, re-read the research dossier's flagged risks *against the finished prose*, line by line. In the first run, the dossier had already flagged all three errors correctly — the lineage, the anatomy, the metallurgy — and the draft contradicted its own research anyway, because compression happens between the dossier and the page. A dossier that is written and never re-read is a dossier that did not do its job.

### Sourcing standard for this stage

- Museum object records, peer-reviewed metallurgy, primary sources in translation, and named scholars outrank encyclopedias, and all of them outrank vendor and replica-seller pages. **Vendor pages are the single largest source of confident weapon misinformation on the web** and they dominate page-one results for exactly the queries a script needs.
- A claim that appears only on retailer sites is treated as folklore until a real source is found, however often it repeats.
- Where a claim survives only as tradition, the narration frames it as tradition ("tradition says," "reputation says," "no such complaint has ever been found in writing"). This is already channel practice for legends; Stage 5A extends it to *mechanisms and materials*, which is where it had been skipped.

### Comment-police pre-mortem (run once, at the end of Stage 5A)

For every entry, write in one line the correction a knowledgeable viewer would most likely leave. Then confirm the script either states it correctly or pre-empts it. Any entry whose likely correction the script does not survive gets rewritten before presenting. The predicted-correction list ships with the audit summary so the channel owner can see the exposure rather than discover it in the comments.

---

## STAGE 5B — REPORTING DISCIPLINE (SELF-CHECK BEFORE PRESENTING)

The errors above were recoverable. Describing the work inaccurately to the channel owner was not, because it removed his ability to catch them. These rules govern what may be *said* about a script, and they are as binding as the ones governing what is written in it.

1. **Name the checks that actually ran.** "Full audit battery" means every component of Stage 5 *and* Stage 5A. If only the mechanical half ran, the report says so, in those words. A clean lint run is reported as a clean lint run, never as an accuracy pass.
2. **"Lock-ready," "final," and "as swept as a draft gets" are prohibited before Stage 5A has run.** They were used repeatedly on a script carrying six unverified errors. If accuracy is unverified, the script is a draft, whatever its polish.
3. **Report the exposure, not just the pass.** Every audit summary ships the predicted-correction list from the comment-police pre-mortem, plus any claim that rests on inference, tradition, or a single source. The channel owner decides what risk to carry; he cannot decide about risk he was not shown.
4. **Own arithmetic and constants.** Runtime is computed at the appendix figure of **185 WPM** and nowhere else. In one session every runtime estimate was given at 168 WPM and every entry-weight sum was wrong by 600 words, both stated with confidence. Recompute in the shell, never in the head, and print the number.
5. **Surface drift unprompted.** If a later instruction has quietly superseded an earlier rule, if a "locked" file has been reopened, or if the work has slid from the process onto the artifact, say so in the same message rather than continuing. Corrections that arrive only when the channel owner notices are corrections that arrived too late.

---

## STAGE 6 — REVISION & VERSIONING

- Rewrites are done **fresh from scratch**, not incremental trimming.
- **Never edit a version file in place.** Every change produces a new numbered file (v2.0 to v2.1 for a fix, v3.0 for a structural change) so any two versions can be diffed and nothing is silently rewritten underneath the channel owner.
- A script written under a superseded channel-skill version is **rewritten, not patched**. Research and roster survive; prose does not.
- Preserve-verbatim lines carried exactly.
- Confirm understanding before major structural changes.
- Version files with explicit suffixes (`-v2`, `-v3`…). **Never overwrite a prior version.**
- Working files in `/home/claude/explaintory/`; deliverables in `/mnt/user-data/outputs/`.

---

## STAGE 7 — VO & ANIMATOR HANDOFF

**VO handoff (every time):**
1. Strip working tags from the title.
2. Top note: *"Read body paragraphs only; headings are labels."*
3. Confirm headers carry no numbers.
4. Append a bulleted pronunciation guide for all Latin/Greek/foreign terms.
5. Sanity-check runtime: word count ÷ 185 WPM ≈ minutes.

**Animator:**
- Works from narration alone; no full visual cue sheet by default.
- If accuracy matters (specific weapons, formations, ships), offer a short "draw these right" reference note instead.

---

## APPENDIX — KEY NUMBERS

| Parameter | Value |
|---|---|
| VO rate (measured) | **185 WPM** (2,000 words ≈ 10:50; 78 words ≈ 0:25) |
| Script length | 1,600–2,000 words |
| Entries | 8–12 (Listicle) |
| HEAVY entry | 250–320 words |
| MEDIUM entry | 170–220 words |
| LIGHT entry | 110–160 words |
| Humor density | 1 dry line / 250–300 words |
| Real quotes | 1–2 per script |
| Colons | ≤2–3 per script |
| Negate-contrast device | exactly 1 |
| Em dashes in body | 0 |
| Battery tool | `explaintory-lint-v3_2.py` (v3.0, v3.1 superseded) |
| Second person | **0 — every voice state**, hard fail |
| Pt 2 seed pool | hold back 4–6 entries |
| High-risk claim types | 7 (Stage 5A) |
| Channel skill version | **v6.6** (v6.5 superseded) |
| Voice states | base · dry wit · dramatic (3, not 2) |
| Dramatic overlay source | StickTory — **their** 50–55% AVD, not ours |
| Subject class | OBJECT or SYSTEM only (Gate 0) |

---

## APPENDIX — AUDIENCE CORRECTIONS LOG

Every accuracy correction that reaches the comments of a published video gets logged here with the claim type, so the same class of error is checked for in every future script. This log is read at Stage 5A. It is the only appendix that grows from audience feedback rather than from internal QC.

**Harvest rule:** read the comments of each published video at the retention post-mortem, sort by most relevant, and log any correction that is (a) specific, (b) plausible, and (c) about a claim the script actually made. Verify before logging — commenters are frequently right about the direction and wrong about the specifics, and an unsourced comment figure never enters a script.

| Date | Video/claim | Claim type | Verified? | Rule produced |
|---|---|---|---|---|
| 2026-08-06 | Khopesh described in a way that implied sword descent; shape used to assert combat use | 1 (lineage), 4 (function from shape) | Yes — descends from the epsilon axe (Hamblin 2006; Wise 1981); hooking use is inferred, not attested | Name the documented ancestor; shape does not testify |
| 2026-08-06 | Khopesh outer/inner curve functions merged | 2 (anatomy) | Yes — outer convex edge cuts, blunt inner curve traps | Two functions in one clause gets checked twice |
| 2026-08-06 | Tamahagane described as one folded steel | 3 (composite as homogeneous) | Yes — sorted by carbon; hard steel to edge, soft iron to core; folding purges slag and evens carbon in poorer steel | Composites must state which material does which job |
| 2026-08-06 | Viewer claim that wootz blades shattered at worse than 50/50 odds | 5 (statistics) | **No — unsourced, contradicts published metallurgy. NOT adopted.** | Log the claim, do not write it in; unsourced comment figures never enter a script |
| 2026-08-06 | Bronze Age grip-tongue sword described as "cast in one piece with its grip, so the hilt could not snap off at the rivets" | 2 (anatomy) | Yes — the flanged tang is integral to the blade; grip plates ARE riveted, inset between flanges that absorb the shock | Construction claims name the actual part; do not simplify a mechanism into its opposite |
| 2026-08-06 | Iberian sword called the Egyptian design "reborn in iron" (continuity-thread callback) | 1 (lineage) | Yes — Quesada Sanz argues origin parallel to the kopis, not derived; the Egyptian link is forum theory | A thread callback is not a licence to assert descent; convergent design is the honest and stronger framing |
| 2026-08-06 | Roman armor modifications stated as a documented response to the Dacian falx | 4 (inference as fact) | Yes — the link is the leading scholarly reading, not attested by any Roman source | Causation drawn by archaeologists is narrated as such; the gap becomes a beat |
| 2026-08-06 | "Captured sabers traveled home in the baggage of half the armies of Europe" | 7 (invented detail) | **No such detail exists — written for the image** | Scene decoration traces to a source or is cut |

**Standing note on the katana:** it draws the most aggressive corrections of any subject on this channel, including reporting threats. Sourced demotion framing is defensible and should not be softened for safety, but every katana claim carries visible attribution in the narration.
