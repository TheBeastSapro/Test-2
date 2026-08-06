import { useState } from 'react'
import { AudioLines, ImageIcon, Music, PenLine, Share2, Waves } from 'lucide-react'
import { useStore } from '../../lib/store'
import { relative } from '../../lib/format'
import { Badge, Empty, PageHeader, Panel, cx } from '../../components/ui'
import type { PlaygroundModuleId } from '../../lib/types'

export const MODULE_META: Record<
  PlaygroundModuleId,
  { label: string; Icon: typeof PenLine; tone: string }
> = {
  tts: { label: 'Text to Speech', Icon: AudioLines, tone: 'bg-violet-50 text-violet-600' },
  sfx: { label: 'Sound Effects', Icon: Waves, tone: 'bg-cyan-50 text-cyan-600' },
  music: { label: 'Music', Icon: Music, tone: 'bg-pink-50 text-pink-600' },
  image: { label: 'Image', Icon: ImageIcon, tone: 'bg-blue-50 text-blue-600' },
  script: { label: 'Script Writing', Icon: PenLine, tone: 'bg-amber-50 text-amber-600' },
  social: { label: 'Social Posts', Icon: Share2, tone: 'bg-emerald-50 text-emerald-600' },
}

const FILTERS = ['all', ...Object.keys(MODULE_META)] as const

export default function Library() {
  const { creations } = useStore()
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all')

  const shown = creations.filter((c) => filter === 'all' || c.module === filter)
  const spent = creations.reduce((a, c) => a + c.credits, 0)

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader
        title="Library"
        subtitle={`${creations.length} creations · ${spent.toLocaleString()} credits spent`}
        action={
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cx(
                  'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                  f === filter ? 'bg-ink text-white' : 'text-subtle hover:bg-zinc-100',
                )}
              >
                {f === 'all' ? 'All' : MODULE_META[f as PlaygroundModuleId].label}
              </button>
            ))}
          </div>
        }
      />

      <Panel bodyClassName="p-0">
        {shown.length === 0 ? (
          <Empty
            title="Nothing here yet"
            hint="Anything Forge or the Playground produces lands in the Library."
          />
        ) : (
          <ul className="divide-y divide-line">
            {shown.map((c) => {
              const meta = MODULE_META[c.module]
              return (
                <li key={c.id} className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-50">
                  <span
                    className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', meta.tone)}
                  >
                    <meta.Icon size={16} strokeWidth={1.8} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{c.title}</span>
                    <span className="mt-0.5 block text-[12px] text-subtle">{c.body}</span>
                    <span className="mt-1 block text-[11px] text-subtle">
                      {meta.label} · {relative(c.at)}
                    </span>
                  </span>
                  <Badge>{c.credits} cr</Badge>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </div>
  )
}
