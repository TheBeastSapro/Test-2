import { useEffect, useMemo, useRef, useState } from 'react'
import { Hash } from 'lucide-react'
import { useStore } from '../lib/store'

import { member, relative } from '../lib/format'
import { Avatar, Button, cx } from '../components/ui'

export default function ChatApp() {
  const { channels, chatMessages, sendChatMessage } = useStore()
  const [channelId, setChannelId] = useState<string>('')
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const channel = channels.find((c) => c.id === channelId) ?? channels[0]
  const thread = useMemo(
    () =>
      chatMessages
        .filter((m) => m.channelId === (channel?.id ?? ''))
        .sort((a, b) => a.at.localeCompare(b.at)),
    [chatMessages, channel?.id],
  )

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [thread.length, channelId])

  const send = (e: React.FormEvent) => {
    e.preventDefault()
    const body = draft.trim()
    if (!body) return
    if (channel) void sendChatMessage(channel.id, body)
    setDraft('')
  }

  return (
    <div className="flex h-full">
      <nav
        aria-label="Conversations"
        className="w-56 shrink-0 overflow-y-auto border-r border-line bg-white p-2"
      >
        {(['channel', 'dm'] as const).map((kind) => (
          <div key={kind} className="mb-3">
            <h2 className="px-2 py-1 text-[10px] font-semibold tracking-wide text-subtle uppercase">
              {kind === 'channel' ? 'Channels' : 'Direct messages'}
            </h2>
            <ul>
              {channels
                .filter((c) => c.kind === kind)
                .map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => setChannelId(c.id)}
                      className={cx(
                        'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px]',
                        c.id === channelId
                          ? 'bg-zinc-100 font-medium text-ink'
                          : 'text-subtle hover:bg-zinc-50',
                      )}
                    >
                      <Hash size={13} className="shrink-0" />
                      <span className="truncate">{c.name}</span>
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </nav>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-13 shrink-0 items-center gap-2 border-b border-line bg-white px-4">
          {channel.kind === 'channel' && <Hash size={15} className="text-subtle" />}
          <h1 className="text-[14px] font-semibold">{channel?.name ?? 'general'}</h1>
          <span className="text-[12px] text-subtle">· workspace channel</span>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {thread.length === 0 && (
            <p className="pt-10 text-center text-[13px] text-subtle">
              No messages yet. Say something.
            </p>
          )}
          {thread.map((m) => (
            <article key={m.id} className="flex gap-2.5">
              <Avatar id={m.authorId} size={28} />
              <div className="min-w-0">
                <p className="text-[12px]">
                  <span className="font-semibold">{member(m.authorId).name}</span>
                  <span className="ml-1.5 text-subtle">{relative(m.at)}</span>
                </p>
                <p className="text-[13px] whitespace-pre-wrap">{m.body}</p>
              </div>
            </article>
          ))}
          <div ref={endRef} />
        </div>

        <form onSubmit={send} className="flex gap-2 border-t border-line bg-white p-3">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Message #${channel?.name ?? 'general'}`}
            aria-label="Message"
            className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-[13px] outline-none focus:border-brand"
          />
          <Button type="submit" variant="primary" disabled={!draft.trim()}>
            Send
          </Button>
        </form>
      </section>
    </div>
  )
}
