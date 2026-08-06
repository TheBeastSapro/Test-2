import { Link } from 'react-router-dom'
import { AtSign, Bot, CheckCheck, ShieldCheck, Wallet } from 'lucide-react'
import { useStore } from '../lib/store'
import { relative } from '../lib/format'
import { Badge, Button, Empty, PageHeader, Panel, cx } from '../components/ui'
import type { InboxItem } from '../lib/types'

const ICON: Record<InboxItem['kind'], typeof AtSign> = {
  mention: AtSign,
  approval: ShieldCheck,
  payout: Wallet,
  automation: Bot,
  review: CheckCheck,
}

const TONE: Record<InboxItem['kind'], string> = {
  mention: 'bg-blue-50 text-blue-600',
  approval: 'bg-violet-50 text-violet-600',
  payout: 'bg-emerald-50 text-emerald-600',
  automation: 'bg-amber-50 text-amber-600',
  review: 'bg-zinc-100 text-zinc-600',
}

export default function InboxApp() {
  const { inbox, markInboxRead, markAllInboxRead, cards } = useStore()
  const unread = inbox.filter((i) => !i.read).length

  const linkFor = (ref: string | null) => {
    const card = cards.find((c) => c.ref === ref)
    return card ? `/boards/${card.boardId}?card=${card.id}` : null
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <PageHeader
        title="Inbox"
        subtitle="Mentions, approvals, payouts and automation runs across every app"
        action={
          <Button size="sm" onClick={markAllInboxRead} disabled={unread === 0}>
            Mark all read
          </Button>
        }
      />
      <Panel bodyClassName="p-0">
        {inbox.length === 0 ? (
          <Empty title="Nothing here" hint="You're all caught up." />
        ) : (
          <ul className="divide-y divide-line">
            {inbox.map((item) => {
              const Icon = ICON[item.kind]
              const to = linkFor(item.cardRef)
              const body = (
                <>
                  <span
                    className={cx(
                      'grid h-8 w-8 shrink-0 place-items-center rounded-lg',
                      TONE[item.kind],
                    )}
                  >
                    <Icon size={15} strokeWidth={1.9} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span
                        className={cx(
                          'truncate text-[13px]',
                          item.read ? 'font-medium' : 'font-semibold',
                        )}
                      >
                        {item.title}
                      </span>
                      {!item.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] text-subtle">
                      {item.body}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {item.cardRef && <Badge>{item.cardRef}</Badge>}
                    <span className="w-12 text-right text-[11px] text-subtle">
                      {relative(item.at)}
                    </span>
                  </span>
                </>
              )
              const cls = cx(
                'flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-zinc-50',
                !item.read && 'bg-brand-soft/30',
              )
              return (
                <li key={item.id}>
                  {to ? (
                    <Link to={to} onClick={() => markInboxRead(item.id)} className={cls}>
                      {body}
                    </Link>
                  ) : (
                    <button onClick={() => markInboxRead(item.id)} className={cls}>
                      {body}
                    </button>
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
