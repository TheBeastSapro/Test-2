import { useState, type ReactNode } from 'react'
import { CloudLightning } from 'lucide-react'
import { useStore } from '../lib/store'
import { Button, cx } from './ui'

/**
 * Sign in / create account.
 *
 * Nothing renders behind this until there is a session, because there is no
 * longer a "local" workspace to fall back to — the data lives on the server
 * and belongs to an account.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading, signIn, signUp } = useStore()
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="grid h-full place-items-center bg-canvas">
        <p className="text-[13px] text-subtle">Loading your workspace…</p>
      </div>
    )
  }

  if (user) return <>{children}</>

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      if (mode === 'up') await signUp(name.trim(), email.trim(), password)
      else await signIn(email.trim(), password)
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'That did not work')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid h-full place-items-center bg-canvas p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">
            <CloudLightning size={18} strokeWidth={2.2} />
          </span>
          <span className="text-[19px] font-semibold tracking-tight">ForgeBoard</span>
        </div>

        <form
          onSubmit={submit}
          className="rounded-xl border border-line bg-white p-5 shadow-[0_1px_2px_rgba(16,17,20,0.04)]"
        >
          <h1 className="text-[15px] font-semibold">
            {mode === 'in' ? 'Sign in' : 'Create your workspace'}
          </h1>
          <p className="mt-0.5 mb-4 text-[12px] text-subtle">
            {mode === 'in'
              ? 'Your boards, files and reviews live on the server.'
              : 'You get a workspace with a starter board. Guests you invite are free.'}
          </p>

          {mode === 'up' && (
            <Field label="Your name">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoComplete="name"
                className={inputCls}
              />
            </Field>
          )}

          <Field label="Email">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className={inputCls}
            />
          </Field>

          <Field label="Password">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === 'up' ? 8 : undefined}
              autoComplete={mode === 'up' ? 'new-password' : 'current-password'}
              className={inputCls}
            />
            {mode === 'up' && (
              <span className="mt-1 block text-[11px] text-subtle">At least 8 characters.</span>
            )}
          </Field>

          {err && (
            <p
              role="alert"
              className="mb-3 rounded-lg border border-red-200 bg-red-50 px-2.5 py-2 text-[12px] text-red-700"
            >
              {err}
            </p>
          )}

          <Button type="submit" variant="primary" className="w-full" disabled={busy}>
            {busy ? 'One moment…' : mode === 'in' ? 'Sign in' : 'Create workspace'}
          </Button>

          <p className="mt-3 text-center text-[12px] text-subtle">
            {mode === 'in' ? "Don't have an account?" : 'Already have one?'}{' '}
            <button
              type="button"
              onClick={() => {
                setMode(mode === 'in' ? 'up' : 'in')
                setErr(null)
              }}
              className="font-medium text-brand hover:underline"
            >
              {mode === 'in' ? 'Create one' : 'Sign in'}
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}

const inputCls = cx(
  'w-full rounded-lg border border-line px-2.5 py-2 text-[13px] outline-none',
  'focus:border-brand',
)

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
        {label}
      </span>
      {children}
    </label>
  )
}
