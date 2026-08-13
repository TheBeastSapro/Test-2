---
name: explaintory-script
description: Run the ExplainTory Scripting SOP end to end — title through Stage 0 gates, research the candidate pool, tier-budget the outline, draft, run the full audit battery and Stage 5A claim verification, and hand off a publishable script. TRIGGER on "script", "write the script", "new script", "script this title", or any video title submitted for writing. Pure scriptwriting; it does not touch voiceover or sound design.
---

# ExplainTory Script

**Sapro gives a title. This runs his SOP and gives back a publishable script.**

The process was already designed, refined through six versions, and is correct.
It is not reinvented here. What was missing was a **conductor** — something that
runs Stages 0 through 7 in order, in one session, loading the right document at
the right stage and running the right tool, without Sapro having to remember
which stage comes next or which check has been skipped.

That conducting is where the hours went. Not the writing.

**The authority order.** `references/claude_explaintory-scripting-sop-v1_7.md` is
the process. `references/claude_explaintory-channel-skill-v6_6.md` is the
craft, and **it wins over any generic FacelessOS guidance**. The Subject-Type
Law sits above everything. Stage 0 gate 7 reads
`references/claude_explaintory-title-scan-sop-v1_4.md`. This file only sequences
them. **When this file and a reference disagree, the reference wins** — and say
so rather than following this one silently.

## Constants — never recompute these in your head

| Parameter | Value | Source |
|---|---|---|
| VO rate | **185 WPM** (2,291 words → 12:21) | channel skill v6.6 |
| Kill-line | inside first **78 words** (0:25) | Fix 1 |
| Listicle length | **1,600–2,000 words**, 8–12 entries | SOP appendix |
| ENTIRE History | 3,300–4,000 words, era blocks | SOP appendix |
| HEAVY / MEDIUM / LIGHT | 250–320 / 170–220 / 110–160 | SOP appendix |
| Em dashes in body | **0** | overlay skill v1.1 |
| Negate-contrast device | exactly **1** per script | Stage 5 item 4 |
| Colons | ≤2–3 per script | Stage 5 item 1 |
| Humor density | 1 dry line / 250–300 words | SOP Stage 4 |
| Voice states | base · dry wit · **dramatic** (3, not 2) | channel skill v6.6 |

SOP Stage 5B rule 4 is binding: *"Recompute in the shell, never in the head, and
print the number."* Every runtime and every word sum in a report comes out of a
tool below, never out of an estimate.

## The stages

### Stage 0 — Gates (before anything)

**Gate 0, Subject class, runs first and outranks every other gate.** OBJECT and
SYSTEM are GO. **PEOPLE and EVENT are STOP** — 5-for-5 versus 0-for-3, and the
worst object video beats the best people video by 19x.

**High AVD is not a green light.** Military Units holds the channel's best AVD
at 41.9% and did 2,800 views. Never cite AVD as evidence a subject will convert;
on this channel that inference is backwards.

Watch the word, not the vibe: *"Every Failed Siege in History"* is an EVENT.
*"Every Siege Engine Explained"* is an OBJECT.

Then gates 1–7 from the SOP: niche, search demand, sparse competition, format
fit, vein check, flop-pattern, title stem. **Check the stem's current status in
the Title Scan SOP before committing** — that list moves faster than the SOP
file, and the SOP records a case where a stem was marked BURNED here and
reversed there on the same day.

A failed gate is a **no-go reported with the gate that failed**, not a script
written anyway with a caveat.

### Stage 0.5 — Pre-flight, the one batched gate

Four questions, asked once, at title lock, before research. Never defaulted
silently:

1. **Voice** — **three states**: base · dry wit · dramatic. Dramatic is the
   StickTory-derived mode of the overlay. Never present this as a two-way
   choice; sessions defaulted past *dramatic* for exactly that reason.
2. **Era headers** — only if the title carries "From Every Era". Default is at
   most two spoken; all-spoken costs ~2–3 AVD points and is Sapro's call.
3. **Target word count / runtime.**
4. **Write mode** — section-by-section with mini-audits, or full draft then one
   battery. Section-by-section is the default for new formats, experiments, and
   anything over ~1,800 words.

Present all four together with recommended answers pre-filled so the reply can
be "go".

**Then keep asking — but only about forks.** The SOP is explicit that pre-flight
does not license silence afterwards. Roster swaps, entries to cut, closer choice,
tone shifts get surfaced *when they become live*. Reversible craft calls (tier
assignment, sentence choices) stay with the writer and are flagged, not asked.

The distinction that matters: **batch the parameters, surface the forks.** The
parameters were costing round trips for no reason. The forks are the control.

### Stage 1 — Research, no drafting

Pool **larger than the script needs**: 14–18 candidates for an 8–12 entry
script, holding back 4–6 to seed a Pt 2.

Per candidate, a mini fact-card: one date/year · one named individual · one hard
number · outcome type · a real sourced quote if one exists. Rate on recognition,
weirdness, explanatory richness, and visual potential for the animator.

**Sourcing standard, from Stage 5A — apply it here, not later.** Museum object
records, peer-reviewed metallurgy, primary sources in translation and named
scholars outrank encyclopedias, and all of them outrank vendor and replica pages.
**Vendor pages are the single largest source of confident weapon misinformation
on the web and they dominate page one for exactly the queries a script needs.** A
claim appearing only on retailer sites is folklore until a real source is found.

Reject or flag single late sources (precedent: Cambyses' cat shields — one
source, 688 years after the event, rejected).

### Stage 2 — Entry confirmation (Sapro gate)

Deliver the rated pool with a recommended selection and order, and what is held
for Pt 2. He confirms, swaps, or adjusts. **Preserve-verbatim lines are logged
and carried exactly through every future version.** Drafting starts only after
sign-off.

### Stage 3 — Structure and outline (not prose)

```bash
python3 scripts/plan.py --entries 9 --words 1800
```

Prints the tier per entry, the word target, the seconds at 185 WPM, the summed
total, and any shape problems. This exists because of a failure the SOP names:
*"every entry-weight sum was wrong by 600 words, both stated with confidence."*

Ordering, Paint Explainer 5-position model: **Position 1** is the most visually
shocking subject, not the most famous. **Rehook at 40–55%** — explicit open loop,
most famous entry, or most ironic story. **Closer** is the most devastating or
resonant, not the most famous. A chronological signal in the title wins.

Then, by hand: the **outcome-type map** (force 1–2 pattern-breakers so not
everything resolves as rise-and-fall failure) and the **duplication check** (no
battle is the primary example twice; no entry re-describes another's mechanic).

A HEAVY that cannot fill its band with substance gets **demoted, not padded**.

### Stage 4 — Draft

Global: no extracted hook section, **no outro** — the final entry's last sentence
ends the script. Headers written **without numbers from the start**. **Zero em
dashes.** If over budget, cut whole **beats**, never shave sentences everywhere —
shaving flattens the tier variation the system exists to create.

Entry 1 carries the 0:30 metric: concrete sensory detail naming the subject in
sentence 1 · counter-intuitive claim by sentence 2 · specific number by sentence
4 · never open abstract.

**Opener shape** — pick per subject, do not default:
**Shape A, straight reveal** — name the subject and negate the assumption in one
breath. Use when the subject is famous or the truth is the hook.
**Shape B, misdirect-then-deflate** — lead with the vivid wrong impression, name
it as the correction. Use for striking-but-misleading hardware. **Only legal when
the deflation is genuinely surprising**; if impression and reality are equally
dramatic, it is spec-first-with-no-frame wearing a costume — fall back to A.

Voice: serious-but-conversational, dry-restrained. Gary Provost rhythm — after
2–3 long sentences, drop a short punch. Every humor line passes the
tonal-restraint test: works read by a serious narrator with a slightly raised
eyebrow, or cut. One comprehension analogy per unfamiliar entry, at
introduction. 1–2 real sourced quotes max, never invented.

Transitions: **But/Therefore logic, never "and then"**, no announcement
transitions. Each entry's first line resolves the previous open loop.

Kickers land on roughly **two-thirds** of entries, not all — some end on a plain
fact, a date, or a quote, and **one entry per script just stops.**

### Stage 5 — The full audit battery

```bash
python3 scripts/lint-v3_1.py script.md --format listicle [--overlay] [--punchline WORD]
```

Covers items 1–4, 9, and the mechanical half of 8. **It cannot cover 5, 6, 7, or
whether a fact is true. A clean run is the floor, not a pass.**

Then, by hand and non-optional: **retention/cadence check** (rehook placement,
tier alternation, shape matches the outline) · **Variety Rotation Log** output
block · **formal Authenticity Audit** output block.

On the deadzone scan: singles are REVIEW, **two or more consecutive is a hard
fail.** The fix is always to write the visual INTO the sentence — a historian
reading a service record becomes the ship anchored off a shoreline firing
inland. Never hand the animator a cue sheet covering a passage that should not
exist.

```bash
python3 scripts/plan.py --verify script.md      # measured tiers, adjacency, band
```

**If the dramatic voice state was chosen**, also:

```bash
python3 scripts/overlay.py script.md --mode explaintory
```

Measures the StickTory rhythm profile (avg ~8.5 words/sentence, ~28% fragments,
~59% short, ~5% long, never three long in a row), the humor levers, open-loop
rotation, telegraphing, and the cold ending. **Nothing else in the battery
measures any of it** — "was the overlay actually applied" was an eyeball
judgement before this.

It also enforces **the port boundary**. Three StickTory rules do not come
across, and the tool checks all three:

| Rule | StickTory | ExplainTory |
|---|---|---|
| 2nd person | the spine | **banned** — third person stays |
| Hedging | "just assert it" | **Stage 5A wins** — attribution required |
| "basically" | signature tic, ~20× | **capped at 3** by the linter |

**The hedging row is the dangerous one.** Importing "never hedge, just assert
it" would reintroduce exactly the class of error Stage 5A exists to catch, on a
channel whose audience timestamps them. Never let the overlay's voice rules
override Stage 5A.

The humor figure is a **floor, not a score** — the template says so itself:
*"keyword humor scorers are noisy and undercount novel phrasings — judge by
reading ALOUD, not a number."* A draft can clear it and be flat. So can the
dramatic engine: a want, a villain with a face, a Big Mistake caused by your
own trust are judged, never counted, and they are what decide whether it works.

### Stage 5A — High-risk claim verification

```bash
python3 scripts/claimscan.py script.md
```

Emits the worksheet: every sentence making one of the seven high-risk claim
types, grouped by entry, with the rule beside it and a blank for the source. It
**verifies nothing** — it does the walking, so the hour goes into opening sources
instead of hunting sentences.

Then three things it cannot do:

- **The dossier re-read.** Re-read the research dossier's flagged risks against
  the finished prose, line by line. In the first run the dossier had already
  flagged all three errors correctly and the draft contradicted its own research
  anyway, because compression happens between the dossier and the page.
- **The cadence heuristic.** Verify hardest the sentences that sound best. Every
  error in that run arrived as an improvement to rhythm. **Fluency is the tell,
  not the defence.** The tool surfaces cadence candidates; the checking is yours.
- **The comment-police pre-mortem.** One line per entry naming the correction a
  knowledgeable viewer would most likely leave. Any entry that does not survive
  its likely correction gets rewritten before presenting. **This list ships with
  the audit summary** — Sapro decides what risk to carry; he cannot decide about
  risk he was not shown.

### Stage 5B — Reporting discipline

Binding on what may be *said* about a script:

1. **Name the checks that actually ran.** A clean lint run is reported as a clean
   lint run, never as an accuracy pass.
2. **"Lock-ready", "final" and "as swept as a draft gets" are prohibited before
   Stage 5A has run.** If accuracy is unverified, it is a draft, whatever its
   polish.
3. **Report the exposure, not just the pass** — predicted corrections, plus every
   claim resting on inference, tradition, or a single source.
4. **Own arithmetic and constants.** Every number from a tool, at 185 WPM.
5. **Surface drift unprompted.** If a later instruction superseded an earlier
   rule, or a "locked" file was reopened, say so in the same message.

### Stage 6 — Versioning

Rewrites are **fresh from scratch**, never incremental trimming. **Never edit a
version file in place** — every change is a new numbered file so any two versions
diff. A script written under a superseded channel-skill version is **rewritten,
not patched**: research and roster survive, prose does not.

### Stage 7 — Handoff

Strip working tags from the title · top note *"Read body paragraphs only;
headings are labels"* · confirm headers carry no numbers · append the
pronunciation guide for all Latin/Greek/foreign terms · sanity-check runtime as
word count ÷ 185.

## Drift found at vendoring — resolved 2026-08-13

All three are closed. Recorded here because Stage 5B rule 5 requires drift be
surfaced, and because the resolutions are the reason these files carry new
version numbers.

- **SOP cited channel skill v6.4; the file was v6.5.** → **SOP v1.7** aligns the
  pointers, and fixes the consequence v6.5 named directly: Stage 0.5 question 1
  offered two voice states when there are three, which is why sessions never
  offered *dramatic*.
- **SOP Gate 7 and Title Scan SOP §0.2 disagreed** on the `From Every Era` stem.
  The 2026-08-06 weekly scan §8.1 had already reversed the burn — the two
  corpses failed **G0 on subject class, not packaging** — and the 2026-08-13
  scan shows the wrapper still climbing (Sword 116,416 at 9.4 days). → **Title
  Scan SOP v1.4** carries the correction; SOP v1.7 discharges the note. Both
  edited in the same pass, as v1.6 required.
- **The 50–55% AVD figure had no owner recorded.** → **Channel skill v6.6.**

### The AVD figure — whose number it is

**50–55% AVD is StickTory's, not ExplainTory's.** The dramatic overlay is
derived from StickTory and ports their approach in full **except the
second-person POV**. ExplainTory's measured AVD is unchanged: **39–42% listicle,
28–30% era-block**. ExplainTory's own post-overlay AVD is **not yet measured**.

Do not cite 50–55% as a channel result, and do not restructure to chase it.
Reading a retention number without checking what it describes is the same class
of error v6.4 was written to fix. The figure's correct use is as evidence the
overlay's *technique* works on its home channel.

**The overlay is UNPROVEN here.** It has been tested in drafting and reads well,
but **no video written with it has been published**, so there is no ExplainTory
retention curve for it at all. It is an open experiment, not doctrine.

That has one practical consequence worth stating at Stage 0.5: **the first
dramatic-mode script is the experiment's first data point.** Say so when
offering the voice states, and when it publishes, record its AVD in the channel
skill as the first real post-overlay row. Until then, dramatic mode is a bet
with good reasoning behind it — not the safe option, and not the proven one.

## Do not

- **Do not skip a stage because the script looks good.** The errors that reach
  the comments are fluent, confident sentences that pass every grep.
- **Do not report a runtime or a word sum computed in your head.**
- **Do not call a clean lint an accuracy pass**, or use "final" before 5A.
- **Do not write a subject that failed Gate 0** because the angle is interesting.
- **Do not restructure to beat the measured AVD.** Match the style that earns it.
- **Do not import from, or write for, the voiceover or sound-design tooling.**
