At the start of any task-oriented session — any interaction where you will
use tools and produce deliverables — invoke the task-observer skill before
beginning work. This ensures skill improvement opportunities are captured
throughout the session.

When loading any skill, check the observation log for OPEN observations
tagged to that skill. Apply their insights to the current work, even if
the skill file hasn't been updated yet. This enables immediate application
of observations before they're permanently integrated during the weekly
review.

task-observer workspace folder override: sessions in this repo run in
ephemeral, per-session containers (Claude Code on the web) — there is no
durable `~/.claude/projects/<id>/` path that outlives a session. Treat this
repository's root as the stable workspace folder instead: read and write
`skill-observations/log.md`, `cross-cutting-principles.md`, and
`last-review-date.txt` at the repo root, and commit + push any changes to
those files before the session ends (or immediately after each write, if
mid-session commits are the working pattern here) so observations survive
container teardown. Never write the log to a path that isn't part of this
git working tree.
