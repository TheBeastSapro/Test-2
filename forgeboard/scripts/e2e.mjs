/**
 * Full-stack browser test: real server, real SQLite, real uploads, real
 * session cookies. Proves the UI is talking to the database rather than to
 * itself.
 */
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const dir = mkdtempSync(join(tmpdir(), 'fb-e2e-'))
const PORT = 8899
const srv = spawn(process.execPath, ['server/index.js'], {
  env: {
    ...process.env,
    PORT: String(PORT),
    FORGEBOARD_DB: join(dir, 'e2e.db'),
    FORGEBOARD_UPLOADS: join(dir, 'uploads'),
    FORGEBOARD_AGENT: 'mock', // deterministic; the CLI path is tested separately
  },
  stdio: ['ignore', 'pipe', 'pipe'],
})
srv.stderr.on('data', (d) => process.stderr.write(`[server] ${d}`))
await new Promise((r) => setTimeout(r, 900))

let pass = 0, fail = 0
const ok = (n, c, extra = '') => {
  if (c) { pass++; console.log(`  ✓ ${n}`) } else { fail++; console.log(`  ✗ ${n} ${extra}`) }
}

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errs = []
p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))
// A 401 from /api/auth/me before sign-in is the correct answer, not a fault.
const EXPECTED = /401 \(Unauthorized\)/
p.on('console', (m) => {
  if (m.type() === 'error' && !EXPECTED.test(m.text())) errs.push(m.text())
})

const base = `http://localhost:${PORT}`
const email = `sapro${Date.now()}@forgeboard.test`

console.log('\nsign up')
await p.goto(base, { waitUntil: 'networkidle' })
ok('auth gate blocks the app', await p.getByRole('heading', { name: 'Sign in' }).isVisible())

await p.getByRole('button', { name: 'Create one' }).click()
await p.getByLabel('Your name').fill('Sapro Test')
await p.getByLabel('Email').fill(email)
await p.getByLabel('Password').fill('a decent password')
await p.getByRole('button', { name: 'Create workspace' }).click()
await p.waitForSelector('nav[aria-label="Apps"]', { timeout: 15000 })
ok('signed in and app rendered', true)

console.log('\nboards (persisted server-side)')
await p.goto(base + '/#/boards', { waitUntil: 'networkidle' })
await p.waitForTimeout(600)
ok('starter board from the server', await p.getByText('Content Pipeline').first().isVisible())

await p.getByLabel('Add a card to Idea').click()
await p.getByLabel('New card title').fill('Svalbard: Where Dying Is Against the Law')
await p.getByRole('button', { name: 'Add card' }).click()
await p.waitForTimeout(1200)
ok('card created', await p.getByText('Svalbard: Where Dying').first().isVisible())

console.log('\nreload proves it is in the database, not memory')
await p.reload({ waitUntil: 'networkidle' })
await p.waitForTimeout(900)
ok('card survives a full reload', await p.getByText('Svalbard: Where Dying').first().isVisible())

console.log('\ndrive: a real file upload')
await p.goto(base + '/#/drive', { waitUntil: 'networkidle' })
await p.waitForTimeout(400)
await p.setInputFiles('input[type="file"]', 'public/clips/tristan-v1.mp4')
await p.waitForTimeout(1500)
ok('uploaded file listed', await p.getByText('tristan-v1.mp4').first().isVisible())

const clip = readFileSync('public/clips/tristan-v1.mp4')
const served = await p.evaluate(async () => {
  const res = await fetch('/api/workspace')
  const d = await res.json()
  const f = d.files[0]
  const head = await fetch(`/api/files/${f.id}/content`, { headers: { Range: 'bytes=0-99' } })
  return { status: head.status, len: (await head.arrayBuffer()).byteLength, size: f.size_bytes }
})
ok('server stored the exact byte count', served.size === clip.length, `${served.size}`)
ok('range request served from disk', served.status === 206 && served.len === 100)

console.log('\nforge: propose -> approve -> board exists')
await p.goto(base + '/#/forge', { waitUntil: 'networkidle' })
await p.getByLabel('Message Forge').fill('make a board where I can manage this channel')
await p.getByLabel('Send').click()
await p.getByRole('button', { name: 'Approve' }).waitFor({ timeout: 20000 })
ok('agent proposed a write', true)
await p.getByRole('button', { name: 'Approve' }).click()
await p.waitForTimeout(1200)
ok('proposal marked applied', await p.getByText('Applied to the workspace').isVisible())

await p.goto(base + '/#/boards', { waitUntil: 'networkidle' })
await p.waitForTimeout(800)
ok('agent-created board is really there',
  await p.getByRole('button', { name: 'Travel Documentary Channel' }).isVisible())

console.log('\nisolation: a second account sees nothing of the first')
const p2 = await b.newPage({ viewport: { width: 1280, height: 800 } })
await p2.goto(base, { waitUntil: 'networkidle' })
await p2.getByRole('button', { name: 'Create one' }).click()
await p2.getByLabel('Your name').fill('Other Person')
await p2.getByLabel('Email').fill(`other${Date.now()}@forgeboard.test`)
await p2.getByLabel('Password').fill('another good password')
await p2.getByRole('button', { name: 'Create workspace' }).click()
await p2.waitForSelector('nav[aria-label="Apps"]', { timeout: 15000 })
await p2.goto(base + '/#/boards', { waitUntil: 'networkidle' })
await p2.waitForTimeout(700)
ok('second account cannot see the first account\'s card',
  (await p2.getByText('Svalbard: Where Dying').count()) === 0)
await p2.goto(base + '/#/drive', { waitUntil: 'networkidle' })
await p2.waitForTimeout(500)
ok('second account cannot see the first account\'s file',
  (await p2.getByText('tristan-v1.mp4').count()) === 0)
await p2.close()

console.log('\nsign out')
await p.goto(base + '/#/', { waitUntil: 'networkidle' })
await p.getByRole('button', { name: /sign out/i }).click()
await p.waitForTimeout(900)
ok('back at the sign-in screen', await p.getByRole('heading', { name: 'Sign in' }).isVisible())

await b.close()
srv.kill('SIGKILL')
rmSync(dir, { recursive: true, force: true })

console.log(errs.length ? `\nCONSOLE ERRORS:\n${errs.join('\n')}` : '\nNO CONSOLE ERRORS')
console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail || errs.length ? 1 : 0)
