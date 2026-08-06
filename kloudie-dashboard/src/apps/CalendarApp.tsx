import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useStore } from '../lib/store'
import { dayKey, isOverdue } from '../lib/format'
import { Button, PageHeader, Panel, Tag, cx } from '../components/ui'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function CalendarApp() {
  const { cards, boards, updateCard } = useStore()
  const [cursor, setCursor] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })

  /** Cards keyed by due day — the Calendar is just another view of the spine. */
  const byDay = useMemo(() => {
    const map = new Map<string, typeof cards>()
    for (const c of cards) {
      if (!c.due) continue
      const k = dayKey(c.due)
      map.set(k, [...(map.get(k) ?? []), c])
    }
    return map
  }, [cards])

  const grid = useMemo(() => {
    const first = new Date(cursor)
    // Monday-first offset.
    const lead = (first.getDay() + 6) % 7
    const start = new Date(first)
    start.setDate(first.getDate() - lead)
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      return d
    })
  }, [cursor])

  const shift = (n: number) =>
    setCursor((c) => new Date(c.getFullYear(), c.getMonth() + n, 1))

  const todayKey = dayKey(new Date())
  const monthLabel = cursor.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  return (
    <div className="mx-auto max-w-6xl p-6">
      <PageHeader
        title="Calendar"
        subtitle="Every card with a due date. Drag a card to reschedule it."
        action={
          <div className="flex items-center gap-1.5">
            <Button size="sm" onClick={() => shift(-1)} aria-label="Previous month">
              <ChevronLeft size={14} />
            </Button>
            <span className="min-w-36 text-center text-[13px] font-semibold">{monthLabel}</span>
            <Button size="sm" onClick={() => shift(1)} aria-label="Next month">
              <ChevronRight size={14} />
            </Button>
          </div>
        }
      />

      <Panel bodyClassName="p-0">
        <div className="grid grid-cols-7 border-b border-line">
          {WEEKDAYS.map((d) => (
            <div
              key={d}
              className="px-2 py-2 text-[10px] font-semibold tracking-wide text-subtle uppercase"
            >
              {d}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((d) => {
            const k = dayKey(d)
            const items = byDay.get(k) ?? []
            const outside = d.getMonth() !== cursor.getMonth()
            return (
              <div
                key={k}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  const id = e.dataTransfer.getData('text/plain')
                  if (id) updateCard(id, { due: new Date(`${k}T12:00:00Z`).toISOString() })
                }}
                className={cx(
                  'min-h-24 border-r border-b border-line p-1.5 last:border-r-0',
                  outside && 'bg-zinc-50/60',
                )}
              >
                <span
                  className={cx(
                    'mb-1 inline-grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-medium tabular-nums',
                    k === todayKey
                      ? 'bg-brand text-white'
                      : outside
                        ? 'text-zinc-300'
                        : 'text-subtle',
                  )}
                >
                  {d.getDate()}
                </span>
                <ul className="space-y-1">
                  {items.map((c) => {
                    const board = boards.find((b) => b.id === c.boardId)
                    const stage = board?.stages.find((s) => s.id === c.stageId)
                    const published = board?.stages.at(-1)?.id === c.stageId
                    return (
                      <li key={c.id}>
                        <Link
                          to={`/boards/${c.boardId}?card=${c.id}`}
                          draggable
                          onDragStart={(e) => e.dataTransfer.setData('text/plain', c.id)}
                          title={`${c.ref} · ${c.title} · ${stage?.name ?? ''}`}
                          className={cx(
                            'block cursor-grab rounded border px-1.5 py-1 text-[10px] leading-tight',
                            published
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                              : isOverdue(c.due)
                                ? 'border-red-200 bg-red-50 text-red-800'
                                : 'border-line bg-white hover:bg-zinc-50',
                          )}
                        >
                          <span className="mb-0.5 block">
                            <Tag>{c.tag}</Tag>
                          </span>
                          <span className="line-clamp-2 font-medium">{c.title}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}
