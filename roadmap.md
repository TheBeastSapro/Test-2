# roadmap.md — 30 days

Written 2026-07-08 from thin evidence (see evidence.md). Where the record was
silent, this plan says so instead of inventing.

## WASTE — where hours die
- **Analysis-of-nothing.** This session: a full six-phase self-analysis pointed
  at an empty container (receipt: evidence.md, record table). Cost: one session.
  Insight-seeking before output-making is the visible leak.
- Repetition tax: **insufficient data** — measurable only from the local archive.

## DELEGATE — hand to AI permanently
1. **Niche research digests.** NexLev is already connected. A scheduled routine
   ("every Monday 9:00: pull outlier faceless channels in my niches, RPM
   deltas, 5 video ideas ranked, one page") converts a connected-but-idle tool
   into a standing input. Hours recovered: whatever manual browsing it replaces.
2. **Idea triage.** Idea-Phantom captures; nothing visible processes. A weekly
   "score my captured ideas against NexLev demand data" run closes that loop.

## FOCUS — what only you can do
- Making the actual videos. No tool on this machine can be the channel.
  The record shows all inputs (research, ideas, identity) and no output stage.
  Confidence: LOW that this is your *exceptional* zone — the record is too
  thin to prove exceptional at anything. It only proves it's the missing stage.

## DROP
- **Empty scaffolding.** `Test` and `Test-2` — delete or use within 7 days.
  A repo named Test with zero commits is a tab left open in your identity.
- Re-running this analysis in cloud containers. It structurally cannot work
  here. One receipt was enough.

## KEEP
- The 12-minute burst (account → repos → session, 18:16–18:28). Whatever state
  of mind that was, it executes. Point it at production once.

## RHYTHM
- **Insufficient data.** One timestamp cluster is not a rhythm. The local
  archive has the real answer.

## The 30 days
- **Week 1 (drop):** Delete or commit to Test/Test-2. Run the six-phase prompt
  on your LOCAL machine where `~/.claude/projects/` lives — that analysis is
  the real one; this document is its stand-in.
- **Weeks 2–4 (delegate):** Create the Monday NexLev digest routine. Create the
  idea-triage routine. Both are one `create_trigger` call in a Claude session.
- **Daily (protect):** One unit of output per burst — a script, a thumbnail
  test, an upload — before any new research or setup. Setup is allowed only
  after output. The record's one confirmed pattern is that setup arrives first;
  invert it.

## Proposed config change (diff — apply only if you approve)

No CLAUDE.md exists in this repo or visibly elsewhere. Proposed new file for
whichever repo becomes the real working repo:

```diff
+ # CLAUDE.md
+ ## Working rules (from 2026-07-08 analysis)
+ - Before any new tooling/setup task, ask: "what did we ship since the last
+   setup task?" If nothing, redirect to output first.
+ - Never create repos/files named test/tmp/scratch in this account; use the
+   session scratchpad instead.
+ - Weekly: NexLev digest routine owns niche research. Don't do it ad hoc.
```

## Proposed skill (draft — kills the visible loop)

`.claude/skills/ship-first/SKILL.md`
```diff
+ ---
+ name: ship-first
+ description: Run before starting any setup, research, or self-analysis task.
+ ---
+ Check the last 7 days of output (commits, uploads, published anything).
+ If output count is 0, respond with the single smallest shippable action
+ toward the YouTube channel and offer to do it now, before the requested
+ setup/research task.
```

Two more skills (repetition-tax killers) are deferred: the repetition they
would kill is only measurable in the local archive. Drafting them from this
container would be invention, not evidence.
