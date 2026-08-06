import { members } from './seed'
import type { Member } from './types'

export const money = (cents: number) =>
  (cents / 100).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: cents % 100 === 0 ? 0 : 2,
  })

export const compact = (n: number) =>
  n >= 1_000_000
    ? `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`
    : n >= 1_000
      ? `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
      : String(n)

export const bytes = (kb: number) =>
  kb >= 1_000_000
    ? `${(kb / 1_000_000).toFixed(1)} GB`
    : kb >= 1_000
      ? `${(kb / 1_000).toFixed(1)} MB`
      : `${kb} KB`

const DAY = 86_400_000

export function relative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const abs = Math.abs(diff)
  const future = diff < 0
  if (abs < 60_000) return 'just now'
  if (abs < 3_600_000) {
    const m = Math.round(abs / 60_000)
    return future ? `in ${m}m` : `${m}m ago`
  }
  if (abs < DAY) {
    const h = Math.round(abs / 3_600_000)
    return future ? `in ${h}h` : `${h}h ago`
  }
  const d = Math.round(abs / DAY)
  if (d < 30) return future ? `in ${d}d` : `${d}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

export const dayKey = (iso: string | Date) =>
  (typeof iso === 'string' ? new Date(iso) : iso).toISOString().slice(0, 10)

const byId = new Map<string, Member>(members.map((m) => [m.id, m]))
export const member = (id: string): Member =>
  byId.get(id) ?? { id, name: 'Unknown', role: 'Guest', guest: true, initials: '??', hue: 0 }

/** True if the date lands inside the next 7 days (drives "Due this week"). */
export const dueThisWeek = (iso: string | null) => {
  if (!iso) return false
  const delta = new Date(iso).getTime() - Date.now()
  return delta >= -DAY && delta <= 7 * DAY
}

export const isOverdue = (iso: string | null) =>
  !!iso && new Date(iso).getTime() < Date.now()
