import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Calendar as CalIcon,
  Clapperboard,
  MessageSquare,
  Paperclip,
  Plus,
  X,
} from 'lucide-react'
import { useStore } from '../lib/store'
import { assets } from '../lib/seed'
import { isOverdue, member, money, relative, shortDate } from '../lib/format'
import {
  Avatar,
  AvatarStack,
  Badge,
  Button,
  Empty,
  PageHeader,
  Progress,
  Tag,
  cx,
} from '../components/ui'
import type { Card } from '../lib/types'

export default function Boards() {
  const { boards, cards, moveCard, addCard } = useStore()
  const { boardId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [dragging, setDragging] = useState<string | null>(null)
  const [over, setOver] = useState<string | null>(null)

  const board = boards.find((b) => b.id === boardId) ?? boards[0]
  const openCard = cards.find((c) => c.id === params.get('card')) ?? null

  if (!board) return <Empty title="No boards yet" />

  const boardCards = cards.filter((c) => c.boardId === board.id)

  const drop = (stageId: string) => {
    if (dragging) moveCard(dragging, stageId)
    setDragging(null)
    setOver(null)
  }

  const quickAdd = (stageId: string) => {
    const title = window.prompt('Card title')?.trim()
    if (!title) return
    addCard({
      boardId: board.id,
      stageId,
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

  return (
    <div className="flex h-full flex-col p-6">
      <PageHeader
        title={board.name}
        subtitle={
          <>
            {board.template} template · {boardCards.length} cards
          </>
        }
        action={
          <div className="flex flex-wrap gap-1.5">
            {boards.map((b) => (
              <Button
                key={b.id}
                size="sm"
                variant={b.id === board.id ? 'primary' : 'default'}
                onClick={() => navigate(`/boards/${b.id}`)}
              >
                {b.name}
              </Button>
            ))}
          </div>
        }
      />

      <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2">
        {board.stages.map((stage) => {
          const stageCards = boardCards.filter((c) => c.stageId === stage.id)
          return (
            <section
              key={stage.id}
              onDragOver={(e) => {
                e.preventDefault()
                setOver(stage.id)
              }}
              onDragLeave={() => setOver((s) => (s === stage.id ? null : s))}
              onDrop={() => drop(stage.id)}
              className={cx(
                'flex w-72 shrink-0 flex-col rounded-xl border bg-white transition-colors',
                over === stage.id ? 'border-brand bg-brand-soft/40' : 'border-line',
              )}
            >
              <header className="flex items-center gap-2 px-3 py-2.5">
                <span className={cx('h-2 w-2 rounded-full', stage.tone)} />
                <h2 className="text-[12px] font-semibold tracking-wide uppercase">
                  {stage.name}
                </h2>
                <Badge>{stageCards.length}</Badge>
                <button
                  onClick={() => quickAdd(stage.id)}
                  aria-label={`Add a card to ${stage.name}`}
                  className="ml-auto grid h-6 w-6 place-items-center rounded text-subtle hover:bg-zinc-100 hover:text-ink"
                >
                  <Plus size={14} />
                </button>
              </header>
              <ul className="min-h-16 flex-1 space-y-2 overflow-y-auto px-2 pb-2">
                {stageCards.map((card) => (
                  <li key={card.id}>
                    <BoardCard
                      card={card}
                      dragging={dragging === card.id}
                      onDragStart={() => setDragging(card.id)}
                      onDragEnd={() => setDragging(null)}
                      onOpen={() => setParams({ card: card.id })}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )
        })}
      </div>

      {openCard && <CardDrawer card={openCard} onClose={() => setParams({})} />}
    </div>
  )
}

function BoardCard({
  card,
  dragging,
  onDragStart,
  onDragEnd,
  onOpen,
}: {
  card: Card
  dragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
  onOpen: () => void
}) {
  const done = card.checklist.filter((i) => i.done).length
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      role="button"
      tabIndex={0}
      className={cx(
        'cursor-grab rounded-lg border border-line bg-white p-2.5 text-left shadow-[0_1px_2px_rgba(16,17,20,0.05)] transition-shadow',
        'hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        dragging && 'opacity-40',
      )}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <Tag>{card.tag}</Tag>
        <span className="text-[10px] font-medium text-subtle">{card.ref}</span>
        {card.due && (
          <span
            className={cx(
              'ml-auto flex items-center gap-1 text-[10px] font-medium',
              isOverdue(card.due) ? 'text-red-600' : 'text-subtle',
            )}
          >
            <CalIcon size={10} />
            {shortDate(card.due)}
          </span>
        )}
      </div>
      <p className="text-[13px] leading-snug font-medium">{card.title}</p>
      {card.checklist.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 flex justify-between text-[10px] text-subtle">
            <span>Progress</span>
            <span className="tabular-nums">
              {done}/{card.checklist.length}
            </span>
          </div>
          <Progress value={done} max={card.checklist.length} />
        </div>
      )}
      <div className="mt-2 flex items-center gap-2 text-[10px] text-subtle">
        {card.comments.length > 0 && (
          <span className="flex items-center gap-0.5">
            <MessageSquare size={11} />
            {card.comments.length}
          </span>
        )}
        {card.attachmentIds.length > 0 && (
          <span className="flex items-center gap-0.5">
            <Paperclip size={11} />
            {card.attachmentIds.length}
          </span>
        )}
        {card.payoutCents > 0 && (
          <span className="font-medium text-emerald-700">{money(card.payoutCents)}</span>
        )}
        <span className="ml-auto">
          <AvatarStack ids={card.assigneeIds} size={20} />
        </span>
      </div>
    </div>
  )
}

function CardDrawer({ card, onClose }: { card: Card; onClose: () => void }) {
  const {
    boards,
    reviewAssets,
    reviewComments,
    toggleChecklistItem,
    addComment,
    updateCard,
  } = useStore()
  const [draft, setDraft] = useState('')
  const board = boards.find((b) => b.id === card.boardId)!
  const done = card.checklist.filter((i) => i.done).length
  const attached = assets.filter((a) => card.attachmentIds.includes(a.id))
  const cuts = reviewAssets
    .filter((a) => a.cardId === card.id)
    .sort((a, b) => b.version - a.version)

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-ink/20"
      onClick={onClose}
      role="presentation"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={card.title}
        onClick={(e) => e.stopPropagation()}
        className="kb-in flex h-full w-full max-w-md flex-col border-l border-line bg-white"
      >
        <header className="flex items-start gap-3 border-b border-line p-4">
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 flex items-center gap-2">
              <Tag>{card.tag}</Tag>
              <span className="text-[11px] font-medium text-subtle">{card.ref}</span>
            </div>
            <h2 className="text-[15px] leading-snug font-semibold">{card.title}</h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-subtle hover:bg-zinc-100 hover:text-ink"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          <dl className="grid grid-cols-2 gap-3 text-[12px]">
            <Field label="Stage">
              <select
                value={card.stageId}
                onChange={(e) => updateCard(card.id, { stageId: e.target.value })}
                className="w-full rounded-md border border-line px-2 py-1 text-[12px]"
              >
                {board.stages.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Due">
              <input
                type="date"
                value={card.due?.slice(0, 10) ?? ''}
                onChange={(e) =>
                  updateCard(card.id, {
                    due: e.target.value ? new Date(e.target.value).toISOString() : null,
                  })
                }
                className="w-full rounded-md border border-line px-2 py-1 text-[12px]"
              />
            </Field>
            <Field label="Assignees">
              {card.assigneeIds.length ? (
                <div className="flex items-center gap-1.5">
                  <AvatarStack ids={card.assigneeIds} size={22} />
                  <span className="truncate text-[12px] text-subtle">
                    {card.assigneeIds.map((id) => member(id).name).join(', ')}
                  </span>
                </div>
              ) : (
                <span className="text-subtle">Unassigned</span>
              )}
            </Field>
            <Field label="Payout on completion">
              <span className="font-medium">
                {card.payoutCents ? money(card.payoutCents) : '—'}
              </span>
            </Field>
          </dl>

          <section>
            <h3 className="mb-2 flex items-center justify-between text-[12px] font-semibold">
              Checklist
              <span className="text-[11px] font-normal text-subtle tabular-nums">
                {done}/{card.checklist.length}
              </span>
            </h3>
            {card.checklist.length === 0 ? (
              <p className="text-[12px] text-subtle">No checklist.</p>
            ) : (
              <ul className="space-y-1.5">
                {card.checklist.map((i) => (
                  <li key={i.id}>
                    <label className="flex cursor-pointer items-center gap-2 text-[13px]">
                      <input
                        type="checkbox"
                        checked={i.done}
                        onChange={() => toggleChecklistItem(card.id, i.id)}
                        className="h-3.5 w-3.5 accent-[var(--color-brand)]"
                      />
                      <span className={cx(i.done && 'text-subtle line-through')}>{i.label}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {cuts.length > 0 && (
            <section>
              <h3 className="mb-2 text-[12px] font-semibold">Cuts in review</h3>
              <ul className="space-y-1.5">
                {cuts.map((cut) => {
                  const open = reviewComments.filter(
                    (rc) => rc.assetId === cut.id && !rc.resolved,
                  ).length
                  return (
                    <li
                      key={cut.id}
                      className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5"
                    >
                      <Clapperboard size={12} className="shrink-0 text-subtle" />
                      <span className="min-w-0 flex-1 truncate text-[12px]">
                        v{cut.version} · {cut.status}
                        {open > 0 && ` · ${open} open`}
                      </span>
                      <Link
                        to={`/review?asset=${cut.id}`}
                        className="shrink-0 rounded-md bg-brand px-2 py-1 text-[11px] font-medium text-white hover:bg-brand/90"
                      >
                        Review
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          {attached.length > 0 && (
            <section>
              <h3 className="mb-2 text-[12px] font-semibold">Attachments</h3>
              <ul className="space-y-1.5">
                {attached.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-[12px]"
                  >
                    <Paperclip size={12} className="text-subtle" />
                    <span className="truncate">{a.name}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-[12px] font-semibold">Comments</h3>
            <ul className="space-y-3">
              {card.comments.map((c) => (
                <li key={c.id} className="flex gap-2">
                  <Avatar id={c.authorId} size={24} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px]">
                      <span className="font-medium">{member(c.authorId).name}</span>
                      <span className="ml-1.5 text-subtle">{relative(c.at)}</span>
                    </p>
                    <p className="text-[13px] text-ink">{c.body}</p>
                  </div>
                </li>
              ))}
              {card.comments.length === 0 && (
                <li className="text-[12px] text-subtle">No comments yet.</li>
              )}
            </ul>
          </section>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            const body = draft.trim()
            if (!body) return
            addComment(card.id, body)
            setDraft('')
          }}
          className="flex gap-2 border-t border-line p-3"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Write a comment…"
            aria-label="Write a comment"
            className="min-w-0 flex-1 rounded-lg border border-line px-2.5 py-1.5 text-[13px] outline-none focus:border-brand"
          />
          <Button type="submit" variant="primary" size="sm" disabled={!draft.trim()}>
            Send
          </Button>
        </form>
      </aside>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="mb-1 text-[10px] font-semibold tracking-wide text-subtle uppercase">
        {label}
      </dt>
      <dd className="m-0">{children}</dd>
    </div>
  )
}
