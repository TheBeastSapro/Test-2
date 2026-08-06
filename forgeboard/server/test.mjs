/**
 * End-to-end API test. Drives the real server over real HTTP against a real
 * SQLite file — no mocks, no in-memory shortcuts. Run: npm run test:server
 */
import { rmSync, mkdtempSync, readFileSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const dir = mkdtempSync(join(tmpdir(), 'fb-test-'))
process.env.FORGEBOARD_DB = join(dir, 'test.db')
process.env.FORGEBOARD_UPLOADS = join(dir, 'uploads')
process.env.FORGEBOARD_NO_LISTEN = '1'
// Keep the agent deterministic here; the CLI path is exercised separately.
process.env.FORGEBOARD_AGENT = 'mock'

const { server } = await import('./index.js')

let pass = 0
let fail = 0
const ok = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ✓ ${name}`) }
  else { fail++; console.log(`  ✗ ${name} ${extra}`) }
}

await new Promise((r) => server.listen(0, r))
const base = `http://localhost:${server.address().port}`
let cookie = ''

async function call(path, { method = 'GET', body, raw, headers = {} } = {}) {
  const res = await fetch(base + path, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(cookie ? { Cookie: cookie } : {}),
      ...headers,
    },
    body: raw ?? (body ? JSON.stringify(body) : undefined),
  })
  const set = res.headers.get('set-cookie')
  if (set) cookie = set.split(';')[0]
  const text = await res.text()
  let data
  try { data = JSON.parse(text) } catch { data = text }
  return { status: res.status, data, res }
}

console.log('\nauth')
{
  const r = await call('/api/auth/me')
  ok('anonymous is rejected', r.status === 401)

  const short = await call('/api/auth/register', {
    method: 'POST', body: { email: 'a@b.co', password: 'short', name: 'A B' },
  })
  ok('short password refused', short.status === 400)

  const reg = await call('/api/auth/register', {
    method: 'POST', body: { email: 'sapro@forgeboard.test', password: 'correct horse battery', name: 'Sapro Test' },
  })
  ok('register returns 201', reg.status === 201, JSON.stringify(reg.data))
  ok('no password hash leaks', !JSON.stringify(reg.data).includes('scrypt'))

  const dupe = await call('/api/auth/register', {
    method: 'POST', body: { email: 'SAPRO@forgeboard.test', password: 'correct horse battery', name: 'Dup' },
  })
  ok('duplicate email refused (case-insensitive)', dupe.status === 409)

  const me = await call('/api/auth/me')
  ok('session works', me.status === 200 && me.data.user.name === 'Sapro Test')

  const bad = await fetch(base + '/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'sapro@forgeboard.test', password: 'wrong' }),
  })
  ok('wrong password refused', bad.status === 401)
}

console.log('\nworkspace')
let boardId, stageId
{
  const r = await call('/api/workspace')
  ok('snapshot returns', r.status === 200)
  ok('starter board seeded', r.data.boards.length === 1, JSON.stringify(r.data.boards))
  ok('board has 5 stages', r.data.stages.length === 5)
  ok('credits start at 1000', r.data.workspace.credits === 1000)
  boardId = r.data.boards[0].id
  stageId = r.data.stages[0].id
}

console.log('\ncards')
let cardId
{
  const c = await call('/api/cards', {
    method: 'POST', body: { boardId, stageId, title: 'Tristan da Cunha', payoutCents: 24000 },
  })
  ok('card created', c.status === 201)
  cardId = c.data.cardId

  const snap = await call('/api/workspace')
  const card = snap.data.cards.find((x) => x.id === cardId)
  ok('card persisted with KB ref', card?.ref === 'KB-1', card?.ref)

  const moveTo = snap.data.stages[3].id
  await call(`/api/cards/${cardId}`, { method: 'PATCH', body: { stageId: moveTo } })
  const snap2 = await call('/api/workspace')
  ok('card moved stage', snap2.data.cards.find((x) => x.id === cardId).stage_id === moveTo)

  await call(`/api/cards/${cardId}/comments`, { method: 'POST', body: { body: 'Rough cut is long.' } })
  const snap3 = await call('/api/workspace')
  ok('comment persisted', snap3.data.cardComments.length === 1)

  const empty = await call(`/api/cards/${cardId}/comments`, { method: 'POST', body: { body: '  ' } })
  ok('empty comment refused', empty.status === 400)
}

console.log('\nfiles + review (real upload, real range requests)')
let fileId, reviewId
{
  const clip = readFileSync('public/clips/tristan-v1.mp4')
  const up = await call(`/api/files?name=tristan-v1.mp4&cardId=${cardId}`, {
    method: 'POST', raw: clip, headers: { 'Content-Type': 'video/mp4' },
  })
  ok('upload accepted', up.status === 201, JSON.stringify(up.data))
  ok('size recorded correctly', up.data.size === clip.length, `${up.data.size} vs ${clip.length}`)
  ok('kind detected as video', up.data.kind === 'video')
  fileId = up.data.id

  const onDisk = statSync(join(dir, 'uploads', `${fileId}.mp4`))
  ok('bytes actually written to disk', onDisk.size === clip.length)

  const full = await fetch(`${base}/api/files/${fileId}/content`, { headers: { Cookie: cookie } })
  const got = Buffer.from(await full.arrayBuffer())
  ok('download returns identical bytes', got.equals(clip))
  ok('advertises range support', full.headers.get('accept-ranges') === 'bytes')

  const part = await fetch(`${base}/api/files/${fileId}/content`, {
    headers: { Cookie: cookie, Range: 'bytes=100-199' },
  })
  const partBuf = Buffer.from(await part.arrayBuffer())
  ok('range request returns 206', part.status === 206)
  ok('range returns exactly 100 bytes', partBuf.length === 100)
  ok('range bytes match the source', partBuf.equals(clip.subarray(100, 200)))
  ok('content-range header correct',
    part.headers.get('content-range') === `bytes 100-199/${clip.length}`)

  const bad = await fetch(`${base}/api/files/${fileId}/content`, {
    headers: { Cookie: cookie, Range: `bytes=${clip.length + 10}-` },
  })
  ok('unsatisfiable range returns 416', bad.status === 416)

  const rv = await call('/api/review', {
    method: 'POST', body: { fileId, title: 'Tristan da Cunha — rough cut', durationSec: 24, fps: 25, cardId },
  })
  ok('review created at v1', rv.status === 201 && rv.data.version === 1)
  reviewId = rv.data.id

  const clip2 = readFileSync('public/clips/tristan-v2.mp4')
  const up2 = await call('/api/files?name=tristan-v2.mp4', {
    method: 'POST', raw: clip2, headers: { 'Content-Type': 'video/mp4' },
  })
  const rv2 = await call('/api/review', {
    method: 'POST', body: { fileId: up2.data.id, title: 'Tristan da Cunha — rough cut', durationSec: 22, fps: 25 },
  })
  ok('same title becomes v2', rv2.data.version === 2)

  await call(`/api/review/${reviewId}/comments`, {
    method: 'POST',
    body: { timecodeSec: 17.2, body: 'VO drifts here.', region: { tool: 'rect', x: 0.1, y: 0.1, w: 0.3, h: 0.2 } },
  })
  const snap = await call('/api/workspace')
  const rc = snap.data.reviewComments[0]
  ok('review note persisted at its timecode', Math.abs(rc.timecode_sec - 17.2) < 0.001)
  ok('drawn region persisted', JSON.parse(rc.region_json).tool === 'rect')

  await call(`/api/review/comments/${rc.id}`, { method: 'PATCH', body: { resolved: true } })
  const snap2 = await call('/api/workspace')
  ok('note resolves', snap2.data.reviewComments[0].resolved === 1)

  await call(`/api/review/${reviewId}`, { method: 'PATCH', body: { status: 'changes requested' } })
  const snap3 = await call('/api/workspace')
  ok('review status updates',
    snap3.data.reviewAssets.find((a) => a.id === reviewId).status === 'changes requested')

  const badStatus = await call(`/api/review/${reviewId}`, { method: 'PATCH', body: { status: 'nonsense' } })
  ok('unknown status refused', badStatus.status === 400)
}

console.log('\nforge (propose -> approve -> written)')
{
  const ask = await call('/api/forge/ask', {
    method: 'POST', body: { message: 'make a board where I can manage this channel' },
  })
  ok('agent replies', ask.status === 200 && !!ask.data.reply)
  ok('agent proposes a write', ask.data.proposal?.kind === 'create_board')
  ok('proposal starts pending', ask.data.proposal.status === 'pending')

  const before = (await call('/api/workspace')).data.boards.length
  const approve = await call('/api/forge/approve', { method: 'POST', body: { messageId: ask.data.messageId } })
  ok('approve succeeds', approve.status === 200)

  const after = await call('/api/workspace')
  ok('board actually created', after.data.boards.length === before + 1)
  ok('first card created with it', after.data.cards.some((c) => c.title === 'First video'))

  const twice = await call('/api/forge/approve', { method: 'POST', body: { messageId: ask.data.messageId } })
  ok('double-approve refused', twice.status === 409)

  const q = await call('/api/forge/ask', {
    method: 'POST', body: { message: 'what is my rpm?', conversationId: ask.data.conversationId },
  })
  ok('question yields no proposal', q.data.proposal === null)
  ok('thread continues in one conversation', q.data.conversationId === ask.data.conversationId)
}

console.log('\nisolation (the important one)')
{
  const mine = await call('/api/workspace')
  const myCard = mine.data.cards[0].id
  const myFile = fileId
  const savedCookie = cookie

  cookie = ''
  await call('/api/auth/register', {
    method: 'POST', body: { email: 'intruder@forgeboard.test', password: 'another password here', name: 'Intruder' },
  })

  const theirs = await call('/api/workspace')
  ok('new user gets their own empty workspace', theirs.data.cards.length === 0)

  const peekCard = await call(`/api/cards/${myCard}`, { method: 'PATCH', body: { title: 'hijacked' } })
  ok("cannot touch another workspace's card", peekCard.status === 404)

  const peekFile = await fetch(`${base}/api/files/${myFile}/content`, { headers: { Cookie: cookie } })
  ok("cannot download another workspace's file", peekFile.status === 404)

  cookie = savedCookie
  const still = await call('/api/workspace')
  ok('original card untouched', still.data.cards.find((c) => c.id === myCard).title !== 'hijacked')
}

console.log('\nlogout')
{
  await call('/api/auth/logout', { method: 'POST' })
  const after = await call('/api/auth/me')
  ok('session revoked server-side', after.status === 401)
}

server.close()
rmSync(dir, { recursive: true, force: true })

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
