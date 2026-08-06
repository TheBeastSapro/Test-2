import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowUp, Check, CloudLightning, Plus, X } from 'lucide-react'
import { useStore } from '../../lib/store'
import { relative } from '../../lib/format'
import { Badge, Button, cx } from '../../components/ui'
import type { AgentMessage, AgentProposal, Conversation } from '../../lib/types'
import { respond } from './agent'

const STARTERS = [
  { kind: 'CREATE', text: 'Write a TikTok script in my style from my latest YouTube upload' },
  { kind: 'DESIGN', text: 'Design a thumbnail for the Tristan da Cunha video' },
  { kind: 'REPURPOSE', text: 'Turn my latest video into a week of social posts' },
  { kind: 'IMPORT', text: 'Grab my latest YouTube transcript into the Brain' },
]

export default function ForgeChat() {
  const { conversations, upsertConversation, credits, spendCredits, ...actions } = useStore()
  const { conversationId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const existing = conversations.find((c) => c.id === conversationId) ?? null
  const [draft, setDraft] = useState('')
  /** Scope control — the agent grounds on the Brain unless you narrow it. */
  const [useBrain, setUseBrain] = useState(true)
  const [thinking, setThinking] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const messages = existing?.messages ?? []

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, thinking])

  // A question typed into the top-bar omnibox arrives as ?q=
  useEffect(() => {
    const q = params.get('q')
    if (!q) return
    setParams({}, { replace: true })
    void submit(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  async function submit(body: string) {
    const text = body.trim()
    if (!text || thinking) return
    setDraft('')

    const id = existing?.id ?? `cv-${Date.now()}`
    const userMsg: AgentMessage = {
      id: `am-${Date.now()}`,
      role: 'user',
      body: text,
      at: new Date().toISOString(),
    }
    const base: Conversation = existing ?? {
      id,
      title: text.length > 52 ? `${text.slice(0, 52)}…` : text,
      messages: [],
      at: new Date().toISOString(),
    }
    const withUser = { ...base, messages: [...base.messages, userMsg] }
    upsertConversation(withUser)
    if (!existing) navigate(`/forge/c/${id}`, { replace: true })

    setThinking(true)
    const reply = await respond(text, { useBrain })
    setThinking(false)
    spendCredits(reply.credits)
    upsertConversation({ ...withUser, messages: [...withUser.messages, reply.message] })
  }

  /**
   * The approval gate. Forge proposes a workspace write; nothing lands until
   * a human confirms. Approving here executes against the same store every
   * other app reads from.
   */
  function resolve(msg: AgentMessage, decision: 'approved' | 'declined') {
    if (!existing || !msg.proposal) return
    const p = msg.proposal

    if (decision === 'approved') {
      if (p.kind === 'create_board') {
        const payload = p.payload as { name: string; template: string; stages: string[] }
        const board = actions.addBoard({
          name: payload.name,
          template: payload.template,
          stages: payload.stages.map((name, i) => ({
            id: `st-${Date.now()}-${i}`,
            name,
            tone: ['bg-zinc-400', 'bg-amber-500', 'bg-violet-500', 'bg-blue-500', 'bg-emerald-500'][
              i % 5
            ],
          })),
        })
        actions.addCard({
          boardId: board.id,
          stageId: board.stages[0].id,
          title: (p.payload.firstCard as string) ?? 'First video',
          tag: 'YOUTUBE',
          due: null,
          assigneeIds: [],
          checklist: [],
          comments: [],
          attachmentIds: [],
          payoutCents: 0,
        })
      }
      if (p.kind === 'create_card') {
        const payload = p.payload as { boardId: string; titles: string[] }
        const board = actions.boards.find((b) => b.id === payload.boardId) ?? actions.boards[0]
        for (const title of payload.titles) {
          actions.addCard({
            boardId: board.id,
            stageId: board.stages[0].id,
            title,
            tag: 'YOUTUBE',
            due: null,
            assigneeIds: [],
            checklist: [],
            comments: [],
            attachmentIds: [],
            payoutCents: 0,
          })
        }
      }
      if (p.kind === 'save_to_brain') {
        actions.addBrainDoc({
          title: (p.payload.title as string) ?? 'Untitled note',
          kind: 'note',
          source: 'Saved by Forge',
          body: (p.payload.body as string) ?? '',
        })
      }
    }

    const next: AgentProposal = { ...p, status: decision }
    upsertConversation({
      ...existing,
      messages: existing.messages.map((m) =>
        m.id === msg.id ? { ...m, proposal: next } : m,
      ),
    })
  }

  const empty = messages.length === 0 && !thinking

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-8">
          {empty ? (
            <div className="pt-10 text-center">
              <CloudLightning size={30} className="mx-auto text-brand" strokeWidth={2} />
              <h1 className="mt-3 text-[22px] font-semibold tracking-tight">
                What's on the agenda?
              </h1>
            </div>
          ) : (
            <ul className="space-y-6">
              {messages.map((m) => (
                <li key={m.id}>
                  {m.role === 'user' ? (
                    <div className="flex justify-end">
                      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-soft px-3.5 py-2.5 text-[13px] whitespace-pre-wrap text-ink">
                        {m.body}
                      </p>
                    </div>
                  ) : (
                    <div className="flex gap-2.5">
                      <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-brand text-white">
                        <CloudLightning size={13} strokeWidth={2.2} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] leading-relaxed whitespace-pre-wrap">
                          {m.body}
                        </p>
                        {m.proposal && (
                          <ProposalCard
                            proposal={m.proposal}
                            onApprove={() => resolve(m, 'approved')}
                            onDecline={() => resolve(m, 'declined')}
                          />
                        )}
                        <p className="mt-1.5 text-[10px] text-subtle">{relative(m.at)}</p>
                      </div>
                    </div>
                  )}
                </li>
              ))}
              {thinking && (
                <li className="flex items-center gap-2.5 text-[13px] text-subtle">
                  <span className="grid h-6 w-6 place-items-center rounded-md bg-brand text-white">
                    <CloudLightning size={13} strokeWidth={2.2} />
                  </span>
                  <span className="animate-pulse">Working…</span>
                </li>
              )}
            </ul>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="shrink-0 px-6 pb-6">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit(draft)
          }}
          className="mx-auto max-w-2xl"
        >
          <div className="mb-2 flex items-center gap-2 rounded-t-xl border border-b-0 border-line bg-zinc-50 px-3 py-1.5 text-[11px] text-subtle">
            <span className="font-semibold tracking-wide uppercase">Forge will use</span>
            <button
              type="button"
              onClick={() => setUseBrain((v) => !v)}
              className={cx(
                'rounded-full px-2 py-0.5 font-medium transition-colors',
                useBrain ? 'bg-brand-soft text-brand' : 'bg-zinc-200 text-zinc-600',
              )}
            >
              {useBrain ? 'your whole workspace' : 'this message only'}
            </button>
            <span className="ml-auto flex items-center gap-1">
              <Plus size={11} />
              Add a doc or source
            </span>
          </div>
          <div className="flex items-end gap-2 rounded-xl border border-line bg-white p-2 transition-colors focus-within:border-brand">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void submit(draft)
                }
              }}
              rows={2}
              placeholder="Describe a task or ask a question"
              aria-label="Message Forge"
              className="min-h-14 flex-1 resize-none bg-transparent px-2 py-1.5 text-[13px] outline-none placeholder:text-subtle"
            />
            <Button
              type="submit"
              variant="primary"
              disabled={!draft.trim() || thinking}
              className="!h-8 !w-8 shrink-0 !rounded-full !px-0"
              aria-label="Send"
            >
              <ArrowUp size={15} />
            </Button>
          </div>
          <p className="mt-1.5 text-center text-[11px] text-subtle">
            {credits.toLocaleString()} credits left · writes are proposed, never applied
            silently
          </p>
        </form>

        {empty && (
          <ul className="mx-auto mt-4 grid max-w-2xl gap-2 sm:grid-cols-2">
            {STARTERS.map((s) => (
              <li key={s.kind}>
                <button
                  onClick={() => void submit(s.text)}
                  className="w-full rounded-xl border border-line bg-white p-3 text-left transition-colors hover:border-brand hover:bg-brand-soft/30"
                >
                  <span className="block text-[10px] font-semibold tracking-wide text-subtle uppercase">
                    {s.kind}
                  </span>
                  <span className="mt-0.5 block text-[12px] text-ink">{s.text}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function ProposalCard({
  proposal,
  onApprove,
  onDecline,
}: {
  proposal: AgentProposal
  onApprove: () => void
  onDecline: () => void
}) {
  const resolved = proposal.status !== 'pending'
  return (
    <div
      className={cx(
        'mt-2.5 rounded-xl border p-3',
        resolved ? 'border-line bg-zinc-50' : 'border-brand/40 bg-brand-soft/40',
      )}
    >
      <div className="flex items-center gap-2">
        <Badge tone={resolved ? 'zinc' : 'blue'}>
          {proposal.kind.replace(/_/g, ' ')}
        </Badge>
        {proposal.status === 'approved' && (
          <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
            <Check size={12} /> Applied to the workspace
          </span>
        )}
        {proposal.status === 'declined' && (
          <span className="flex items-center gap-1 text-[11px] font-medium text-subtle">
            <X size={12} /> Declined
          </span>
        )}
      </div>
      <p className="mt-2 text-[12px] text-ink">{proposal.summary}</p>
      {!resolved && (
        <div className="mt-2.5 flex gap-2">
          <Button size="sm" variant="primary" onClick={onApprove}>
            Approve
          </Button>
          <Button size="sm" onClick={onDecline}>
            Decline
          </Button>
        </div>
      )}
    </div>
  )
}
