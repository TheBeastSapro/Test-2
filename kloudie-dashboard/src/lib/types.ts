/**
 * The data spine.
 *
 * Kloudboard's central architectural choice is that a *card* is the single unit
 * of work, and every surface — Boards, Calendar, Dashboard counts, Economy
 * payouts, the agent — reads and writes that same record. Payouts can be linked
 * to completed cards only because there is one card table, not five.
 * We keep that property here.
 */

export type AppId =
  | 'inbox'
  | 'dashboard'
  | 'boards'
  | 'calendar'
  | 'chat'
  | 'files'
  | 'economy'
  | 'portal'
  | 'kloudie'

export type CardTag =
  | 'YOUTUBE'
  | 'PODCAST'
  | 'MARKETING'
  | 'DESIGN'
  | 'SHORTS'
  | 'NEWSLETTER'

export interface ChecklistItem {
  id: string
  label: string
  done: boolean
}

export interface CardComment {
  id: string
  authorId: string
  body: string
  at: string
}

export interface Card {
  id: string
  /** Human reference, e.g. KB-26 — the handle the MCP `search_tasks` tool uses. */
  ref: string
  boardId: string
  stageId: string
  title: string
  tag: CardTag
  /** ISO date. Drives Calendar and "Due this week". */
  due: string | null
  assigneeIds: string[]
  checklist: ChecklistItem[]
  comments: CardComment[]
  /** Links this card to an asset in Files. */
  attachmentIds: string[]
  /** Agreed payout for the freelancer who completes it — the Economy link. */
  payoutCents: number
  createdAt: string
}

export interface Stage {
  id: string
  name: string
  /** Tailwind dot colour class. */
  tone: string
}

export interface Board {
  id: string
  name: string
  /** Which template it was created from — the agent builds boards from these. */
  template: string
  stages: Stage[]
}

export interface Member {
  id: string
  name: string
  role: 'Owner' | 'Editor' | 'Writer' | 'Designer' | 'Guest'
  /** Guests are free and unlimited on every plan — kloudboard's growth loop. */
  guest: boolean
  initials: string
  hue: number
  payoutMethod?: PayoutMethod
}

export type PayoutMethod =
  | 'PayPal'
  | 'Wise'
  | 'Payoneer'
  | 'Revolut'
  | 'Venmo'
  | 'Cash App'
  | 'Zelle'
  | 'Crypto'

export interface Payout {
  id: string
  memberId: string
  /** Payouts are card-linked: you pay for delivered work, not for time. */
  cardIds: string[]
  amountCents: number
  method: PayoutMethod
  status: 'requested' | 'scheduled' | 'paid'
  /** Auto-generated on payment — "no chasing freelancers". */
  invoiceNo: string | null
  at: string
}

export interface Contract {
  id: string
  memberId: string
  title: string
  status: 'draft' | 'sent' | 'signed'
  at: string
}

export interface Asset {
  id: string
  name: string
  kind: 'audio' | 'image' | 'doc' | 'video' | 'other'
  sizeKb: number
  cardId: string | null
  at: string
}

export interface ChatChannel {
  id: string
  name: string
  kind: 'channel' | 'dm'
  memberIds: string[]
}

export interface ChatMessage {
  id: string
  channelId: string
  authorId: string
  body: string
  at: string
}

export interface InboxItem {
  id: string
  kind: 'mention' | 'approval' | 'payout' | 'automation' | 'review'
  title: string
  body: string
  cardRef: string | null
  at: string
  read: boolean
}

/** A Brain entry: the browsable, curatable memory the agent grounds on. */
export interface BrainDoc {
  id: string
  title: string
  kind: 'transcript' | 'note' | 'sop' | 'synced'
  /** Where it came from — pasted links get transcribed on ingest. */
  source: string
  body: string
  at: string
}

/** A Library creation: a durable artifact the agent produced. */
export interface Creation {
  id: string
  title: string
  module: PlaygroundModuleId
  /** Text output, or a synthetic descriptor for media. */
  body: string
  credits: number
  at: string
}

export type PlaygroundModuleId =
  | 'tts'
  | 'sfx'
  | 'music'
  | 'image'
  | 'script'
  | 'social'

export interface Automation {
  id: string
  name: string
  trigger: string
  action: string
  enabled: boolean
  runs: number
}

export interface Competitor {
  id: string
  handle: string
  platform: 'YouTube' | 'Instagram'
  subs: number
  /** Recent-upload performance vs the channel's own baseline. */
  outlier: number
  niche: string
}

export interface VideoStat {
  id: string
  title: string
  platform: 'YouTube' | 'TikTok' | 'Instagram'
  views: number
  watchHours: number
  rpm: number
  revenueCents: number
  publishedAt: string
}

/** An agent turn. Writes are proposed, then approved, then executed. */
export interface AgentMessage {
  id: string
  role: 'user' | 'agent'
  body: string
  /** Present when the agent wants to write to the workspace. */
  proposal?: AgentProposal
  at: string
}

export interface AgentProposal {
  id: string
  summary: string
  kind: 'create_board' | 'create_card' | 'save_to_brain' | 'create_automation'
  payload: Record<string, unknown>
  status: 'pending' | 'approved' | 'declined'
}

export interface Conversation {
  id: string
  title: string
  messages: AgentMessage[]
  at: string
}

export interface Workspace {
  id: string
  name: string
}
