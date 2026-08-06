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
  { id: 'multilingual-v2', name: 'Multilingual v2', hint: 'The most expressive' },
  { id: 'turbo-v2.5', name: 'Turbo v2.5', hint: 'Fast, high quality' },
]

const PLACEHOLDER: Record<PlaygroundModuleId, string> = {
  tts: 'Paste your script. This is Bermuda, a lonely rock in the middle of the ocean with no fresh water, no rivers, and virtually no natural resources…',
  sfx: 'Describe the sound. Wind across an empty coastline, distant gulls, two seconds.',
  music: 'Describe the bed. Ambient, low tension, no percussion, three minutes, loopable.',
  image: 'Describe the image. High-contrast YouTube thumbnail, aerial island, arrow and circle treatment, 1280×720.',
  script: 'Describe the script. A 1,500-word documentary about Tristan da Cunha, in my channel voice, raw text only.',
  social: 'Describe the posts. Turn my latest upload into a nine-post X thread, hook first.',
}

export default function Playground() {
  const { creations, credits, spendCredits, addCreation } = useStore()
  const [module, setModule] = useState<PlaygroundModuleId>('tts')
  const [text, setText] = useState('')
  const [voice, setVoice] = useState(VOICES[0])
  const [model, setModel] = useState(MODELS[0].id)
  const [speed, setSpeed] = useState(1)
  const [stability, setStability] = useState(0.5)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const meta = MODULE_META[module]
  const cost =
    module === 'tts' ? Math.max(1, Math.ceil(text.length / 10)) : CREDIT_COST[module]
  const affordable = credits >= cost && text.trim().length > 0

  const history = creations.filter((c) => c.module === module)

  async function generate() {
    if (!affordable || busy) return
    setBusy(true)
    setResult(null)
    await new Promise((r) => setTimeout(r, 900))

    const title =
      text.trim().slice(0, 60) + (text.trim().length > 60 ? '…' : '')
    const body =
      module === 'tts'
        ? `${Math.max(1, Math.round(text.length / 900))}:${String(
            Math.round((text.length % 900) / 15),
          ).padStart(2, '0')} · ${voice.split(' — ')[0]} · ${
            MODELS.find((m) => m.id === model)?.name
          } · ${text.length} characters`
        : `${meta.label} output · ${text.trim().split(/\s+/).length} words of prompt`

    addCreation({ title, module, body, credits: cost })
    spendCredits(cost)
    setResult(body)
    setBusy(false)
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
                  onClick={() => void generate()}
                >
                  <Sparkles size={13} />
                  {busy ? 'Generating…' : 'Generate'}
                </Button>
              </div>
            </Panel>

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
