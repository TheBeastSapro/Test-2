import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileAudio, FileImage, FileText, FileVideo, Package } from 'lucide-react'
import { useStore } from '../lib/store'
import { assets } from '../lib/seed'
import { bytes, relative } from '../lib/format'
import { Badge, Empty, PageHeader, Panel, cx } from '../components/ui'
import type { Asset } from '../lib/types'

const ICON: Record<Asset['kind'], typeof FileText> = {
  audio: FileAudio,
  image: FileImage,
  doc: FileText,
  video: FileVideo,
  other: Package,
}

const TONE: Record<Asset['kind'], string> = {
  audio: 'bg-violet-50 text-violet-600',
  image: 'bg-blue-50 text-blue-600',
  doc: 'bg-amber-50 text-amber-600',
  video: 'bg-emerald-50 text-emerald-600',
  other: 'bg-zinc-100 text-zinc-600',
}

const FILTERS = ['all', 'audio', 'image', 'doc', 'video', 'other'] as const

export default function FilesApp() {
  const { cards } = useStore()
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all')

  const shown = assets.filter((a) => filter === 'all' || a.kind === filter)
  const totalKb = assets.reduce((a, x) => a + x.sizeKb, 0)

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="Files"
        subtitle={`${assets.length} assets · ${bytes(totalKb)} of 50 GB used`}
        action={
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cx(
                  'rounded-lg px-2.5 py-1 text-[12px] font-medium capitalize transition-colors',
                  f === filter ? 'bg-ink text-white' : 'text-subtle hover:bg-zinc-100',
                )}
              >
                {f}
              </button>
            ))}
          </div>
        }
      />

      <Panel bodyClassName="p-0">
        {shown.length === 0 ? (
          <Empty title="No files of that type" />
        ) : (
          <ul className="divide-y divide-line">
            {shown.map((a) => {
              const Icon = ICON[a.kind]
              const card = cards.find((c) => c.id === a.cardId)
              return (
                <li key={a.id} className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-50">
                  <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', TONE[a.kind])}>
                    <Icon size={16} strokeWidth={1.8} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{a.name}</span>
                    <span className="block text-[11px] text-subtle">
                      {bytes(a.sizeKb)} · added {relative(a.at)}
                    </span>
                  </span>
                  {card ? (
                    <Link
                      to={`/boards/${card.boardId}?card=${card.id}`}
                      className="shrink-0"
                      title={card.title}
                    >
                      <Badge tone="blue">{card.ref}</Badge>
                    </Link>
                  ) : (
                    <Badge>Unlinked</Badge>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </div>
  )
}
