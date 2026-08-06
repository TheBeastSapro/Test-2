import type { AgentMessage } from '../../lib/types'

/**
 * The agent seam.
 *
 * This is a deterministic stand-in so the whole approval → execute → visible-in-
 * every-app loop is real and demonstrable without a model key. Everything the UI
 * depends on lives in the return shape, so swapping in a real call means
 * replacing the body of `respond` and nothing else:
 *
 *   const res = await fetch('/api/kloudie', { method: 'POST', body: … })
 *   return { message: toAgentMessage(await res.json()), credits: res.credits }
 *
 * Kloudboard's own MCP surface splits the same way — cheap structured writes
 * (`create_card`, `manage_card`) cost nothing, and only `ask_kloudie` burns
 * credits. The `credits` field here mirrors that.
 */

interface Reply {
  message: AgentMessage
  credits: number
}

const msg = (body: string, proposal?: AgentMessage['proposal']): AgentMessage => ({
  id: `am-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
  role: 'agent',
  body,
  proposal,
  at: new Date().toISOString(),
})

const has = (t: string, ...words: string[]) => words.some((w) => t.includes(w))

export async function respond(
  input: string,
  opts: { useBrain: boolean },
): Promise<Reply> {
  // Simulated latency so the "Working…" state is observable.
  await new Promise((r) => setTimeout(r, 700))

  const t = input.toLowerCase()
  const grounding = opts.useBrain
    ? 'Grounded on your Brain — channel voice SOP, the 1,500-word structure note, and the Bermuda transcript.'
    : 'Ignoring Brain context, as asked. Working only from what you gave me here.'

  if (has(t, 'board', 'kanban', 'manage this channel')) {
    return {
      credits: 45,
      message: msg(
        `I'll build a board from the YouTube Automation template — the five stages that template uses are Idea, Script, Voiceover, Editing and Published — and drop your first video into Idea.\n\n${grounding}`,
        {
          id: `pr-${Date.now()}`,
          kind: 'create_board',
          status: 'pending',
          summary:
            'Create board "Travel Documentary Channel 2" from the YouTube Automation template with 5 stages, and add 1 card.',
          payload: {
            name: 'Travel Documentary Channel 2',
            template: 'YouTube Automation',
            stages: ['Idea', 'Script', 'Voiceover', 'Editing', 'Published'],
            firstCard: 'How People Live in Bermuda',
          },
        },
      ),
    }
  }

  if (has(t, 'script', 'write me', 'similar')) {
    return {
      credits: 140,
      message: msg(
        `Done — 1,480 words, raw text, no headings, same six-beat structure as the reference transcript.\n\nI matched the cold open to 11 seconds of read time and led with a concrete number, per your voice SOP. Saved to Library.\n\n${grounding}`,
      ),
    }
  }

  if (has(t, 'niche', 'competitor', 'scan', 'faceless')) {
    return {
      credits: 60,
      message: msg(
        `Five channels clear every filter — under 100k subs, started in the last four months, at least one video past 200k views, monetized and faceless.\n\nThe one worth acting on is @topunrealplanet: 1.2k subs, 2.7x outlier against its own baseline, running our exact format. A small channel breaking in is the signal that the niche is still open — a big one just means you're late.\n\nAll five are tracked now.`,
      ),
    }
  }

  if (has(t, 'transcript', 'import', 'brain', 'save')) {
    return {
      credits: 20,
      message: msg(
        'I can pull that transcript and index it so future scripts can ground on it.',
        {
          id: `pr-${Date.now()}`,
          kind: 'save_to_brain',
          status: 'pending',
          summary: 'Transcribe the linked video and save it to the Brain.',
          payload: {
            title: 'Imported transcript',
            body: 'Transcribed on ingest and indexed for semantic search.',
          },
        },
      ),
    }
  }

  if (has(t, 'social', 'repurpose', 'tiktok', 'thread', 'posts')) {
    return {
      credits: 38,
      message: msg(
        `Nine posts, hook-first, each one standing alone if it's the only one somebody reads.\n\nI kept your rule about not opening with a rhetorical question. Saved to Library.\n\n${grounding}`,
      ),
    }
  }

  if (has(t, 'thumbnail', 'design', 'image')) {
    return {
      credits: 24,
      message: msg(
        'Four thumbnail concepts at 1280×720, high contrast, using the arrow-and-circle treatment that outperformed on the Bermuda upload. Saved to Library.',
      ),
    }
  }

  if (has(t, 'plan', 'slate', 'ideas', 'next videos')) {
    return {
      credits: 55,
      message: msg(
        `Three ideas that fit the format and have proven demand in adjacent channels.\n\n${grounding}`,
        {
          id: `pr-${Date.now()}`,
          kind: 'create_card',
          status: 'pending',
          summary: 'Add 3 cards to the first stage of your Travel Documentary board.',
          payload: {
            boardId: 'b-1',
            titles: [
              'Kerguelen: The Islands of Desolation',
              'Pitcairn: 40 People and a Mutiny',
              'Socotra: The Island That Looks Like Another Planet',
            ],
          },
        },
      ),
    }
  }

  return {
    credits: 15,
    message: msg(
      `I can work across the whole workspace — build boards and cards, write scripts in your channel voice, generate voiceovers, scan competitors, and set up automations.\n\nTry: "make a board where I can manage this channel", "generate a script from this transcript", or "scan our niche for faceless channels".\n\n${grounding}`,
    ),
  }
}
