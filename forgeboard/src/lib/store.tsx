import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, auth, type AuthUser, type FileRow, type Snapshot } from './api'
import { setMemberRegistry } from './format'
import type {
  Board,
  BrainDoc,
  Card,
  Conversation,
  InboxItem,
  Member,
  Payout,
  PlaygroundModuleId,
  ReviewAsset,
  ReviewComment,
  ReviewRegion,
} from './types'

/**
 * Server-backed store.
 *
 * Every mutation is a request; the snapshot is refetched after it lands. That
 * is chattier than patching local state, but it means the screen can never
 * disagree with the database — which matters far more here, because the same
 * workspace is now reachable from another browser and another person.
 */

const EMPTY: Snapshot = {
  workspaceName: '',
  channels: [],
  chatMessages: [],
  competitors: [],
  contracts: [],
  credits: 0,
  members: [],
  boards: [],
  cards: [],
  files: [],
  reviewAssets: [],
  reviewComments: [],
  payouts: [],
  brain: [],
  creations: [],
  conversations: [],
  inbox: [],
  automations: [],
  agentProvider: 'mock',
}

interface Store extends Snapshot {
  user: AuthUser | null
  loading: boolean
  error: string | null
  refresh(): Promise<void>
  signIn(email: string, password: string): Promise<void>
  signUp(name: string, email: string, password: string): Promise<void>
  signOut(): Promise<void>

  moveCard(cardId: string, stageId: string): Promise<void>
  updateCard(cardId: string, patch: Partial<Card>): Promise<void>
  addCard(input: {
    boardId: string
    stageId?: string
    title: string
    tag?: string
    due?: string | null
    payoutCents?: number
  }): Promise<void>
  addComment(cardId: string, body: string): Promise<void>
  addBoard(input: { name: string; template: string; stages: string[] }): Promise<void>

  uploadFile(file: File, cardId?: string | null): Promise<FileRow | null>
  createReview(input: {
    fileId: string
    title?: string
    durationSec?: number
    fps?: number
    cardId?: string | null
  }): Promise<void>
  addReviewComment(
    assetId: string,
    input: { timecodeSec: number; body: string; region: ReviewRegion | null },
  ): Promise<void>
  toggleReviewComment(commentId: string, resolved: boolean): Promise<void>
  setReviewStatus(assetId: string, status: ReviewAsset['status']): Promise<void>

  addBrainDoc(input: { title: string; kind?: string; source?: string; body?: string }): Promise<void>
  setPayoutPaid(payoutId: string): Promise<void>
  markAllInboxRead(): Promise<void>
  markInboxRead(itemId: string): Promise<void>
  addInboxItem(input: { kind: string; title: string; body?: string; cardRef?: string | null }): Promise<void>
  toggleChecklistItem(itemId: string, done: boolean): Promise<void>
  sendChatMessage(channelId: string, body: string): Promise<void>
  setAutomationEnabled(autoId: string, enabled: boolean): Promise<void>
  deleteReviewComment(commentId: string): Promise<void>

  ask(input: { message: string; conversationId?: string | null; useBrain?: boolean }): Promise<{
    conversationId: string
    messageId: string
    note: string | null
  }>
  approveProposal(messageId: string): Promise<void>
  declineProposal(messageId: string): Promise<void>
  generate(input: {
    module: PlaygroundModuleId
    prompt: string
    settings?: Record<string, unknown>
  }): Promise<{ title: string; body: string; credits: number }>
}

const Ctx = createContext<Store | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [snap, setSnap] = useState<Snapshot>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Components resolve authors through member(); keep it fed from the server
  // so avatars and names are real users rather than seed data.
  useEffect(() => setMemberRegistry(snap.members), [snap.members])

  const refresh = useCallback(async () => {
    try {
      setSnap(await api.snapshot())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the workspace')
    }
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const { user: u } = await auth.me()
        setUser(u)
        await refresh()
      } catch {
        setUser(null)
      } finally {
        setLoading(false)
      }
    })()
  }, [refresh])

  const store = useMemo<Store>(() => {
    /** Run a mutation, then resync. Errors surface rather than failing silently. */
    const act = async (fn: () => Promise<unknown>) => {
      try {
        await fn()
        await refresh()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Something went wrong')
        throw e
      }
    }

    return {
      ...snap,
      user,
      loading,
      error,
      refresh,

      signIn: async (email, password) => {
        const { user: u } = await auth.login(email, password)
        setUser(u)
        await refresh()
      },
      signUp: async (name, email, password) => {
        const { user: u } = await auth.register(name, email, password)
        setUser(u)
        await refresh()
      },
      signOut: async () => {
        await auth.logout()
        setUser(null)
        setSnap(EMPTY)
      },

      moveCard: (cardId, stageId) => act(() => api.updateCard(cardId, { stageId })),
      updateCard: (cardId, p) =>
        act(() =>
          api.updateCard(cardId, {
            ...(p.stageId !== undefined ? { stageId: p.stageId } : {}),
            ...(p.title !== undefined ? { title: p.title } : {}),
            ...(p.due !== undefined ? { due: p.due } : {}),
            ...(p.tag !== undefined ? { tag: p.tag } : {}),
            ...(p.payoutCents !== undefined ? { payoutCents: p.payoutCents } : {}),
          }),
        ),
      addCard: (input) => act(() => api.createCard(input)),
      addComment: (cardId, body) => act(() => api.addCardComment(cardId, body)),
      addBoard: ({ name, template, stages }) =>
        act(() => api.createBoard(name, template, stages)),

      uploadFile: async (file, cardId) => {
        let created: FileRow | null = null
        await act(async () => {
          const r = await api.uploadFile(file, cardId)
          created = {
            id: r.id,
            name: r.name,
            kind: r.kind as FileRow['kind'],
            sizeKb: Math.max(1, Math.round(r.size / 1024)),
            cardId: cardId ?? null,
            at: new Date().toISOString(),
            url: `/api/files/${r.id}/content`,
          }
        })
        return created
      },
      createReview: (input) => act(() => api.createReview(input)),
      addReviewComment: (assetId, input) => act(() => api.addReviewComment(assetId, input)),
      toggleReviewComment: (commentId, resolved) =>
        act(() => api.setReviewCommentResolved(commentId, resolved)),
      setReviewStatus: (assetId, status) => act(() => api.setReviewStatus(assetId, status)),

      addBrainDoc: (input) => act(() => api.addBrainDoc(input)),
      setPayoutPaid: (payoutId) => act(() => api.payPayout(payoutId)),
      markAllInboxRead: () => act(() => api.markInboxAllRead()),
      markInboxRead: (itemId) => act(() => api.markInboxRead(itemId)),
      addInboxItem: (input) => act(() => api.addInboxItem(input)),
      toggleChecklistItem: (itemId, done) => act(() => api.toggleChecklistItem(itemId, done)),
      sendChatMessage: (channelId, body) => act(() => api.sendChatMessage(channelId, body)),
      setAutomationEnabled: (autoId, enabled) => act(() => api.setAutomationEnabled(autoId, enabled)),
      deleteReviewComment: (commentId) => act(() => api.deleteReviewComment(commentId)),

      ask: async (input) => {
        const r = await api.ask(input)
        await refresh()
        return { conversationId: r.conversationId, messageId: r.messageId, note: r.note }
      },
      approveProposal: (messageId) => act(() => api.approve(messageId)),
      declineProposal: (messageId) => act(() => api.decline(messageId)),

      generate: async (input) => {
        const r = await api.generate(input)
        await refresh()
        return { title: r.title, body: r.body, credits: r.credits }
      },
    }
  }, [snap, user, loading, error, refresh])

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>
}

export function useStore() {
  const s = useContext(Ctx)
  if (!s) throw new Error('useStore must be used inside <StoreProvider>')
  return s
}

/** Credit cost per Playground module — the metered-AI half of the model. */
export const CREDIT_COST: Record<PlaygroundModuleId, number> = {
  tts: 1, // per 10 characters
  sfx: 24,
  music: 60,
  image: 24,
  script: 140,
  social: 38,
}

export type { Board, BrainDoc, Card, Conversation, InboxItem, Member, Payout, ReviewComment }
