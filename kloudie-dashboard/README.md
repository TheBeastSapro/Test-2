# kloudie-dashboard

A working clone of the Kloudboard / kloudie workspace — every module except
video editing. The teardown it was built from is in
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

**Nine apps in the rail**

| App | What works |
|---|---|
| **Inbox** | Mentions, approvals, payout requests, automation runs. Unread badge on the rail, click-through to the originating card. |
| **Dashboard** | 90-day KPI tiles, hand-rolled SVG views chart, board stage counts, "Due this week", connected apps, top content table. |
| **Boards** | Kanban with real drag-and-drop between stages, per-stage quick add, card drawer with stage/due/assignees, live checklist, comments, attachments, card-linked payout. |
| **Calendar** | Month grid of every card with a due date. Drag a card to a new day to reschedule it — it writes to the same card the board reads. |
| **Chat** | Channels and DMs, live message send. |
| **Files** | Asset library, type filters, storage total, links back to the card each asset belongs to. |
| **Economy** | Payouts linked to the cards they paid for, "Pay now" generates an invoice number, team roster with guest flags, contracts. |
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
Boards, Calendar, Dashboard counts, Files, Economy payouts, the Client Portal
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

## Excluded

Per the brief — everything except video editing:

- **Review / annotation** — the Frame.io-style timestamped video markup.
- **Video generation** in the Playground; *Image & Video* is Image only.

---

## Stack

React 19 · TypeScript · Vite 8 · Tailwind v4 · react-router · lucide-react.
No state library — a context + `useState` store in `src/lib/store.tsx` is
enough at this size. No charting library — the one chart is 30 lines of SVG.

`npm run verify` drives the built app in headless Chromium: every route asserted
free of console errors, then the primary state loop driven end to end
(agent proposes → approve → records appear in another app → credits decrement →
survives reload).
