import { spawn } from 'node:child_process'
import { db } from './db.js'

/**
 * Forge — the agent.
 *
 * Runs by shelling out to the `claude` CLI, which authenticates with whatever
 * the machine is already logged into. On a Claude subscription that means no
 * metered API key and no per-token bill.
 *
 * The important caveat, stated in code because it is easy to forget:
 * subscription auth is *per person*. It is fine for you running ForgeBoard on
 * your own machine. Serving other people's requests through your subscription
 * on a deployed multi-user instance is not — that needs an API key. So the
 * provider is pluggable, and `FORGEBOARD_AGENT=api` is the seam for later.
 *
 * The model never writes to the database directly. It returns a proposal, the
 * user approves it, and the server executes — the same gate the real product
 * uses, and the reason a hallucinated board never silently appears.
 */

const TIMEOUT_MS = Number(process.env.FORGEBOARD_AGENT_TIMEOUT ?? 120_000)

export function agentProvider() {
  if (process.env.FORGEBOARD_AGENT) return process.env.FORGEBOARD_AGENT
  return 'cli'
}

/** Compact workspace summary so the model answers about real data. */
function workspaceContext(workspaceId) {
  const boards = db
    .prepare(`SELECT id, name, template FROM boards WHERE workspace_id = ?`)
    .all(workspaceId)
  const stages = db
    .prepare(
      `SELECT s.id, s.name, s.board_id FROM stages s
       JOIN boards b ON b.id = s.board_id WHERE b.workspace_id = ?
       ORDER BY s.position`,
    )
    .all(workspaceId)
  const cards = db
    .prepare(
      `SELECT ref, title, board_id, stage_id FROM cards
       WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 40`,
    )
    .all(workspaceId)
  const brain = db
    .prepare(
      `SELECT title, kind, substr(body, 1, 400) AS excerpt FROM brain_docs
       WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 12`,
    )
    .all(workspaceId)

  return {
    boards: boards.map((b) => ({
      ...b,
      stages: stages.filter((s) => s.board_id === b.id).map((s) => ({ id: s.id, name: s.name })),
    })),
    cards,
    brain,
  }
}

const SCHEMA = `Reply with ONE JSON object and nothing else. No markdown fence, no prose outside it.

{
  "reply": "what you say to the user, plain text",
  "proposal": null | {
    "kind": "create_board" | "create_card" | "save_to_brain",
    "summary": "one sentence describing exactly what will change",
    "payload": { ... }
  }
}

Payloads:
- create_board:   { "name": string, "template": string, "stages": string[], "firstCard": string|null }
- create_card:    { "boardId": string, "titles": string[] }
- save_to_brain:  { "title": string, "kind": "note"|"sop"|"transcript", "body": string }

Rules:
- Propose a write ONLY when the user asked for something to be created or changed.
  Questions get "proposal": null.
- Use real ids from the workspace context. Never invent a boardId.
- Keep "reply" under 120 words. Say what you did, not what you are about to do.`

function buildPrompt({ message, context, useBrain, history }) {
  const parts = [
    'You are Forge, the AI agent inside ForgeBoard, a workspace for creative teams',
    '(boards, drive, frame-accurate video review, freelancer payouts).',
    '',
    SCHEMA,
    '',
    '--- WORKSPACE ---',
    JSON.stringify(context, null, 1),
  ]
  if (!useBrain) {
    parts.push('', 'The user asked you NOT to use Brain context. Ignore the "brain" array above.')
  }
  if (history?.length) {
    parts.push('', '--- EARLIER IN THIS THREAD ---')
    for (const m of history.slice(-6)) parts.push(`${m.role}: ${m.body}`)
  }
  parts.push('', '--- USER MESSAGE ---', message)
  return parts.join('\n')
}

/** Pull the JSON object out of a reply that may still be wrapped. */
function extractJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  const candidate = (fenced ? fenced[1] : text).trim()
  const start = candidate.indexOf('{')
  const end = candidate.lastIndexOf('}')
  if (start === -1 || end === -1) return null
  try {
    return JSON.parse(candidate.slice(start, end + 1))
  } catch {
    return null
  }
}

function runClaudeCli(prompt) {
  return new Promise((resolve, reject) => {
    // Prompt goes on stdin, never argv: it is user input, it can be long, and
    // it must never be parsed by a shell.
    const child = spawn(
      process.env.FORGEBOARD_CLAUDE_BIN ?? 'claude',
      ['-p', '--output-format', 'json'],
      { stdio: ['pipe', 'pipe', 'pipe'] },
    )

    let out = ''
    let err = ''
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      reject(Object.assign(new Error('Forge timed out'), { status: 504 }))
    }, TIMEOUT_MS)

    child.stdout.on('data', (d) => (out += d))
    child.stderr.on('data', (d) => (err += d))
    child.on('error', (e) => {
      clearTimeout(timer)
      reject(e)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code !== 0) {
        reject(
          Object.assign(new Error(err.trim() || `claude exited ${code}`), { status: 502 }),
        )
        return
      }
      resolve(out)
    })

    child.stdin.end(prompt)
  })
}

/** Deterministic stand-in so the app still works with no CLI present. */
function mockReply(message) {
  const t = message.toLowerCase()
  if (/board|kanban|manage this channel/.test(t)) {
    return {
      reply:
        'I can set up a board from the YouTube Automation template — Idea, Script, Voiceover, Editing, Published — and drop your first video into Idea.',
      proposal: {
        kind: 'create_board',
        summary: 'Create a board with 5 stages and add 1 card.',
        payload: {
          name: 'Travel Documentary Channel',
          template: 'YouTube Automation',
          stages: ['Idea', 'Script', 'Voiceover', 'Editing', 'Published'],
          firstCard: 'First video',
        },
      },
    }
  }
  return {
    reply:
      'Forge is running without a model right now, so this is a canned reply. Install the Claude CLI and sign in, or set FORGEBOARD_AGENT=api with a key, and I will answer for real.',
    proposal: null,
  }
}

export async function askForge({ workspaceId, message, useBrain = true, history = [] }) {
  const provider = agentProvider()
  const context = workspaceContext(workspaceId)

  if (provider === 'mock') {
    return { ...mockReply(message), provider: 'mock', credits: 0 }
  }

  const prompt = buildPrompt({ message, context, useBrain, history })

  let raw
  try {
    raw = await runClaudeCli(prompt)
  } catch (e) {
    if (e.code === 'ENOENT') {
      return {
        ...mockReply(message),
        provider: 'mock',
        credits: 0,
        note: 'claude CLI not found on PATH — falling back to the canned agent.',
      }
    }
    throw e
  }

  // `--output-format json` wraps the reply; older shapes return it bare.
  let envelope
  try {
    envelope = JSON.parse(raw)
  } catch {
    envelope = null
  }
  const text = envelope?.result ?? envelope?.completion ?? raw

  const parsed = extractJson(typeof text === 'string' ? text : JSON.stringify(text))
  if (!parsed?.reply) {
    return {
      reply:
        typeof text === 'string' && text.trim()
          ? text.trim().slice(0, 2000)
          : 'Forge replied with something I could not parse.',
      proposal: null,
      provider,
      credits: 0,
    }
  }

  return {
    reply: String(parsed.reply),
    proposal: parsed.proposal ?? null,
    provider,
    // Subscription auth is not metered per call, so nothing is charged here.
    credits: 0,
  }
}
