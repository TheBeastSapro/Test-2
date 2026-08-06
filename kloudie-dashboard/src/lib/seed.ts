import type {
  Asset,
  Automation,
  Board,
  BrainDoc,
  Card,
  ChatChannel,
  ChatMessage,
  Competitor,
  Contract,
  Conversation,
  Creation,
  InboxItem,
  Member,
  Payout,
  ReviewAsset,
  ReviewComment,
  VideoStat,
  Workspace,
} from './types'

/**
 * Seed workspace, modelled on the faceless-documentary channel operation the
 * source video walks through, so every screen has plausible connected data.
 */

const DAY = 86_400_000
const now = new Date('2026-08-06T09:00:00Z').getTime()
const at = (dayOffset: number, hour = 10) =>
  new Date(now + dayOffset * DAY + hour * 3_600_000).toISOString()

export const workspaces: Workspace[] = [
  { id: 'ws-1', name: 'Personal Brand Content' },
  { id: 'ws-2', name: 'Impossible Travel' },
  { id: 'ws-3', name: 'Nexarc Growth' },
]

export const members: Member[] = [
  { id: 'm-1', name: 'Sapro', role: 'Owner', guest: false, initials: 'SA', hue: 232 },
  { id: 'm-2', name: 'Mira Holt', role: 'Writer', guest: false, initials: 'MH', hue: 168, payoutMethod: 'Wise' },
  { id: 'm-3', name: 'Deniz Aksoy', role: 'Editor', guest: true, initials: 'DA', hue: 22, payoutMethod: 'Payoneer' },
  { id: 'm-4', name: 'Junas Lind', role: 'Editor', guest: true, initials: 'JL', hue: 288, payoutMethod: 'PayPal' },
  { id: 'm-5', name: 'Rea Okafor', role: 'Designer', guest: true, initials: 'RO', hue: 340, payoutMethod: 'Revolut' },
]

export const boards: Board[] = [
  {
    id: 'b-1',
    name: 'Travel Documentary Channel',
    template: 'YouTube Automation',
    stages: [
      { id: 's-idea', name: 'Idea', tone: 'bg-zinc-400' },
      { id: 's-script', name: 'Script', tone: 'bg-amber-500' },
      { id: 's-voice', name: 'Voiceover', tone: 'bg-violet-500' },
      { id: 's-edit', name: 'Editing', tone: 'bg-blue-500' },
      { id: 's-published', name: 'Published', tone: 'bg-emerald-500' },
    ],
  },
  {
    id: 'b-2',
    name: 'Personal Brand',
    template: 'Content Calendar',
    stages: [
      { id: 's2-todo', name: 'To do', tone: 'bg-zinc-400' },
      { id: 's2-progress', name: 'In progress', tone: 'bg-amber-500' },
      { id: 's2-published', name: 'Published', tone: 'bg-emerald-500' },
    ],
  },
]

const check = (labels: string[], doneCount: number) =>
  labels.map((label, i) => ({ id: `c${i}`, label, done: i < doneCount }))

export const cards: Card[] = [
  {
    id: 'card-1', ref: 'KB-26', boardId: 'b-1', stageId: 's-published',
    title: 'How People Live in Bermuda | 60,000 People on a Rock with Zero Resources',
    tag: 'YOUTUBE', due: at(-3), assigneeIds: ['m-2', 'm-3'],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 5),
    comments: [
      { id: 'cm-1', authorId: 'm-3', body: 'Final cut uploaded, colour pass done.', at: at(-4, 14) },
      { id: 'cm-2', authorId: 'm-1', body: 'Live. 1.3M views in 7 days.', at: at(-3, 9) },
    ],
    attachmentIds: ['a-1', 'a-2'], payoutCents: 24_000, createdAt: at(-18),
  },
  {
    id: 'card-2', ref: 'KB-27', boardId: 'b-1', stageId: 's-edit',
    title: 'Why Tristan da Cunha Is the Most Isolated Island on Earth',
    tag: 'YOUTUBE', due: at(2), assigneeIds: ['m-3'],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 3),
    comments: [{ id: 'cm-3', authorId: 'm-3', body: 'Rough cut at 11 min, trimming the intro.', at: at(-1, 16) }],
    attachmentIds: ['a-3'], payoutCents: 24_000, createdAt: at(-11),
  },
  {
    id: 'card-3', ref: 'KB-28', boardId: 'b-1', stageId: 's-voice',
    title: 'Curaçao: The Smallest Island That Surprised the World',
    tag: 'YOUTUBE', due: at(4), assigneeIds: ['m-2'],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 2),
    comments: [], attachmentIds: [], payoutCents: 24_000, createdAt: at(-8),
  },
  {
    id: 'card-4', ref: 'KB-29', boardId: 'b-1', stageId: 's-script',
    title: 'Guyana: The Country That Struck Oil and Changed Overnight',
    tag: 'YOUTUBE', due: at(6), assigneeIds: ['m-2'],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 1),
    comments: [], attachmentIds: [], payoutCents: 24_000, createdAt: at(-6),
  },
  {
    id: 'card-5', ref: 'KB-30', boardId: 'b-1', stageId: 's-idea',
    title: 'The Marshall Islands and the Test That Never Ended',
    tag: 'YOUTUBE', due: at(11), assigneeIds: [],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 0),
    comments: [], attachmentIds: [], payoutCents: 24_000, createdAt: at(-2),
  },
  {
    id: 'card-6', ref: 'KB-31', boardId: 'b-1', stageId: 's-idea',
    title: 'Svalbard: Where Dying Is Against the Law',
    tag: 'YOUTUBE', due: at(14), assigneeIds: [],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 0),
    comments: [], attachmentIds: [], payoutCents: 24_000, createdAt: at(-1),
  },
  {
    id: 'card-7', ref: 'KB-32', boardId: 'b-1', stageId: 's-published',
    title: 'Bermuda Part II: The Insurance Capital Nobody Talks About',
    tag: 'YOUTUBE', due: at(-9), assigneeIds: ['m-4'],
    checklist: check(['Script', 'Voiceover', 'Edit', 'Thumbnail', 'Upload'], 5),
    comments: [], attachmentIds: [], payoutCents: 22_000, createdAt: at(-24),
  },
  {
    id: 'card-8', ref: 'KB-33', boardId: 'b-2', stageId: 's2-progress',
    title: 'Thread: the 8-step faceless pipeline',
    tag: 'MARKETING', due: at(1), assigneeIds: ['m-1'],
    checklist: check(['Draft', 'Edit', 'Schedule'], 1),
    comments: [], attachmentIds: [], payoutCents: 0, createdAt: at(-3),
  },
  {
    id: 'card-9', ref: 'KB-34', boardId: 'b-2', stageId: 's2-todo',
    title: 'Channel teardown carousel',
    tag: 'DESIGN', due: at(5), assigneeIds: ['m-5'],
    checklist: check(['Copy', 'Design', 'Export'], 0),
    comments: [], attachmentIds: [], payoutCents: 9_000, createdAt: at(-2),
  },
  {
    id: 'card-10', ref: 'KB-35', boardId: 'b-2', stageId: 's2-published',
    title: 'Newsletter #14 — RPM by niche',
    tag: 'NEWSLETTER', due: at(-5), assigneeIds: ['m-2'],
    checklist: check(['Draft', 'Edit', 'Send'], 3),
    comments: [], attachmentIds: [], payoutCents: 6_000, createdAt: at(-12),
  },
]

/**
 * Cuts under review. The clips in `public/clips` are generated locally with
 * ffmpeg and carry a burned-in timecode, so frame stepping can be checked
 * against what the frame itself says.
 */
export const reviewAssets: ReviewAsset[] = [
  { id: 'rv-1', cardId: 'card-2', title: 'Tristan da Cunha — rough cut', version: 1, src: 'clips/tristan-v1', durationSec: 24, fps: 25, status: 'changes requested', uploadedBy: 'm-3', at: at(-4) },
  { id: 'rv-2', cardId: 'card-2', title: 'Tristan da Cunha — rough cut', version: 2, src: 'clips/tristan-v2', durationSec: 22, fps: 25, status: 'in review', uploadedBy: 'm-3', at: at(-1) },
  { id: 'rv-3', cardId: 'card-3', title: 'Curaçao — assembly', version: 1, src: 'clips/curacao-v1', durationSec: 18, fps: 25, status: 'in review', uploadedBy: 'm-4', at: at(0, 8) },
]

export const reviewComments: ReviewComment[] = [
  { id: 'rc-1', assetId: 'rv-1', authorId: 'm-1', timecodeSec: 2.4, body: 'Cold open runs long — cut this to under 12 seconds per the voice SOP.', region: { tool: 'rect', x: 0.06, y: 0.1, w: 0.4, h: 0.3 }, resolved: true, at: at(-4, 15) },
  { id: 'rc-2', assetId: 'rv-1', authorId: 'm-1', timecodeSec: 9.8, body: 'Lower third sits over the horizon line. Drop it 40px.', region: { tool: 'arrow', x: 0.55, y: 0.62, w: 0.35, h: 0.18 }, resolved: true, at: at(-4, 15) },
  { id: 'rc-3', assetId: 'rv-1', authorId: 'm-2', timecodeSec: 17.2, body: 'VO and picture drift apart here — about half a second late.', region: null, resolved: false, at: at(-4, 16) },
  { id: 'rc-4', assetId: 'rv-2', authorId: 'm-1', timecodeSec: 5.0, body: 'Much better. One more: hold this shot two beats longer before the cut.', region: { tool: 'rect', x: 0.3, y: 0.28, w: 0.3, h: 0.34 }, resolved: false, at: at(-1, 11) },
  { id: 'rc-5', assetId: 'rv-2', authorId: 'm-5', timecodeSec: 12.6, body: 'Colour is warmer than the Bermuda upload. Match the grade.', region: null, resolved: false, at: at(-1, 12) },
  { id: 'rc-6', assetId: 'rv-3', authorId: 'm-1', timecodeSec: 3.1, body: 'Missing the map beat that made Bermuda work. Add it before the reveal.', region: { tool: 'pin', x: 0.12, y: 0.3, w: 0, h: 0 }, resolved: false, at: at(0, 9) },
]

export const assets: Asset[] = [
  { id: 'a-1', name: 'bermuda-voiceover-final.mp3', kind: 'audio', sizeKb: 7_420, cardId: 'card-1', at: at(-6) },
  { id: 'a-2', name: 'bermuda-thumbnail-v3.png', kind: 'image', sizeKb: 880, cardId: 'card-1', at: at(-5) },
  { id: 'a-3', name: 'tristan-script-v2.md', kind: 'doc', sizeKb: 22, cardId: 'card-2', at: at(-2) },
  { id: 'a-4', name: 'channel-brand-kit.zip', kind: 'other', sizeKb: 41_300, cardId: null, at: at(-30) },
  { id: 'a-5', name: 'curacao-broll-pack.mp4', kind: 'video', sizeKb: 1_204_000, cardId: 'card-3', at: at(-3) },
  { id: 'a-6', name: 'steve-voice-reference.mp3', kind: 'audio', sizeKb: 1_120, cardId: null, at: at(-20) },
  { id: 'a-7', name: 'guyana-outline.md', kind: 'doc', sizeKb: 14, cardId: 'card-4', at: at(-4) },
  { id: 'a-8', name: 'intro-sting.wav', kind: 'audio', sizeKb: 3_400, cardId: null, at: at(-15) },
]

export const payouts: Payout[] = [
  { id: 'p-1', memberId: 'm-3', cardIds: ['card-1'], amountCents: 24_000, method: 'Payoneer', status: 'paid', invoiceNo: 'INV-0041', at: at(-3) },
  { id: 'p-2', memberId: 'm-4', cardIds: ['card-7'], amountCents: 22_000, method: 'PayPal', status: 'paid', invoiceNo: 'INV-0040', at: at(-9) },
  { id: 'p-3', memberId: 'm-2', cardIds: ['card-10'], amountCents: 6_000, method: 'Wise', status: 'paid', invoiceNo: 'INV-0039', at: at(-5) },
  { id: 'p-4', memberId: 'm-3', cardIds: ['card-2'], amountCents: 24_000, method: 'Payoneer', status: 'scheduled', invoiceNo: null, at: at(3) },
  { id: 'p-5', memberId: 'm-5', cardIds: ['card-9'], amountCents: 9_000, method: 'Revolut', status: 'requested', invoiceNo: null, at: at(0) },
]

export const contracts: Contract[] = [
  { id: 'ct-1', memberId: 'm-3', title: 'Long-form editor — retainer', status: 'signed', at: at(-26) },
  { id: 'ct-2', memberId: 'm-4', title: 'Long-form editor — per video', status: 'signed', at: at(-20) },
  { id: 'ct-3', memberId: 'm-2', title: 'Script writer — retainer', status: 'signed', at: at(-30) },
  { id: 'ct-4', memberId: 'm-5', title: 'Designer — per asset', status: 'sent', at: at(-2) },
]

export const channels: ChatChannel[] = [
  { id: 'ch-1', name: 'general', kind: 'channel', memberIds: ['m-1', 'm-2', 'm-3', 'm-4', 'm-5'] },
  { id: 'ch-2', name: 'scripts', kind: 'channel', memberIds: ['m-1', 'm-2'] },
  { id: 'ch-3', name: 'editing', kind: 'channel', memberIds: ['m-1', 'm-3', 'm-4'] },
  { id: 'ch-4', name: 'Deniz Aksoy', kind: 'dm', memberIds: ['m-1', 'm-3'] },
  { id: 'ch-5', name: 'Mira Holt', kind: 'dm', memberIds: ['m-1', 'm-2'] },
]

export const messages: ChatMessage[] = [
  { id: 'msg-1', channelId: 'ch-1', authorId: 'm-1', body: 'Bermuda is live — 1.3M in 7 days. Same format for the next four.', at: at(-3, 9) },
  { id: 'msg-2', channelId: 'ch-1', authorId: 'm-2', body: 'Tristan script is in the Brain, 1,480 words, same structure.', at: at(-3, 10) },
  { id: 'msg-3', channelId: 'ch-1', authorId: 'm-3', body: 'On it. Rough cut by Friday.', at: at(-3, 11) },
  { id: 'msg-4', channelId: 'ch-2', authorId: 'm-2', body: 'Keeping the cold open under 12 seconds from now on — retention held better on Bermuda.', at: at(-2, 15) },
  { id: 'msg-5', channelId: 'ch-2', authorId: 'm-1', body: 'Agreed. Put that in the SOP so kloudie writes it that way by default.', at: at(-2, 16) },
  { id: 'msg-6', channelId: 'ch-3', authorId: 'm-3', body: 'B-roll pack for Curaçao is uploaded, 1.2GB.', at: at(-1, 12) },
  { id: 'msg-7', channelId: 'ch-4', authorId: 'm-3', body: 'Payout for KB-27 — can you schedule it for the 9th?', at: at(0, 8) },
  { id: 'msg-8', channelId: 'ch-4', authorId: 'm-1', body: 'Scheduled. Invoice will generate automatically.', at: at(0, 8) },
  { id: 'msg-9', channelId: 'ch-5', authorId: 'm-2', body: 'Guyana outline is up — want it at 1,500 words like the rest?', at: at(0, 9) },
]

export const inbox: InboxItem[] = [
  { id: 'i-1', kind: 'payout', title: 'Rea Okafor requested a payout', body: '$90.00 for KB-34 — Channel teardown carousel.', cardRef: 'KB-34', at: at(0, 8), read: false },
  { id: 'i-2', kind: 'approval', title: 'kloudie wants to create 3 cards', body: 'From "Q3 documentary slate" — Svalbard, Marshall Islands, Kerguelen.', cardRef: null, at: at(0, 7), read: false },
  { id: 'i-3', kind: 'mention', title: 'Mira Holt mentioned you in #scripts', body: '"@Sapro put that in the SOP so kloudie writes it that way by default."', cardRef: null, at: at(-2, 16), read: false },
  { id: 'i-4', kind: 'automation', title: 'Automation ran: Script ready → notify editor', body: 'KB-28 moved to Voiceover, Deniz Aksoy notified.', cardRef: 'KB-28', at: at(-1, 9), read: true },
  { id: 'i-5', kind: 'mention', title: 'Deniz Aksoy commented on KB-27', body: '"Rough cut at 11 min, trimming the intro."', cardRef: 'KB-27', at: at(-1, 16), read: true },
  { id: 'i-6', kind: 'automation', title: 'Weekly rollup is ready', body: '4 completed, 3 created, 6.2d median cycle time.', cardRef: null, at: at(-1, 6), read: true },
]

export const brain: BrainDoc[] = [
  {
    id: 'br-1', title: 'Bermuda — full transcript (competitor)', kind: 'transcript',
    source: 'youtube.com/watch?v=3HZHJ20UfYs', at: at(-14),
    body: 'This is Bermuda, a lonely rock in the middle of the ocean with no fresh water, no rivers, and virtually no natural resources. Completely surrounded by the open sea, it faces powerful storms from every direction. Yet Bermuda is one of the wealthiest places in the world, where more than 60,000 people enjoy one of the highest standards of living on the planet…',
  },
  {
    id: 'br-2', title: 'Channel voice & style SOP', kind: 'sop', source: 'Written by Sapro', at: at(-28),
    body: 'Cold open under 12 seconds. One concrete number in the first sentence. No rhetorical questions in the first minute. Second person sparingly. Sentence length alternates long/short. Never open with "Imagine".',
  },
  {
    id: 'br-3', title: 'Documentary script structure (1,500 words)', kind: 'note', source: 'Written by Mira Holt', at: at(-21),
    body: 'Hook (0:00–0:12) → Stakes (0:12–1:00) → Geography/context (1:00–3:00) → The turn (3:00–5:00) → Human consequence (5:00–7:00) → Resolution + forward look (7:00–8:00).',
  },
  {
    id: 'br-4', title: 'RPM benchmarks by niche', kind: 'note', source: 'Written by Sapro', at: at(-19),
    body: 'Travel documentary long-form: $8–14 US-weighted. True crime: $10–18. AI sci-fi story films: $4–9, high variance. Shorts: under $1 — not worth the slot.',
  },
  {
    id: 'br-5', title: 'Tristan da Cunha — research notes', kind: 'note', source: 'Written by Mira Holt', at: at(-11),
    body: 'Population 245. Nearest inhabited land is Saint Helena, 2,430 km. No airstrip — access is a six-day boat from Cape Town. Shared farmland, no outside land ownership permitted.',
  },
  {
    id: 'br-6', title: 'Impossible Travel — channel analytics export', kind: 'synced', source: 'YouTube Studio (synced)', at: at(-2),
    body: '861,331 views / 150,500 watch hours / +3,200 subscribers / $11,241.98 estimated revenue over the trailing 90 days. Median view duration 4:12 on 14-minute uploads.',
  },
]

export const creations: Creation[] = [
  { id: 'cr-1', title: 'Bermuda voiceover — Steve, Multilingual v2', module: 'tts', body: '8:04 · 44.1kHz mp3 · 2,712 characters', credits: 271, at: at(-6) },
  { id: 'cr-2', title: 'Tristan da Cunha script (1,480 words)', module: 'script', body: 'Long-form documentary script in channel voice, raw text, no headings.', credits: 140, at: at(-4) },
  { id: 'cr-3', title: 'Bermuda thumbnail concepts (4)', module: 'image', body: '1280×720 · high contrast · arrow + circle treatment', credits: 96, at: at(-5) },
  { id: 'cr-4', title: 'Ocean ambience bed — 3:00 loop', module: 'music', body: 'Ambient, low tension, no percussion', credits: 60, at: at(-5) },
  { id: 'cr-5', title: 'Thread: the 8-step faceless pipeline', module: 'social', body: '9 posts, X format, hook-first', credits: 38, at: at(-3) },
  { id: 'cr-6', title: 'Wind + gull transition SFX', module: 'sfx', body: '6 variations · 2s each', credits: 24, at: at(-2) },
]

export const automations: Automation[] = [
  { id: 'au-1', name: 'Script ready → notify editor', trigger: 'Card moves to Voiceover', action: 'DM the assigned editor and post in #editing', enabled: true, runs: 34 },
  { id: 'au-2', name: 'Published → pay the editor', trigger: 'Card moves to Published', action: 'Schedule the card payout and generate the invoice', enabled: true, runs: 21 },
  { id: 'au-3', name: 'Weekly rollup', trigger: 'Every Monday 06:00', action: 'Post board KPIs to Inbox and #general', enabled: true, runs: 12 },
  { id: 'au-4', name: 'Competitor watch', trigger: 'Every Sunday 18:00', action: 'Scan tracked channels, save 2x+ outliers to Brain', enabled: true, runs: 9 },
  { id: 'au-5', name: 'Stale card nudge', trigger: 'Card sits in a stage 5+ days', action: 'Comment on the card and mention the assignee', enabled: false, runs: 3 },
]

export const competitors: Competitor[] = [
  { id: 'co-1', handle: '@ImpossibleTravel', platform: 'YouTube', subs: 19_800, outlier: 10.4, niche: 'Extreme travel documentary' },
  { id: 'co-2', handle: '@NebulaProphecy', platform: 'YouTube', subs: 74_500, outlier: 6.1, niche: 'AI sci-fi story films' },
  { id: 'co-3', handle: '@LilianaTheSurvivor', platform: 'YouTube', subs: 8_100, outlier: 4.8, niche: 'Nomad survival travel docs' },
  { id: 'co-4', handle: '@deadenddocs', platform: 'YouTube', subs: 46_800, outlier: 3.2, niche: 'True crime / bodycam docs' },
  { id: 'co-5', handle: '@topunrealplanet', platform: 'YouTube', subs: 1_240, outlier: 2.7, niche: 'Extreme travel documentary' },
]

/**
 * Trailing-90-day channel totals. Every KPI tile derives from this one object
 * so views, revenue and RPM can never drift apart. Figures match the channel
 * shown in the source recording.
 */
export const channel90d = {
  views: 861_331,
  watchHours: 150_500,
  revenueCents: 1_124_198,
}

/** Top content *within the 90-day window* — a subset of the channel totals. */
export const videoStats: VideoStat[] = [
  { id: 'v-1', title: 'How People Live in Bermuda', platform: 'YouTube', views: 402_000, watchHours: 19_300, rpm: 5.72, revenueCents: 229_944, publishedAt: at(-7) },
  { id: 'v-2', title: 'Bermuda Part II: The Insurance Capital', platform: 'YouTube', views: 188_000, watchHours: 9_100, rpm: 9.10, revenueCents: 171_080, publishedAt: at(-9) },
  { id: 'v-3', title: 'The Island With No Airport', platform: 'YouTube', views: 121_000, watchHours: 5_900, rpm: 11.40, revenueCents: 137_940, publishedAt: at(-21) },
  { id: 'v-4', title: 'Why Nobody Lives in Kerguelen', platform: 'YouTube', views: 74_400, watchHours: 3_500, rpm: 8.30, revenueCents: 61_752, publishedAt: at(-34) },
  { id: 'v-5', title: '8-step faceless pipeline', platform: 'Instagram', views: 41_200, watchHours: 640, rpm: 1.10, revenueCents: 4_532, publishedAt: at(-4) },
]

/**
 * 90 days of daily views, shaped like the chart in the source recording — a
 * rising baseline with two viral bumps. Normalised so the series sums to
 * exactly `channel90d.views`, keeping the chart and the KPI tile in agreement.
 */
export const viewsSeries: { date: string; views: number }[] = (() => {
  // Gaussian bumps rather than single-day spikes: a video going viral lifts a
  // week, not one point.
  const bump = (i: number, centre: number, height: number, width: number) =>
    height * Math.exp(-((i - centre) ** 2) / (2 * width ** 2))

  const raw = Array.from({ length: 90 }, (_, i) => {
    const base = 5_200 + i * 92
    const wave = Math.sin(i / 4.5) * 1_100 + Math.sin(i / 11) * 1_900
    const viral = bump(i, 31, 15_500, 3.4) + bump(i, 55, 5_200, 2.6) + bump(i, 84, 21_000, 3.1)
    return Math.max(900, base + wave + viral)
  })

  const scale = channel90d.views / raw.reduce((a, v) => a + v, 0)
  return raw.map((v, i) => ({
    date: new Date(now - (89 - i) * DAY).toISOString().slice(0, 10),
    views: Math.round(v * scale),
  }))
})()

export const conversations: Conversation[] = [
  {
    id: 'cv-1', title: 'Generate a similar script to the transcript', at: at(-4),
    messages: [
      {
        id: 'am-1', role: 'user', at: at(-4),
        body: 'Generate me a similar script to the transcript I\'ll attach. It\'s one of my best performing previous videos — use the same voice, style and information.\n\nDo not use any brain context, just generate the script purely based on the transcript provided.\n\nKeep the same structure. Make it 1500 words. Output raw text only, no headings or brackets.',
      },
      {
        id: 'am-2', role: 'agent', at: at(-4),
        body: 'Done — 1,480 words, raw text, same six-beat structure as the Bermuda transcript. I matched the cold open length (11 seconds of read time) and kept the "one concrete number in the first sentence" pattern.\n\nSaved to Library as "Tristan da Cunha script (1,480 words)".',
      },
    ],
  },
  {
    id: 'cv-2', title: 'Scan our niche for viral faceless channels', at: at(-6),
    messages: [
      { id: 'am-3', role: 'user', at: at(-6), body: 'Scan the niche for faceless long-form channels under 100k subs, started in the last 1–4 months, with a viral video over 200k views.' },
      { id: 'am-4', role: 'agent', at: at(-6), body: 'Found 5 that clear every filter. Two are directly in our lane — @topunrealplanet (1.2k subs, 2.7x outlier) is running our exact format, which is the signal worth acting on: a small channel breaking in means the niche is still open.\n\nAll five are now tracked in Competitors.' },
    ],
  },
  { id: 'cv-3', title: 'Clean up the boards by finished state', at: at(-8), messages: [] },
  { id: 'cv-4', title: 'Analyse my YouTube for the last 90 days', at: at(-10), messages: [] },
  { id: 'cv-5', title: 'Draft the freelancer onboarding contract', at: at(-13), messages: [] },
]

export const CREDITS_START = 64_653
