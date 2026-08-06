import { useState } from 'react'
import { CheckCircle2, MessageCircleWarning, ShieldCheck } from 'lucide-react'
import { useStore } from '../lib/store'
import { relative, shortDate } from '../lib/format'
import {
  Badge,
  Button,
  Empty,
  Field,
  Modal,
  PageHeader,
  Panel,
  Progress,
  Tag,
  cx,
  fieldCls,
} from '../components/ui'

/**
 * The guest-facing view of a board.
 *
 * ForgeBoard's pricing thesis lives here: clients and freelancers review and
 * approve work without consuming a paid seat, which is what pulls the whole
 * supply chain into the workspace. So the portal is deliberately narrow — a
 * guest sees the deliverables shared with them and nothing else: no other
 * clients, no internal boards, no financials.
 */
export default function ClientPortal() {
  const { boards, cards, addComment, addInboxItem } = useStore()
  const [boardId, setBoardId] = useState(boards[0]?.id ?? '')
  const [decided, setDecided] = useState<Record<string, 'approved' | 'changes'>>({})
  const [asking, setAsking] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const board = boards.find((b) => b.id === boardId) ?? boards[0]
  if (!board) return <Empty title="No boards to share" />

  // Guests only see work that has actually reached a reviewable stage.
  const reviewable = board.stages.slice(-2).map((s) => s.id)
  const shared = cards.filter(
    (c) => c.boardId === board.id && reviewable.includes(c.stageId),
  )

  const decide = (cardId: string, verdict: 'approved' | 'changes', note: string) => {
    const card = cards.find((c) => c.id === cardId)
    if (!card || !note) return

    addComment(cardId, note)
    addInboxItem({
      kind: verdict === 'approved' ? 'review' : 'approval',
      title:
        verdict === 'approved'
          ? `Client approved ${card.ref}`
          : `Client requested changes on ${card.ref}`,
      body: note,
      cardRef: card.ref,
    })
    setDecided((d) => ({ ...d, [cardId]: verdict }))
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader
        title="Client portal"
        subtitle="What a guest sees. Approvals land in your Inbox and on the card — and cost no seat."
        action={
          <div className="flex flex-wrap gap-1.5">
            {boards.map((b) => (
              <Button
                key={b.id}
                size="sm"
                variant={b.id === board.id ? 'primary' : 'default'}
                onClick={() => setBoardId(b.id)}
              >
                {b.name}
              </Button>
            ))}
          </div>
        }
      />

      <div className="mb-4 flex items-center gap-2 rounded-xl border border-line bg-white px-4 py-3">
        <ShieldCheck size={16} className="shrink-0 text-emerald-600" />
        <p className="text-[12px] text-subtle">
          Guests see only the deliverables shared with them — never your other
          clients, internal boards, or financials.
        </p>
        <Badge tone="green">Free guest</Badge>
      </div>

      <Panel title={`${board.name} — shared deliverables`} bodyClassName="p-0">
        {shared.length === 0 ? (
          <Empty
            title="Nothing shared yet"
            hint="Cards become visible to guests once they reach a review stage."
          />
        ) : (
          <ul className="divide-y divide-line">
            {shared.map((c) => {
              const done = c.checklist.filter((i) => i.done).length
              const verdict = decided[c.id]
              return (
                <li key={c.id} className="px-4 py-3.5">
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <Tag>{c.tag}</Tag>
                        <span className="text-[11px] text-subtle">{c.ref}</span>
                        {c.due && (
                          <span className="text-[11px] text-subtle">
                            · due {shortDate(c.due)}
                          </span>
                        )}
                      </div>
                      <p className="text-[13px] font-medium">{c.title}</p>
                      {c.checklist.length > 0 && (
                        <div className="mt-2 max-w-xs">
                          <Progress value={done} max={c.checklist.length} />
                        </div>
                      )}
                      {c.comments.length > 0 && (
                        <p className="mt-2 text-[12px] text-subtle">
                          Latest: “{c.comments.at(-1)!.body}” ·{' '}
                          {relative(c.comments.at(-1)!.at)}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1.5">
                      {verdict ? (
                        <span
                          className={cx(
                            'flex items-center gap-1 text-[12px] font-medium',
                            verdict === 'approved' ? 'text-emerald-600' : 'text-amber-600',
                          )}
                        >
                          {verdict === 'approved' ? (
                            <CheckCircle2 size={13} />
                          ) : (
                            <MessageCircleWarning size={13} />
                          )}
                          {verdict === 'approved' ? 'Approved' : 'Changes requested'}
                        </span>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => decide(c.id, 'approved', 'Approved by the client.')}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => {
                              setAsking(c.id)
                              setReason('')
                            }}
                          >
                            Request changes
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>

      {asking && (
        <Modal
          title="Request changes"
          onClose={() => setAsking(null)}
          footer={
            <>
              <Button size="sm" onClick={() => setAsking(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                disabled={!reason.trim()}
                onClick={() => {
                  decide(asking, 'changes', reason.trim())
                  setAsking(null)
                }}
              >
                Send to the team
              </Button>
            </>
          }
        >
          <Field
            label="What needs to change?"
            hint="Lands on the card and in the team's Inbox."
          >
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              placeholder="The cold open runs long — cut it to under 12 seconds."
              className={fieldCls + ' resize-y'}
            />
          </Field>
        </Modal>
      )}
    </div>
  )
}
