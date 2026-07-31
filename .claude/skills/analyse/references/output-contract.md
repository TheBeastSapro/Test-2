# Output contract

The JSON is the interface. Reports get read once; the JSON gets consumed by batch
synthesis, by storage, by whatever is built on top. Renaming a field to something
that reads nicer breaks those consumers silently, so treat the field names as fixed
and put the nuance in the values.

Two rules that carry most of the weight:

- **`null` means "not determined". Never use `0`, `""`, or `"unknown"` for it.**
  `words_per_minute: 0` says someone stood there in silence; `null` says you could
  not measure it. A consumer averaging those two gets a very different answer.
- **Every enum value comes from `references/frameworks.md`**, or is `"other"` with
  a description. Free-text where an enum belongs is what makes a dataset
  un-aggregatable.

## Per-video schema

`schema_version` is `"1.0"`. Bump it if you change field meanings.

```json
{
  "schema_version": "1.0",
  "analysed_at": "2026-07-31T00:00:00Z",

  "source": {
    "url": "https://www.instagram.com/reel/DZU1D_8OI62/",
    "platform": "instagram",
    "video_id": "DZU1D_8OI62",
    "creator_handle": "@kallawaymarketing",
    "creator_followers": 13000,
    "status": "analysed",
    "watched_span": "full",
    "unavailable_reason": null
  },

  "metrics": {
    "duration_seconds": 47.0,
    "word_count": 231,
    "words_per_minute": 295,
    "pace_band": "very_fast",
    "hook_duration_seconds": 3.2,
    "hook_share_of_runtime": 0.068,
    "cuts_per_minute": 38,
    "views": null,
    "likes": null,
    "comments": null,
    "engagement_rate": null
  },

  "transcript": {
    "full_text": "This is how you turn Claude into a social media machine...",
    "segments": [
      { "start": 0.0, "end": 3.2, "text": "This is how you turn Claude into a social media machine." }
    ]
  },

  "format": {
    "primary": "screen_recording",
    "secondary": "voiceover_broll",
    "delivery": "voiceover",
    "production_tier": "phone_edited",
    "aspect_ratio": "9:16",
    "evidence": "Entire runtime is screen capture of the Claude UI with a voiceover; no face on camera."
  },

  "topic_and_angle": {
    "topic": "Using Claude for social media content research",
    "angle": "A single slash command replaces manual competitor research",
    "claim": "One plugin gives Claude 14 social media skills, including /analyze",
    "audience": "Content creators and social media managers already using AI tools",
    "desire": "Faster growth without more manual research hours",
    "why_now": "Positioned as newly possible — 'Claude just changed social media forever'"
  },

  "storytelling_structure": {
    "framework": "7_section",
    "completeness": "5/7",
    "missing_sections": ["credibility", "objection"],
    "absence_looks_deliberate": true,
    "sections": [
      {
        "name": "hook_promise",
        "start": 0.0,
        "end": 3.2,
        "transcript_span": "This is how you turn Claude into a social media machine.",
        "function": "States the transformation and frames it as little-known.",
        "strength": "strong"
      }
    ]
  },

  "hook": {
    "verbatim": "This is how you turn Claude into a social media machine. Most people don't know this, but you can just type /analyze into Claude, paste any video link, and get a full analysis",
    "duration_seconds": 3.2,
    "types": ["capability_reveal", "contrarian", "transformation"],
    "pattern": "Most people don't know this, but you can just <SIMPLE ACTION> and get <DISPROPORTIONATE OUTCOME>",
    "promise": "Paste a link, receive a complete breakdown of why the video works",
    "payoff_alignment": {
      "score": 3,
      "reasoning": "The mechanism is shown and is real, but the payoff is gated behind installing a specific paid plugin, which the hook does not disclose."
    },
    "visual_hook": "Cursor typing /analyze into a live Claude input, output streaming immediately",
    "text_hook": "Claude Just Changed Social Media Forever",
    "rewrite_templates": [
      "Most people don't know you can <ACTION> in <TOOL> and get <OUTPUT> in one step"
    ]
  },

  "visual_layout": {
    "framing": "screen_only",
    "subject": "screen",
    "captions": {
      "style": "word_by_word",
      "position": "centre",
      "treatment": "heavy sans, white with black outline, active word highlighted",
      "burned_in": true
    },
    "on_screen_text": [
      { "text": "Paste URL And Get Every Secret In That Video", "role": "title_card", "start": 4.0, "end": 8.0 }
    ],
    "cuts_per_minute": 38,
    "zoom_pattern": "jump_zoom",
    "transitions": ["hard_cut"],
    "b_roll_ratio": 0.15,
    "colour": "natural",
    "lighting": "n/a",
    "branding": "Handle watermark bottom-left throughout"
  },

  "cta": {
    "present": true,
    "verbatim": "comment 'Claude' and I'll send it through",
    "placement_seconds": 43.0,
    "type": "comment_keyword",
    "friction": "low"
  },

  "replication": {
    "what_to_steal": [
      "Show the command being typed and the output arriving in the same unbroken shot — the proof is the demo"
    ],
    "what_not_to_steal": [
      "The 'changed everything' framing, which depends on the tool actually being novel at time of posting"
    ],
    "effort": "low"
  },

  "confidence": {
    "transcript": "high",
    "visual": "high",
    "metrics": "medium",
    "notes": "Cut count estimated from observed pace, not frame-counted. Views and likes not exposed by the tool."
  }
}
```

## Field notes where it is easy to get wrong

**`source.status`** — `analysed` / `unavailable` / `partial`. Anything other than
`analysed` needs `unavailable_reason` filled in. This is what lets a batch report
honestly say "8 of 10 analysed".

**`source.watched_span`** — `full`, or a range like `"0s-30s"`. On clipped YouTube
watches this is the audit trail for why the visual analysis is thinner than the
transcript analysis. Without it, a reader cannot tell a shallow analysis from a
shallow video.

**`metrics.views` / `likes` / `comments`** — populated for YouTube from
`youtube_video_details`. The Instagram and TikTok watch tools do not return
engagement numbers, so these stay `null` there. Do not infer them from a follower
count.

**`metrics.cuts_per_minute`** — an estimate unless you genuinely counted. If
estimated, say so in `confidence.notes`. It is a useful comparative number and a
terrible absolute one.

**`hook.pattern`** — the reusable skeleton with specifics replaced by
`<PLACEHOLDERS>`. This field is the one most likely to be read directly by a
downstream consumer, because it is the part a creator can act on immediately. Make
it genuinely reusable — not the original sentence with two words swapped.

**`storytelling_structure.missing_sections`** plus `absence_looks_deliberate` —
these two together are where structural insight lives. A missing `credibility`
section in a creator with an established audience is a choice; the same gap in a new
account is a weakness.

**`replication.effort`** — `low` / `medium` / `high`, tracking
`format.production_tier`. It answers "could I make this tomorrow", which is usually
the user's real question.

## Batch schema

```json
{
  "schema_version": "1.0",
  "analysed_at": "2026-07-31T00:00:00Z",
  "video_count": 9,
  "analysed_count": 8,
  "videos": [
    { "video_id": "DZU1D_8OI62", "platform": "instagram", "status": "analysed" }
  ],
  "scope": {
    "platforms": ["instagram", "tiktok"],
    "creators": ["@kallawaymarketing"],
    "shared_niche": "AI tools for content creators",
    "caveats": "All 8 from a 3-day window; seasonal effects not separable."
  },

  "patterns": [
    {
      "claim": "Hook names a specific slash command or UI action rather than a benefit",
      "prevalence": "6/8",
      "video_ids": ["DZU1D_8OI62"],
      "evidence": [
        { "video_id": "DZU1D_8OI62", "quote": "you can just type /analyze into Claude" }
      ],
      "strength": "strong",
      "counter_examples": ["ABC123 opens with a follower-count result instead"]
    }
  ],

  "trends": [
    {
      "claim": "Shift from face-to-camera toward screen-recording-with-voiceover",
      "direction": "increasing",
      "basis": "5 of 6 videos posted in the last week are screen-first; both older ones are talking-head",
      "confidence": "low",
      "confidence_reason": "8 videos over 3 days cannot separate a trend from one creator's habit."
    }
  ],

  "insights": [
    {
      "insight": "Every high-alignment video shows the tool working before naming it; low-alignment ones name it first",
      "reasoning": "Alignment scores of 4-5 all place the demo before the product name; the two scoring 2 lead with the product.",
      "actionable_as": "Demo first, name second.",
      "supporting_video_ids": ["DZU1D_8OI62"]
    }
  ],

  "outliers": [
    {
      "video_id": "XYZ789",
      "why_it_differs": "Only video with no CTA; also the only one over 90 seconds.",
      "worth_investigating": true
    }
  ],

  "playbook": {
    "hook_formula": "Most people don't know you can <ACTION> in <TOOL> and get <OUTPUT>",
    "structure": ["hook_promise", "mechanism", "proof", "cta"],
    "format": "screen_recording with voiceover, word-by-word burned captions",
    "target_metrics": { "duration_seconds": "40-60", "words_per_minute": "180-220", "cuts_per_minute": "30-40" },
    "cta": "comment_keyword",
    "avoid": ["Naming the product before showing it work"]
  }
}
```

`prevalence` is always `"n/total"` as a string, where `total` is `analysed_count`,
not `video_count` — patterns are counted over videos actually analysed. Anything
below `2/n` is not a pattern and belongs in `outliers`.
