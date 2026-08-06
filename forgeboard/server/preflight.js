import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'

const require_ = createRequire(import.meta.url)

/**
 * Checks the things that actually stop ForgeBoard starting on a fresh machine,
 * and says what to do about each. A clear message here is worth more than a
 * stack trace three layers into a module that failed to import.
 */

const RED = (s) => `\x1b[31m${s}\x1b[0m`
const YEL = (s) => `\x1b[33m${s}\x1b[0m`
const DIM = (s) => `\x1b[2m${s}\x1b[0m`
const BOLD = (s) => `\x1b[1m${s}\x1b[0m`

export function preflight() {
  const problems = []
  const notes = []

  // node:sqlite is the database. It landed in Node 22.5.
  const [maj, min] = process.versions.node.split('.').map(Number)
  if (maj < 22 || (maj === 22 && min < 5)) {
    problems.push(
      `Node ${process.versions.node} is too old — ForgeBoard's database (node:sqlite) needs Node 22.5 or newer.\n` +
        `    Install Node 22 LTS from https://nodejs.org, or with nvm:  ${BOLD('nvm install 22 && nvm use 22')}`,
    )
  } else {
    try {
      // Some 22.x builds require --experimental-sqlite. Load it synchronously
      // so a refusal is caught here rather than surfacing as an unhandled
      // rejection somewhere further in.
      require_('node:sqlite')
    } catch (e) {
      problems.push(
        `Node has node:sqlite but refused to load it: ${e.message}\n` +
          `    Try starting with:  ${BOLD('node --experimental-sqlite server/index.js')}`,
      )
    }
  }

  // The agent is optional — the app runs without it, just less usefully.
  if ((process.env.FORGEBOARD_AGENT ?? 'cli') === 'cli') {
    try {
      execFileSync(process.env.FORGEBOARD_CLAUDE_BIN ?? 'claude', ['--version'], {
        stdio: 'pipe',
        timeout: 15_000,
      })
    } catch {
      notes.push(
        `Forge will use canned replies — the ${BOLD('claude')} CLI is not on PATH.\n` +
          `    Install it and sign in with your Claude subscription:\n` +
          `      ${BOLD('npm install -g @anthropic-ai/claude-code')}  then  ${BOLD('claude')}\n` +
          `    Everything else works regardless.`,
      )
    }
  }

  if (!process.env.ELEVENLABS_API_KEY) {
    notes.push(
      `Playground audio is off — no ${BOLD('ELEVENLABS_API_KEY')} set.\n` +
        `    Script Writing and Social Posts still work (they run on Forge, free).\n` +
        `    To switch on speech and sound effects:  ${BOLD('ELEVENLABS_API_KEY=sk_... npm start')}`,
    )
  }

  if (problems.length) {
    console.error(`\n${RED('ForgeBoard cannot start:')}\n`)
    for (const p of problems) console.error(`  • ${p}\n`)
    process.exit(1)
  }

  for (const n of notes) console.log(`  ${YEL('note')}  ${n}\n`)
}

export function banner(port, agent) {
  const url = `http://localhost:${port}`
  console.log(`
  ${BOLD('ForgeBoard')} is running

    ${BOLD(url)}

  ${DIM(`agent: ${agent === 'cli' ? 'Claude CLI (your subscription)' : agent}`)}
  ${DIM('database: data/forgeboard.db   uploads: data/uploads')}
  ${DIM('first time? create an account on the sign-in screen — it is local to this machine')}

  ${DIM('stop with Ctrl+C')}
`)
}
