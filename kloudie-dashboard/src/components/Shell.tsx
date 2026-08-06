import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Calendar,
  CloudLightning,
  CreditCard,
  Folder,
  Home,
  Inbox,
  Kanban,
  MessageSquare,
  Clapperboard,
  Search,
  ShieldCheck,
  Sparkles,
  UserPlus,
} from 'lucide-react'
import { useStore } from '../lib/store'
import { workspaces } from '../lib/seed'
import { compact } from '../lib/format'
import { Avatar, cx } from './ui'
import type { AppId } from '../lib/types'

const APPS: { id: AppId; to: string; label: string; Icon: typeof Home }[] = [
  { id: 'inbox', to: '/inbox', label: 'Inbox', Icon: Inbox },
  { id: 'dashboard', to: '/', label: 'Dashboard', Icon: Home },
  { id: 'boards', to: '/boards', label: 'Boards', Icon: Kanban },
  { id: 'calendar', to: '/calendar', label: 'Calendar', Icon: Calendar },
  { id: 'chat', to: '/chat', label: 'Chat', Icon: MessageSquare },
  { id: 'files', to: '/files', label: 'Files', Icon: Folder },
  { id: 'review', to: '/review', label: 'Review', Icon: Clapperboard },
  { id: 'economy', to: '/economy', label: 'Economy', Icon: CreditCard },
  { id: 'portal', to: '/portal', label: 'Client portal', Icon: ShieldCheck },
  { id: 'kloudie', to: '/kloudie', label: 'kloudie', Icon: CloudLightning },
]

export function Shell({ children }: { children: React.ReactNode }) {
  const { inbox, credits, workspaceId, setWorkspace } = useStore()
  const [searchOpen, setSearchOpen] = useState(false)
  const unread = inbox.filter((i) => !i.read).length

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full flex-col">
      <TopBar
        workspaceId={workspaceId}
        onWorkspace={setWorkspace}
        credits={credits}
        onSearch={() => setSearchOpen(true)}
      />
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Apps" className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-white py-3">
          {APPS.map(({ id, to, label, Icon }) => (
            <NavLink
              key={id}
              to={to}
              end={to === '/'}
              title={label}
              aria-label={label}
              className={({ isActive }) =>
                cx(
                  'relative grid h-9 w-9 place-items-center rounded-lg transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
                  isActive ? 'bg-zinc-100 text-ink' : 'text-subtle hover:bg-zinc-50 hover:text-ink',
                )
              }
            >
              <Icon size={18} strokeWidth={1.8} />
              {id === 'inbox' && unread > 0 && (
                <span className="absolute top-1 right-1 grid h-4 min-w-4 place-items-center rounded-full bg-brand px-1 text-[9px] font-bold text-white">
                  {unread}
                </span>
              )}
            </NavLink>
          ))}
          <div className="mt-auto flex flex-col items-center gap-1 text-subtle">
            <button
              title="Invite — guests are free and unlimited"
              className="grid h-9 w-9 place-items-center rounded-lg hover:bg-zinc-50 hover:text-ink"
            >
              <UserPlus size={18} strokeWidth={1.8} />
            </button>
            <span className="text-[9px]">Invite</span>
          </div>
        </nav>
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      {searchOpen && <CommandPalette onClose={() => setSearchOpen(false)} />}
    </div>
  )
}

function TopBar({
  workspaceId,
  onWorkspace,
  credits,
  onSearch,
}: {
  workspaceId: string
  onWorkspace: (id: string) => void
  credits: number
  onSearch: () => void
}) {
  const navigate = useNavigate()
  const [ask, setAsk] = useState('')

  const submitAsk = (e: React.FormEvent) => {
    e.preventDefault()
    const q = ask.trim()
    if (!q) return
    setAsk('')
    navigate(`/kloudie?q=${encodeURIComponent(q)}`)
  }

  return (
    <header className="flex h-13 shrink-0 items-center gap-3 border-b border-line bg-white px-3 py-2.5">
      <div className="flex w-56 shrink-0 items-center gap-2">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-brand text-white">
          <CloudLightning size={14} strokeWidth={2.2} />
        </span>
        <label className="sr-only" htmlFor="ws">
          Workspace
        </label>
        <select
          id="ws"
          value={workspaceId}
          onChange={(e) => onWorkspace(e.target.value)}
          className="min-w-0 cursor-pointer truncate rounded-md border border-transparent bg-transparent py-1 pr-6 pl-1 text-[13px] font-semibold hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-brand"
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </div>

      <button
        onClick={onSearch}
        className="flex h-8 w-52 items-center gap-2 rounded-lg border border-line px-2.5 text-[12px] text-subtle transition-colors hover:bg-zinc-50"
      >
        <Search size={14} />
        <span>Search</span>
        <kbd className="ml-auto rounded border border-line bg-zinc-50 px-1 font-sans text-[10px]">
          ⌘K
        </kbd>
      </button>

      <form onSubmit={submitAsk} className="mx-auto hidden max-w-md flex-1 md:block">
        <div className="flex h-8 items-center gap-2 rounded-full border border-line px-3 transition-colors focus-within:border-brand">
          <Sparkles size={14} className="shrink-0 text-brand" />
          <input
            value={ask}
            onChange={(e) => setAsk(e.target.value)}
            placeholder="Ask kloudie"
            aria-label="Ask kloudie"
            className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-subtle"
          />
        </div>
      </form>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <span
          title="AI credits — generation is metered, structure is free"
          className="hidden rounded-full bg-brand-soft px-2.5 py-1 text-[11px] font-semibold text-brand sm:block"
        >
          {compact(credits)} credits
        </span>
        <Avatar id="m-1" size={26} />
      </div>
    </header>
  )
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const { cards, boards, brain, creations } = useStore()
  const [q, setQ] = useState('')
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => inputRef.current?.focus(), [])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return []
    const hit = (s: string) => s.toLowerCase().includes(needle)
    return [
      ...cards
        .filter((c) => hit(c.title) || hit(c.ref))
        .map((c) => ({ id: c.id, group: 'Cards', label: `${c.ref} · ${c.title}`, to: `/boards/${c.boardId}?card=${c.id}` })),
      ...boards.filter((b) => hit(b.name)).map((b) => ({ id: b.id, group: 'Boards', label: b.name, to: `/boards/${b.id}` })),
      ...brain
        .filter((d) => hit(d.title) || hit(d.body))
        .map((d) => ({ id: d.id, group: 'Brain', label: d.title, to: `/kloudie/brain?doc=${d.id}` })),
      ...creations.filter((c) => hit(c.title)).map((c) => ({ id: c.id, group: 'Library', label: c.title, to: '/kloudie/library' })),
    ].slice(0, 12)
  }, [q, cards, boards, brain, creations])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/20 pt-[12vh]"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search workspace"
        onClick={(e) => e.stopPropagation()}
        className="kb-in w-full max-w-lg overflow-hidden rounded-xl border border-line bg-white shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-line px-3.5">
          <Search size={16} className="text-subtle" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            placeholder="Search cards, boards, Brain, Library…"
            className="h-12 flex-1 bg-transparent text-[14px] outline-none placeholder:text-subtle"
          />
        </div>
        <ul className="max-h-80 overflow-y-auto p-1.5">
          {results.length === 0 ? (
            <li className="px-3 py-6 text-center text-[12px] text-subtle">
              {q ? 'No matches.' : 'Search across every app in the workspace.'}
            </li>
          ) : (
            results.map((r) => (
              <li key={`${r.group}-${r.id}`}>
                <button
                  onClick={() => {
                    navigate(r.to)
                    onClose()
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-zinc-50"
                >
                  <span className="w-16 shrink-0 text-[10px] font-semibold tracking-wide text-subtle uppercase">
                    {r.group}
                  </span>
                  <span className="truncate">{r.label}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  )
}
