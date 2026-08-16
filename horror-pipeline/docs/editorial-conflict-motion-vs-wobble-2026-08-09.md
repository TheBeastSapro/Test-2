# Conflict: "nothing is ever static" vs "no idle wobble"

*Created 2026-08-09. This is a RECORD of a conflict, not a decision. It follows the
convention of `chat-transcript-findings-2026-08-08.md`: where two standards disagree,
flag it rather than resolve it. The owner resolves it.*

## The owner's instruction that surfaced it

> "The video shouldn't be measured. It should take those measurements but adapt
> according to the voiceover/script, not to lock with measurements. It should act just
> like how real video editors think, like Vu or competitors. The video should feel
> polished, not feel like it was done by an AI. Viewers shouldn't find any difference."

## The two rules

**House rule #1**, `CLAUDE.md`: *"Nothing is ever fully static. Every held image carries
a continuous slow zoom or pan. Every icon and every text pop animates in."*

**Motion doctrine, Part 2**: idle sine loops (breathe, float, drift, glow pulse) are
BANNED as sustained motion. They read as *"the video is waiting."* A scene that finishes
entering with seconds left is a **planning bug**: add story, not wobble.

## Why both are right

They were written against different failures.

House rule #1 exists because editors delivered 100 percent frozen shots. Vu's first
sample measured pixel-static throughout; Abel's Siren Head section had a five-second
assembled icon grid. The rule fixed a real, repeated, measured defect and it worked.

The motion doctrine exists because a machine applying that rule to every shot produces
constant meaningless drift. Everything moves, nothing means anything. That is an AI tell,
and it is precisely what the owner is asking to avoid.

## The distinction that resolves it

A camera move is legitimate when it is **camera with intent**: it establishes, travels,
and arrives somewhere the narration cares about. It is **wobble** when it exists to keep
a motion metric up.

Same pixels. Different reason. Viewers feel the difference without being able to name it.

The doctrine's own test: pause at any second and something *meaningful* must be
mid-flight — a reveal landing, the camera travelling, an element doing what the narration
says. Note "meaningful", not "something is moving".

## What this changes about the build

**Measurements become failure detectors, not targets.**

| Metric | Wrong use | Right use |
|---|---|---|
| Motion >= 22% | maximise it | catch a dead section |
| avgShotSec 2.2 | set every shot to 2.2 | check the distribution has variation |
| maxHoldSec 4.0 | — | hard failure, keep as is |
| Pops per section | fill a quota | catch tapering in the back half |

**Shot length falls out of the beat, not the other way round.** A tense line holds; a
list beat cuts fast. The 2.2s average in the references EMERGES from variation. It was
never a value any single shot was set to.

**Every beat is assigned a reason to keep moving**, chosen from what the narration is
doing: staged reveal (hold content back, pay it off on narration beats), camera with
intent (establish, travel, arrive), or animated sequence (elements act out the beat).

## Two things a metric-driven build actively destroys

**Stillness before climax.** A scheduled 0.3 to 0.75s pause between the action and its
result. A renderer maximising motion percentage would never insert one, and every reveal
lands softer without it. Dead-zone detection must distinguish a section that has died
from a deliberate dramatic comma, or QC will punish the thing that makes the cut good.

**One current, with reserved vectors that mean something.** The film picks one dominant
direction and ordinary cuts use it. Upward means elevation, a push means going deeper, a
pull means arrival. Spending a reserved vector for variety is the anti-pattern. Only 2 to
3 transition types across a whole video, repeated. A different transition each time is
the amateur tell.

## Supporting evidence already in this repo

- `spec/BUILD-PACKET.md` section 9: *"the model is a very fast, very consistent,
  completely tasteless editor"*, and *"a 25.1 percent motion score and a dead-boring
  section are entirely compatible."*
- `chat-transcript-findings-2026-08-08.md` section 9: when three editors independently
  stalled on the same seven seconds, the script was the cause. An automated pipeline
  *"should refuse to render a beat it has no shot idea for rather than hold on a zoom."*
  Holding on a zoom is exactly idle wobble.
- Motion doctrine: *"Audio is the clock. Re-time scenes to the VO's real word timestamps;
  never rush a read to fit a slot."* The build packet already half-encodes this by using
  word anchors rather than timestamps in sheets.

## Open decision for the owner

Does house rule #1 get restated as something like: *every held image is under a camera
move with a destination, and a shot with no destination is a planning failure, not an
excuse for a slow zoom*?

That keeps the defect the rule was written to catch (frozen shots) while removing the
licence to fill time with drift. Nothing else in the brief changes.

Until this is settled, the sheet generator is not written, because this decides what it
generates.
