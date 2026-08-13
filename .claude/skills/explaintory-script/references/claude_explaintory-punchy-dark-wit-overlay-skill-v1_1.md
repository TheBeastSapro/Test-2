---
name: explaintory-punchy-dark-wit-overlay
description: Optional narration-style overlay for ExplainTory scripts. Runs in one of two modes — DRY WIT (rhythm and restrained dark humor over fact clusters) or DRAMATIC (each entry built as a small tragedy with a want, a named party and a mistake). Always ask which mode before drafting. Load after the main explaintory-channel skill. This overlay strictly prohibits second-person narration and close imitation of any individual creator's wording.
version: 1.1
---

# ExplainTory Punchy Dark-Wit Overlay

## CHANGELOG — v1.1 (2026-08-09)

v1.0 remains untouched at its own path.

1. **Priority order fixed.** v1.0 ranked the channel skill above this overlay with no carve-out, so
   the channel skill's "~1 dry observation per 250-300 words" won every density conflict and this
   document never took effect. Read literally, v1.0 was a no-op. See
   `claude/skill-file-audit-2026-08-06.md` item 10.
2. **Density carve-out added** so that conflict cannot recur.
3. **Fact guard added.** The overlay gets no research rights when running as a pass over a draft.
4. **Fact floors moved from sentence scale to entry scale.**
5. **Two modes added, with a question before drafting.** DRY WIT is v1.0's behaviour. DRAMATIC ports
   the dramatic engine from `StickTory_Script_Template_v3.md` down to entry scale.
6. **Counting apparatus removed.** An earlier draft of v1.1 carried a spec-stack cap, a licensed-
   fact-free-run count, and a long numeric audit list. The first time the cap disagreed with the
   channel owner's ear, the ear was right. Numbers stay in the diagnosis documents, where they
   belong; this document gives craft guidance and is judged by reading aloud.
7. **"No joke in the run-up" corrected.** An earlier draft banned any aside before the belief beat,
   on the theory that irony there primes disbelief. Tested against the reference entry, that was
   wrong — the aside it removed was the entry's only moment of narrator presence, and cutting it
   made a tighter entry that read colder. The rule now distinguishes a wink at the design's expense
   from a warm aside about a person. See Mode 2, element 3.

### The mechanism behind 1–4

The channel skill enforces **quantitative floors** — a checkable fact every 2–3 sentences, ≥1 date
and ≥1 named individual and ≥1 hard number per section, one dry observation per 250–300 words. This
overlay makes **qualitative calls** — breathe here, joke there, let this sentence run long, exit now.
v1.0's priority order put the counting above the judgment, so every voice decision lost to a
counting rule. That is why the overlay read as inert, why entries came out as fact clusters rather
than small tragedies, and why finished scripts felt over-researched.

---

## Purpose

This is an **additive voice overlay**, not a replacement channel skill.

Load it **after** the main `explaintory-channel` skill. The main skill still controls research
standards, topic and roster selection, runtime and word budgets, promise-to-payoff cycles, entry
ordering and era structure, section approval, storyboard requirements, and the no-intro/no-outro
rules.

This overlay controls sentence rhythm, personality density, dark humor, modern comparisons, reaction
lines, mini-reversals, section exits and transitions, where fact density is allowed to thin, and
whether an entry is built as a fact cluster or as a small tragedy.

The target is an original ExplainTory voice with the energy and retention mechanics of fast
dark-history narration, without copying another creator's phrases, jokes, sentence templates or
persona.

**What the viewer is there for:** enjoyment. Not to be informed at, not to be impressed by the
research. The pleasure is company — someone visibly interested in this material, taking them
through it. Everything below serves that.

---

## Activation

Apply this overlay when the user asks for punchier narration, more personality, darker humor, faster
comedic rhythm, StickTory-inspired energy, a less encyclopedic script, or a stronger
reaction-and-reversal pattern.

ExplainTory structure and precision remain fixed. The overlay increases rhythm, observation and
controlled dark wit. Never announce the style reference inside the script.

---

## MODE SELECTION — ask before drafting

**After the entry list is locked and before any script text is written, ask which mode.** Fold it
into the same turn as the channel skill's section-by-section question. The choice belongs to the
channel owner, per script.

> Which overlay mode for this script — DRY WIT, DRAMATIC, or mixed by position?

### MODE 1 — DRY WIT (v1.0 behaviour)

Entries are fact clusters delivered with rhythm and restrained dark humor. The grip is the subject
itself: the spectacle, the absurdity, the scale.

Best for high-recognition subjects that carry themselves, lighter entries, and any entry where the
mechanism is the interesting part.

### MODE 2 — DRAMATIC

Each entry is built as a small tragedy at entry scale. Ported from the StickTory dramatic engine,
which runs at script scale there and cannot here, because a listicle has no continuous protagonist.
The elements survive the transfer; the protagonist does not.

Five elements, in order:

1. **A want, stated first.** Not an activity. A problem someone needed solved and could not solve.
   Open on the want, not on the object.
2. **A responsible party with a name.** A directorate, a design bureau, a commander. Named parties,
   not "the British." A system can fail; only a party can be wrong. An institution is enough.
3. **A sincere-belief beat.** The case *for* the subject, immediately before it fails. This is the
   element Mode 1 has no version of, and it is the whole difference. Without it the failure is a
   foregone conclusion rather than a reversal.
   - It runs as long as it takes to be believed and no longer. If the want was set up properly, a
     few words will do it.
   - **Watch what kind of aside sits in the run-up.** A wink at the design's expense right before
     the belief beat primes the viewer to disbelieve and sabotages it. A warm aside about a *person*
     does the opposite — it makes the narrator someone worth listening to at the moment he asks you
     to take the design seriously. The Shute line in the reference entry is doing exactly that job,
     and removing it made the entry colder, not cleaner.
4. **The mistake, isolated and late.** The assumption the whole thing rested on, given its own line,
   landing **at** the reversal. Never telegraphed, never pre-explained. Place it directly against
   the belief beat with nothing in between.
5. **Breath, then a cold exit.** Let the pivot stand alone before the consequence lands. End on one
   device. No joke after the final line.

A Mode 2 entry runs longer than the same facts as a fact cluster, so it is a heavier entry. Don't
build a whole script from them — a few per script, never adjacent. Default placement is entry 1, the
rehook, and the final entry. That's a starting assumption, not a measured result.

### Reference entry — Mode 2

> The Atlantic Wall's sea defences needed more than a ton of explosive to breach, and in 1943 the
> Royal Navy had no way to get that up a beach under fire. The Directorate of Miscellaneous Weapons
> Development found one. Send it up by itself.
>
> They called it the Panjandrum. Two wooden wheels, ten feet across, joined by a drum built to carry
> four thousand pounds of charge. Seventy cordite rockets around the rims. Fire them together and it
> would cross the sand at sixty miles an hour. One of the engineers was Sub-Lieutenant Nevil Shute,
> later better known as a novelist. On paper it worked. On paper it was the only answer anyone had.
>
> All of it depended on seventy rockets burning at the same rate.
>
> They never did. At Westward Ho on 7 September 1943 the wheel leaned out of its line within seconds,
> and every modification bought a worse run than the last. By January 1944 a clamp gave, rockets came
> off the rim in flight, and admirals and generals went over the pebble ridge into their own barbed
> wire while the Navy's photographer, Klemantaski, ran. It was scrapped within weeks.
>
> It had been carrying sand.

*Want* = a ton of explosive with no way to move it. *Party* = the Directorate. *Narrator presence* =
the Shute aside, the entry's one moment of company. *Sincere belief* = the doubled "On paper," which
is the sound of someone talking themselves into it. *Mistake* = the line standing alone, broken
immediately by "They never did." *Cold exit* = "It had been carrying sand," one device,
recontextualising the entry.

It never pre-announces the failure and never mocks the men. Its single aside is warm rather than
sharp. The name arrives as the answer to the setup rather than as a label.

**What got cut on the way there, because the cuts are the lesson:**

- A flourish that restated the speed the sentence had already given.
- Two specs that drew nothing — the wheel's width, the weight of an individual rocket.

And what got cut and then put back: the Shute aside, and the second half of the belief beat. Both
were removed as "unnecessary" and both left the entry worse. The doubled "On paper" is a person
talking themselves into something, which one line alone doesn't do. The Shute line is the only place
anyone sounds like they're enjoying this.

The test that survived all of it: **cut what restates, keep what makes you believe, and keep whatever
makes the narrator present.**

---

## Non-Negotiable Boundaries

### 1. No second-person narration

Never place the audience inside the historical scene. No *you*, *your*, *yourself*, no commands to
the viewer, no viewer roleplay, no "imagine" or "picture yourself" constructions, no statements about
what the viewer sees, feels, thinks or would do.

Use third-person or observational narration:

- The defenders watched from the wall.
- The machine appeared above the rooftops.
- From a distance, it looked like a moving building.
- On paper, the plan was excellent. Paper was doing considerable work.

### 2. No close imitation

Borrow broad technique only — fast scene entry, dark understatement, fact-linked humor, modern
comparison, short reaction line, escalation and reversal.

Never borrow recognizable catchphrases, signature sentence sequences, repeated joke structures unique
to another channel, distinctive metaphors from competitor transcripts, a competitor's narrator
persona, or verbatim and lightly paraphrased transcript lines. All wording is newly written.

### 3. No comedy-channel drift

History is the subject. Humor is the delivery system. Every joke must clarify scale, expose
absurdity, compress a judgment, mark a reversal, release tension after a grim fact, or make a
mechanism memorable. Delete any joke that pauses the explanation without improving it.

### 4. No em dashes in narration

Periods, commas, colons or parentheses. The spoken script contains no em dashes.

### 5. No invented certainty

A punchline cannot strengthen a disputed fact. Uncertain claims stay visibly uncertain — *probably*,
*reportedly*, *contemporary accounts describe*, *estimates place it at*, *surviving evidence
suggests*. Humor comes after the uncertainty is preserved, never by erasing it.

---

## The Fact Guard

**When this overlay runs as a pass over an existing draft, it has no research rights.** It may
re-time, re-image, reorder and compress what the draft already contains. It may not add a fact, a
number, an age, a name, a date, a physical action or a causal claim that isn't already there.

- **Compress, never delete.** Facts in the draft survive into the output. A number cut as inert is
  reported, not quietly dropped.
- **Never soften a sourced figure.** "Forty percent" does not become "nearly half." Hedged stays
  hedged.
- **Flag, don't invent.** If a beat wants a fact the draft doesn't have, raise it and ship without it.

> RESEARCH REQUEST — [entry]. [What the beat needs.] [Why it would be the stronger exit.]
> Not asserting it. Entry ships without it unless sourced.

The failure mode this exists for: an aggressive lift pass does not distinguish between intensifying
something already present and asserting something new. Both feel identical while writing.

**Mode 2 note.** The sincere-belief beat asserts nothing new — it re-describes intent the draft
already contains. If an entry has no want, no named party or no stated assumption, it runs Mode 1 and
raises a request. Never invent an assumption to give an entry a tragedy.

---

## Core Voice Formula

> Concrete scene → useful fact → dry reaction → escalation → reversal or payoff

A flexible rhythm, not a template. Skip any beat that adds nothing.

> The engineers covered the tower in iron plates and loaded catapults onto nine separate floors. Hundreds of men pushed from underneath while eight enormous wheels carried the structure forward. It was less a vehicle than an office building with hostile intentions. Then it reached Rhodes, where its size stopped looking impressive and started looking convenient to target.

The facts carry the paragraph. The joke clarifies the visual. The last line reverses the apparent
advantage.

---

## Personality Density

Enough that a narrator is present. Not so much that the history stops.

A personality beat can be a short reaction, a dry judgment, a modern comparison, a compressed ironic
observation, a grim understatement, or a factual reversal.

What to listen for when reading it back:

- Two overt jokes back to back. The second one always sounds cheap.
- Every paragraph landing on a punchline.
- Every section landing on a punchline. Some should end on damage, failure, or a hard fact.
- A stretch where the wit is running but nothing is being explained.
- A section with no narrator in it at all.

The opening carries the heaviest retention load and can afford more personality.

**A Mode 2 entry can run almost humourless, but it still needs at least one moment of company or it
reads cold.** Drama substitutes for wit. Nothing substitutes for a narrator.

---

## Sentence Rhythm

Mix hard within a paragraph: one longer explanatory sentence, one medium factual one, one short
reaction or turn, one that escalates or reverses.

> The cannon required a stone ball weighing hundreds of kilograms and a crew willing to spend hours preparing a single shot. Its barrel was longer than many houses. Reloading was not rapid. Neither was anything else nearby once it fired.

**Short lines must earn their space.** *That was the theory. It worked once. The wall disagreed.
Subtle it was not. Logistics had arrived. Then physics intervened.* Not: *that was crazy, pretty
wild, things got worse, let that sink in.*

**Don't let the cadence automate.** Across a script, let one section run mostly factual and stop
abruptly, one use a longer absurd comparison, one delay the joke to the final line, one carry no joke
at all, one open on the consequence before naming the subject. Predictable wit is another exit ramp.

**Rhythm is a decision per beat.** Fragment where something lands. Let the sentence run where the
mechanism needs room. Whatever average falls out of those decisions is a by-product — writing toward
a number produces the rhythm-uniformity the channel skill identifies as the tell of generated writing.

---

## The Narrator in the Room

The single biggest lever, and the easiest to leave out. The viewer's pleasure is watching someone
who is visibly interested take them through this. In third person the narrator's attitude lands on
the *material* rather than on the viewer, but he is just as present.

**Say the quiet part flatly.** State the decision, then let a short sentence carry the eyebrow.
> The Directorate proposed sending it up the beach on its own. This was approved.

**Ask the obvious question the record didn't.**
> Nobody seems to have asked what would happen if they didn't fire together. It is the first question.

**Refuse the grand claim.**
> The design was described as revolutionary. It was certainly unlike anything else, which is a different claim.

**Take the promise literally.**
> It was advertised as mobile. The road network was not consulted.

**Give credit where it's absurd.**
> To be fair to the design, it did move.

**Be cheerful about grim logistics.**
> Assembly took six weeks, which is a long time to be visible.

**The double-take.** Repeat the fact as though checking it. This is the third-person form of *are you
serious?*, the biggest lever in the StickTory template, and it survives the transfer intact.
> The plan required the crew to run toward the explosion. That was the plan.

**The warm aside about a person.** Not a judgment, not a wink — a small human detail the narrator
clearly enjoys knowing.
> One of the engineers was Sub-Lieutenant Nevil Shute, later better known as a novelist.

Placement: the sharp forms belong after a failure or alongside an institutional decision. The warm
form is the only one safe immediately before a Mode 2 belief beat.

---

## Humor Engines

Use the engine the material offers. Don't force all of them into every section.

**A. Dark understatement.** A severe consequence in restrained language. *Survival was not the design
priority. The crew received very little margin for professional development. Medical support remained
theoretical.* The line must follow a concrete fact, or it's empty sarcasm.

**B. Bureaucratic absurdity.** An outrageous decision treated with administrative calm. *The proposal
advanced to testing, which was generous of the proposal. The army approved the concept before reality
completed its review.* Best for failed prototypes, procurement disasters and vanity projects.

> **Humor attacks the institution, never the harm.** Across 22 competitor scripts this holds without
> exception: the darkest subject in that corpus carries the *lowest* share of humor attached to
> suffering, and aims its jokes at the bureaucracy around the atrocity instead. Joke about the
> committee that approved the weapon. Never about the men it landed on.

**C. Scale comparison.** *Closer to a moving apartment block than a siege engine. The barrel occupied
the sort of space normally reserved for a railway carriage.* Familiar objects with stable scale, one
strong image rather than several weak ones, no memes or celebrities, dimensions verified first.

**D. Ironic label versus outcome.** *Demetrius was called "the Besieger." Rhodes complicated the
branding.* Strongest when the irony is already in the record.

**E. Mechanical deadpan.** Describe the mechanism accurately, then acknowledge what that implies.
*The rockets were attached around the wheel so it would spin forward. Direction was more of an
aspiration. The recoil system absorbed the first shock. The crew absorbed the rest.*

**F. Grim arithmetic.** Two sourced numbers side by side, mismatch as the joke. *One shot required
hundreds of men. The target required one wall.* Never invent the calculation.

**G. Compressed judgment.** One brief opinion after the evidence. *Sensible was not the brief. The
engineers had solved the wrong problem perfectly. The concept had ambition. Mobility did not.*
Micro-judgments create human authorship, and must stay defensible from facts already stated.

### Sarcastic reassurance without second person

Reassurance that collapses, kept observational:

- The armor protected the crew from arrows. The fire, smoke, collapsing timber and trapped exits remained separate issues.
- The weapon could be moved by rail. Unfortunately, wars were not always scheduled beside one.
- The blast was tested far from major cities. "Far" became a relative term at fifty megatons.

At most one of these per short section.

---

## Entry Construction

**Open on the object, action or consequence.** *A forty-metre tower began rolling toward Rhodes. The
castle offered to surrender before the trebuchet was finished.* Not era context, inventor biography,
definitions, abstract statements about warfare changing, or a backward reference that only means
something if you saw the last section. *Mode 2 exception: open on the want; the object arrives one
beat later as its answer.*

**Name the grip early** — spectacle, absurdity, irony, stakes, mystery, failure or scale — inside the
first two or three sentences.

**Attach humor to the fact.** Not *the weapon was huge, that was hilarious*, but *the weapon needed
two parallel railway tracks, making "mobile artillery" a technically correct description with
unusually strict terms and conditions.*

**Escalate with a worse or stranger fact** — a larger number, a hidden limitation, a human cost, a
failed field result, a logistical burden, an ironic order, a strategic consequence. The next promise
arrives before the last payoff goes cold.

**Exit after the real payoff.** Once the spectacle, absurdity or reversal has landed, leave. No museum
location, no inventor biography, no repeated specifications, no legacy summary, no lesson, no formal
bridge.

---

## Transitions

**Default: hard cut.** Section payoff, hard visual cut, era header, new subject acts immediately. No
transition sentence is required merely because the era changed. The channel skill's cap on spoken era
headers wins over this default.

**A bridge survives only if it delivers** escalation, causal consequence, contrast, a reveal, an
original joke, or a drawable image.

> Good: Timber towers could reach the wall. Counterweights made it possible to remove the wall instead.
> Bad: Moving into the medieval era, weapons continued to become larger and more advanced.

Never "next," "now," or "moving on" as structural filler.

---

## Technical Explanation

Mechanics stay understandable beneath the personality. State what moves, what supplies the force,
what the force does, one familiar comparison if needed, then back to the historical consequence.

> A counterweight dropped at one end of the beam, whipping the throwing arm upward at the other. The sling extended that motion like an extra joint, releasing the stone near the top of the arc. It was a mechanical lever scaled until the wall became the smaller object.

The analogy clarifies the mechanism. It doesn't replace it.

---

## Fact and Joke Sequencing

> Fact first. Interpretation second. Joke third.

Never joke first, unsupported claim second, source buried later. The history should still be
understandable with every humorous line removed. Humor sharpens the script; it doesn't hold it up.

Hold the channel skill's density **across the entry** rather than sentence by sentence. Every section
still carries a date, a named individual and a hard number — those are cheap and the authority rests
on them. But the belief beat, the pivot and the exit don't need to carry facts, and forcing them to is
what kills those lines.

### Numbers that draw, numbers that don't

Keep a number if it makes a picture: *ten feet across*, *seventy rockets* when seventy is the thing
that fails, *sixty miles an hour*, a date, a name.

Cut it if it's a second measurement of the same object, a figure restating a requirement already
stated, or anything that never returns.

The tell for over-research isn't how many numbers a passage has, it's how many are inert. Four vivid
ones in a row read fine. Two dead ones read like a datasheet.

One thing to watch: a line you cut may have been breaking up a run of specs without anyone noticing.
After cutting, read the surrounding passage back.

---

## Tonal Limits

No meme phrasing, internet slang, stand-up setup language, or winking at "the video." No repeated
*apparently* or *because of course* jokes. Not *classic [country]*, *what could go wrong?*, *spoiler
alert*, *let that sink in*, *welcome to…* punchlines, or casual praise like *kind of awesome*. Never
describe graphic suffering for amusement.

The delivery should work read by a serious narrator with a slightly raised eyebrow.

---

## Originality

Before approving a line: is the wording original, does the humor come from this specific fact, could
it be pasted into ten unrelated videos, and does it sound like ExplainTory or like an impression of
another narrator? Cut anything failing the first, second or fourth. Portable punchlines are a warning
sign; specific historical observation is stronger and safer.

---

## Before You Ship

Read the section out loud. That's the test. Everything below is what to listen for, plus two
mechanical checks for things that are simply banned.

By ear:

- Does the opening give a picture in the first sentence?
- Is anyone in the room? Can you hear a narrator, or is this just information arriving?
- Is there a stretch where the wit runs and nothing gets explained?
- Does the section end after its payoff, or does it keep going?
- Mode 2: is the design believed before it breaks, and does the mistake land at the reversal rather
  than before it?
- Does any number sound inert?
- Was any fact from the draft lost, or any new one asserted?

Mechanical, because these are binary:

```bash
grep -nEi '\b(you|your|yours|yourself|yourselves)\b' script.md   # second person
grep -n '—' script.md                                            # em dashes
grep -nEi 'what could go wrong|spoiler alert|let that sink in|because of course' script.md
```

Across the finished script: humor should thin as the stakes rise rather than run flat; at least one
major section should be nearly humourless; no two entries should lean on the same joke engine; the
technical explanations should still be complete; and the dramatic entries should be few and never
adjacent.

> **Open question, not a rule.** Across 22 StickTory scripts the humor curve is a clean decay —
> roughly three times the joke rate at the start as at the end, with nothing breaking the pattern.
> Whether a third-person listicle behaves the same way is untested. Don't act on it until an
> ExplainTory script has been published and its curve mapped.

---

## Compact Drafting Commands

**MODE 1 — DRY WIT**

> Write in ExplainTory's factual third-person voice with faster dark-wit rhythm. Open on a drawable action or consequence. Keep a narrator in the room — someone visibly interested, reacting to the material rather than to the viewer. Attach every joke to a sourced fact, and aim it at the institution rather than the harm. Fragment where a beat lands; let the sentence run where the mechanism needs room. Use a concrete modern comparison when it clarifies scale. Escalate into a limitation, consequence or ironic reversal. Exit after the payoff. Hold fact density across the entry, not sentence by sentence, and let the payoff breathe. Keep numbers that draw a picture and cut the ones that don't. Hard cuts between eras unless a bridge adds real escalation or humor. Never use second-person narration, viewer roleplay, em dashes, meme language, copied catchphrases, or close imitation of another creator's wording. Add no fact the draft doesn't already contain.

**MODE 2 — DRAMATIC**

> Write this entry as a small tragedy in ExplainTory's factual third-person voice. Open on the want: a problem someone needed solved and could not solve. Name the responsible party. Introduce the subject as the answer to that want. Give the narrator one warm moment somewhere in there — a human detail he clearly enjoys knowing — but no wink at the design's expense before the belief beat. Make the case for the design sincerely, in however many words it takes to be believed. Then name the single assumption everything rested on, standing alone and directly against the belief, and break it immediately — never earlier, never pre-explained. Let the pivot breathe before the consequence lands. End cold on one device, no joke after the final line. Keep numbers that draw a picture and cut the ones that don't. No second person, no em dashes, no meme language. Add no fact the draft doesn't already contain; if the want, the party or the assumption isn't there, run Mode 1 and raise a research request.

---

## Priority Order

1. Accuracy and source integrity
2. The Fact Guard
3. Main ExplainTory channel skill
4. Retention doctrine and payoff proximity
5. Clarity and drawability
6. This voice overlay
7. Individual joke preference

A stronger joke never outranks a clearer or more accurate explanation.

### Density carve-out — the reason v1.0 did nothing

Item 3 does **not** extend to humor density, personality density or sentence rhythm. When this
overlay is loaded, its guidance on those supersedes the channel skill's "~1 dry observation per
250–300 words," which is the unloaded default and applies only when this overlay is absent.

Without the carve-out the ranking is circular: the overlay exists to raise density, the channel skill
caps density, and the channel skill outranks the overlay — so the overlay can never take effect. That
is what v1.0 did, and it is the most likely single cause of the overlay reading as though it were
doing roughly a quarter of its job.

### Enforcement scale for fact floors

Item 3 also does not extend to the **scale** at which fact floors are enforced. When this overlay is
loaded, "a checkable fact every two or three sentences" is held across the entry rather than sentence
by sentence, and the belief beat, the payoff breath and the entry exit are free to carry none. The
per-section date, named individual and hard number are unchanged.

The sentence-scale reading doesn't forbid the strongest lines outright — it makes them feel like
violations while drafting. A writer holding "a fact every two or three sentences" doesn't write the
sincere-belief beat; they write "the design was approved in 1943 after Admiralty review," which adds
a fact and kills the moment. It also collides with letting a payoff breathe, which needs fact-free
space by definition.

Everything else in the channel skill still outranks this document: structure, entry ordering,
kill-line timing, era-header caps, word budgets, and the no-outro rule.
