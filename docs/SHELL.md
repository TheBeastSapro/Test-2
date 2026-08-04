# The shell: a channel is a project

## What is wrong today

Forgecast's rail is the account. Studio, the two format workspaces, Research, Styles,
Skills, Files, Analytics and Activity are all account-wide pages, and a chat thread belongs
to a login rather than to a channel. With one channel that distinction is invisible, because
the account *is* the channel. With two it is the whole problem: "how is the space channel
doing" has no page, and "which chats were about the space channel" has no answer.

A Channels lane in the rail was added as a half-measure. It makes a channel reachable. It
does not make a channel the thing you are inside.

## The shape it should be

Everything scopes to a channel, and the operator's own screenshot is the
specification:

```
┌────┬──────────────────┬───────────────┬──────────────────────────────┐
│ U  │ Untitled    ●Idle │ Skills        │ thumbnail-design             │
│ C  │             +     │ ai-host-setup │                              │
│ 📷 │ ▸ Chat            │   +4          │ file: [SKILL.md] [composi…]  │
│ U  │ ▸ Skills          │ audio-mix-as… │                       [Edit] │
│    │ ▸ Analytics       │ authentic-se… │ Skill 02 — Thumbnail Design  │
│ +  │ ▸ Files           │ broll-select… │ …                            │
│    │ ▸ Activity        │ captions      │                              │
│    │ CHATS          ⌄  │ …             │                              │
│    │  New chat         │               │                              │
│    │  7h ago · 0 msgs  │               │                              │
└────┴──────────────────┴───────────────┴──────────────────────────────┘
```

* **Channel strip** (far left, narrow). One tile per channel, showing its initial or avatar.
  The active one is marked. A `+` at the bottom creates a channel. This is the only
  account-wide element left, and it exists to switch between projects.
* **Channel column.** The channel's name and derived status at the top, with a `+` that
  starts a new chat *in this channel*. Below it the per-channel nav — Chat, Skills,
  Analytics, Files, Activity — then a `CHATS` list of that channel's threads with their
  age and message count.
* **Content columns.** Whatever the nav selected, scoped to the channel.

## Why this is not cosmetic

Three things follow from it that the current shape cannot express.

**A chat is about a channel.** `Conversation.channel_id` already exists in `models.py` and
nothing in the UI reads it, so every thread is an account-wide thread. The consequence is
that the agent's memory of "this channel" is whatever the transcript happens to still
contain, rather than something the app knows. Scoping the thread means the agent can be told
which channel it is in before the operator types anything.

**Skills, Files, Analytics and Activity are per-channel questions.** "What did the agent do"
is only useful as "what did the agent do *on this channel*". Account-wide versions of these
pages force the operator to filter mentally, on every visit, and mental filtering is where
two channels' numbers get confused.

**A skill is a directory, not a file.** The screenshot shows `ai-host-setup +4` and
`image-to-video +1`, and the main pane has `file:` tabs for `SKILL.md` and
`composition-bank.md`. So a skill is a folder containing `SKILL.md` plus companion documents,
and the `+N` badge is the companion count. The four documents just added — `image-to-video`
with its cookbook, `visual-register`, `storyboard` — are already this shape by accident and
should be stored as it deliberately.

## Order of work

The database is the easy half and it is nearly done: `Conversation.channel_id` exists but is
a bare `Integer` with no foreign key, no index, and no cascade. It needs to become a real
relationship, with a migration, and a decision about what happens to the threads that predate
it — they have no channel, and pretending they belong to the first one would silently attach
months of unrelated work to it. A null channel means "not about a channel yet", which is a
real state and should stay representable.

The shell is the harder half, because `base.html` is one template shared by every page and
every page supplies its context through `shell()` in `routes_web.py`. Changing the rail
changes every page at once, which is exactly why it is worth doing carefully and once.

What must not regress: the format split (long-form vs Shorts decides the pipeline, the aspect
ratio and the length, so it cannot simply be deleted in favour of channels); the embed mode
that lets the chat's Studio panel render the real preview page; and the responsive collapse
under 900px, where the rail becomes a scrolling row.
