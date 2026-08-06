import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { useStore } from '../lib/store'

import { member, money, relative, shortDate } from '../lib/format'
import { Avatar, Badge, Button, Empty, PageHeader, Panel, cx } from '../components/ui'
import type { Payout } from '../lib/types'

const STATUS_TONE: Record<Payout['status'], 'green' | 'amber' | 'blue'> = {
  paid: 'green',
  scheduled: 'blue',
  requested: 'amber',
}

export default function PayApp() {
  const { payouts, cards, members, contracts, setPayoutPaid } = useStore()

  const paid = payouts.filter((p) => p.status === 'paid')
  const requested = payouts.filter((p) => p.status === 'requested')
  const queued = payouts.filter((p) => p.status === 'scheduled')
  const requestedTotal = requested.reduce((a, p) => a + p.amountCents, 0)
  const queuedTotal = queued.reduce((a, p) => a + p.amountCents, 0)
  const paidTotal = paid.reduce((a, p) => a + p.amountCents, 0)

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="Pay"
        subtitle="Bulk payouts to staff and freelancers, with an approval layer. Every payout links to the cards it paid for."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Money label="Paid" value={paidTotal} hint={`${paid.length} payouts`} />
        <Money label="Pending approval" value={requestedTotal} hint={`${requested.length} to approve`} />
        <Money label="Queued" value={queuedTotal} hint={`${queued.length} scheduled`} />
        <Money
          label="Cost per published video"
          value={
            cards.filter((c) => c.payoutCents > 0).length
              ? Math.round(
                  cards.reduce((a, c) => a + c.payoutCents, 0) /
                    cards.filter((c) => c.payoutCents > 0).length,
                )
              : 0
          }
          hint="Average across all cards"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-2" title="Payouts" bodyClassName="p-0">
          {payouts.length === 0 ? (
            <Empty title="No payouts yet" />
          ) : (
            <ul className="divide-y divide-line">
              {[...payouts]
                .sort((a, b) => b.at.localeCompare(a.at))
                .map((p) => {
                  const linked = cards.filter((c) => p.cardIds.includes(c.id))
                  return (
                    <li key={p.id} className="flex items-center gap-3 px-4 py-3">
                      <Avatar id={p.memberId} size={30} />
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2 text-[13px] font-medium">
                          {member(p.memberId).name}
                          <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                        </p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-subtle">
                          <span>{p.method}</span>
                          <span>·</span>
                          <span>{shortDate(p.at)}</span>
                          {linked.map((c) => (
                            <Link
                              key={c.id}
                              to={`/boards/${c.boardId}?card=${c.id}`}
                              title={c.title}
                              className="font-medium text-brand hover:underline"
                            >
                              {c.ref}
                            </Link>
                          ))}
                          {p.invoiceNo && (
                            <span className="flex items-center gap-0.5">
                              <FileText size={10} />
                              {p.invoiceNo}
                            </span>
                          )}
                        </p>
                      </div>
                      <span className="shrink-0 text-[14px] font-semibold tabular-nums">
                        {money(p.amountCents)}
                      </span>
                      {p.status !== 'paid' && (
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => void setPayoutPaid(p.id)}
                        >
                          Pay now
                        </Button>
                      )}
                    </li>
                  )
                })}
            </ul>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Team" bodyClassName="p-0">
            <ul className="divide-y divide-line">
              {members.map((m) => (
                <li key={m.id} className="flex items-center gap-2.5 px-4 py-2.5">
                  <Avatar id={m.id} size={26} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{m.name}</span>
                    <span className="block text-[11px] text-subtle">
                      {m.role}
                      {m.payoutMethod && ` · ${m.payoutMethod}`}
                    </span>
                  </span>
                  {m.guest && <Badge>Guest</Badge>}
                </li>
              ))}
            </ul>
            <p className="border-t border-line px-4 py-2.5 text-[11px] text-subtle">
              Guests are free and unlimited on every plan.
            </p>
          </Panel>

          <Panel title="Contracts" bodyClassName="p-0">
            <ul className="divide-y divide-line">
              {contracts.map((c) => (
                <li key={c.id} className="px-4 py-2.5">
                  <p className="text-[13px] font-medium">{c.title}</p>
                  <p className="mt-0.5 flex items-center gap-2 text-[11px] text-subtle">
                    <span>{member(c.memberId).name}</span>
                    <span
                      className={cx(
                        'font-medium',
                        c.status === 'signed' ? 'text-emerald-600' : 'text-amber-600',
                      )}
                    >
                      {c.status}
                    </span>
                    <span>{relative(c.at)}</span>
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  )
}

function Money({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-[0_1px_2px_rgba(16,17,20,0.04)]">
      <p className="text-[12px] text-subtle">{label}</p>
      <p className="mt-1 text-[24px] leading-tight font-semibold tracking-tight tabular-nums">
        {money(value)}
      </p>
      <p className="mt-0.5 text-[11px] text-subtle">{hint}</p>
    </div>
  )
}
