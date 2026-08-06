import { randomBytes, scrypt as _scrypt, timingSafeEqual } from 'node:crypto'
import { promisify } from 'node:util'
import { db, id, nowIso } from './db.js'

const scrypt = promisify(_scrypt)

/**
 * Passwords and sessions.
 *
 * scrypt from node:crypto — memory-hard, in the standard library, no
 * dependency and no service. Sessions are opaque random ids in an HttpOnly
 * cookie with a row in the database, so logging out actually revokes rather
 * than just dropping a token the server still trusts.
 */

const SESSION_DAYS = 30

export async function hashPassword(plain) {
  const salt = randomBytes(16)
  const key = await scrypt(plain, salt, 64)
  return `scrypt$${salt.toString('base64')}$${key.toString('base64')}`
}

export async function verifyPassword(plain, stored) {
  const [scheme, saltB64, keyB64] = String(stored).split('$')
  if (scheme !== 'scrypt' || !saltB64 || !keyB64) return false
  const key = Buffer.from(keyB64, 'base64')
  const candidate = await scrypt(plain, Buffer.from(saltB64, 'base64'), key.length)
  // Constant-time: a length mismatch must not short-circuit before comparing.
  return key.length === candidate.length && timingSafeEqual(key, candidate)
}

export function createSession(userId) {
  const sid = id('sess')
  const expires = new Date(Date.now() + SESSION_DAYS * 86_400_000).toISOString()
  db.prepare(`INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)`)
    .run(sid, userId, expires)
  return { sid, expires }
}

export function destroySession(sid) {
  db.prepare(`DELETE FROM sessions WHERE id = ?`).run(sid)
}

/** Resolve a cookie to a user, dropping the row if it has expired. */
export function userFromSession(sid) {
  if (!sid) return null
  const row = db
    .prepare(
      `SELECT u.*, s.expires_at FROM sessions s
       JOIN users u ON u.id = s.user_id WHERE s.id = ?`,
    )
    .get(sid)
  if (!row) return null
  if (new Date(row.expires_at).getTime() < Date.now()) {
    destroySession(sid)
    return null
  }
  const { password_hash: _pw, expires_at: _exp, ...user } = row
  return user
}

const INITIALS = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || '??'

export async function registerUser({ email, password, name }) {
  const exists = db.prepare(`SELECT 1 FROM users WHERE email = ?`).get(email)
  if (exists) throw Object.assign(new Error('That email is already registered'), { status: 409 })

  const uid = id('u')
  db.prepare(
    `INSERT INTO users (id, email, password_hash, name, initials, hue, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    uid,
    email,
    await hashPassword(password),
    name,
    INITIALS(name),
    Math.floor(Math.random() * 360),
    nowIso(),
  )
  return db.prepare(`SELECT id, email, name, initials, hue FROM users WHERE id = ?`).get(uid)
}

export async function login({ email, password }) {
  const row = db.prepare(`SELECT * FROM users WHERE email = ?`).get(email)
  // Hash anyway on a miss so a missing account and a wrong password take a
  // similar amount of time.
  const ok = row
    ? await verifyPassword(password, row.password_hash)
    : await verifyPassword(password, await hashPassword('decoy'))
  if (!row || !ok) throw Object.assign(new Error('Wrong email or password'), { status: 401 })
  const { password_hash: _pw, ...user } = row
  return user
}

export function cookieHeader(sid, expires) {
  const parts = [
    `fb_session=${sid}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Expires=${new Date(expires).toUTCString()}`,
  ]
  if (process.env.FORGEBOARD_HTTPS === '1') parts.push('Secure')
  return parts.join('; ')
}

export const clearCookieHeader = () =>
  'fb_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'

export function parseCookies(header = '') {
  return Object.fromEntries(
    header
      .split(';')
      .map((c) => c.trim().split('='))
      .filter(([k, v]) => k && v !== undefined)
      .map(([k, ...v]) => [k, decodeURIComponent(v.join('='))]),
  )
}
