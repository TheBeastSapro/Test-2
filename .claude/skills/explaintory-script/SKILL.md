---
name: explaintory-script
description: Write a finished ExplainTory script from a title alone — research it with sources, confirm the angle and outline at ONE batched gate, then draft and converge on the exact word count before delivering. TRIGGER on "script", "write the script", "new script", "script this title", or any bare video title submitted for writing. Pure scriptwriting; it does not touch voiceover or sound design.
---

# ExplainTory Script

**Sapro gives a title. This gives back a finished, measured script.** One
confirmation in the middle, nothing else. Everything the old chat workflow asked
him — length, tone, structure, audience, what to include — is already answered in
`script_profile.json`, because those answers never changed between videos and
asking again was the waste.

Deliver two files:

- `<Title>.txt` — the script, passing `measure.py`
- `<Title> — research.md` — the sourced fact pack it was written from

Scope: writing only. Voiceover and sound design are separate skills and this one
does not call them, import from them, or produce anything shaped for them.

## The one gate, and why it exists

The back-and-forth was never the problem. **The questions are a control Sapro
installed on purpose so the script does not drift**, and removing them would
trade hours of chat for a finished script that is quietly about the wrong thing.
What cost the hours was spreading those questions across an afternoon, one round
trip at a time.

So the questions still get answered — all at once, up front, with the answers
already filled in. He reads one block and says "go", or changes one line.

**Everything before the gate is research. Everything after it is silent.** Do not
come back with "should the tone be X" or "is 12 minutes right". If a question
matters, it belongs in the gate block; if it does not fit there, the profile
already answers it.

## Pipeline

| Stage | What happens | Asks anything? |
|---|---|---|
| research | build the sourced fact pack | no |
| **spec gate** | angle + outline + budget, in one block | **yes, once** |
| draft | write to the per-chapter budget | no |
| converge | `measure.py` until it passes | no |
| deliver | script + research file | no |

## 1. Research — before any angle is chosen

Do the research first. An angle picked before the sources are open is a guess
that the research then gets bent to support, and bending it is how a script ends
up with a confident claim nobody can source.

Rules, all from the profile's `research` block:

- **Never cite a source you did not open.** Fetch it and read it.
- Primary and contemporary sources outrank encyclopaedias, which outrank
  listicles and content farms.
- **Two independent sources for any number that reaches the hook.** The hook is
  the most-repeated sentence in the video and the most likely to be screenshotted.
- Record what could **not** be verified. That list is the only thing standing
  between an unsourced claim and a script, because an unsourced claim that sounds
  good will otherwise be written in by default.
- Note the strongest counter-argument to the angle. If it holds, the angle
  changes — and that decision is enormously cheaper here than in a draft.

Write `<Title> — research.md` as you go: claim, source, link, and a confidence
mark. It ships with the script. When a fact is questioned three months later,
this file is the answer.

## 2. The spec gate — one block, then silence

Show exactly this, filled in, and wait:

```
  "The Ship That Sank Twice"

  ANGLE     The Vasa did not sink from bad luck. Three people measured the
            fault before launch and were overruled by a king who wanted a
            second gun deck. It is a story about who is allowed to be right.
            (rejected: "famous shipwrecks" — no through-line; "Swedish naval
            history" — the title promises one ship)

  OUTLINE   1  The Order          250   the second gun deck arrives by letter
            2  The Shipwright     250   Hybertsson dies mid-build
            3  The Stability Test 250   thirty men, three passes, stopped
            ...
            8  The Salvage        248   1961, ninety-five percent intact

  BUDGET    12:00 · 2160 words · hook 75 · outro 60 · 8 chapters
  SOURCES   9 opened · 2 claims unverified (listed in the research file)
  RISK      The "overruled by the king" line rests on one 1628 transcript.

  go?
```

Four things and a question. **The rejected angles matter** — they are what
proves the chosen one was chosen rather than stumbled into, and they are how he
redirects in one word if the pick is wrong.

Then stop. A gate that is followed by more questions is not a gate.

## 3. Draft to the budget, chapter by chapter

`measure.py --plan --runtime 12 --chapters 8` gives the per-chapter word target.
Write each chapter to its own number, not to a feeling about the whole.

This is the difference that ends the loop. A script written as one 2,160-word
blob and then trimmed loses whichever paragraphs are easiest to cut, which are
rarely the weakest ones. A script written as eight 250-word chapters lands
within a few percent on the first pass, and the convergence below is a trim
rather than a rewrite.

Writing rules live in the profile — `hook`, `rhythm`, `substance`, `voice`,
`retention`. The ones that matter most in practice:

- **The hook opens on the strangest verifiable fact, stated flat.** No set-up, no
  promise of what the video will cover. The banned-opener list in the profile is
  enforced by the gate, so "Have you ever wondered" fails the build rather than
  reaching him.
- **Every chapter ends on something the next one answers.** A chapter that
  summarises itself is where the viewer leaves.
- **Specific beats summarised.** "Forty-one ships" over "a fleet". This is
  measured as fact density and it is the gate that catches a script which passes
  everything else and still says nothing.
- **Vary sentence length on purpose.** A four-word sentence after a thirty-word
  one is the whole rhythm of the read. Uniform length is measurable and it is the
  signature of writing that sounds machine-made.

### The overlay is a collaborator, not an audience

The channel runs a dramatic overlay in the StickTory style and measures **50–55%
average view duration** with it. That number is a constraint, not a target to
beat: the current style is what produces it, so a generated script matches that
style rather than improving on it with a structure nobody has tested.

Practically: **state the dramatic beat as a fact and let it land.** The overlay
dramatises; the narration does not need to. Adjectives compete with the visual,
facts feed it. Put reveals at chapter boundaries, where the overlay cuts.

## 4. Converge — measure, never estimate

```bash
python3 scripts/measure.py "<Title>.txt" --runtime 12 --chapters 8
```

**Do not hand over a script that has not passed this.** Exit code 0 or it is not
finished.

The output is not a verdict, it is an edit list with targets and numbers:

```
  EDIT LIST:
    - [length] cut 118 words
    - [chapter_balance] chapter 4 'The Ledger': cut 118 words
    - [banned_phrases] rewrite those lines: testament to, stark reminder
```

Execute it literally, re-run, repeat. It terminates because every instruction
names a place and an amount. This is the entire reason the tool exists: a model
cannot count its own words. It estimates them, confidently and wrongly, and
"make it a bit longer" aimed at that estimate is what turned a script into an
afternoon.

So: **never report a word count from reading the draft.** Read it out of
`measure.py`. Never claim a script is "about the right length" — run the gate.

Warnings (`chapter_balance`, `sentence_rhythm`, `sentence_max`,
`no_stage_directions`) do not block delivery, but say which ones are outstanding
in the delivery message. Do not report a clean run when the run was not clean.

## 5. The pronunciation guide

Every script ends with one, because the names in it are the ones a reader gets
wrong:

```
Pronunciation

Vasa — VAH-sah
Hybertsson — HOO-bert-son
Klas Fleming — KLAHS FLEM-ing
```

The heading must literally contain the word *Pronunciation* — that is what the
detector matches, and without it the section is not recognised as an appendix.
Respellings only, never IPA. Every non-obvious proper noun in the script earns an
entry; the gate reports the count but cannot know which names are hard, so add
them as they are written rather than hunting at the end.

## Calibration — make the profile his, not mine

`script_profile.json` ships with some values measured and some marked
`default_unverified` in its `_provenance` block. **Those are starting points, not
facts about the channel.** Point the calibrator at real published scripts and it
replaces them with measurements:

```bash
python3 scripts/calibrate.py ~/scripts/ --write
```

It also settles a question that is otherwise pure speculation — which decisions
actually change between videos:

```
  quantity                  median      min      max   verdict
  runtime (min)               11.4     10.0     11.5   CONSTANT
  chapters                     8.0      7.0      8.0   CONSTANT
  hook words                    31       31       31   CONSTANT

  ASK PER VIDEO: nothing — every measured quantity is stable
```

Anything it calls `VARIES` belongs in the spec gate. Anything `CONSTANT` gets
locked and never asked again. A writer usually cannot say from memory whether
their videos are all the same length; the files know.

It deliberately does **not** touch taste — banned phrases, hook rules, voice.
A corpus of good scripts cannot tell you what a bad one would have contained.

## Do not

- **Do not ask a second question.** One gate. If something is genuinely
  undecidable, put it in the gate block as a flagged risk line and proceed with
  the stated assumption.
- **Do not deliver an unmeasured script.** The gate is cheap; his time is not.
- **Do not report length, density or chapter counts from reading.** Every number
  in the delivery message comes out of `measure.py`.
- **Do not write a fact the research file cannot support.** If it is too good to
  cut, source it or mark it contested in the script itself.
- **Do not restructure to beat 50–55% AVD.** That number is what the current
  style already earns. Match it.
- **Do not import from, or write for, the voiceover or sound-design tooling.**
  This skill is scriptwriting only.
