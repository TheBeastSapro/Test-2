# Reverse-engineering Kloudboard / kloudie

Source: [@grundstromleo, 2026-08-05](https://x.com/grundstromleo/status/2085091378791338033)
— *"how to use Claude Code to run a $11,000/month faceless youtube channel
business"* (21:16 screen recording), cross-referenced against the live product
at `kloudboard.com`, `app.kloudboard.com`, `kloudboard.com/mcp`, and
`kloudboard.com/roadmap` (fetched 2026-08-06).

Everything below is observed evidence — UI frames pulled at 1 fps from the
recording, plus the vendor's own public pages. Where something is inference
rather than observation it is marked **(inferred)**.

---

## 1. What the product actually is

Two names that get used interchangeably in the video, but they are different
layers:

| Name | What it is |
|---|---|
| **kloudboard** | The platform / workspace. `app.kloudboard.com`. Positioning: *"The workspace built for creative teams."* |
| **kloudie** | The AI agent that lives **inside** kloudboard as one of the apps in the rail. Currently shipped as "kloudie 2.0". |

The pitch is explicitly **stack replacement**, not "another tool":

> Replace your entire software stack · Centralize every project & client ·
> Built-in AI in every workflow
> — `REPLACES [Trello · Slack · Frame.io · Notion · …] +14 TOOLS`

Pricing is the tell for the strategy — **Free forever up to 5 members with
unlimited free guests**, then **$10/member/mo**. Clients and freelancers never
consume a paid seat. That is a deliberate land-grab: the whole freelance supply
chain gets pulled into the workspace for free, and only the core team pays.

Business model detail worth stealing: **AI credits** are the metered resource
(1,000 on signup, +300/mo free, +2,500/seat/mo on Pro), not seats alone.

---

## 2. The built-in apps — the actual answer to "what did he build"

### 2.1 Top-level app rail (8 apps)

Observed in-app at `app.kloudboard.com`, left edge, top to bottom:

| # | App | Icon | What it replaces | What it does |
|---|---|---|---|---|
| 1 | **Inbox** | tray | Slack/email notifications | Cross-workspace action feed, approvals, mentions |
| 2 | **Dashboard / Home** | house | Notion dashboards | KPI tiles, views chart, connected apps, "Due this week", Monthly Progress (ACTIVE / DONE / OVERDUE) |
| 3 | **Boards** | kanban | Trello, Asana | Kanban per project. Cards = deliverables (a video, a post). Columns are stages. Cards carry type tags (`YOUTUBE`, `PODCAST`, `MARKETING`, `DESIGN`), due date, checklist progress, assignee avatars, comment counts |
| 4 | **Calendar** | calendar | Notion calendar, publish schedulers | Due dates / publish schedule view over the boards |
| 5 | **Chat** | speech bubble | Slack | Channels + DMs, scoped per project |
| 6 | **Files / Assets** | folder | Google Drive, Dropbox | Asset management, brand assets, media, attachments on cards |
| 7 | **Economy** | credit card | Wise + PayPal + Bill.com + DocuSign | Freelancer payouts, invoices, contracts, onboarding — the money layer |
| 8 | **kloudie** | cloud | ChatGPT / Claude / Jasper | The agent (see §2.2) |

Plus, persistently in the chrome: workspace switcher (top-left, e.g. *"Personal
Brand Content"*), global search with `⌘K`, an **"Ask kloudie"** omnibox pinned
centre-top, a Feedback button, and **Invite** pinned to the bottom of the rail.

### 2.2 kloudie — the agent app (6 sections)

| Section | What it does |
|---|---|
| **New chat** | Opens the agent. Empty state: *"What's on the agenda?"* with quick-start cards — CREATE / DESIGN / REPURPOSE / IMPORT |
| **Library** | Every creation the agent produced, with fetchable media links |
| **Brain** | The knowledge base. Docs, **video transcripts**, synced content. Semantically searchable. This is what makes the agent write "in your voice" |
| **Automations** | Triggered workflows ("remind teammates when a script is ready for voiceover") |
| **Playground** | Direct-access generation tools (see §2.3) |
| **Conversations** | Chat history list down the left |

Two details that matter for cloning it:

- The composer has a **context scope selector** — *"KLOUDIE WILL USE: your
  whole workspace. Add a doc, source, or past creation to focus this reply."*
  In the video Leo explicitly writes *"do not use any brain context"* to
  suppress it. Scope is a first-class control, not a hidden RAG step.
- The agent **proposes a task and waits for approval** before acting
  (*"Claude did just create the task, you simply press on approve"*). Write
  actions are gated by a human confirm step.

### 2.3 Playground — the generation modules

Sub-nav, grouped by medium, with a live credit meter at the bottom
(observed: `64,653 credits`):

| Group | Module | Notes |
|---|---|---|
| **AUDIO** | Text to Speech | ElevenLabs-backed. Voice picker (e.g. *"Steve — Deep & Authoritative"*), model choice (**Eleven Multilingual v2** / **Eleven Turbo v2.5**), Speed + Stability sliders, 5,000-character limit, inline waveform player, Settings / History tabs |
| | Sound Effects | |
| | Music | |
| **VISUALS** | Image & Video | |
| **WRITING** | Script Writing | |
| | Social Posts | |

### 2.4 Economy — the money layer

The most differentiated part, and the hardest to copy:

- **Automated payouts** — pay freelancers straight from the board, *linked to
  the cards they completed*. Rails: PayPal, Payoneer, Wise, Venmo, Cash App,
  Zelle, Revolut, crypto.
- **Auto-generated invoices** on every payment ("no chasing freelancers").
- **Contracts** — set up and signed in-app, stored in the CRM.
- **Freelancer onboarding** — contract signing as part of joining.
- **Payment requests** — freelancers can request payment, labelled as
  freelancer-created.

### 2.5 Review / annotation — the Frame.io replacement

Timestamped annotation on video assets, triggered by a Review button on a
card's attachment. **This is the module excluded from the build** (see §5).

### 2.6 MCP server — `https://api.kloudboard.com/api/mcp`

Auth: OAuth 2.1 + PKCE with **automatic client registration** — no API key, no
client secret. Scoped to one workspace at consent. Streamable HTTP, so any MCP
client works, not just Claude.

19 tools, and the split is instructive — cheap structured reads, cheap
structured writes, and one expensive escape hatch:

**Reads (fast, ~1s, no credit cost)**
`get_workspace_overview` · `search_brain` · `get_video_performance` ·
`search_tasks` · `get_card_state` · `get_board_stage_counts` ·
`get_weekly_rollup` · `list_creations`

**External lookups**
`youtube_channel` · `instagram_account` · `competitor_channel` (ranks a
competitor's recent uploads by **outlier multiple vs their own baseline**)

**Writes (structured, no credit cost, no deletes on this surface)**
`create_card` · `create_task` · `manage_card` · `manage_task` ·
`save_to_brain` (links get transcribed on ingest) · `manage_competitors`

**Agent handoff (burns workspace AI credits)**
`ask_kloudie` · `get_conversation_update` (poll a long-running job)

> Design lesson: they did **not** expose "one tool that does everything". Cheap
> deterministic operations are their own tools; only genuinely open-ended work
> is handed to the agent, and it is explicitly priced. Deletes are absent from
> the MCP surface entirely.

### 2.7 Browser extension

Injects into YouTube and YouTube Studio (visible in the recording's header):
**Connect MCP**, **Combined Analytics**, and a **Net Profit Calculator** button
next to YouTube's own revenue chart.

*(The blue overlay panel showing Outlier 10.4x / VPH / Engagement / RPM / Est
Earnings on the watch page is **vidIQ**, a separate third-party product — not
part of kloudboard. Easy to misattribute from the video.)*

### 2.8 Public roadmap — what is not built yet

Shipped 15 · In progress 0 · **Planned 4**:

- Auto-fetch income/expenses by connecting bank accounts and affiliate software
- Loom-style screen recording, embeddable in cards
- An upgraded Review feature
- A *Playground* in the build-your-own sense — internal tools, workflows,
  agents, external API connections, with context of the whole project

---

## 3. The workflow the video actually demonstrates

The $11k/month channel pipeline, step by step, with the tool used at each stage:

| # | Step | Tool |
|---|---|---|
| 1 | Niche research — *"20 faceless long-form channels, <100k subs, started 1–4 months ago, a viral video >200k views, monetized"* | **Claude Code** + the **NexLev** MCP connector → a 20-row table (channel, niche, started, subs, est. rev/mo, viral video views, avg length, link) |
| 2 | Competitor analysis — copy the winner's top video title, search it on YouTube, find the *small* channels breaking in | YouTube search |
| 3 | Transcript extraction of the proven video | `youtubetotranscript.com` |
| 4 | Script generation — *"generate a similar script to the transcript, same voice/style, 1500 words, raw text"* | **kloudie** chat |
| 5 | Voiceover | **kloudie → Playground → Text to Speech** (ElevenLabs) |
| 6 | Production board — *"make a board where I can manage this channel, add the video I generated as a card, base it on the most used YouTube automation template"* — the agent builds the columns and places the card | **kloudie → Boards** |
| 7 | Hire an editor — explicitly **not** Fiverr or Upwork; a Discord community's `post-a-job` channel → job form → DMs from editors | Discord |
| 8 | Publish + track | YouTube Studio + extension overlay |

The economics quoted: 861.3K views / 150.5K watch hours / +3.2K subs /
**$11,241.98** over 90 days at ~4.2K subscribers — a ~$10 RPM on long-form
documentary content.

Note the structural claim underneath the whole video: **the moat is the
production pipeline, not the AI.** The niche that wins is the one where content
has "somewhat of a barrier to entry" — a scripted, voiced-over, human-edited
documentary that a kid with one prompt cannot reproduce.

---

## 4. What it was built from — the lineage

You don't have to guess this one. Kloudboard publishes **42 comparison pages**
under `/compare`, grouped by category, and each names the product it is
displacing. That list *is* the blueprint — read as "which app did he take each
module from", it answers itself:

| Module in kloudboard | Taken from | Their own framing |
|---|---|---|
| **Boards** | **Trello** (card UI), Monday.com, Asana, ClickUp, Notion, Airtable, Jira, Linear, Basecamp, Wrike, Hive, Podio, MeisterTask, Nifty, Smartsheet, Teamwork, ProofHub, Workfront | *"love Trello's cards but tired of bolting on a proofing tool, a chat app, a payments service, and three Power-Ups"* |
| **Review / annotation** | **Frame.io**, Ziflow, Filestage, Wipster, ReviewStudio, PageProof, Dropbox Replay, Vimeo Review, Clipflow, Timeliner | *"love frame.io's video review but tired of paying for chat, payments, kanban, and storage in five other tools"* |
| **Chat** | **Slack**, Discord, Microsoft Teams, WhatsApp | Slack and Discord are **bridged**, not just replaced — messages sync in |
| **Files** | **Google Drive**, Dropbox, Shade | *"the files live next to the work"* |
| **Planning canvas** | **Milanote** | |
| **Screen recording** (planned) | **Loom** | On the roadmap, not shipped |
| **Economy** | **Productive**, Workamajig, Function Point — plus the payment rails themselves (Wise, PayPal, Payoneer, Revolut) | Agency-ops suites, minus the ERP weight |
| **Playground → Text to Speech** | **ElevenLabs** (the model names are theirs: Multilingual v2, Turbo v2.5) | |
| **kloudie agent** | **ChatGPT / Claude** — the composer, conversation rail, and context-scope selector are lifted straight from that pattern | *"New AI Agent kloudie 2.0"* |
| **MCP connector** | **Anthropic's MCP spec** — OAuth 2.1 + PKCE, streamable HTTP | Deliberately client-agnostic |

**The single biggest structural borrow is ClickUp.** Kloudboard's whole thesis —
*"Replace your entire software stack"*, one workspace, one price, tool-sprawl
statistics on the homepage — is ClickUp's "one app to replace them all" playbook,
re-aimed from software teams at creative teams. Their own ClickUp page says the
quiet part: they are not claiming a better idea, they are claiming a better
*fit* and cheaper terms (*"the workflow without the AI surcharge or the 60MB
storage wall"*).

The three things they added that the sources don't have, and which are the
actual product:

1. **Freelancer payouts wired to cards.** No project tool does this. Frame.io
   won't pay your editor; Wise doesn't know which video the payment was for.
2. **Free unlimited guests.** Everyone else charges per seat, which is exactly
   why teams email files instead. Making clients and freelancers free is what
   pulls the whole supply chain into the workspace.
3. **An agent with workspace-wide context.** Not a chat sidebar — an app with
   its own memory (Brain), artifacts (Library), and scheduler (Automations).

Read as strategy: **take a category-leading UI people already know (Trello's
board), keep it, and absorb the four tools they had to bolt around it.** The
comparison pages all repeat the same sentence shape — *"love X, but tired of
bolting on…"* — because that is the entire pitch.

### Extra modules found on the product pages

Not visible in the recording, but documented:

- **Client Portal** — branded, free guest access, per-project scoping, in-context
  approvals and revision requests tracked against each asset.
- **Custom fields on boards** — platform, format, length, client, campaign;
  filter and group by any of them.
- **Real-time collaboration** on boards, no refresh.
- **Version history** on assets, plus secure per-asset share links.
- **Integrations** — Slack and Discord message sync, Google Calendar event sync,
  Zapier, and webhooks.
- **Automations** can notify Slack/Discord/email, and chain multiple actions per
  rule.

---

## 5. Architecture worth copying

1. **One data spine, many views.** A card is the unit of work. Boards,
   Calendar, Dashboard counts, Economy payouts, and the agent all read and
   write the *same* card. Payouts linking to completed cards is only possible
   because of this.
2. **The agent is an app, not a chat sidebar.** It has its own nav, its own
   persistent artifacts (Library), its own memory (Brain), and its own
   scheduler (Automations).
3. **Memory is a browsable noun.** "Brain" is a place users open and curate,
   not invisible RAG. Transcription-on-ingest means a pasted YouTube link
   becomes searchable text.
4. **Approval gate on agent writes.** Propose → approve → execute.
5. **Metered AI, unmetered structure.** Credits price generation; CRUD is free.
   Mirrored exactly in the MCP tool split.
6. **Guests are free.** Growth loop and data-gravity play in one decision.

---

## 6. Scope of this build

Originally scoped as *"all except video editing"*, then extended to include the
Review module. **Everything documented above is now implemented** in
`kloudie-dashboard/` — ten apps in the rail, including Review and the Client
Portal found on the product pages.

The one remaining gap is **video generation** in the Playground's *Image &
Video* module, kept as **Image** only. That is generative video, not video
editing, and it is the one surface where a convincing implementation would
require a real model endpoint rather than a UI.

Note on what "review" means here — it is worth being precise, because the
distinction is the product: kloudboard does **not** ship a video *editor*. There
is no timeline, no cutting, no rendering. It ships frame-accurate *review* —
scrub, step, mark a region, pin a note to an exact frame, approve or send back.
The editing happens in Premiere or Resolve; kloudboard owns the feedback loop
around it, which is the part that is actually painful to coordinate across a
freelance team. Building an editor would have been a different, much larger
product, and not the one being reverse-engineered.

See the directory's README for what is real behaviour versus seeded data.
