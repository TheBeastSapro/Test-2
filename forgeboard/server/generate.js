import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { db, id, nowIso } from './db.js'
import { askForge } from './agent.js'

/**
 * The Playground.
 *
 * Two kinds of module, and they cost very different things:
 *
 * - Writing (script, social) runs through Forge, which means the Claude CLI,
 *   which means a subscription rather than a bill. Free to run.
 * - Audio and images need a third-party model. ElevenLabs for speech and sound,
 *   an image API for stills. Those are metered, so they stay switched off until
 *   a key is present — and when it is, they light up with no code change.
 *
 * A module without its key does not pretend. It returns `configured: false`
 * with the exact environment variable to set, so the UI can say something true
 * instead of producing a fake result.
 */

const UPLOADS = resolve(process.env.FORGEBOARD_UPLOADS ?? 'data/uploads')

const ELEVEN_KEY = () => process.env.ELEVENLABS_API_KEY ?? ''
const ELEVEN_VOICE = () => process.env.ELEVENLABS_VOICE_ID ?? 'JBFqnCBsd6RMkjVDRZzb'

/** Which env var a module needs, or null when it runs on the subscription. */
export const MODULE_REQUIREMENT = {
  tts: 'ELEVENLABS_API_KEY',
  sfx: 'ELEVENLABS_API_KEY',
  music: 'ELEVENLABS_API_KEY',
  image: 'IMAGE_API_KEY',
  script: null,
  social: null,
}

export function moduleStatus() {
  return Object.fromEntries(
    Object.entries(MODULE_REQUIREMENT).map(([m, envVar]) => [
      m,
      { configured: !envVar || !!process.env[envVar], requires: envVar },
    ]),
  )
}

function storeFile({ workspaceId, userId, name, mime, bytes, kind }) {
  mkdirSync(UPLOADS, { recursive: true })
  const fid = id('f')
  const ext = mime.includes('mpeg') ? '.mp3' : mime.includes('wav') ? '.wav' : '.bin'
  const path = join(UPLOADS, `${fid}${ext}`)
  writeFileSync(path, bytes)
  db.prepare(
    `INSERT INTO files (id, workspace_id, card_id, name, kind, mime, size_bytes, storage_path, uploaded_by, created_at)
     VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(fid, workspaceId, name, kind, mime, bytes.length, path, userId, nowIso())
  return fid
}

function recordCreation({ workspaceId, title, module, body, credits }) {
  const cid = id('cr')
  db.prepare(
    `INSERT INTO creations (id, workspace_id, title, module, body, credits, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).run(cid, workspaceId, title, module, body, credits, nowIso())
  return cid
}

/** Credits are the metered resource; structure stays free, as in the original. */
function chargeCredits(workspaceId, credits) {
  if (credits <= 0) return
  db.prepare(`UPDATE workspaces SET credits = MAX(0, credits - ?) WHERE id = ?`)
    .run(credits, workspaceId)
}

async function elevenSpeech({ prompt, settings }) {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${settings.voiceId ?? ELEVEN_VOICE()}`,
    {
      method: 'POST',
      headers: {
        'xi-api-key': ELEVEN_KEY(),
        'Content-Type': 'application/json',
        Accept: 'audio/mpeg',
      },
      body: JSON.stringify({
        text: prompt,
        model_id: settings.model === 'turbo-v2.5' ? 'eleven_turbo_v2_5' : 'eleven_multilingual_v2',
        voice_settings: {
          stability: settings.stability ?? 0.5,
          similarity_boost: settings.similarity ?? 0.75,
          style: settings.style ?? 0,
          speed: settings.speed ?? 1,
        },
      }),
    },
  )
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw Object.assign(new Error(`ElevenLabs refused the request: ${detail.slice(0, 300)}`), {
      status: res.status === 401 ? 401 : 502,
    })
  }
  return { bytes: Buffer.from(await res.arrayBuffer()), mime: 'audio/mpeg' }
}

async function elevenSoundEffect({ prompt, settings }) {
  const res = await fetch('https://api.elevenlabs.io/v1/sound-generation', {
    method: 'POST',
    headers: {
      'xi-api-key': ELEVEN_KEY(),
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg',
    },
    body: JSON.stringify({
      text: prompt,
      duration_seconds: settings.seconds ?? null,
    }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw Object.assign(new Error(`ElevenLabs refused the request: ${detail.slice(0, 300)}`), {
      status: res.status === 401 ? 401 : 502,
    })
  }
  return { bytes: Buffer.from(await res.arrayBuffer()), mime: 'audio/mpeg' }
}

export async function generate({ workspaceId, userId, module, prompt, settings = {} }) {
  const requirement = MODULE_REQUIREMENT[module]
  if (requirement === undefined) {
    throw Object.assign(new Error(`Unknown module: ${module}`), { status: 400 })
  }

  // ---- writing: runs on Forge, so it is free
  if (module === 'script' || module === 'social') {
    const framing =
      module === 'script'
        ? 'Write the script itself as the "reply" field. Raw text, no headings, no brackets. Set "proposal" to null.'
        : 'Write the posts as the "reply" field, numbered, one per line group. Set "proposal" to null.'
    const out = await askForge({
      workspaceId,
      message: `${prompt}\n\n${framing}`,
      useBrain: settings.groundOnBrain !== false,
    })
    const title = prompt.trim().slice(0, 60) + (prompt.trim().length > 60 ? '…' : '')
    const creationId = recordCreation({
      workspaceId, title, module, body: out.reply, credits: 0,
    })
    return {
      id: creationId,
      title,
      body: out.reply,
      credits: 0,
      configured: true,
      provider: out.provider,
    }
  }

  // ---- media: needs a paid key, and says so honestly when it has none
  if (requirement && !process.env[requirement]) {
    throw Object.assign(
      new Error(
        `${module} needs a ${requirement}. Set it in the environment and restart — no code change needed.`,
      ),
      { status: 503 },
    )
  }

  if (module === 'tts' || module === 'sfx') {
    const { bytes, mime } =
      module === 'tts'
        ? await elevenSpeech({ prompt, settings })
        : await elevenSoundEffect({ prompt, settings })

    const title = prompt.trim().slice(0, 60) + (prompt.trim().length > 60 ? '…' : '')
    const name = `${module}-${Date.now()}.mp3`
    const fileId = storeFile({
      workspaceId, userId, name, mime, bytes, kind: 'audio',
    })
    const credits = module === 'tts' ? Math.max(1, Math.ceil(prompt.length / 10)) : 24
    chargeCredits(workspaceId, credits)
    const creationId = recordCreation({
      workspaceId,
      title,
      module,
      body: `${(bytes.length / 1024).toFixed(0)} KB · ${mime}`,
      credits,
    })
    return { id: creationId, title, body: `Saved to Drive as ${name}`, credits, fileId, configured: true }
  }

  throw Object.assign(
    new Error(`${module} is not wired to a provider yet.`),
    { status: 501 },
  )
}
