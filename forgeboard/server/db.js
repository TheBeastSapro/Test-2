import { DatabaseSync } from 'node:sqlite'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

/**
 * The database.
 *
 * SQLite via node:sqlite, which ships with Node 22 — no native build, no
 * server process, no hosting bill. The whole database is one file, which also
 * makes backup a copy and reset a delete.
 *
 * The schema keeps the property the front-end prototype was built around: a
 * card is the single unit of work, and boards, calendar, files, review and
 * payouts all reference that one row rather than keeping their own copies.
 */

const DB_PATH = resolve(process.env.FORGEBOARD_DB ?? 'data/forgeboard.db')
mkdirSync(dirname(DB_PATH), { recursive: true })

export const db = new DatabaseSync(DB_PATH)

db.exec(`PRAGMA journal_mode = WAL;`)
db.exec(`PRAGMA foreign_keys = ON;`)

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  name          TEXT NOT NULL,
  initials      TEXT NOT NULL,
  hue           INTEGER NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS workspaces (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  owner_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credits    INTEGER NOT NULL DEFAULT 1000,
  created_at TEXT NOT NULL
);

-- Guests are free and unlimited; the flag is what makes that policy real
-- rather than a marketing line.
CREATE TABLE IF NOT EXISTS memberships (
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role         TEXT NOT NULL DEFAULT 'Member',
  is_guest     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS boards (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  template     TEXT NOT NULL DEFAULT 'Blank',
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_boards_ws ON boards(workspace_id);

CREATE TABLE IF NOT EXISTS stages (
  id       TEXT PRIMARY KEY,
  board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  name     TEXT NOT NULL,
  tone     TEXT NOT NULL DEFAULT 'bg-zinc-400',
  position INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stages_board ON stages(board_id);

CREATE TABLE IF NOT EXISTS cards (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  board_id     TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  stage_id     TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  ref          TEXT NOT NULL,
  title        TEXT NOT NULL,
  tag          TEXT NOT NULL DEFAULT 'YOUTUBE',
  due          TEXT,
  payout_cents INTEGER NOT NULL DEFAULT 0,
  position     INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_board ON cards(board_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_ref ON cards(workspace_id, ref);

CREATE TABLE IF NOT EXISTS card_assignees (
  card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (card_id, user_id)
);

CREATE TABLE IF NOT EXISTS checklist_items (
  id       TEXT PRIMARY KEY,
  card_id  TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  label    TEXT NOT NULL,
  done     INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_check_card ON checklist_items(card_id);

CREATE TABLE IF NOT EXISTS card_comments (
  id         TEXT PRIMARY KEY,
  card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  author_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cardcomments_card ON card_comments(card_id);

-- Real uploads. storage_path points at a file on disk; nothing is held in the
-- database, so the row stays small and the media streams.
CREATE TABLE IF NOT EXISTS files (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  card_id      TEXT REFERENCES cards(id) ON DELETE SET NULL,
  name         TEXT NOT NULL,
  kind         TEXT NOT NULL,
  mime         TEXT NOT NULL,
  size_bytes   INTEGER NOT NULL,
  storage_path TEXT NOT NULL,
  favorited    INTEGER NOT NULL DEFAULT 0,
  trashed      INTEGER NOT NULL DEFAULT 0,
  uploaded_by  TEXT NOT NULL REFERENCES users(id),
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_ws ON files(workspace_id);

CREATE TABLE IF NOT EXISTS review_assets (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  file_id      TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  card_id      TEXT REFERENCES cards(id) ON DELETE SET NULL,
  title        TEXT NOT NULL,
  version      INTEGER NOT NULL DEFAULT 1,
  duration_sec REAL NOT NULL DEFAULT 0,
  fps          REAL NOT NULL DEFAULT 25,
  status       TEXT NOT NULL DEFAULT 'in review',
  uploaded_by  TEXT NOT NULL REFERENCES users(id),
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_ws ON review_assets(workspace_id);

CREATE TABLE IF NOT EXISTS review_comments (
  id           TEXT PRIMARY KEY,
  asset_id     TEXT NOT NULL REFERENCES review_assets(id) ON DELETE CASCADE,
  author_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  timecode_sec REAL NOT NULL,
  body         TEXT NOT NULL,
  region_json  TEXT,
  resolved     INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revcomments_asset ON review_comments(asset_id);

CREATE TABLE IF NOT EXISTS payouts (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  member_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount_cents INTEGER NOT NULL,
  method       TEXT NOT NULL DEFAULT 'Wise',
  status       TEXT NOT NULL DEFAULT 'requested',
  invoice_no   TEXT,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payouts_ws ON payouts(workspace_id);

CREATE TABLE IF NOT EXISTS payout_cards (
  payout_id TEXT NOT NULL REFERENCES payouts(id) ON DELETE CASCADE,
  card_id   TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  PRIMARY KEY (payout_id, card_id)
);

CREATE TABLE IF NOT EXISTS brain_docs (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  kind         TEXT NOT NULL DEFAULT 'note',
  source       TEXT NOT NULL DEFAULT '',
  body         TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_brain_ws ON brain_docs(workspace_id);

CREATE TABLE IF NOT EXISTS creations (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  module       TEXT NOT NULL,
  body         TEXT NOT NULL DEFAULT '',
  credits      INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL,
  body            TEXT NOT NULL,
  proposal_json   TEXT,
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS inbox (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL DEFAULT '',
  card_ref     TEXT,
  read         INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inbox_user ON inbox(workspace_id, user_id);

CREATE TABLE IF NOT EXISTS automations (
  id           TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  trigger      TEXT NOT NULL,
  action       TEXT NOT NULL,
  enabled      INTEGER NOT NULL DEFAULT 1,
  runs         INTEGER NOT NULL DEFAULT 0
);
`)

export const nowIso = () => new Date().toISOString()

/** Short, URL-safe, collision-resistant enough for row ids. */
export function id(prefix) {
  const b = new Uint8Array(9)
  crypto.getRandomValues(b)
  return `${prefix}_${Buffer.from(b).toString('base64url')}`
}

/** Next KB-N reference for a workspace. Unique index enforces it too. */
export function nextCardRef(workspaceId) {
  const row = db
    .prepare(
      `SELECT ref FROM cards WHERE workspace_id = ?
       ORDER BY CAST(substr(ref, 4) AS INTEGER) DESC LIMIT 1`,
    )
    .get(workspaceId)
  const n = row ? Number(String(row.ref).slice(3)) : 0
  return `KB-${n + 1}`
}
