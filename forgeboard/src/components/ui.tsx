import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { member } from '../lib/format'

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function Panel({
  title,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section
      className={cx(
        'rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(16,17,20,0.04)]',
        className,
      )}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          {action}
        </header>
      )}
      <div className={cx('p-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export function Avatar({ id, size = 24 }: { id: string; size?: number }) {
  const m = member(id)
  return (
    <span
      title={`${m.name}${m.guest ? ' · guest' : ''}`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.4,
        background: `hsl(${m.hue} 62% 92%)`,
        color: `hsl(${m.hue} 55% 32%)`,
      }}
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold ring-2 ring-white"
    >
      {m.initials}
    </span>
  )
}

export function AvatarStack({ ids, size = 24 }: { ids: string[]; size?: number }) {
  if (!ids.length) return null
  return (
    <span className="flex -space-x-1.5">
      {ids.slice(0, 3).map((id) => (
        <Avatar key={id} id={id} size={size} />
      ))}
    </span>
  )
}

const TAG_TONE: Record<string, string> = {
  YOUTUBE: 'bg-red-50 text-red-700',
  PODCAST: 'bg-violet-50 text-violet-700',
  MARKETING: 'bg-amber-50 text-amber-700',
  DESIGN: 'bg-blue-50 text-blue-700',
  SHORTS: 'bg-pink-50 text-pink-700',
  NEWSLETTER: 'bg-emerald-50 text-emerald-700',
}

export function Tag({ children }: { children: string }) {
  return (
    <span
      className={cx(
        'rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider',
        TAG_TONE[children] ?? 'bg-zinc-100 text-zinc-600',
      )}
    >
      {children}
    </span>
  )
}

export function Badge({
  children,
  tone = 'zinc',
}: {
  children: ReactNode
  tone?: 'zinc' | 'green' | 'amber' | 'blue' | 'red'
}) {
  const tones = {
    zinc: 'bg-zinc-100 text-zinc-600',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    blue: 'bg-brand-soft text-brand',
    red: 'bg-red-50 text-red-700',
  }
  return (
    <span className={cx('rounded-full px-2 py-0.5 text-[11px] font-medium', tones[tone])}>
      {children}
    </span>
  )
}

export function Button({
  children,
  variant = 'default',
  size = 'md',
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
}) {
  const variants = {
    default: 'border border-line bg-white hover:bg-zinc-50 text-ink',
    primary: 'bg-brand text-white hover:bg-brand/90 border border-transparent',
    ghost: 'text-subtle hover:bg-zinc-100 hover:text-ink border border-transparent',
    danger: 'border border-red-200 bg-white text-red-600 hover:bg-red-50',
  }
  return (
    <button
      {...rest}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-7 px-2.5 text-[12px]' : 'h-9 px-3 text-[13px]',
        variants[variant],
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Progress({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.round((value / max) * 100)
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={`${value} of ${max} complete`}
      className="h-1 w-full overflow-hidden rounded-full bg-zinc-100"
    >
      <div
        className={cx('h-full rounded-full', pct === 100 ? 'bg-emerald-500' : 'bg-brand')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-6 py-14 text-center">
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {hint && <p className="max-w-sm text-[12px] text-subtle">{hint}</p>}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-[13px] text-subtle">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

/**
 * A modal that behaves like one: Escape closes it, the backdrop closes it,
 * focus lands inside on open, and the body cannot scroll behind it.
 */
export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.querySelector<HTMLElement>('input, textarea, button')?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/25 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="kb-in w-full max-w-md overflow-hidden rounded-xl border border-line bg-white shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-[14px] font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-7 w-7 place-items-center rounded-lg text-subtle hover:bg-zinc-100 hover:text-ink"
          >
            <X size={16} />
          </button>
        </header>
        <div className="p-4">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-line bg-zinc-50 px-4 py-3">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}

/** The text input a field uses. One definition so they cannot drift apart. */
export const fieldCls = cx(
  'w-full rounded-lg border border-line px-2.5 py-2 text-[13px] outline-none',
  'focus:border-brand',
)

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-subtle">{hint}</span>}
    </label>
  )
}
