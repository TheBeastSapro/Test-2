import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import * as seed from './seed'
import type {
  Automation,
  Board,
  BrainDoc,
  Card,
  ChatMessage,
  Competitor,
  Conversation,
  Creation,
  InboxItem,
  Payout,
  PlaygroundModuleId,
} from './types'

const STORAGE_KEY = 'kloudboard.workspace.v1'

interface State {
  workspaceId: string
  boards: Board[]
  cards: Card[]
  payouts: Payout[]
  messages: ChatMessage[]
  inbox: InboxItem[]
  brain: BrainDoc[]
  creations: Creation[]
  automations: Automation[]
  competitors: Competitor[]
  conversations: Conversation[]
  credits: number
}

const initial = (): State => ({
  workspaceId: seed.workspaces[0].id,
  boards: seed.boards,
  cards: seed.cards,
  payouts: seed.payouts,
  messages: seed.messages,
  inbox: seed.inbox,
  brain: seed.brain,
  creations: seed.creations,
  automations: seed.automations,
  competitors: seed.competitors,
  conversations: seed.conversations,
  credits: seed.CREDITS_START,
})

function load(): State {
  if (typeof localStorage === 'undefined') return initial()
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return initial()
    // Merge over a fresh baseline so a seed change never leaves a half-shaped
    // object behind from an older persisted session.
    return { ...initial(), ...(JSON.parse(raw) as Partial<State>) }
  } catch {
    return initial()
  }
}

interface Store extends State {
  setWorkspace(id: string): void
  moveCard(cardId: string, stageId: string): void
  addCard(card: Omit<Card, 'id' | 'ref' | 'createdAt'>): Card
  updateCard(cardId: string, patch: Partial<Card>): void
  toggleChecklistItem(cardId: string, itemId: string): void
  addComment(cardId: string, body: string): void
  addBoard(board: Omit<Board, 'id'>): Board
  sendMessage(channelId: string, body: string): void
  markInboxRead(id: string): void
  markAllInboxRead(): void
  addInboxItem(item: Omit<InboxItem, 'id' | 'at' | 'read'>): void
  setPayoutStatus(id: string, status: Payout['status']): void
  addBrainDoc(doc: Omit<BrainDoc, 'id' | 'at'>): void
  addCreation(c: Omit<Creation, 'id' | 'at'>): void
  toggleAutomation(id: string): void
  spendCredits(n: number): void
  upsertConversation(c: Conversation): void
  reset(): void
}

const Ctx = createContext<Store | null>(null)

let seq = 1000
const nextId = (p: string) => `${p}-${++seq}-${Math.random().toString(36).slice(2, 7)}`

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(load)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Storage full or blocked (private mode). The app stays fully usable
      // in memory; only cross-reload persistence is lost.
    }
  }, [state])

  const patch = useCallback(
    (fn: (s: State) => Partial<State>) => setState((s) => ({ ...s, ...fn(s) })),
    [],
  )

  const store = useMemo<Store>(() => {
    const mapCards = (s: State, id: string, fn: (c: Card) => Card) =>
      s.cards.map((c) => (c.id === id ? fn(c) : c))

    return {
      ...state,

      setWorkspace: (workspaceId) => patch(() => ({ workspaceId })),

      moveCard: (cardId, stageId) =>
        patch((s) => ({ cards: mapCards(s, cardId, (c) => ({ ...c, stageId })) })),

      addCard: (input) => {
        const nums = state.cards.map((c) => Number(c.ref.split('-')[1]) || 0)
        const card: Card = {
          ...input,
          id: nextId('card'),
          ref: `KB-${Math.max(0, ...nums) + 1}`,
          createdAt: new Date().toISOString(),
        }
        patch((s) => ({ cards: [...s.cards, card] }))
        return card
      },

      updateCard: (cardId, p) =>
        patch((s) => ({ cards: mapCards(s, cardId, (c) => ({ ...c, ...p })) })),

      toggleChecklistItem: (cardId, itemId) =>
        patch((s) => ({
          cards: mapCards(s, cardId, (c) => ({
            ...c,
            checklist: c.checklist.map((i) =>
              i.id === itemId ? { ...i, done: !i.done } : i,
            ),
          })),
        })),

      addComment: (cardId, body) =>
        patch((s) => ({
          cards: mapCards(s, cardId, (c) => ({
            ...c,
            comments: [
              ...c.comments,
              { id: nextId('cm'), authorId: 'm-1', body, at: new Date().toISOString() },
            ],
          })),
        })),

      addBoard: (input) => {
        const board: Board = { ...input, id: nextId('b') }
        patch((s) => ({ boards: [...s.boards, board] }))
        return board
      },

      sendMessage: (channelId, body) =>
        patch((s) => ({
          messages: [
            ...s.messages,
            { id: nextId('msg'), channelId, authorId: 'm-1', body, at: new Date().toISOString() },
          ],
        })),

      markInboxRead: (id) =>
        patch((s) => ({
          inbox: s.inbox.map((i) => (i.id === id ? { ...i, read: true } : i)),
        })),

      markAllInboxRead: () =>
        patch((s) => ({ inbox: s.inbox.map((i) => ({ ...i, read: true })) })),

      addInboxItem: (item) =>
        patch((s) => ({
          inbox: [
            { ...item, id: nextId('i'), at: new Date().toISOString(), read: false },
            ...s.inbox,
          ],
        })),

      setPayoutStatus: (id, status) =>
        patch((s) => ({
          payouts: s.payouts.map((p) =>
            p.id !== id
              ? p
              : {
                  ...p,
                  status,
                  // Invoices generate on payment — the "no chasing freelancers" rule.
                  invoiceNo:
                    status === 'paid' && !p.invoiceNo
                      ? `INV-${String(4_042 + s.payouts.length).padStart(4, '0')}`
                      : p.invoiceNo,
                },
          ),
        })),

      addBrainDoc: (doc) =>
        patch((s) => ({
          brain: [{ ...doc, id: nextId('br'), at: new Date().toISOString() }, ...s.brain],
        })),

      addCreation: (c) =>
        patch((s) => ({
          creations: [{ ...c, id: nextId('cr'), at: new Date().toISOString() }, ...s.creations],
        })),

      toggleAutomation: (id) =>
        patch((s) => ({
          automations: s.automations.map((a) =>
            a.id === id ? { ...a, enabled: !a.enabled } : a,
          ),
        })),

      spendCredits: (n) => patch((s) => ({ credits: Math.max(0, s.credits - n) })),

      upsertConversation: (c) =>
        patch((s) => {
          const exists = s.conversations.some((x) => x.id === c.id)
          return {
            conversations: exists
              ? s.conversations.map((x) => (x.id === c.id ? c : x))
              : [c, ...s.conversations],
          }
        }),

      reset: () => {
        try {
          localStorage.removeItem(STORAGE_KEY)
        } catch {
          /* nothing to clear */
        }
        setState(initial())
      },
    }
  }, [state, patch])

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
