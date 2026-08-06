import { createServer } from 'node:http'
import { createReadStream, createWriteStream, mkdirSync, statSync, unlinkSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { db, id, nowIso, nextCardRef } from './db.js'
import {
  clearCookieHeader,
  cookieHeader,
  createSession,
  destroySession,
  login,
  parseCookies,
  registerUser,
  userFromSession,
} from './auth.js'
import { agentProvider, askForge } from './agent.js'
import { generate } from './generate.js'

const PORT = Number(process.env.PORT ?? 8787)
const UPLOADS = resolve(process.env.FORGEBOARD_UPLOADS ?? 'data/uploads')
const STATIC = resolve(process.env.FORGEBOARD_STATIC ?? 'dist')
mkdirSync(UPLOADS, { recursive: true })

const MAX_UPLOAD = 512 * 1024 * 1024

// ---------------------------------------------------------------- helpers

const json = (res, status, body) => {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
    'Cache-Control': 'no-store',
  })
  res.end(payload)
}

async function readJson(req, limit = 2 * 1024 * 1024) {
  const chunks = []
  let size = 0
  for await (const c of req) {
    size += c.length
    if (size > limit) throw Object.assign(new Error('Body too large'), { status: 413 })
    chunks.push(c)
  }
  if (!chunks.length) return {}
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    throw Object.assign(new Error('Invalid JSON'), { status: 400 })
  }
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
}

const kindOf = (mime) =>
  mime.startsWith('video/') ? 'video'
  : mime.startsWith('audio/') ? 'audio'
  : mime.startsWith('image/') ? 'image'
  : /pdf|text|json|markdown/.test(mime) ? 'doc'
  : 'other'

/** Membership is the authorisation boundary: no row, no access. */
function requireMember(user, workspaceId) {
  const m = db
    .prepare(`SELECT * FROM memberships WHERE workspace_id = ? AND user_id = ?`)
    .get(workspaceId, user.id)
  if (!m) throw Object.assign(new Error('Not found'), { status: 404 })
  return m
}

function defaultWorkspace(user) {
  const row = db
    .prepare(
      `SELECT w.* FROM workspaces w
       JOIN memberships m ON m.workspace_id = w.id
       WHERE m.user_id = ? ORDER BY w.created_at LIMIT 1`,
    )
    .get(user.id)
  return row ?? null
}

// ------------------------------------------------------------- bootstrap

/** Everything the front-end needs for a workspace, in one round trip. */
function snapshot(workspaceId) {
  const q = (sql, ...a) => db.prepare(sql).all(workspaceId, ...a)

  const cards = q(`SELECT * FROM cards WHERE workspace_id = ? ORDER BY position, created_at`)
  const cardIds = new Set(cards.map((c) => c.id))
  const keep = (rows, key = 'card_id') => rows.filter((r) => cardIds.has(r[key]))

  return {
    workspace: db.prepare(`SELECT * FROM workspaces WHERE id = ?`).get(workspaceId),
    members: db
      .prepare(
        `SELECT u.id, u.name, u.initials, u.hue, m.role, m.is_guest
         FROM memberships m JOIN users u ON u.id = m.user_id
         WHERE m.workspace_id = ?`,
      )
      .all(workspaceId),
    boards: q(`SELECT * FROM boards WHERE workspace_id = ? ORDER BY created_at`),
    stages: db
      .prepare(
        `SELECT s.* FROM stages s JOIN boards b ON b.id = s.board_id
         WHERE b.workspace_id = ? ORDER BY s.position`,
      )
      .all(workspaceId),
    cards,
    assignees: keep(
      db
        .prepare(
          `SELECT ca.* FROM card_assignees ca JOIN cards c ON c.id = ca.card_id
           WHERE c.workspace_id = ?`,
        )
        .all(workspaceId),
    ),
    checklist: keep(
      db
        .prepare(
          `SELECT ci.* FROM checklist_items ci JOIN cards c ON c.id = ci.card_id
           WHERE c.workspace_id = ? ORDER BY ci.position`,
        )
        .all(workspaceId),
    ),
    cardComments: keep(
      db
        .prepare(
          `SELECT cc.* FROM card_comments cc JOIN cards c ON c.id = cc.card_id
           WHERE c.workspace_id = ? ORDER BY cc.created_at`,
        )
        .all(workspaceId),
    ),
    files: q(`SELECT * FROM files WHERE workspace_id = ? AND trashed = 0 ORDER BY created_at DESC`),
    reviewAssets: q(`SELECT * FROM review_assets WHERE workspace_id = ? ORDER BY version`),
    reviewComments: db
      .prepare(
        `SELECT rc.* FROM review_comments rc JOIN review_assets ra ON ra.id = rc.asset_id
         WHERE ra.workspace_id = ? ORDER BY rc.timecode_sec`,
      )
      .all(workspaceId),
    payouts: q(`SELECT * FROM payouts WHERE workspace_id = ? ORDER BY created_at DESC`),
    payoutCards: db
      .prepare(
        `SELECT pc.* FROM payout_cards pc JOIN payouts p ON p.id = pc.payout_id
         WHERE p.workspace_id = ?`,
      )
      .all(workspaceId),
    brain: q(`SELECT * FROM brain_docs WHERE workspace_id = ? ORDER BY created_at DESC`),
    creations: q(`SELECT * FROM creations WHERE workspace_id = ? ORDER BY created_at DESC`),
    conversations: q(`SELECT * FROM conversations WHERE workspace_id = ? ORDER BY created_at DESC`),
    messages: db
      .prepare(
        `SELECT m.* FROM messages m JOIN conversations c ON c.id = m.conversation_id
         WHERE c.workspace_id = ? ORDER BY m.created_at`,
      )
      .all(workspaceId),
    inbox: q(`SELECT * FROM inbox WHERE workspace_id = ? ORDER BY created_at DESC`),
    automations: q(`SELECT * FROM automations WHERE workspace_id = ?`),
    channels: q(`SELECT * FROM channels WHERE workspace_id = ?`),
    chatMessages: db
      .prepare(
        `SELECT cm.* FROM chat_messages cm JOIN channels ch ON ch.id = cm.channel_id
         WHERE ch.workspace_id = ? ORDER BY cm.created_at`,
      )
      .all(workspaceId),
    competitors: q(`SELECT * FROM competitors WHERE workspace_id = ?`),
    contracts: q(`SELECT * FROM contracts WHERE workspace_id = ? ORDER BY created_at DESC`),
    agent: { provider: agentProvider() },
  }
}

/** A new account gets a workspace with a starter board so nothing is empty. */
function seedWorkspace(user, name = `${user.name.split(' ')[0]}'s workspace`) {
  const wid = id('ws')
  db.prepare(
    `INSERT INTO workspaces (id, name, owner_id, credits, created_at) VALUES (?, ?, ?, ?, ?)`,
  ).run(wid, name, user.id, 1000, nowIso())
  db.prepare(
    `INSERT INTO memberships (workspace_id, user_id, role, is_guest) VALUES (?, ?, 'Owner', 0)`,
  ).run(wid, user.id)

  const bid = id('b')
  db.prepare(
    `INSERT INTO boards (id, workspace_id, name, template, created_at) VALUES (?, ?, ?, ?, ?)`,
  ).run(bid, wid, 'Content Pipeline', 'YouTube Automation', nowIso())
  const stages = ['Idea', 'Script', 'Voiceover', 'Editing', 'Published']
  const tones = ['bg-zinc-400', 'bg-amber-500', 'bg-violet-500', 'bg-blue-500', 'bg-emerald-500']
  stages.forEach((s, i) =>
    db
      .prepare(`INSERT INTO stages (id, board_id, name, tone, position) VALUES (?, ?, ?, ?, ?)`)
      .run(id('st'), bid, s, tones[i], i),
  )
  db.prepare(`INSERT INTO channels (id, workspace_id, name, kind) VALUES (?, ?, 'general', 'channel')`)
    .run(id('ch'), wid)
  return wid
}

// ----------------------------------------------------------------- routes

async function api(req, res, url, user) {
  const p = url.pathname
  const seg = p.split('/').filter(Boolean) // ['api', ...]
  const method = req.method

  // ---- auth (no session required)
  if (p === '/api/auth/register' && method === 'POST') {
    const { email, password, name } = await readJson(req)
    if (!email || !password || !name)
      throw Object.assign(new Error('Email, password and name are required'), { status: 400 })
    if (String(password).length < 8)
      throw Object.assign(new Error('Password must be at least 8 characters'), { status: 400 })
    const u = await registerUser({ email: String(email).trim(), password, name: String(name).trim() })
    seedWorkspace(u)
    const { sid, expires } = createSession(u.id)
    res.setHeader('Set-Cookie', cookieHeader(sid, expires))
    return json(res, 201, { user: u })
  }

  if (p === '/api/auth/login' && method === 'POST') {
    const { email, password } = await readJson(req)
    const u = await login({ email: String(email ?? '').trim(), password: String(password ?? '') })
    if (!defaultWorkspace(u)) seedWorkspace(u)
    const { sid, expires } = createSession(u.id)
    res.setHeader('Set-Cookie', cookieHeader(sid, expires))
    return json(res, 200, { user: u })
  }

  if (p === '/api/auth/logout' && method === 'POST') {
    const sid = parseCookies(req.headers.cookie).fb_session
    if (sid) destroySession(sid)
    res.setHeader('Set-Cookie', clearCookieHeader())
    return json(res, 200, { ok: true })
  }

  if (p === '/api/auth/me') {
    return json(res, user ? 200 : 401, user ? { user } : { error: 'Not signed in' })
  }

  // ---- everything below needs a session
  if (!user) throw Object.assign(new Error('Not signed in'), { status: 401 })

  if (p === '/api/workspace' && method === 'GET') {
    const ws = defaultWorkspace(user)
    if (!ws) throw Object.assign(new Error('No workspace'), { status: 404 })
    return json(res, 200, snapshot(ws.id))
  }

  const ws = defaultWorkspace(user)
  if (!ws) throw Object.assign(new Error('No workspace'), { status: 404 })
  requireMember(user, ws.id)

  // ---- boards & cards
  if (p === '/api/boards' && method === 'POST') {
    const { name, template = 'Blank', stages = ['To do', 'Doing', 'Done'] } = await readJson(req)
    if (!name) throw Object.assign(new Error('Board name is required'), { status: 400 })
    const bid = id('b')
    db.prepare(
      `INSERT INTO boards (id, workspace_id, name, template, created_at) VALUES (?, ?, ?, ?, ?)`,
    ).run(bid, ws.id, name, template, nowIso())
    const tones = ['bg-zinc-400', 'bg-amber-500', 'bg-violet-500', 'bg-blue-500', 'bg-emerald-500']
    stages.forEach((s, i) =>
      db
        .prepare(`INSERT INTO stages (id, board_id, name, tone, position) VALUES (?, ?, ?, ?, ?)`)
        .run(id('st'), bid, String(s), tones[i % tones.length], i),
    )
    return json(res, 201, { boardId: bid })
  }

  if (p === '/api/cards' && method === 'POST') {
    const { boardId, stageId, title, tag = 'YOUTUBE', due = null, payoutCents = 0 } =
      await readJson(req)
    const board = db
      .prepare(`SELECT * FROM boards WHERE id = ? AND workspace_id = ?`)
      .get(boardId, ws.id)
    if (!board) throw Object.assign(new Error('Board not found'), { status: 404 })
    const stage =
      db.prepare(`SELECT * FROM stages WHERE id = ? AND board_id = ?`).get(stageId, boardId) ??
      db.prepare(`SELECT * FROM stages WHERE board_id = ? ORDER BY position LIMIT 1`).get(boardId)
    if (!stage) throw Object.assign(new Error('Board has no stages'), { status: 400 })
    if (!title) throw Object.assign(new Error('Card title is required'), { status: 400 })

    const cid = id('c')
    db.prepare(
      `INSERT INTO cards (id, workspace_id, board_id, stage_id, ref, title, tag, due, payout_cents, position, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(cid, ws.id, boardId, stage.id, nextCardRef(ws.id), title, tag, due, payoutCents, 0, nowIso())
    return json(res, 201, { cardId: cid })
  }

  if (seg[1] === 'cards' && seg[2] && seg.length === 3 && method === 'PATCH') {
    const card = db
      .prepare(`SELECT * FROM cards WHERE id = ? AND workspace_id = ?`)
      .get(seg[2], ws.id)
    if (!card) throw Object.assign(new Error('Card not found'), { status: 404 })
    const body = await readJson(req)
    const allowed = { stage_id: 'stageId', title: 'title', tag: 'tag', due: 'due', payout_cents: 'payoutCents' }
    for (const [col, key] of Object.entries(allowed)) {
      if (key in body) db.prepare(`UPDATE cards SET ${col} = ? WHERE id = ?`).run(body[key], card.id)
    }
    return json(res, 200, { ok: true })
  }

  if (seg[1] === 'cards' && seg[3] === 'comments' && method === 'POST') {
    const card = db
      .prepare(`SELECT * FROM cards WHERE id = ? AND workspace_id = ?`)
      .get(seg[2], ws.id)
    if (!card) throw Object.assign(new Error('Card not found'), { status: 404 })
    const { body } = await readJson(req)
    if (!body?.trim()) throw Object.assign(new Error('Comment cannot be empty'), { status: 400 })
    const cid = id('cm')
    db.prepare(
      `INSERT INTO card_comments (id, card_id, author_id, body, created_at) VALUES (?, ?, ?, ?, ?)`,
    ).run(cid, card.id, user.id, body.trim(), nowIso())
    return json(res, 201, { id: cid })
  }

  // ---- files: raw upload, ranged download
  if (p === '/api/files' && method === 'POST') {
    const name = String(url.searchParams.get('name') ?? 'upload.bin')
    const mime = req.headers['content-type'] ?? 'application/octet-stream'
    const cardId = url.searchParams.get('cardId') || null

    const fid = id('f')
    const safeExt = extname(name).slice(0, 10).replace(/[^.\w]/g, '')
    const storagePath = join(UPLOADS, `${fid}${safeExt}`)

    let size = 0
    const sink = createWriteStream(storagePath)
    req.on('data', (c) => {
      size += c.length
      if (size > MAX_UPLOAD) req.destroy(new Error('Upload too large'))
    })
    try {
      await pipeline(req, sink)
    } catch (e) {
      try { unlinkSync(storagePath) } catch { /* nothing to clean */ }
      throw Object.assign(new Error('Upload failed: ' + e.message), { status: 413 })
    }

    db.prepare(
      `INSERT INTO files (id, workspace_id, card_id, name, kind, mime, size_bytes, storage_path, uploaded_by, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(fid, ws.id, cardId, name, kindOf(mime), mime, size, storagePath, user.id, nowIso())

    return json(res, 201, { id: fid, name, size, kind: kindOf(mime) })
  }

  if (seg[1] === 'files' && seg[2] && seg[3] === 'content' && method === 'GET') {
    const f = db
      .prepare(`SELECT * FROM files WHERE id = ? AND workspace_id = ?`)
      .get(seg[2], ws.id)
    if (!f) throw Object.assign(new Error('File not found'), { status: 404 })

    const total = statSync(f.storage_path).size
    const range = req.headers.range

    // Range support is not optional here: without it the review player cannot
    // seek, and Safari will not play the video at all.
    if (range) {
      const m = /bytes=(\d*)-(\d*)/.exec(range)
      let start = m?.[1] ? Number(m[1]) : 0
      let end = m?.[2] ? Number(m[2]) : total - 1
      if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= total) {
        res.writeHead(416, { 'Content-Range': `bytes */${total}` })
        return res.end()
      }
      end = Math.min(end, total - 1)
      res.writeHead(206, {
        'Content-Type': f.mime,
        'Content-Length': end - start + 1,
        'Content-Range': `bytes ${start}-${end}/${total}`,
        'Accept-Ranges': 'bytes',
      })
      return pipeline(createReadStream(f.storage_path, { start, end }), res).catch(() => {})
    }

    res.writeHead(200, {
      'Content-Type': f.mime,
      'Content-Length': total,
      'Accept-Ranges': 'bytes',
    })
    return pipeline(createReadStream(f.storage_path), res).catch(() => {})
  }

  // ---- review
  if (p === '/api/review' && method === 'POST') {
    const { fileId, title, durationSec = 0, fps = 25, cardId = null } = await readJson(req)
    const f = db.prepare(`SELECT * FROM files WHERE id = ? AND workspace_id = ?`).get(fileId, ws.id)
    if (!f) throw Object.assign(new Error('File not found'), { status: 404 })

    const name = title || f.name
    // A "new version" is another asset sharing the title, so history survives.
    const prev = db
      .prepare(
        `SELECT MAX(version) AS v FROM review_assets WHERE workspace_id = ? AND title = ?`,
      )
      .get(ws.id, name)
    const rid = id('rv')
    db.prepare(
      `INSERT INTO review_assets (id, workspace_id, file_id, card_id, title, version, duration_sec, fps, status, uploaded_by, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in review', ?, ?)`,
    ).run(rid, ws.id, f.id, cardId ?? f.card_id, name, (prev?.v ?? 0) + 1, durationSec, fps, user.id, nowIso())
    return json(res, 201, { id: rid, version: (prev?.v ?? 0) + 1 })
  }

  if (seg[1] === 'review' && seg[3] === 'comments' && method === 'POST') {
    const asset = db
      .prepare(`SELECT * FROM review_assets WHERE id = ? AND workspace_id = ?`)
      .get(seg[2], ws.id)
    if (!asset) throw Object.assign(new Error('Review not found'), { status: 404 })
    const { timecodeSec = 0, body, region = null } = await readJson(req)
    if (!body?.trim()) throw Object.assign(new Error('Note cannot be empty'), { status: 400 })
    const rcid = id('rc')
    db.prepare(
      `INSERT INTO review_comments (id, asset_id, author_id, timecode_sec, body, region_json, resolved, created_at)
       VALUES (?, ?, ?, ?, ?, ?, 0, ?)`,
    ).run(rcid, asset.id, user.id, Number(timecodeSec) || 0, body.trim(),
      region ? JSON.stringify(region) : null, nowIso())
    return json(res, 201, { id: rcid })
  }

  if (seg[1] === 'review' && seg[2] === 'comments' && seg[3] && method === 'PATCH') {
    const { resolved } = await readJson(req)
    db.prepare(
      `UPDATE review_comments SET resolved = ?
       WHERE id = ? AND asset_id IN (SELECT id FROM review_assets WHERE workspace_id = ?)`,
    ).run(resolved ? 1 : 0, seg[3], ws.id)
    return json(res, 200, { ok: true })
  }

  if (seg[1] === 'review' && seg[2] && seg.length === 3 && method === 'PATCH') {
    const { status } = await readJson(req)
    if (!['in review', 'approved', 'changes requested'].includes(status))
      throw Object.assign(new Error('Unknown review status'), { status: 400 })
    db.prepare(`UPDATE review_assets SET status = ? WHERE id = ? AND workspace_id = ?`)
      .run(status, seg[2], ws.id)
    return json(res, 200, { ok: true })
  }

  // ---- brain
  if (p === '/api/brain' && method === 'POST') {
    const { title, kind = 'note', source = '', body = '' } = await readJson(req)
    if (!title?.trim()) throw Object.assign(new Error('Title is required'), { status: 400 })
    const bid = id('br')
    db.prepare(
      `INSERT INTO brain_docs (id, workspace_id, title, kind, source, body, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).run(bid, ws.id, title.trim(), kind, source, body, nowIso())
    return json(res, 201, { id: bid })
  }

  // ---- payouts
  if (seg[1] === 'payouts' && seg[3] === 'pay' && method === 'POST') {
    const p0 = db
      .prepare(`SELECT * FROM payouts WHERE id = ? AND workspace_id = ?`)
      .get(seg[2], ws.id)
    if (!p0) throw Object.assign(new Error('Payout not found'), { status: 404 })
    const n = db
      .prepare(`SELECT COUNT(*) AS c FROM payouts WHERE workspace_id = ? AND invoice_no IS NOT NULL`)
      .get(ws.id).c
    const invoice = p0.invoice_no ?? `INV-${String(1 + n).padStart(4, '0')}`
    db.prepare(`UPDATE payouts SET status = 'paid', invoice_no = ? WHERE id = ?`)
      .run(invoice, p0.id)
    return json(res, 200, { invoiceNo: invoice })
  }

  // ---- inbox
  if (p === '/api/inbox/read-all' && method === 'POST') {
    db.prepare(`UPDATE inbox SET read = 1 WHERE workspace_id = ? AND user_id = ?`)
      .run(ws.id, user.id)
    return json(res, 200, { ok: true })
  }

  // ---- checklist
  if (p === '/api/checklist' && method === 'POST') {
    const { cardId, label } = await readJson(req)
    const card = db.prepare(`SELECT * FROM cards WHERE id = ? AND workspace_id = ?`).get(cardId, ws.id)
    if (!card) throw Object.assign(new Error('Card not found'), { status: 404 })
    if (!label?.trim()) throw Object.assign(new Error('Label is required'), { status: 400 })
    const n = db.prepare(`SELECT COUNT(*) AS c FROM checklist_items WHERE card_id = ?`).get(cardId).c
    const iid = id('ci')
    db.prepare(`INSERT INTO checklist_items (id, card_id, label, done, position) VALUES (?, ?, ?, 0, ?)`)
      .run(iid, cardId, label.trim(), n)
    return json(res, 201, { id: iid })
  }

  if (seg[1] === 'checklist' && seg[2] && method === 'PATCH') {
    const { done } = await readJson(req)
    db.prepare(
      `UPDATE checklist_items SET done = ?
       WHERE id = ? AND card_id IN (SELECT id FROM cards WHERE workspace_id = ?)`,
    ).run(done ? 1 : 0, seg[2], ws.id)
    return json(res, 200, { ok: true })
  }

  // ---- chat
  if (seg[1] === 'chat' && seg[2] && seg[3] === 'messages' && method === 'POST') {
    const ch = db.prepare(`SELECT * FROM channels WHERE id = ? AND workspace_id = ?`).get(seg[2], ws.id)
    if (!ch) throw Object.assign(new Error('Channel not found'), { status: 404 })
    const { body } = await readJson(req)
    if (!body?.trim()) throw Object.assign(new Error('Message cannot be empty'), { status: 400 })
    const mid = id('chm')
    db.prepare(
      `INSERT INTO chat_messages (id, channel_id, author_id, body, created_at) VALUES (?, ?, ?, ?, ?)`,
    ).run(mid, ch.id, user.id, body.trim(), nowIso())
    return json(res, 201, { id: mid })
  }

  // ---- inbox
  if (p === '/api/inbox' && method === 'POST') {
    const { kind = 'mention', title, body = '', cardRef = null } = await readJson(req)
    if (!title?.trim()) throw Object.assign(new Error('Title is required'), { status: 400 })
    const iid = id('i')
    db.prepare(
      `INSERT INTO inbox (id, workspace_id, user_id, kind, title, body, card_ref, read, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)`,
    ).run(iid, ws.id, user.id, kind, title.trim(), body, cardRef, nowIso())
    return json(res, 201, { id: iid })
  }

  if (seg[1] === 'inbox' && seg[2] && seg[2] !== 'read-all' && method === 'PATCH') {
    db.prepare(`UPDATE inbox SET read = 1 WHERE id = ? AND workspace_id = ? AND user_id = ?`)
      .run(seg[2], ws.id, user.id)
    return json(res, 200, { ok: true })
  }

  // ---- automations
  if (seg[1] === 'automations' && seg[2] && method === 'PATCH') {
    const { enabled } = await readJson(req)
    db.prepare(`UPDATE automations SET enabled = ? WHERE id = ? AND workspace_id = ?`)
      .run(enabled ? 1 : 0, seg[2], ws.id)
    return json(res, 200, { ok: true })
  }

  // ---- review comment delete
  if (seg[1] === 'review' && seg[2] === 'comments' && seg[3] && method === 'DELETE') {
    db.prepare(
      `DELETE FROM review_comments
       WHERE id = ? AND asset_id IN (SELECT id FROM review_assets WHERE workspace_id = ?)`,
    ).run(seg[3], ws.id)
    return json(res, 200, { ok: true })
  }

  // ---- generation
  if (p === '/api/generate' && method === 'POST') {
    const { module: mod, prompt, settings = {} } = await readJson(req)
    if (!prompt?.trim()) throw Object.assign(new Error('Give it something to work from'), { status: 400 })
    const out = await generate({ workspaceId: ws.id, userId: user.id, module: mod, prompt, settings })
    return json(res, 201, out)
  }

  // ---- Forge
  if (p === '/api/forge/ask' && method === 'POST') {
    const { message, conversationId = null, useBrain = true } = await readJson(req)
    if (!message?.trim()) throw Object.assign(new Error('Message cannot be empty'), { status: 400 })

    let convId = conversationId
    if (convId) {
      const owned = db
        .prepare(`SELECT 1 FROM conversations WHERE id = ? AND workspace_id = ?`)
        .get(convId, ws.id)
      if (!owned) convId = null
    }
    if (!convId) {
      convId = id('cv')
      db.prepare(
        `INSERT INTO conversations (id, workspace_id, user_id, title, created_at) VALUES (?, ?, ?, ?, ?)`,
      ).run(convId, ws.id, user.id, message.trim().slice(0, 60), nowIso())
    }

    db.prepare(
      `INSERT INTO messages (id, conversation_id, role, body, created_at) VALUES (?, ?, 'user', ?, ?)`,
    ).run(id('m'), convId, message.trim(), nowIso())

    const history = db
      .prepare(`SELECT role, body FROM messages WHERE conversation_id = ? ORDER BY created_at`)
      .all(convId)

    const out = await askForge({
      workspaceId: ws.id,
      message: message.trim(),
      useBrain,
      history: history.slice(0, -1),
    })

    const mid = id('m')
    // The proposal is stored pending; it changes nothing until approved.
    const proposal = out.proposal
      ? { ...out.proposal, id: id('pr'), status: 'pending' }
      : null
    db.prepare(
      `INSERT INTO messages (id, conversation_id, role, body, proposal_json, created_at)
       VALUES (?, ?, 'agent', ?, ?, ?)`,
    ).run(mid, convId, out.reply, proposal ? JSON.stringify(proposal) : null, nowIso())

    return json(res, 200, {
      conversationId: convId,
      messageId: mid,
      reply: out.reply,
      proposal,
      provider: out.provider,
      note: out.note ?? null,
    })
  }

  if (p === '/api/forge/approve' && method === 'POST') {
    const { messageId } = await readJson(req)
    const row = db
      .prepare(
        `SELECT m.* FROM messages m JOIN conversations c ON c.id = m.conversation_id
         WHERE m.id = ? AND c.workspace_id = ?`,
      )
      .get(messageId, ws.id)
    if (!row?.proposal_json) throw Object.assign(new Error('No proposal on that message'), { status: 404 })

    const proposal = JSON.parse(row.proposal_json)
    if (proposal.status !== 'pending')
      throw Object.assign(new Error('Already resolved'), { status: 409 })

    const created = execProposal(ws.id, user.id, proposal)
    proposal.status = 'approved'
    db.prepare(`UPDATE messages SET proposal_json = ? WHERE id = ?`)
      .run(JSON.stringify(proposal), row.id)
    return json(res, 200, { ok: true, created })
  }

  if (p === '/api/forge/decline' && method === 'POST') {
    const { messageId } = await readJson(req)
    const row = db
      .prepare(
        `SELECT m.* FROM messages m JOIN conversations c ON c.id = m.conversation_id
         WHERE m.id = ? AND c.workspace_id = ?`,
      )
      .get(messageId, ws.id)
    if (!row?.proposal_json) throw Object.assign(new Error('No proposal'), { status: 404 })
    const proposal = JSON.parse(row.proposal_json)
    proposal.status = 'declined'
    db.prepare(`UPDATE messages SET proposal_json = ? WHERE id = ?`)
      .run(JSON.stringify(proposal), row.id)
    return json(res, 200, { ok: true })
  }

  throw Object.assign(new Error('Not found'), { status: 404 })
}

/**
 * Execute an approved proposal. This is the only path from model output to a
 * database write, and it validates every id rather than trusting the payload.
 */
function execProposal(workspaceId, userId, proposal) {
  const { kind, payload = {} } = proposal

  if (kind === 'create_board') {
    const bid = id('b')
    db.prepare(
      `INSERT INTO boards (id, workspace_id, name, template, created_at) VALUES (?, ?, ?, ?, ?)`,
    ).run(bid, workspaceId, String(payload.name ?? 'New board'), String(payload.template ?? 'Blank'), nowIso())
    const stages = Array.isArray(payload.stages) && payload.stages.length
      ? payload.stages
      : ['To do', 'Doing', 'Done']
    const tones = ['bg-zinc-400', 'bg-amber-500', 'bg-violet-500', 'bg-blue-500', 'bg-emerald-500']
    const stageIds = stages.map((s, i) => {
      const sid = id('st')
      db.prepare(`INSERT INTO stages (id, board_id, name, tone, position) VALUES (?, ?, ?, ?, ?)`)
        .run(sid, bid, String(s), tones[i % tones.length], i)
      return sid
    })
    let cardId = null
    if (payload.firstCard) {
      cardId = id('c')
      db.prepare(
        `INSERT INTO cards (id, workspace_id, board_id, stage_id, ref, title, tag, payout_cents, position, created_at)
         VALUES (?, ?, ?, ?, ?, ?, 'YOUTUBE', 0, 0, ?)`,
      ).run(cardId, workspaceId, bid, stageIds[0], nextCardRef(workspaceId), String(payload.firstCard), nowIso())
    }
    return { boardId: bid, cardId }
  }

  if (kind === 'create_card') {
    // Never trust a model-supplied boardId without checking it belongs here.
    const board =
      db.prepare(`SELECT * FROM boards WHERE id = ? AND workspace_id = ?`)
        .get(payload.boardId, workspaceId) ??
      db.prepare(`SELECT * FROM boards WHERE workspace_id = ? ORDER BY created_at LIMIT 1`)
        .get(workspaceId)
    if (!board) throw Object.assign(new Error('No board to add cards to'), { status: 400 })
    const stage = db
      .prepare(`SELECT * FROM stages WHERE board_id = ? ORDER BY position LIMIT 1`)
      .get(board.id)
    const ids = []
    for (const title of payload.titles ?? []) {
      const cid = id('c')
      db.prepare(
        `INSERT INTO cards (id, workspace_id, board_id, stage_id, ref, title, tag, payout_cents, position, created_at)
         VALUES (?, ?, ?, ?, ?, ?, 'YOUTUBE', 0, 0, ?)`,
      ).run(cid, workspaceId, board.id, stage.id, nextCardRef(workspaceId), String(title), nowIso())
      ids.push(cid)
    }
    return { cardIds: ids }
  }

  if (kind === 'save_to_brain') {
    const bid = id('br')
    db.prepare(
      `INSERT INTO brain_docs (id, workspace_id, title, kind, source, body, created_at)
       VALUES (?, ?, ?, ?, 'Saved by Forge', ?, ?)`,
    ).run(bid, workspaceId, String(payload.title ?? 'Untitled'), String(payload.kind ?? 'note'),
      String(payload.body ?? ''), nowIso())
    return { brainDocId: bid }
  }

  throw Object.assign(new Error(`Unknown proposal kind: ${kind}`), { status: 400 })
}

// ---------------------------------------------------------------- static

function serveStatic(req, res, url) {
  const clean = url.pathname.replace(/\.\.+/g, '.').replace(/^\/+/, '')
  let file = join(STATIC, clean || 'index.html')
  try {
    if (!statSync(file).isFile()) throw new Error('dir')
  } catch {
    file = join(STATIC, 'index.html') // SPA fallback
  }
  try {
    const s = statSync(file)
    res.writeHead(200, {
      'Content-Type': MIME[extname(file)] ?? 'application/octet-stream',
      'Content-Length': s.size,
    })
    createReadStream(file).pipe(res)
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' })
    res.end('Not found')
  }
}

// ---------------------------------------------------------------- server

export const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host ?? 'localhost'}`)
  try {
    if (url.pathname.startsWith('/api/')) {
      const sid = parseCookies(req.headers.cookie).fb_session
      const user = userFromSession(sid)
      await api(req, res, url, user)
      return
    }
    serveStatic(req, res, url)
  } catch (e) {
    if (res.headersSent) return res.end()
    const status = e.status ?? 500
    if (status >= 500) console.error(e)
    json(res, status, { error: e.message ?? 'Server error' })
  }
})

if (process.env.FORGEBOARD_NO_LISTEN !== '1') {
  server.listen(PORT, () => {
    console.log(`ForgeBoard on http://localhost:${PORT}  (agent: ${agentProvider()})`)
  })
}
