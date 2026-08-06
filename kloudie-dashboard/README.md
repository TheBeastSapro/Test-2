# kloudie-dashboard

A working clone of the Kloudboard / kloudie workspace, Review module included.
The teardown it was built from is in
[`../REVERSE-ENGINEERING.md`](../REVERSE-ENGINEERING.md).

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b && vite build
npm run verify     # headless pass over every route + end-to-end state flow
```

No backend, no API keys, no network calls. State lives in `localStorage` under
`kloudboard.workspace.v1`.

---

## What's in it

**Eleven apps in the rail**

| App | What works |
|---|---|
| **Inbox** | Mentions, approvals, payout requests, automation runs. Unread badge on the rail, click-through to the originating card. |
| **Dashboard** | 90-day KPI tiles, hand-rolled SVG views chart, board stage counts, "Due this week", connected apps, top content table. |
| **Boards** | Kanban with real drag-and-drop between stages, per-stage quick add, card drawer with stage/due/assignees, live checklist, comments, attachments, card-linked payout. |
| **Calendar** | Month grid of every card with a due date. Drag a card to a new day to reschedule it — it writes to the same card the board reads. |
| **Chat** | Channels and DMs, live message send. |
| **Drive** | File library, type filters, storage total, links back to the card each file belongs to. |
| **Review** | Frame-accurate video review (below). |
| **Pay** | Payouts linked to the cards they paid for, with Paid / Pending approval / Queued tiles. "Pay now" generates an invoice. Team roster with guest flags, contracts. |
| **Invoices** | Its own app, as in the original — derived from paid payouts, each naming the cards it paid for. |
| **Client portal** | The guest-facing view. Approve or request changes on shared deliverables; the decision lands as a card comment *and* an Inbox item. |
| **kloudie** | The agent (below). |

**kloudie's five sections**

- **Chat** — proposes workspace writes and waits for approval before executing.
- **Library** — every creation, filterable by module, with credit cost.
- **Brain** — the searchable knowledge base the agent grounds on; add notes.
- **Automations** — toggle rules on and off; tracked competitors with outlier
  multiples.
- **Playground** — six generation modules (Text to Speech, Sound Effects, Music,
  Image, Script Writing, Social Posts) with an ElevenLabs-style settings panel,
  per-module history, and live credit metering.

Plus: workspace switcher, `⌘K` command palette searching cards / boards / Brain /
Library, and an "Ask kloudie" omnibox that routes into a new agent conversation.

---

## The two ideas worth keeping

**1. One card, every view.** `src/lib/types.ts` defines a single `Card`, and
Boards, Calendar, Dashboard counts, Drive, Pay payouts, the Client Portal
and the agent all read and write *that same record*. Reschedule on the Calendar
and the board moves. Approve in the portal and a comment appears on the card and
an item appears in the Inbox. Payouts can reference the cards they paid for
because there is one card table, not five — which is exactly why Kloudboard can
pay a freelancer for a specific delivered video and Frame.io plus Wise cannot.

**2. Writes are proposed, not applied.** The agent never mutates the workspace
directly. It returns a proposal, the UI renders it with Approve / Decline, and
only approval executes against the store. Try it:

> `make a board where I can manage this channel`

→ approve → a new board with five stages and a card exists in **Boards**, and
the credit counter has dropped.

---

## Real vs. seeded

**Real behaviour** — all state mutation and persistence, drag-and-drop, the
approval gate, credit metering and spend, search, filtering, routing, the
portal → card → inbox chain, invoice generation on payment.

**Seeded** — the workspace contents in `src/lib/seed.ts` (a faceless
documentary channel modelled on the one in the source video), and the agent's
replies.

**The one seam to replace for a real backend:** `src/apps/kloudie/agent.ts`.
It is a deterministic stand-in with the exact shape a real call returns
(`{ message, credits }`), so swapping in a model means replacing the body of
`respond()` and nothing else. Everything else in the app is already wired to
real state.

Analytics figures derive from a single `channel90d` object so views, revenue and
RPM can't drift apart.

---

## Review — the Frame.io module

Open it from the rail, or from **Review** on a cut in any card's drawer.

- **Frame-accurate transport.** SMPTE timecode (`MM:SS:FF`), single-frame
  stepping, `←`/`→` for one frame, `shift` for one second, `space` to play. The
  clips carry a burned-in timecode so stepping can be checked against the frame
  itself.
- **Notes pinned to a frame.** Every note anchors to an exact timecode — that
  same anchor is the marker on the timeline, the seek target when clicked, and
  the frame its drawing belongs to.
- **Five annotation tools**, matching the original: **pin, arrow, line,
  rectangle, freehand**, plus undo. Pick one, mark the frame, write the note.
  The mark reappears over the picture when playback reaches that timecode.
  Everything is stored normalised (0–1) and rendered in a unit SVG viewBox, so
  marks stay correct at any player size.
- **Playback speed** — 0.5x to 2x.
- **Resolve / reopen**, with an open-note count and a resolved filter.
- **Versions.** v1 / v2 of the same deliverable, each with its own note set,
  hanging off the card the board already tracks.
- **Approve / Request changes** — writes a comment on the card *and* an item to
  the Inbox, the same way the Client Portal does.

Two encodes ship per clip (H.264 `.mp4` and VP9 `.webm`, ~600 KB total,
generated locally with ffmpeg). Safari and most Chrome builds take the mp4;
Chromium builds without proprietary codecs — including the one the verify
script drives — take the webm.

**One deliberate divergence:** the original displays decimal seconds
(`0:02.86`); this shows SMPTE `MM:SS:FF`. SMPTE is the unit an editor scrubs
in, but the original's choice is arguably better for a product whose pricing
model makes clients free — the person leaving the note usually isn't an editor.

**What this deliberately is not:** an editor. There is no timeline, no cutting,
no rendering — because kloudboard doesn't ship those either. It owns the
feedback loop around the edit, not the edit.

---

## Excluded

- **Video generation** in the Playground; *Image & Video* is Image only. That's
  generative video rather than video editing, and the only surface that would
  need a real model endpoint to be anything but a mock.

---

## Stack

React 19 · TypeScript · Vite 8 · Tailwind v4 · react-router · lucide-react.
No state library — a context + `useState` store in `src/lib/store.tsx` is
enough at this size. No charting library — the one chart is 30 lines of SVG.

`npm run verify` drives the built app in headless Chromium. It clears
`localStorage` first, so runs are repeatable rather than accumulating. It
asserts every route is free of console errors, then drives the real loops end to
end: agent proposes → approve → records appear in another app → credits
decrement → survives reload; and in Review, frame stepping lands on the exact
frame, a drawn note pins to its timecode and persists, versions swap both source
and note set, and a decision reaches both the card and the Inbox.
