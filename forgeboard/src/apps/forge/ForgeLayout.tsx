import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  BookOpen,
  Brain as BrainIcon,
  CloudLightning,
  Plus,
  SlidersHorizontal,
  Workflow,
} from 'lucide-react'
import { useStore } from '../../lib/store'
import { relative } from '../../lib/format'
import { cx } from '../../components/ui'

const SECTIONS = [
  { to: '/forge/library', label: 'Library', Icon: BookOpen },
  { to: '/forge/brain', label: 'Brain', Icon: BrainIcon },
  { to: '/forge/automations', label: 'Automations', Icon: Workflow },
  { to: '/forge/playground', label: 'Playground', Icon: SlidersHorizontal },
]

export default function ForgeLayout() {
  const { conversations, credits } = useStore()
  const navigate = useNavigate()

  return (
    <div className="flex h-full">
      <nav
        aria-label="Forge"
        className="flex w-60 shrink-0 flex-col border-r border-line bg-white"
      >
        <div className="flex items-center gap-2 px-4 py-3.5">
          <CloudLightning size={17} className="text-brand" strokeWidth={2.2} />
          <span className="text-[15px] font-semibold">Forge</span>
        </div>

        <div className="px-3">
          <button
            onClick={() => navigate('/forge')}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand-soft py-2 text-[13px] font-medium text-brand transition-colors hover:bg-brand/10"
          >
            <Plus size={14} />
            New chat
          </button>
        </div>

        <ul className="mt-3 space-y-0.5 px-2">
          {SECTIONS.map(({ to, label, Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  cx(
                    'flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px]',
                    isActive
                      ? 'bg-zinc-100 font-medium text-ink'
                      : 'text-subtle hover:bg-zinc-50 hover:text-ink',
                  )
                }
              >
                <Icon size={15} strokeWidth={1.8} />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>

        <h2 className="mt-5 px-4 pb-1 text-[10px] font-semibold tracking-wide text-subtle uppercase">
          Conversations
        </h2>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
          {conversations.map((c) => (
            <li key={c.id}>
              <NavLink
                to={`/forge/c/${c.id}`}
                className={({ isActive }) =>
                  cx(
                    'block rounded-lg px-2 py-1.5',
                    isActive ? 'bg-zinc-100' : 'hover:bg-zinc-50',
                  )
                }
              >
                <span className="block truncate text-[12px] font-medium text-ink">
                  {c.title}
                </span>
                <span className="block text-[10px] text-subtle">{relative(c.at)}</span>
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="border-t border-line px-4 py-2.5 text-center text-[11px] font-medium text-subtle">
          {credits.toLocaleString()} credits
        </div>
      </nav>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  )
}
