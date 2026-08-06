import { Link } from 'react-router-dom'
import { ArrowUpRight, Camera, Check, Music2, PlaySquare, Wallet } from 'lucide-react'
import { useStore } from '../lib/store'
import { channel90d, videoStats, viewsSeries } from '../lib/seed'
import { compact, dueThisWeek, isOverdue, money, relative, shortDate } from '../lib/format'
import { AvatarStack, Badge, Panel, PageHeader, Tag, cx } from '../components/ui'

export default function Dashboard() {
  const { cards, boards, payouts } = useStore()

  // One source for every tile: views, revenue and RPM cannot disagree.
  const rpm = channel90d.revenueCents / 100 / (channel90d.views / 1000)

  const due = cards
    .filter((c) => dueThisWeek(c.due))
    .sort((a, b) => (a.due ?? '').localeCompare(b.due ?? ''))

  const published = boards[0]?.stages.at(-1)?.id
  const active = cards.filter((c) => c.stageId !== published).length
  const done = cards.filter((c) => c.stageId === published).length
  const overdue = cards.filter(
    (c) => c.stageId !== published && isOverdue(c.due),
  ).length

  const owed = payouts
    .filter((p) => p.status !== 'paid')
    .reduce((a, p) => a + p.amountCents, 0)

  return (
    <div className="mx-auto max-w-6xl p-6">
      <PageHeader
        title="Dashboard"
        subtitle="Last 90 days across every connected channel"
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Views" value={compact(channel90d.views)} delta="+728%" />
        <Stat label="Watch time (hours)" value={compact(channel90d.watchHours)} delta="+559%" />
        <Stat label="Estimated revenue" value={money(channel90d.revenueCents)} delta="+223%" />
        <Stat label="Average RPM" value={`$${rpm.toFixed(2)}`} hint="per 1,000 views" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          title="Views"
          action={<span className="text-[11px] text-subtle">May 8 – Aug 6, 2026</span>}
        >
          <ViewsChart />
        </Panel>

        <Panel title="Monthly progress" action={<Badge tone="blue">This month</Badge>}>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Counter label="Active" value={active} tone="text-brand" />
            <Counter label="Done" value={done} tone="text-emerald-600" />
            <Counter
              label="Overdue"
              value={overdue}
              tone={overdue ? 'text-red-600' : 'text-zinc-400'}
            />
          </div>
          <div className="mt-4 border-t border-line pt-3">
            <p className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
              Owed to freelancers
            </p>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="text-[22px] font-semibold">{money(owed)}</span>
              <Link
                to="/pay"
                className="text-[12px] font-medium text-brand hover:underline"
              >
                Pay →
              </Link>
            </p>
          </div>
        </Panel>

        <Panel
          className="lg:col-span-2"
          title="Due this week"
          action={<Badge>{due.length} items</Badge>}
          bodyClassName="p-0"
        >
          {due.length === 0 ? (
            <p className="px-4 py-8 text-center text-[13px] text-subtle">Nothing due.</p>
          ) : (
            <ul className="divide-y divide-line">
              {due.map((c) => (
                <li key={c.id}>
                  <Link
                    to={`/boards/${c.boardId}?card=${c.id}`}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-zinc-50"
                  >
                    <Tag>{c.tag}</Tag>
                    <span className="min-w-0 flex-1 truncate text-[13px]">{c.title}</span>
                    <AvatarStack ids={c.assigneeIds} size={20} />
                    <span
                      className={cx(
                        'w-16 shrink-0 text-right text-[11px] font-medium',
                        isOverdue(c.due) ? 'text-red-600' : 'text-subtle',
                      )}
                    >
                      {c.due ? shortDate(c.due) : '—'}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Connected apps">
          <ul className="space-y-2.5">
            {[
              { Icon: PlaySquare, name: 'YouTube', detail: 'Impossible Travel' },
              { Icon: Camera, name: 'Instagram', detail: '@impossibletravel' },
              { Icon: Music2, name: 'TikTok', detail: '@impossibletravel' },
              { Icon: Wallet, name: 'Wise', detail: 'Payouts enabled' },
            ].map(({ Icon, name, detail }) => (
              <li key={name} className="flex items-center gap-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-lg border border-line text-subtle">
                  <Icon size={15} strokeWidth={1.8} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-medium">{name}</span>
                  <span className="block truncate text-[11px] text-subtle">{detail}</span>
                </span>
                <Check size={14} className="shrink-0 text-emerald-600" />
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="lg:col-span-3" title="Top content" bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold tracking-wide text-subtle uppercase">
                  <th className="px-4 py-2.5 font-semibold">Video</th>
                  <th className="px-4 py-2.5 font-semibold">Platform</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Views</th>
                  <th className="px-4 py-2.5 text-right font-semibold">RPM</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Revenue</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Published</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {videoStats.map((v) => (
                  <tr key={v.id} className="hover:bg-zinc-50">
                    <td className="max-w-xs truncate px-4 py-2.5 font-medium">{v.title}</td>
                    <td className="px-4 py-2.5 text-subtle">{v.platform}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{compact(v.views)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">${v.rpm.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                      {money(v.revenueCents)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-subtle">
                      {relative(v.publishedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  delta,
  hint,
}: {
  label: string
  value: string
  delta?: string
  hint?: string
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-[0_1px_2px_rgba(16,17,20,0.04)]">
      <p className="text-[12px] text-subtle">{label}</p>
      <p className="mt-1 text-[26px] leading-tight font-semibold tracking-tight">{value}</p>
      {delta && (
        <p className="mt-0.5 flex items-center gap-0.5 text-[11px] font-medium text-emerald-600">
          <ArrowUpRight size={12} />
          {delta} vs previous 90 days
        </p>
      )}
      {hint && <p className="mt-0.5 text-[11px] text-subtle">{hint}</p>}
    </div>
  )
}

function Counter({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-zinc-50 py-3">
      <p className={cx('text-[24px] leading-none font-semibold tabular-nums', tone)}>{value}</p>
      <p className="mt-1 text-[10px] font-semibold tracking-wide text-subtle uppercase">
        {label}
      </p>
    </div>
  )
}

/** Hand-rolled area chart — no charting dependency for one sparkline. */
function ViewsChart() {
  const w = 720
  const h = 180
  const pad = 4
  const max = Math.max(...viewsSeries.map((d) => d.views))

  const pts = viewsSeries.map((d, i) => {
    const x = pad + (i / (viewsSeries.length - 1)) * (w - pad * 2)
    const y = h - pad - (d.views / max) * (h - pad * 2)
    return [x, y] as const
  })

  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${w - pad},${h} L${pad},${h} Z`

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="h-44 w-full"
        role="img"
        aria-label={`Daily views over 90 days, peaking at ${compact(max)}`}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-brand)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--color-brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={pad}
            x2={w - pad}
            y1={h * f}
            y2={h * f}
            stroke="var(--color-line)"
            strokeWidth="1"
          />
        ))}
        <path d={area} fill="url(#viewsFill)" />
        <path
          d={line}
          fill="none"
          stroke="var(--color-brand)"
          strokeWidth="1.75"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
        />
      </svg>
      <figcaption className="mt-2 flex justify-between text-[11px] text-subtle">
        <span>{shortDate(viewsSeries[0].date)}</span>
        <span>Peak {compact(max)}/day</span>
        <span>{shortDate(viewsSeries.at(-1)!.date)}</span>
      </figcaption>
    </figure>
  )
}
