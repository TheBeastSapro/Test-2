import { Link } from 'react-router-dom'
import { Download, FileText, HardDrive } from 'lucide-react'
import { useStore } from '../lib/store'
import { member, money, shortDate } from '../lib/format'
import { Avatar, Badge, Button, Empty, PageHeader, Panel } from '../components/ui'

/**
 * Invoices is its own top-level app in forgeboard, not a tab inside Pay.
 * Verified in-app: "Generated automatically when payouts are paid, or created
 * manually. Download, or save a copy to Drive."
 *
 * Nothing is authored here — an invoice is a *derived* record. It exists
 * because a payout was paid, and a payout exists because a card was delivered.
 * That chain is the whole point: the invoice can name the work it paid for.
 */
export default function InvoicesApp() {
  const { payouts, cards } = useStore()

  const invoiced = payouts
    .filter((p) => p.invoiceNo)
    .sort((a, b) => b.at.localeCompare(a.at))

  const total = invoiced.reduce((a, p) => a + p.amountCents, 0)

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader
        title="Invoices"
        subtitle="Generated automatically when payouts are paid. Download, or save a copy to Drive."
        action={
          <Button size="sm" variant="primary">
            New invoice
          </Button>
        }
      />

      <Panel bodyClassName="p-0">
        {invoiced.length === 0 ? (
          <Empty
            title="No invoices yet"
            hint="Invoices are generated automatically when payouts are paid."
          />
        ) : (
          <>
            <ul className="divide-y divide-line">
              {invoiced.map((p) => {
                const linked = cards.filter((c) => p.cardIds.includes(c.id))
                return (
                  <li key={p.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-zinc-100 text-subtle">
                      <FileText size={16} strokeWidth={1.8} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-[13px] font-medium">
                        {p.invoiceNo}
                        <Badge tone="green">paid</Badge>
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-subtle">
                        <Avatar id={p.memberId} size={16} />
                        <span>{member(p.memberId).name}</span>
                        <span>·</span>
                        <span>{shortDate(p.at)}</span>
                        <span>·</span>
                        <span>{p.method}</span>
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
                      </p>
                    </div>
                    <span className="shrink-0 text-[14px] font-semibold tabular-nums">
                      {money(p.amountCents)}
                    </span>
                    <span className="flex shrink-0 gap-1">
                      <Button size="sm" title="Download">
                        <Download size={13} />
                      </Button>
                      <Button size="sm" title="Save a copy to Drive">
                        <HardDrive size={13} />
                      </Button>
                    </span>
                  </li>
                )
              })}
            </ul>
            <p className="flex items-center justify-between border-t border-line px-4 py-2.5 text-[12px]">
              <span className="text-subtle">{invoiced.length} invoices</span>
              <span className="font-semibold tabular-nums">{money(total)}</span>
            </p>
          </>
        )}
      </Panel>
    </div>
  )
}
