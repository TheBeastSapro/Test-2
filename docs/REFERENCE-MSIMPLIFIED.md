# Measured: M Simplified

A reference format taken apart so it can be reproduced rather than described. Every
number here was measured on 2026-08-07, not estimated — the channel listing and the
outlier scores from the metadata API, the edit from watching the top video, the script
template from its transcript, and the audience reading from its comments.

Recorded because a measurement nobody wrote down is a measurement that gets made again
differently. Where a figure is a judgement rather than a count, it says so.

## The channel

| | |
|---|---|
| Handle | `@MSimplifiedx` (`UCqXlPGw_s8Mr7YOSVZYjWOg`) |
| Subscribers | 68,400 |
| Videos | 33 |
| Total views | 11,696,948 |
| Mean views | 354,453 |
| Started | 2025-12-11 |

Eight months old, 33 videos, 11.7M views. That ratio is the reason this channel is
worth taking apart: the format is doing the work, not the back catalogue and not the
subscriber count.

### Outliers

| Video | Views | Multiple | Runtime |
|---|---|---|---|
| Doctor Nowhere's BIGGEST Monsters Explained in 9 Minutes | 1.9M | 5.4× | 8:52 |
| Trevor Henderson Biggest Giants Explained in 9 Minutes | 1.5M | 4.2× | 9:05 |
| Trevor Henderson's Largest Creatures Explained in 9 Minutes | 980K | 2.8× | 8:40 |
| Analog Horror Largest Monsters Explained in 9 Minutes | 969K | 2.7× | 9:38 |
| Creepiest Japanese Urban Horror Legends Explained in 8 Minutes (Part 2) | 916K | 2.6× | 8:38 |
| Creepiest SCPs Explained in 9 Minutes | 634K | 1.8× | 9:16 |
| Creepiest Sea Creatures Explained in 8 Minutes | 588K | 1.7× | 8:47 |
| Largest SCP Creatures Explained in 8 Minutes | 575K | 1.6× | 8:12 |

Runtime range across the outliers is 8:12–9:38. Nothing is short, nothing runs long.

### The title

One formula, on every video:

```
[Franchise or category] [superlative] Explained in [N] Minutes
```

`Biggest` / `Largest` / `Creepiest` are the whole superlative vocabulary. The number is
the real runtime rounded up, and it is a promise of *brevity* — the title's job is not
mystery, it is "this is bounded and you will get all of it".

The franchise slot is where the search demand lives: Trevor Henderson, SCP, Doctor
Nowhere, Analog Horror, Japanese urban legends. The channel is not competing on the
topic, it is packaging an existing fandom's canon.

Note what this format does **not** do: no question titles, no withheld outcome, no
parentheticals except `(Part 2)`, no ALL CAPS beyond the franchise's own styling.

## The script

Seven segments, roughly 62 seconds each, plus two calls to action. Every segment is the
same four parts in the same order:

1. **The name, spoken bare.** "Amber." / "House Walker." / "Driving down the highway."
   A noun phrase and a full stop. This is also the on-screen title card.
2. **An encounter anecdote**, ~30s. Third person, an ordinary person in an ordinary
   place, present-tense build. Always the same shape: something is noticed → it is
   misread as mundane → it moves → the horror lands.
   > "One night, a young man noticed his neighbor's lights flicker. He looked outside
   > and saw something tall standing beside the house. At first, it didn't move. Then
   > suddenly, its arm stretched forward and smashed through the window."
3. **Physical description and stats**, ~20s. Switches register completely — from story
   to specification. Always carries a height in metres, usually a weight range in kg,
   often the imperial conversion.
   > "Amber is a tall, distorted humanoid with a reddish-brown body and extremely long
   > limbs, estimated to stand around 23 m in height."
4. **Survival instructions**, ~8s. Opens verbatim: **"To survive this creature,"**
   followed by two or three imperatives.
   > "…stay away from windows at night, especially during fall and winter. Keep them
   > secured. If seen, do not look at it and create distance immediately."

### The source: one fandom wiki page per segment

The segment structure is not invented. It is the **section structure of the creature's
fandom wiki page**, and both the script and the artwork come from the same page.

Verified against `doctor-nowhere-creatures.fandom.com`, read through the MediaWiki API
(`action=parse&page=Amber&prop=wikitext`). The page carries:

| Wiki | Video |
|---|---|
| `image=Amber111.png` (1284×1284 PNG) | the creature cutout used in every Amber shot |
| `height=Around 13 to 33 feet`, `weight=Approximately 456 lbs (206 kg)` | the on-screen stat card |
| `==Appearance==` | the specification beat |
| `==Behaviour==` | the encounter anecdote |
| `==How to Survive==` | the survival block, verbatim as a section name |

The prose tracks it closely. The wiki's Appearance section reads "a vaguely humanoid
creature with a reddish-brown skin tone, disproportionately long arms and legs, long
fingers strong enough to break glass, and an eye that can split open to reveal a large
mouth in the middle of its chest. No discernible head is present." The narration reads
"a tall, distorted humanoid with a reddish-brown body and extremely long limbs … it has
no head, and its most disturbing feature is a large eye on its torso that can split open
into a mouth. Its fingers are long and strong enough to break through windows."

The anecdote is the wiki's too. The page records "A young man in a small town in
*Tennessee* reported watching Amber break its hand through the window of his neighbor's
home and retrieving a child that lived there and popping the child into its mouth." The
video opens on exactly that encounter, dramatised into present tense.

**One discrepancy, recorded rather than explained away.** The wiki gives Amber's height
as 13–33 feet and its weight as 456 lbs. The video says "around 23 m" — roughly 75 feet
— and does not state a weight for this creature. So the prose is taken from the page and
the headline figure is not. This document does not know where the video's numbers come
from, and does not guess.

The channel's own name for its segments is on the page: **"How to Survive"** is a wiki
section heading, not a scriptwriting choice.

The stats and the survival block are the format's actual invention. The anecdote is
what every horror-narration channel does; the switch into specification and then into
instructions is what makes it feel like a briefing rather than a campfire story, and it
is what the audience quotes back (below).

### The calls to action

* **Mid-roll at 3:07**, after segment three of seven — a little past a third:
  "If you've made it this far, you probably like this kind of content. So don't forget
  to like, subscribe, and drop a comment."
* **End at 8:36**: like and subscribe, then — the load-bearing half —
  "tell me in the comments which creature or horror topic you want to see in the next
  video."

That last line is not politeness. It is the topic pipeline, and the comments show it
working (below).

## The edit

Measured by watching the first 150 seconds of the 1.9M-view video.

**Assets, by share of screen time**

| Kind | Share | Provenance |
|---|---|---|
| Creature artwork | ~70% | **sourced canonical art**, reused as PNG cutouts |
| 2D illustration / stick figures | ~20% | the channel's own |
| Background plates | ~10% | generated |

This is the finding an earlier pass of this document got wrong, and the correction
matters more than anything else here.

The creatures are **not generated**. They are the original artworks — Doctor Nowhere's
Amber, Trevor Henderson's House Walker — lifted as cutouts and composited over
background plates. Verified three ways:

* The audience knows the canon and polices it. One commenter corrects the video on Sun
  Man's second form. A generated Amber would be wrong in ways this audience would say
  out loud, and nobody does.
* The same creature image is reused across every shot of that creature; only scale,
  position and a puppet rotation change. Amber's arm at 0:13 moves independently of its
  torso — a separate layer, not an image-to-video clip.
* The cutouts are sharp, with clean edges and a lighting profile that does not match the
  plate behind them. The *backgrounds* carry the generation artefacts — smeared texture,
  incoherent architecture — and the creatures do not.

So the format's asset pipeline is **retrieval, not generation**, for the thing the video
is actually about. Generation is used only for the plate it stands on.

**Motion.** Predominantly static images with a Ken Burns push. A small number of shots
carry real animation — Amber's arm stretching (0:10), the Housewalker's legs (1:07) —
which look like puppet-warp or a short image-to-video loop rather than a generated
clip. Particle overlays are used sparingly: falling snow (0:59), fog (2:18).

The important part is the ratio: motion is the exception, and it lands on the beat the
narration is describing. This is a channel that pays for animation about twice a
minute, not continuously.

**Cutting.** Shots hold **2–4 seconds**, and the rhythm does not change between the
hook and the body. **Hard cuts only** — no dissolves, no whip pans, no glitch
transitions anywhere in the sample.

**Colour.** High-saturation, clean digital. No VHS, no analog-horror grain, no
chromatic aberration, despite the subject matter. Occasional vignette on a reveal.

**Audio.** TTS narration, deep and calm, steady pace. A low suspense pad underneath —
one commenter asks "Why is the music so chill?", which is the format working: the
delivery is flat and the content carries the tension. Diegetic effects on events:
glass shattering (0:11), heavy footfalls (1:07), wind and fog ambience (2:18).

### Text on screen — the finding that matters most

**There are no burned-in narration captions.** None. On a faceless explainer with TTS
narration, which is the one place the whole genre burns subtitles.

What is on screen instead:

* **The monster's name**, top centre, black handwritten-style face, on the segment's
  first shot.
* **Stats** — height and weight — in green/yellow type, appearing on the specification
  beat (0:44, 1:53).
* **Speech bubbles**: white bubble, black text, over the stick-figure inserts.

So the screen carries the *data* and the *gags*, and lets the voice carry the prose.
This is the opposite of the default assumption, and it is not a small stylistic detail
— burning narration captions onto this format would bury the three elements that
distinguish it.

### The gags

Not incidental. There are stick-figure reaction inserts — a man shivering (0:21), a man
running (2:08) — and speech-bubble jokes placed against the horror:

> "There's a good snack in this house" (0:05)

## What the audience actually responds to

From the top comments on the 1.9M video (739 comments):

| Likes | Comment | What it tells us |
|---|---|---|
| 136 | "It looks like a mushroom bigger than yours" 😭👏🏿 | quoting a **speech-bubble gag** |
| 104 | A six-step joke list of "How I'd survive driving down the highway" | riffing on the **survival block** |
| 87 | "3:40 bro screamed in lowercase 💔" | the flat TTS delivery of a scream, as comedy |
| 39 | "3:40 5:35 Ahhh, hmmmm, most calmest man in history" | same |

The single most-liked comment on the video is a quotation of a gag that occupies about
two seconds of a nine-minute video. The second is a parody of the survival block. The
third and fourth are jokes about the narrator's flatness.

**The horror is the premise; the comedy is the engagement.** A reproduction of this
format that copies the anecdotes, the stats and the survival tips but drops the
speech-bubble gags would reproduce everything except the reason people comment.

Two other patterns worth noting:

* **Viewers write their own chapter lists.** Two of the top twenty comments are
  hand-made timestamp indexes. The video has no chapters; the audience made them.
  That is unmet demand and a free structural signal.
* **The comments are the topic backlog.** "I wanna see the Bolid One", "Please make us
  see the Anchorage", "An explanation of some of the biggest SCPs would be awesome" —
  and *Creepiest SCPs Explained in 9 Minutes* and *Largest SCP Creatures Explained in
  8 Minutes* both exist. The end CTA asks for requests and the requests become videos.

## What Forgecast would get wrong today

The gap list, kept current. Struck items name the commit that closed them, because a gap
list that only grows is one nobody trusts, and one that quietly drops finished items
loses the record of what the work was for.

1. ~~**It generates the subject instead of fetching it.**~~ Closed. `research/fandom.py`
   reads the canonical artwork off the wiki, reachable as `read_fandom`. The format's
   b-roll is retrieval, and an audience that polices its own canon will reject a
   generated Amber.
2. ~~**It researches the wrong place.**~~ Partly closed. The wiki reader exists and the
   agent reaches for it; the pipeline's own `research_node` still resolves to
   Tavily/Brave/Wikipedia and does not know about it. Open.
3. ~~**Captions.**~~ Closed. Burning is read off the learned style, and the hook gate
   previews what the render will actually produce.
4. ~~**No name card, no stat card, no speech bubble.**~~ Closed. All three are
   `MotionPlan` kinds; the stat card takes the wiki reader's rows unchanged.
5. ~~**No gag layer at all.**~~ Closed. Bubbles are planned onto the story beat and
   never onto the shot carrying the name card.
6. ~~**Compositing.**~~ Closed. `layers/shot.py` places a subject on a plate, scaled by
   its opaque region and anchored on a horizon.
7. ~~**Transitions.**~~ Closed, and the original claim here was backwards: the renderer
   always hard-cut, so this reference was reproduced by accident and a reference that
   *dissolves* was the one being rendered wrong.
8. **Motion budget.** Open. The segment planner rations motion to the story beat, but
   the pipeline does not use the planner yet.
9. ~~**No comment mining.**~~ Closed. `research/requests.py` tallies what the audience
   asked for, reachable as `audience_requests`.
10. **Chapters.** Open. The audience writes timestamp indexes by hand in the comments,
    publishing chapters is free, nothing generates them, and `vision/chapters.py` — which
    can read them off a reference — still has no production caller.

### Still open, beyond the original list

* **The planner is not in the pipeline.** `edit/segment.py` writes the shot list and the
  agent can call it; `broll_plan` does not. Until it does, a run still decides each shot
  at render time.
* **The wiki's image is often a whole scene, not a cutout.** Amber's is the creature
  between houses, shot through a window. So fetch-then-matte is a real step — and on
  that asset the matte came back `usable=False` and was right to.

## Rights, unresolved

Fandom's site content is CC-BY-SA by default under their terms, but an image uploaded to
a fandom wiki is frequently the original artist's copyright and is hosted there under
fair-use or by permission. The API's `extmetadata` for `Amber111.png` returned no licence
fields, so **this document does not know what licence that image carries** and does not
assume one.

That is a real product constraint, not a footnote: a pipeline that pulls canonical
artwork needs to record where each asset came from and surface it, the way
`footage.attribution_markdown` already does for stock. What it must not do is assume the
answer.
