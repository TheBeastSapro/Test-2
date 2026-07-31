# Analysis frameworks

Fixed vocabularies. The point of a closed list is that ten analyses become
countable: "6/9 used a contrarian hook" is only meaningful if everyone reaches for
the same word. If a video genuinely does not fit, use `other` and describe it —
that is a signal the taxonomy needs extending, not licence to freestyle.

## Contents

1. [Hook types](#1-hook-types)
2. [Hook–payoff alignment](#2-hookpayoff-alignment)
3. [The 7-section storytelling structure](#3-the-7-section-storytelling-structure)
4. [Format taxonomy](#4-format-taxonomy)
5. [Visual layout vocabulary](#5-visual-layout-vocabulary)
6. [CTA types](#6-cta-types)
7. [Pace bands](#7-pace-bands)

---

## 1. Hook types

The hook is everything before the video has earned attention — in practice the
first 1–5 seconds, ending at the first beat where the promise is fully stated. A
hook usually combines two or three of these; record them in order of prominence,
strongest first.

| Slug | Mechanism | Recognisable by |
|---|---|---|
| `contrarian` | Asserts the common belief is wrong | "Most people don't know", "everyone gets this wrong", "stop doing X" |
| `capability_reveal` | Names a thing the viewer didn't know was possible | "you can just…", "did you know you can…" |
| `transformation` | Promises a state change | "how to turn X into Y", "$0 to $10k" |
| `result_proof` | Leads with an outcome already achieved | "this got 2M views", shows the dashboard first |
| `curiosity_gap` | Withholds the specific thing being discussed | "the one setting nobody uses" |
| `authority` | Establishes standing before the claim | "I've spent 10 years", "as a former X" |
| `callout` | Names the target audience explicitly | "if you're a freelancer, listen" |
| `pain_naming` | Articulates a frustration precisely | "you spend hours on this and it still…" |
| `warning` | Threatens a cost of inaction | "this is costing you", "before you do X, watch this" |
| `in_medias_res` | Opens mid-action, context withheld | no preamble, already demonstrating |
| `question` | Direct question to viewer | "ever wondered why…" |
| `list_promise` | Numbered payload promised | "3 ways to…", "5 tools that…" |
| `story_cold_open` | Narrative first line | "So last week a client sent me…" |
| `stakes_number` | A concrete figure creates weight | "I lost $40,000 learning this" |
| `other` | Fits nothing above — describe it | |

Record three things about the hook beyond its type:

- **verbatim** — exact words, no cleanup
- **duration_seconds** — where the hook ends and the body begins
- **pattern** — the reusable template with specifics removed, e.g.
  `"Most people don't know this, but you can just <ACTION> and get <OUTCOME>"`.
  The pattern is the transferable asset; the verbatim is the evidence.

## 2. Hook–payoff alignment

Score 1–5. This is the most actionable number in the report, so resist rounding it
upward out of politeness.

| Score | Meaning |
|---|---|
| 5 | Delivers exactly what was promised, and more |
| 4 | Delivers the promise |
| 3 | Delivers a weaker version, or delivers late |
| 2 | Partially delivers; the specific promise is dodged |
| 1 | Bait — the promise is not addressed, or resolves into an ad |

Always attach reasoning that names both halves: what was promised, what arrived. A
score with no reasoning cannot be argued with, which makes it useless.

Note the common legitimate case: a video that scores 2 on alignment can still be a
top performer, because bait works on views and fails on trust. Say both.

## 3. The 7-section storytelling structure

Short-form video that performs tends to move through these beats. Not every video
hits all seven, and the *absence* of a section is often the most interesting
finding — a video with no `credibility` beat that still converts tells you the
creator's audience already trusts them.

| # | Section | Job | Typical share of runtime |
|---|---|---|---|
| 1 | `hook_promise` | Stop the scroll, state the promise | 5–15% |
| 2 | `credibility` | Why this speaker | 0–10% |
| 3 | `context_stakes` | Why it matters now | 5–20% |
| 4 | `mechanism` | The actual how — the substance | 30–50% |
| 5 | `proof` | Demonstration, receipts, screen | 10–25% |
| 6 | `objection` | Dissolve the obvious "but…" | 0–15% |
| 7 | `cta` | The next step | 5–15% |

For each section present, record: `name`, `start`, `end`, a short
`transcript_span` quote, `function` (what it does *in this specific video*), and
`strength` (`strong` / `adequate` / `weak` / `absent`).

Then record `completeness` as `n/7`, and — more useful — which sections are missing
and whether their absence looks deliberate.

**Do not force-fit.** If a video is a 12-second single-joke skit, it has
`hook_promise` and nothing else. Mapping seven sections onto it invents structure
that is not there, and invented structure poisons the batch synthesis, where it
becomes a fake pattern.

## 4. Format taxonomy

`primary` is what the viewer would call it; `secondary` is optional.

`talking_head` · `screen_recording` · `voiceover_broll` · `tutorial_walkthrough`
· `listicle` · `case_study` · `pov_skit` · `interview_clip` · `podcast_clip` ·
`text_on_screen` · `react_commentary` · `greenscreen` · `day_in_life` ·
`product_demo` · `ugc_ad` · `compilation` · `other`

Also record:

- `delivery` — `direct_to_camera` / `voiceover` / `on_screen_text_only` /
  `dialogue` / `silent_demo`
- `production_tier` — `phone_raw` (single take, no edit polish) /
  `phone_edited` (cuts, captions, zooms) / `produced` (multi-source, motion
  graphics, colour grade) / `studio`
- `aspect_ratio` — `9:16` / `1:1` / `16:9` / `4:5`
- `evidence` — one line on why you classified it that way

`production_tier` matters more than it looks: it is the proxy for how expensive the
format is to copy, and it feeds `replication.effort`.

## 5. Visual layout vocabulary

This is the part text-only analysis cannot reach, so it is where the watch call
earns its cost. Be concrete and physical.

**Framing** — `close_up` / `medium` / `wide` / `screen_only` / `screen_with_pip` /
`mixed`. Note the subject: face, hands, screen, product, none.

**Captions** — the highest-leverage visual detail in short form:
- `style` — `word_by_word` / `phrase` / `full_sentence` / `none`
- `position` — `centre` / `lower_third` / `upper_third` / `varies`
- `treatment` — weight, colour, outline, highlight colour on the active word
- `burned_in` — true/false (burned captions survive muted autoplay)

**On-screen text** — list each distinct element with its `text`, `role`
(`title_card` / `label` / `emphasis` / `list_item` / `metric` / `arrow_callout`),
and rough timing. Quote it exactly; on-screen text is frequently a second, denser
script running in parallel with the audio, and comparing the two reveals what the
creator thinks the actual message is.

**Motion and pace**
- `cuts_per_minute` — count if feasible, estimate with a stated band if not
- `zoom_pattern` — `jump_zoom` / `slow_push` / `static` / `handheld`
- `transitions` — `hard_cut` / `whip` / `match_cut` / `graphic_wipe`
- `b_roll_ratio` — rough share of runtime that is not the primary subject

**Look** — `colour` (natural / graded / high_contrast / desaturated),
`lighting` (natural / ring / softbox / mixed), `branding` (handle watermark,
recurring lower-third, colour signature).

## 6. CTA types

`comment_keyword` (comment a word to receive something) · `follow` ·
`link_in_bio` · `dm_keyword` · `save_share` · `watch_next` · `subscribe` ·
`purchase` · `none`

Record `verbatim`, `placement_seconds`, and `friction` — how much work the viewer
must do (`none` / `low` / `medium` / `high`). `comment_keyword` is low friction and
feeds the algorithm, which is why it recurs in growth-focused accounts; noting it
as a *choice* rather than a detail is what makes the observation useful.

## 7. Pace bands

Speech rate, from `scripts/metrics.py pace`:

| WPM | Band | Reads as |
|---|---|---|
| < 110 | `slow` | Deliberate, authoritative, or padded |
| 110–149 | `measured` | Conversational, explainer default |
| 150–179 | `brisk` | Energetic, standard short-form |
| 180–209 | `fast` | High-density, rewatch-driven |
| ≥ 210 | `very_fast` | Compressed; often scripted and sped in post |

Pace is only interesting next to format. 200 WPM on a `talking_head` is urgency;
200 WPM on a `voiceover_broll` is information density. Interpret it against the
format rather than in isolation.
