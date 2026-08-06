import { ArrowRight, Eye, Zap } from 'lucide-react'
import { useStore } from '../../lib/store'
import { compact } from '../../lib/format'
import { Badge, Panel, PageHeader, cx } from '../../components/ui'

export default function Automations() {
  const { automations, toggleAutomation, competitors } = useStore()
  const active = automations.filter((a) => a.enabled).length

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader
        title="Automations"
        subtitle={`${active} of ${automations.length} running · they fire against the same cards every other app reads`}
      />

      <Panel bodyClassName="p-0" className="mb-4">
        <ul className="divide-y divide-line">
          {automations.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-4 py-3">
              <span
                className={cx(
                  'grid h-9 w-9 shrink-0 place-items-center rounded-lg',
                  a.enabled ? 'bg-amber-50 text-amber-600' : 'bg-zinc-100 text-zinc-400',
                )}
              >
                <Zap size={16} strokeWidth={1.9} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium">{a.name}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-subtle">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-medium">
                    {a.trigger}
                  </span>
                  <ArrowRight size={10} />
                  <span>{a.action}</span>
                </p>
              </div>
              <Badge>{a.runs} runs</Badge>
              <button
                role="switch"
                aria-checked={a.enabled}
                aria-label={`${a.enabled ? 'Disable' : 'Enable'} ${a.name}`}
                onClick={() => toggleAutomation(a.id)}
                className={cx(
                  'relative h-5 w-9 shrink-0 rounded-full transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
                  a.enabled ? 'bg-brand' : 'bg-zinc-300',
                )}
              >
                <span
                  className={cx(
                    'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all',
                    a.enabled ? 'left-4.5' : 'left-0.5',
                  )}
                />
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel
        title={
          <span className="flex items-center gap-1.5">
            <Eye size={13} /> Tracked competitors
          </span>
        }
        action={
          <span className="text-[11px] text-subtle">Feed the weekly niche scan</span>
        }
        bodyClassName="p-0"
      >
        <ul className="divide-y divide-line">
          {competitors.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-4 py-2.5">
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium">{c.handle}</span>
                <span className="block text-[11px] text-subtle">
                  {c.niche} · {compact(c.subs)} subs · {c.platform}
                </span>
              </span>
              <Badge tone={c.outlier >= 5 ? 'green' : c.outlier >= 2.5 ? 'amber' : 'zinc'}>
                {c.outlier.toFixed(1)}x outlier
              </Badge>
            </li>
          ))}
        </ul>
        <p className="border-t border-line px-4 py-2.5 text-[11px] text-subtle">
          Outlier is measured against each channel's own baseline, not the niche
          average — a small channel at 2.7x is the signal that the niche is still
          open.
        </p>
      </Panel>
    </div>
  )
}
