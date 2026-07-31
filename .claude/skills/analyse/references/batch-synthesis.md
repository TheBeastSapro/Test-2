# Batch synthesis

This is the step that justifies pasting nine links instead of one. It is also the
step where this kind of analysis usually goes wrong, because "find the patterns" is
an invitation to produce confident-sounding generalisations from three data points.

The discipline below exists to stop that. A pattern the user acts on and that turns
out to be noise costs them real time and real reach.

## The core rule

**A pattern is a claim about frequency, so it must carry a count.**

Every entry in `patterns` has `prevalence: "n/total"` and per-video `evidence` with
quotes. Before writing any pattern, you should be able to point at the specific
videos. If you can point at one, it is an observation about that video — put it in
`outliers`. Below `2/n`, it is not a pattern.

Count with the script rather than by memory:

```bash
python3 scripts/metrics.py batch analysis/*.json
```

It tallies hook types, formats, CTA types, structure completeness, missing
sections, pace bands, and alignment scores across every per-video JSON, and prints
the counts and ranges. Deriving patterns from that table instead of from
recollection is the difference between a finding and a vibe.

## Process

**1. Build the table.** Run the script. Look at what is actually frequent.

**2. Write patterns from the counts.** Each one names a mechanism, not a vibe.

- Vibe: "These creators use strong hooks." Unfalsifiable and unusable.
- Mechanism: "6/8 hooks name a specific UI action (`/analyze`, `cmd+K`) rather
  than an outcome." Countable, quotable, copyable.

**3. Actively hunt counter-examples.** For every pattern, check the videos that
*don't* fit and record them in `counter_examples`. A pattern holding 6/8 with the
two exceptions named is trustworthy. The same pattern presented as universal is
not, and the exceptions are frequently the interesting part — they are either the
best video in the set or the worst.

**4. Separate patterns from trends.** A pattern is what is *common* in the set. A
trend is a claim about *change over time*, and it needs publish dates and enough
spread to support it. Eight videos from one week cannot show a trend; say so in
`confidence_reason` rather than dressing a snapshot as a direction. It is genuinely
fine — and more useful — to write `"trends": []` with a note that the sample cannot
support any.

**5. Derive insights.** An insight is a *relationship* between two things you
measured, which is what neither a single-video report nor a frequency table can
show. This is the highest-value output in the whole skill.

The shape to look for: "every video with X also has Y." For example — videos scoring
4–5 on hook alignment all place the demo before the product name; the two scoring 2
name the product first. That is an insight because it connects a structural choice
to a quality outcome, and it converts directly into a rule: demo first, name second.

Each insight needs `reasoning` (the evidence path) and `actionable_as` (the rule in
one line). If you cannot write `actionable_as`, it is an observation, not an
insight.

**6. Write the playbook.** The compressed synthesis: the hook formula, the section
order, the format, target metric ranges, the CTA, and what to avoid. This is what
the user will actually reread, so keep every field concrete enough to execute
against — `"duration_seconds": "40-60"` rather than `"keep it short"`.

## Honesty requirements

State the sample's limits in `scope.caveats` every time. The ones that matter:

- **Single creator.** Patterns across one creator's videos describe *that creator's
  style*, not what works in the niche. This is the most common shape of input —
  someone pastes eight videos from one account — and the most commonly overstated
  conclusion.
- **Survivorship.** Videos get pasted because they performed. Without the
  underperformers you cannot know whether a pattern causes success or merely
  accompanies it. Never write that a pattern *causes* performance from a set of
  winners alone.
- **No engagement data.** Instagram and TikTok watch calls return no view or like
  counts, so "high-performing" rests on the user's selection, not measurement. If
  the user did not say why these videos, ask or state the assumption.
- **Narrow time window.** Kills trend claims. Say so.
- **Partial batch.** If videos failed, `analysed_count` < `video_count` and the
  report says which and why, up front.

Stating a limit does not weaken the analysis — it tells the user which conclusions
they can spend money on. A synthesis over 4 videos that says "this is a style read
of one creator, not a niche pattern" is more useful than one over 40 that implies
laws of nature.

## Report structure

```markdown
# Batch analysis: <slug>
<n> videos · <platforms> · <date range> · <m> analysed, <k> unavailable

## Scope and limits
What this set is, and what it cannot tell you.

## Patterns
### <Pattern claim> — 6/8
Evidence: quotes with video ids.
Counter-examples: the videos that don't fit, and why.

## Trends
Or: why this sample cannot support any.

## Insights
### <Insight>
Reasoning · Actionable as: <one-line rule>

## Outliers
The videos that broke the pattern, and whether that's worth a look.

## Playbook
The compressed, executable version.

## Per-video index
| # | Creator | Format | Hook types | Align | WPM | Structure |
```

The per-video index table is what makes the batch report navigable, and it is the
easiest thing to feed into a UI later — one row per video, all comparable fields.
