import { useState } from 'react'
import { Play, Sparkles } from 'lucide-react'
import { useStore, CREDIT_COST } from '../../lib/store'
import { relative } from '../../lib/format'
import { Badge, Button, Panel, cx } from '../../components/ui'
import { MODULE_META } from './Library'
import type { PlaygroundModuleId } from '../../lib/types'

const GROUPS: { label: string; modules: PlaygroundModuleId[] }[] = [
  { label: 'Audio', modules: ['tts', 'sfx', 'music'] },
  // Video generation is deliberately absent — see README, "What was excluded".
  { label: 'Visuals', modules: ['image'] },
  { label: 'Writing', modules: ['script', 'social'] },
]

const VOICES = [
  'Steve — Deep & Authoritative',
  'Marguerite — Warm Documentary',
  'Jonas — Neutral Narrator',
  'Aria — Bright & Conversational',
]

const MODELS = [
  { id: 'multilingual-v2', name: 'Eleven Multilingual v2', hint: 'The most expressive Text to Speech' },
  { id: 'turbo-v2.5', name: 'Eleven Turbo v2.5', hint: 'Fast, high quality' },
]

/**
 * Prompt starters, verified in-app. They do more work than they look like:
 * they teach the module's grammar without documentation, and they seed the
 * empty state with the vocabulary of the niche.
 */
const STARTERS: Record<PlaygroundModuleId, string[]> = {
  tts: ['Faceless video narration', 'Short-form hook', 'Video call to action', 'Documentary style', 'Podcast intro'],
  sfx: ['Whoosh transition', 'Rain on a tent', 'Retro game power-up', 'Crowd cheering in a stadium', 'Cinematic impact hit'],
  music: ['Lofi study beat', 'Epic orchestral trailer', 'Warm acoustic folk', 'Synthwave night drive', 'Ambient meditation pad'],
  image: ['High-contrast thumbnail', 'Aerial island establishing shot', 'Arrow and circle treatment'],
  script: ['Faceless YouTube video', '60-second reel from my niche', 'Remake my best performer', 'Talking-head tutorial'],
  social: ['Repurpose my latest video', 'Thread in my niche', 'Behind-the-scenes post', 'Audience question post'],
}

/** Per-model pricing shown at the point of choice, as the original does. */
const IMAGE_MODELS = [
  { id: 'nb2', name: 'Nano Banana 2', credits: 48 },
  { id: 'nb-pro', name: 'Nano Banana Pro', credits: 96 },
]

const SOCIAL_PLATFORMS = ['X', 'LinkedIn', 'Instagram', 'TikTok', 'YouTube']

const PLACEHOLDER: Record<PlaygroundModuleId, string> = {
  tts: 'Paste your script. This is Bermuda, a lonely rock in the middle of the ocean with no fresh water, no rivers, and virtually no natural resources…',
  sfx: 'Describe the sound. Wind across an empty coastline, distant gulls, two seconds.',
  music: 'Describe the bed. Ambient, low tension, no percussion, three minutes, loopable.',
  image: 'Describe the image. High-contrast YouTube thumbnail, aerial island, arrow and circle treatment, 1280×720.',
  script: 'Describe the script. A 1,500-word documentary about Tristan da Cunha, in my channel voice, raw text only.',
  social: 'Describe the posts. Turn my latest upload into a nine-post X thread, hook first.',
}

export default function Playground() {
  const { creations, credits, generate } = useStore()
  const [module, setModule] = useState<PlaygroundModuleId>('tts')
  const [text, setText] = useState('')
  const [voice, setVoice] = useState(VOICES[0])
  const [model, setModel] = useState(MODELS[0].id)
  const [speed, setSpeed] = useState(1)
  const [stability, setStability] = useState(0.5)
  const [similarity, setSimilarity] = useState(0.75)
  const [style, setStyle] = useState(0)
  const [imageModel, setImageModel] = useState(IMAGE_MODELS[0].id)
  const [seconds, setSeconds] = useState(3)
  const [groundOnBrain, setGroundOnBrain] = useState(true)
  const [platforms, setPlatforms] = useState<string[]>(['X', 'LinkedIn'])
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const meta = MODULE_META[module]
  const cost =
    module === 'tts'
      ? Math.max(1, Math.ceil(text.length / 10))
      : module === 'image'
        ? (IMAGE_MODELS.find((m) => m.id === imageModel)?.credits ?? 48)
        : CREDIT_COST[module]
  const affordable = credits >= cost && text.trim().length > 0

  const history = creations.filter((c) => c.module === module)

  async function run() {
    if (!affordable || busy) return
    setBusy(true)
    setResult(null)
    setErr(null)
    try {
      const out = await generate({
        module,
        prompt: text,
        settings: { voice, model, speed, stability, similarity, style, imageModel, seconds, groundOnBrain, platforms },
      })
      setResult(out.body)
    } catch (e) {
      // Audio and image modules need a paid provider key. Say so plainly
      // rather than inventing a result.
      setErr(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full">
      <nav
        aria-label="Playground modules"
        className="w-52 shrink-0 overflow-y-auto border-r border-line bg-white p-2"
      >
        <h1 className="px-2 py-2 text-[15px] font-semibold">Playground</h1>
        {GROUPS.map((g) => (
          <div key={g.label} className="mb-3">
            <h2 className="px-2 py-1 text-[10px] font-semibold tracking-wide text-subtle uppercase">
              {g.label}
            </h2>
            <ul>
              {g.modules.map((id) => {
                const m = MODULE_META[id]
                return (
                  <li key={id}>
                    <button
                      onClick={() => {
                        setModule(id)
                        setResult(null)
                      }}
                      className={cx(
                        'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px]',
                        id === module
                          ? 'bg-zinc-100 font-medium text-ink'
                          : 'text-subtle hover:bg-zinc-50 hover:text-ink',
                      )}
                    >
                      <m.Icon size={14} strokeWidth={1.8} />
                      {m.label}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
        <p className="mt-auto rounded-lg bg-zinc-50 px-2.5 py-2 text-center text-[11px] font-medium text-subtle">
          {credits.toLocaleString()} credits
        </p>
      </nav>

      <div className="min-w-0 flex-1 overflow-y-auto p-5">
        <div className="mx-auto grid max-w-4xl gap-4 lg:grid-cols-[1fr_260px]">
          <div className="space-y-4">
            <Panel
              title={meta.label}
              action={<Badge tone="blue">{cost} credits</Badge>}
              bodyClassName="p-0"
            >
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={PLACEHOLDER[module]}
                aria-label={`${meta.label} prompt`}
                maxLength={module === 'tts' ? 5000 : 2000}
                className="min-h-64 w-full resize-y bg-transparent p-4 text-[13px] leading-relaxed outline-none placeholder:text-subtle"
              />
              <div className="flex items-center gap-3 border-t border-line px-4 py-2.5">
                <span className="text-[11px] text-subtle tabular-nums">
                  {text.length.toLocaleString()} / {module === 'tts' ? '5,000' : '2,000'}{' '}
                  characters
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  className="ml-auto"
                  disabled={!affordable || busy}
                  onClick={() => void run()}
                >
                  <Sparkles size={13} />
                  {busy ? 'Generating…' : module === 'tts' ? 'Generate speech' : 'Generate'}
                </Button>
              </div>
            </Panel>

            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-subtle">Get started with</span>
              {STARTERS[module].map((chip) => (
                <button
                  key={chip}
                  onClick={() => setText((t) => (t ? `${t} ${chip}` : chip))}
                  className="rounded-full border border-line bg-white px-2.5 py-1 text-[11px] text-subtle transition-colors hover:border-brand hover:text-brand"
                >
                  {chip}
                </button>
              ))}
            </div>

            {err && (
              <Panel title="Not available yet" className="kb-in">
                <p className="text-[12.5px] text-ink">{err}</p>
              </Panel>
            )}

            {result && (
              <Panel title="Result" className="kb-in">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand text-white">
                    <Play size={14} fill="currentColor" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium">Generated</p>
                    <p className="text-[11px] text-subtle">{result}</p>
                  </div>
                  <Badge tone="green">Saved to Library</Badge>
                </div>
                <div className="mt-3 flex h-8 items-end gap-0.5" aria-hidden>
                  {Array.from({ length: 64 }, (_, i) => (
                    <span
                      key={i}
                      className="flex-1 rounded-full bg-brand/30"
                      style={{ height: `${18 + Math.abs(Math.sin(i / 3.1)) * 78}%` }}
                    />
                  ))}
                </div>
              </Panel>
            )}
          </div>

          <div className="space-y-4">
            {module === 'tts' && (
              <Panel title="Settings">
                <label className="mb-3 block">
                  <span className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
                    Voice
                  </span>
                  <select
                    value={voice}
                    onChange={(e) => setVoice(e.target.value)}
                    className="w-full rounded-lg border border-line px-2 py-1.5 text-[12px]"
                  >
                    {VOICES.map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                </label>

                <fieldset className="mb-3">
                  <legend className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
                    Model
                  </legend>
                  <div className="space-y-1.5">
                    {MODELS.map((m) => (
                      <label
                        key={m.id}
                        className={cx(
                          'flex cursor-pointer items-start gap-2 rounded-lg border p-2',
                          model === m.id ? 'border-brand bg-brand-soft/50' : 'border-line',
                        )}
                      >
                        <input
                          type="radio"
                          name="model"
                          checked={model === m.id}
                          onChange={() => setModel(m.id)}
                          className="mt-0.5 accent-[var(--color-brand)]"
                        />
                        <span>
                          <span className="block text-[12px] font-medium">{m.name}</span>
                          <span className="block text-[11px] text-subtle">{m.hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>

                <Slider label="Speed" min="Slower" max="Faster" value={speed} onChange={setSpeed} lo={0.5} hi={1.5} step={0.05} />
                <Slider label="Stability" min="More variable" max="More stable" value={stability} onChange={setStability} lo={0} hi={1} step={0.05} />
                <Slider label="Similarity" min="Low" max="High" value={similarity} onChange={setSimilarity} lo={0} hi={1} step={0.05} />
                <Slider label="Style Exaggeration" min="None" max="Exaggerated" value={style} onChange={setStyle} lo={0} hi={1} step={0.05} />
              </Panel>
            )}

            {(module === 'sfx' || module === 'music') && (
              <Panel title="Settings">
                <Slider
                  label={module === 'sfx' ? 'Duration' : 'Length'}
                  min="0:01"
                  max={module === 'sfx' ? '0:22' : '5:00'}
                  value={seconds}
                  onChange={setSeconds}
                  lo={1}
                  hi={module === 'sfx' ? 22 : 300}
                  step={1}
                />
                <p className="text-[11px] text-subtle tabular-nums">
                  {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
                </p>
              </Panel>
            )}

            {module === 'image' && (
              <Panel title="Settings">
                <fieldset>
                  <legend className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
                    Model
                  </legend>
                  <div className="space-y-1.5">
                    {IMAGE_MODELS.map((m) => (
                      <label
                        key={m.id}
                        className={cx(
                          'flex cursor-pointer items-center gap-2 rounded-lg border p-2',
                          imageModel === m.id ? 'border-brand bg-brand-soft/50' : 'border-line',
                        )}
                      >
                        <input
                          type="radio"
                          name="imageModel"
                          checked={imageModel === m.id}
                          onChange={() => setImageModel(m.id)}
                          className="accent-[var(--color-brand)]"
                        />
                        <span className="flex-1 text-[12px] font-medium">{m.name}</span>
                        <Badge>{m.credits} cr</Badge>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </Panel>
            )}

            {module === 'script' && (
              <Panel title="Settings">
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    checked={groundOnBrain}
                    onChange={() => setGroundOnBrain((v) => !v)}
                    className="mt-0.5 h-3.5 w-3.5 accent-[var(--color-brand)]"
                  />
                  <span>
                    <span className="block text-[12px] font-medium">
                      Ground on workspace Brain
                    </span>
                    <span className="mt-0.5 block text-[11px] text-subtle">
                      Scripts pick up your voice, your audience, and what you have
                      already published.
                    </span>
                  </span>
                </label>
              </Panel>
            )}

            {module === 'social' && (
              <Panel title="Settings">
                <fieldset>
                  <legend className="mb-1.5 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
                    Platforms
                  </legend>
                  <div className="space-y-1">
                    {SOCIAL_PLATFORMS.map((pf) => (
                      <label key={pf} className="flex cursor-pointer items-center gap-2 text-[12px]">
                        <input
                          type="checkbox"
                          checked={platforms.includes(pf)}
                          onChange={() =>
                            setPlatforms((v) =>
                              v.includes(pf) ? v.filter((x) => x !== pf) : [...v, pf],
                            )
                          }
                          className="h-3.5 w-3.5 accent-[var(--color-brand)]"
                        />
                        {pf}
                      </label>
                    ))}
                  </div>
                  <p className="mt-2 text-[11px] text-subtle">
                    Each platform gets its own version.
                  </p>
                </fieldset>
              </Panel>
            )}

            <Panel title="History" bodyClassName="p-0">
              {history.length === 0 ? (
                <p className="px-4 py-6 text-center text-[12px] text-subtle">
                  Nothing generated yet.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {history.slice(0, 8).map((c) => (
                    <li key={c.id} className="px-3 py-2">
                      <p className="truncate text-[12px] font-medium">{c.title}</p>
                      <p className="text-[10px] text-subtle">
                        {c.credits} cr · {relative(c.at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      </div>
    </div>
  )
}

function Slider({
  label,
  min,
  max,
  value,
  onChange,
  lo,
  hi,
  step,
}: {
  label: string
  min: string
  max: string
  value: number
  onChange: (n: number) => void
  lo: number
  hi: number
  step: number
}) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">
        {label}
      </span>
      <input
        type="range"
        min={lo}
        max={hi}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--color-brand)]"
      />
      <span className="flex justify-between text-[10px] text-subtle">
        <span>{min}</span>
        <span>{max}</span>
      </span>
    </label>
  )
}
