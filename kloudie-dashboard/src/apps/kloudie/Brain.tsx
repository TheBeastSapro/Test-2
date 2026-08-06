import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileText, Link2, NotebookPen, Search } from 'lucide-react'
import { useStore } from '../../lib/store'
import { relative } from '../../lib/format'
import { Badge, Button, Empty, PageHeader, Panel, cx } from '../../components/ui'
import type { BrainDoc } from '../../lib/types'

const KIND_ICON: Record<BrainDoc['kind'], typeof FileText> = {
  transcript: FileText,
  note: NotebookPen,
  sop: NotebookPen,
  synced: Link2,
}

export default function Brain() {
  const { brain, addBrainDoc } = useStore()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')

  const results = useMemo(() => {
    const n = q.trim().toLowerCase()
    if (!n) return brain
    return brain.filter(
      (d) => d.title.toLowerCase().includes(n) || d.body.toLowerCase().includes(n),
    )
  }, [brain, q])

  const selected = brain.find((d) => d.id === params.get('doc')) ?? results[0] ?? null

  const addNote = () => {
    const title = window.prompt('Note title')?.trim()
    if (!title) return
    const body = window.prompt('What should kloudie remember?')?.trim() ?? ''
    addBrainDoc({ title, kind: 'note', source: 'Written by you', body })
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="Brain"
        subtitle="What kloudie grounds on. Pasted links are transcribed on ingest, then searchable."
        action={
          <Button size="sm" variant="primary" onClick={addNote}>
            Add note
          </Button>
        }
      />

      <div className="mb-4 flex h-9 items-center gap-2 rounded-lg border border-line bg-white px-3 focus-within:border-brand">
        <Search size={15} className="text-subtle" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search the Brain…"
          aria-label="Search the Brain"
          className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-subtle"
        />
        <span className="text-[11px] text-subtle">{results.length} of {brain.length}</span>
      </div>

      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        <Panel bodyClassName="p-0">
          {results.length === 0 ? (
            <Empty title="No matches" />
          ) : (
            <ul className="divide-y divide-line">
              {results.map((d) => {
                const Icon = KIND_ICON[d.kind]
                return (
                  <li key={d.id}>
                    <button
                      onClick={() => setParams({ doc: d.id })}
                      className={cx(
                        'flex w-full items-start gap-2 px-3 py-2.5 text-left',
                        selected?.id === d.id ? 'bg-brand-soft/50' : 'hover:bg-zinc-50',
                      )}
                    >
                      <Icon size={14} className="mt-0.5 shrink-0 text-subtle" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] font-medium">
                          {d.title}
                        </span>
                        <span className="block text-[10px] text-subtle">
                          {d.kind} · {relative(d.at)}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>

        {selected ? (
          <Panel
            title={selected.title}
            action={<Badge tone="blue">{selected.kind}</Badge>}
          >
            <p className="mb-3 flex items-center gap-1.5 text-[11px] text-subtle">
              <Link2 size={11} />
              {selected.source} · added {relative(selected.at)}
            </p>
            <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{selected.body}</p>
          </Panel>
        ) : (
          <Panel>
            <Empty title="Nothing selected" hint="Pick a document to read it." />
          </Panel>
        )}
      </div>
    </div>
  )
}
