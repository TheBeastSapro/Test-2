import type {
  Automation,
  BrainDoc,
  Board,
  Card,
  Conversation,
  Creation,
  InboxItem,
  Member,
  Competitor,
  Contract,
  Payout,
  ReviewAsset,
  ReviewComment,
  ReviewRegion,
} from './types'

/**
 * The API boundary.
 *
 * The server speaks SQL rows (snake_case, integer booleans, JSON in TEXT
 * columns). The UI speaks the domain types it was built against. Translating
 * once here means neither side has to know about the other's shape, and the
 * components didn't change when the app grew a backend.
 */

export interface AuthUser {
  id: string
  email: string
  name: string
  initials: string
  hue: number
}

export interface Snapshot {
  workspaceName: string
  channels: { id: string; name: string; kind: 'channel' | 'dm' }[]
  chatMessages: { id: string; channelId: string; authorId: string; body: string; at: string }[]
  competitors: Competitor[]
  contracts: Contract[]
  credits: number
  members: Member[]
  boards: Board[]
  cards: Card[]
  files: FileRow[]
  reviewAssets: ReviewAsset[]
  reviewComments: ReviewComment[]
  payouts: Payout[]
  brain: BrainDoc[]
  creations: Creation[]
  conversations: Conversation[]
  inbox: InboxItem[]
  automations: Automation[]
  agentProvider: string
}

export interface FileRow {
  id: string
  name: string
  kind: 'audio' | 'image' | 'doc' | 'video' | 'other'
  sizeKb: number
  cardId: string | null
  at: string
  url: string
}

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init.body && typeof init.body === 'string'
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init.headers,
    },
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) throw new ApiError(data.error ?? `Request failed (${res.status})`, res.status)
  return data as T
}

const post = <T>(path: string, body?: unknown) =>
  req<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body: unknown) =>
  req<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

// ------------------------------------------------------------------- auth

export const auth = {
  me: () => req<{ user: AuthUser }>('/api/auth/me'),
  login: (email: string, password: string) =>
    post<{ user: AuthUser }>('/api/auth/login', { email, password }),
  register: (name: string, email: string, password: string) =>
    post<{ user: AuthUser }>('/api/auth/register', { name, email, password }),
  logout: () => post<{ ok: true }>('/api/auth/logout'),
}

// -------------------------------------------------------------- normalise

/* eslint-disable @typescript-eslint/no-explicit-any */
function toSnapshot(raw: any): Snapshot {
  const assigneesByCard = new Map<string, string[]>()
  for (const a of raw.assignees ?? []) {
    assigneesByCard.set(a.card_id, [...(assigneesByCard.get(a.card_id) ?? []), a.user_id])
  }

  const checklistByCard = new Map<string, Card['checklist']>()
  for (const i of raw.checklist ?? []) {
    checklistByCard.set(i.card_id, [
      ...(checklistByCard.get(i.card_id) ?? []),
      { id: i.id, label: i.label, done: !!i.done },
    ])
  }

  const commentsByCard = new Map<string, Card['comments']>()
  for (const c of raw.cardComments ?? []) {
    commentsByCard.set(c.card_id, [
      ...(commentsByCard.get(c.card_id) ?? []),
      { id: c.id, authorId: c.author_id, body: c.body, at: c.created_at },
    ])
  }

  const filesByCard = new Map<string, string[]>()
  for (const f of raw.files ?? []) {
    if (f.card_id) filesByCard.set(f.card_id, [...(filesByCard.get(f.card_id) ?? []), f.id])
  }

  const cardsByPayout = new Map<string, string[]>()
  for (const pc of raw.payoutCards ?? []) {
    cardsByPayout.set(pc.payout_id, [...(cardsByPayout.get(pc.payout_id) ?? []), pc.card_id])
  }

  const messagesByConv = new Map<string, Conversation['messages']>()
  for (const m of raw.messages ?? []) {
    messagesByConv.set(m.conversation_id, [
      ...(messagesByConv.get(m.conversation_id) ?? []),
      {
        id: m.id,
        role: m.role,
        body: m.body,
        proposal: m.proposal_json ? JSON.parse(m.proposal_json) : undefined,
        at: m.created_at,
      },
    ])
  }

  return {
    workspaceName: raw.workspace?.name ?? 'Workspace',
    credits: raw.workspace?.credits ?? 0,
    agentProvider: raw.agent?.provider ?? 'mock',

    channels: (raw.channels ?? []).map((c: any) => ({ id: c.id, name: c.name, kind: c.kind })),
    chatMessages: (raw.chatMessages ?? []).map((m: any) => ({
      id: m.id, channelId: m.channel_id, authorId: m.author_id, body: m.body, at: m.created_at,
    })),
    competitors: (raw.competitors ?? []).map((c: any): Competitor => ({
      id: c.id, handle: c.handle, platform: c.platform, subs: c.subs, outlier: c.outlier, niche: c.niche,
    })),
    contracts: (raw.contracts ?? []).map((c: any): Contract => ({
      id: c.id, memberId: c.member_id, title: c.title, status: c.status, at: c.created_at,
    })),

    members: (raw.members ?? []).map((m: any): Member => ({
      id: m.id,
      name: m.name,
      role: m.role,
      guest: !!m.is_guest,
      initials: m.initials,
      hue: m.hue,
    })),

    boards: (raw.boards ?? []).map((b: any): Board => ({
      id: b.id,
      name: b.name,
      template: b.template,
      stages: (raw.stages ?? [])
        .filter((s: any) => s.board_id === b.id)
        .map((s: any) => ({ id: s.id, name: s.name, tone: s.tone })),
    })),

    cards: (raw.cards ?? []).map((c: any): Card => ({
      id: c.id,
      ref: c.ref,
      boardId: c.board_id,
      stageId: c.stage_id,
      title: c.title,
      tag: c.tag,
      due: c.due,
      assigneeIds: assigneesByCard.get(c.id) ?? [],
      checklist: checklistByCard.get(c.id) ?? [],
      comments: commentsByCard.get(c.id) ?? [],
      attachmentIds: filesByCard.get(c.id) ?? [],
      payoutCents: c.payout_cents,
      createdAt: c.created_at,
    })),

    files: (raw.files ?? []).map((f: any): FileRow => ({
      id: f.id,
      name: f.name,
      kind: f.kind,
      sizeKb: Math.max(1, Math.round(f.size_bytes / 1024)),
      cardId: f.card_id,
      at: f.created_at,
      url: `/api/files/${f.id}/content`,
    })),

    reviewAssets: (raw.reviewAssets ?? []).map((a: any): ReviewAsset => ({
      id: a.id,
      cardId: a.card_id,
      title: a.title,
      version: a.version,
      // The player streams from the API, so the "src" is an endpoint.
      src: `/api/files/${a.file_id}/content`,
      durationSec: a.duration_sec,
      fps: a.fps || 25,
      status: a.status,
      uploadedBy: a.uploaded_by,
      at: a.created_at,
    })),

    reviewComments: (raw.reviewComments ?? []).map((c: any): ReviewComment => ({
      id: c.id,
      assetId: c.asset_id,
      authorId: c.author_id,
      timecodeSec: c.timecode_sec,
      body: c.body,
      region: c.region_json ? (JSON.parse(c.region_json) as ReviewRegion) : null,
      resolved: !!c.resolved,
      at: c.created_at,
    })),

    payouts: (raw.payouts ?? []).map((p: any): Payout => ({
      id: p.id,
      memberId: p.member_id,
      cardIds: cardsByPayout.get(p.id) ?? [],
      amountCents: p.amount_cents,
      method: p.method,
      status: p.status,
      invoiceNo: p.invoice_no,
      at: p.created_at,
    })),

    brain: (raw.brain ?? []).map((b: any): BrainDoc => ({
      id: b.id,
      title: b.title,
      kind: b.kind,
      source: b.source,
      body: b.body,
      at: b.created_at,
    })),

    creations: (raw.creations ?? []).map((c: any): Creation => ({
      id: c.id,
      title: c.title,
      module: c.module,
      body: c.body,
      credits: c.credits,
      at: c.created_at,
    })),

    conversations: (raw.conversations ?? []).map((c: any): Conversation => ({
      id: c.id,
      title: c.title,
      messages: messagesByConv.get(c.id) ?? [],
      at: c.created_at,
    })),

    inbox: (raw.inbox ?? []).map((i: any): InboxItem => ({
      id: i.id,
      kind: i.kind,
      title: i.title,
      body: i.body,
      cardRef: i.card_ref,
      at: i.created_at,
      read: !!i.read,
    })),

    automations: (raw.automations ?? []).map((a: any): Automation => ({
      id: a.id,
      name: a.name,
      trigger: a.trigger,
      action: a.action,
      enabled: !!a.enabled,
      runs: a.runs,
    })),
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ------------------------------------------------------------------- api

export const api = {
  snapshot: async (): Promise<Snapshot> => toSnapshot(await req('/api/workspace')),

  createBoard: (name: string, template: string, stages: string[]) =>
    post<{ boardId: string }>('/api/boards', { name, template, stages }),

  createCard: (input: {
    boardId: string
    stageId?: string
    title: string
    tag?: string
    due?: string | null
    payoutCents?: number
  }) => post<{ cardId: string }>('/api/cards', input),

  updateCard: (cardId: string, body: Partial<Record<string, unknown>>) =>
    patch(`/api/cards/${cardId}`, body),

  addCardComment: (cardId: string, body: string) =>
    post(`/api/cards/${cardId}/comments`, { body }),

  /** Raw-body upload: no multipart parser needed on either side. */
  uploadFile: async (file: File, cardId?: string | null) => {
    const q = new URLSearchParams({ name: file.name })
    if (cardId) q.set('cardId', cardId)
    return req<{ id: string; name: string; size: number; kind: string }>(
      `/api/files?${q}`,
      { method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } },
    )
  },

  createReview: (input: {
    fileId: string
    title?: string
    durationSec?: number
    fps?: number
    cardId?: string | null
  }) => post<{ id: string; version: number }>('/api/review', input),

  addReviewComment: (
    assetId: string,
    input: { timecodeSec: number; body: string; region: ReviewRegion | null },
  ) => post(`/api/review/${assetId}/comments`, input),

  setReviewCommentResolved: (commentId: string, resolved: boolean) =>
    patch(`/api/review/comments/${commentId}`, { resolved }),

  setReviewStatus: (assetId: string, status: ReviewAsset['status']) =>
    patch(`/api/review/${assetId}`, { status }),

  addBrainDoc: (input: { title: string; kind?: string; source?: string; body?: string }) =>
    post('/api/brain', input),

  payPayout: (payoutId: string) => post<{ invoiceNo: string }>(`/api/payouts/${payoutId}/pay`),

  markInboxAllRead: () => post('/api/inbox/read-all'),
  markInboxRead: (itemId: string) => patch(`/api/inbox/${itemId}`, {}),
  addInboxItem: (input: { kind: string; title: string; body?: string; cardRef?: string | null }) =>
    post('/api/inbox', input),
  toggleChecklistItem: (itemId: string, done: boolean) =>
    patch(`/api/checklist/${itemId}`, { done }),
  sendChatMessage: (channelId: string, body: string) =>
    post(`/api/chat/${channelId}/messages`, { body }),
  setAutomationEnabled: (autoId: string, enabled: boolean) =>
    patch(`/api/automations/${autoId}`, { enabled }),
  deleteReviewComment: (commentId: string) =>
    req(`/api/review/comments/${commentId}`, { method: 'DELETE' }),

  ask: (input: { message: string; conversationId?: string | null; useBrain?: boolean }) =>
    post<{
      conversationId: string
      messageId: string
      reply: string
      proposal: { id: string; kind: string; summary: string; status: string } | null
      provider: string
      note: string | null
    }>('/api/forge/ask', input),

  approve: (messageId: string) => post('/api/forge/approve', { messageId }),
  decline: (messageId: string) => post('/api/forge/decline', { messageId }),

  generate: (input: { module: string; prompt: string; settings?: Record<string, unknown> }) =>
    post<{ id: string; title: string; body: string; credits: number; fileId?: string }>(
      '/api/generate',
      input,
    ),
}

export { ApiError }
