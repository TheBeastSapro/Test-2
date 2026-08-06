import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  MessageCircleWarning,
  Pause,
  Pencil,
  Play,
  Trash2,
  X,
} from 'lucide-react'
import { useStore } from '../lib/store'
import { member, relative } from '../lib/format'
import {
  Avatar,
  Badge,
  Button,
  Empty,
  PageHeader,
  Panel,
  cx,
} from '../components/ui'
import type {
  ReviewAsset,
  ReviewComment,
  ReviewRegion,
  ReviewTool,
} from '../lib/types'

/** The tool palette the real product ships, minus plain select. */
const TOOLS: { id: ReviewTool; label: string; glyph: string }[] = [
  { id: 'pin', label: 'Pin', glyph: '◎' },
  { id: 'arrow', label: 'Arrow', glyph: '↗' },
  { id: 'line', label: 'Line', glyph: '╱' },
  { id: 'rect', label: 'Rectangle', glyph: '▭' },
  { id: 'draw', label: 'Freehand', glyph: '✎' },
]

const SPEEDS = [0.5, 1, 1.5, 2]

/**
 * The Frame.io-style review module.
 *
 * The whole point of frame-accurate review is that a note is worthless unless
 * it says *where*. So every comment is anchored to an exact frame, and
 * optionally to a rectangle on that frame — the marker on the timeline, the
 * seek target when you click it, and the overlay that appears when playback
 * reaches it are all the same anchor.
 */

const STATUS_TONE: Record<ReviewAsset['status'], 'blue' | 'green' | 'amber'> = {
  'in review': 'blue',
  approved: 'green',
  'changes requested': 'amber',
}

/** SMPTE-style HH:MM:SS:FF — frames, not milliseconds, is the unit editors use. */
function timecode(sec: number, fps: number) {
  const total = Math.max(0, Math.round(sec * fps))
  const f = total % fps
  const s = Math.floor(total / fps) % 60
  const m = Math.floor(total / (fps * 60)) % 60
  const h = Math.floor(total / (fps * 3600))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${h > 0 ? `${pad(h)}:` : ''}${pad(m)}:${pad(s)}:${pad(f)}`
}

export default function Review() {
  const {
    reviewAssets,
    reviewComments,
    cards,
    addReviewComment,
    toggleReviewComment,
    deleteReviewComment,
    setReviewStatus,
    addComment,
    addInboxItem,
  } = useStore()

  const [params, setParams] = useSearchParams()
  const videoRef = useRef<HTMLVideoElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)

  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [draft, setDraft] = useState('')
  /** Drawing mode: the next drag on the frame becomes the comment's region. */
  const [tool, setTool] = useState<ReviewTool | null>(null)
  const [rate, setRate] = useState(1)
  const [pending, setPending] = useState<ReviewRegion | null>(null)
  const [dragFrom, setDragFrom] = useState<{ x: number; y: number } | null>(null)
  const [showResolved, setShowResolved] = useState(false)

  const asset =
    reviewAssets.find((a) => a.id === params.get('asset')) ?? reviewAssets[0]

  const comments = useMemo(
    () =>
      reviewComments
        .filter((c) => c.assetId === asset?.id)
        .sort((a, b) => a.timecodeSec - b.timecodeSec),
    [reviewComments, asset?.id],
  )

  const visible = showResolved ? comments : comments.filter((c) => !c.resolved)
  const open = comments.filter((c) => !c.resolved).length

  // Versions of the same deliverable, newest last.
  const versions = useMemo(
    () =>
      asset
        ? reviewAssets
            .filter((a) => a.cardId === asset.cardId && a.title === asset.title)
            .sort((a, b) => a.version - b.version)
        : [],
    [reviewAssets, asset],
  )

  const seek = useCallback((sec: number) => {
    const v = videoRef.current
    if (!v) return
    v.currentTime = Math.max(0, Math.min(sec, v.duration || sec))
    setTime(v.currentTime)
  }, [])

  const step = useCallback(
    (frames: number) => {
      if (!asset) return
      const v = videoRef.current
      if (!v) return
      v.pause()
      seek(v.currentTime + frames / asset.fps)
    },
    [asset, seek],
  )

  // Reset transport state when switching cut.
  useEffect(() => {
    setTime(0)
    setPlaying(false)
    setPending(null)
    setTool(null)
  }, [asset?.id])

  // J/K/L-adjacent shortcuts. Editors expect arrows to step frames.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable) return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        step(e.shiftKey ? -asset!.fps : -1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        step(e.shiftKey ? asset!.fps : 1)
      } else if (e.key === ' ') {
        e.preventDefault()
        const v = videoRef.current
        if (!v) return
        v.paused ? void v.play() : v.pause()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, asset])

  if (!asset) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <PageHeader title="Review" />
        <Panel>
          <Empty title="Nothing in review" hint="Attach a cut to a card to start a review." />
        </Panel>
      </div>
    )
  }

  const card = cards.find((c) => c.id === asset.cardId)

  const pointFrom = (e: React.PointerEvent) => {
    const r = stageRef.current!.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body = draft.trim()
    if (!body) return
    addReviewComment({
      assetId: asset.id,
      authorId: 'm-1',
      timecodeSec: time,
      body,
      region: pending,
    })
    setDraft('')
    setPending(null)
    setTool(null)
  }

  const decide = (status: 'approved' | 'changes requested') => {
    setReviewStatus(asset.id, status)
    const label = `${asset.title} v${asset.version}`
    if (card) {
      addComment(
        card.id,
        status === 'approved'
          ? `${label} approved in Review.`
          : `Changes requested on ${label} — ${open} open note${open === 1 ? '' : 's'}.`,
      )
    }
    addInboxItem({
      kind: 'review',
      title:
        status === 'approved'
          ? `${label} approved`
          : `Changes requested on ${label}`,
      body:
        status === 'approved'
          ? 'Ready to publish.'
          : `${open} open note${open === 1 ? '' : 's'} on the timeline.`,
      cardRef: card?.ref ?? null,
    })
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col p-5">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-[18px] font-semibold tracking-tight">
              {asset.title}
            </h1>
            <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-subtle">
              <Badge tone={STATUS_TONE[asset.status]}>{asset.status}</Badge>
              <span>
                Uploaded by {member(asset.uploadedBy).name} · {relative(asset.at)}
              </span>
              {card && (
                <Link
                  to={`/boards/${card.boardId}?card=${card.id}`}
                  className="font-medium text-brand hover:underline"
                >
                  {card.ref}
                </Link>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {versions.map((v) => (
              <Button
                key={v.id}
                size="sm"
                variant={v.id === asset.id ? 'primary' : 'default'}
                onClick={() => setParams({ asset: v.id })}
              >
                v{v.version}
              </Button>
            ))}
          </div>
        </div>

        {/* Stage */}
        <div
          ref={stageRef}
          onPointerDown={(e) => {
            if (!tool) return
            e.currentTarget.setPointerCapture(e.pointerId)
            const p = pointFrom(e)
            setDragFrom(p)
            setPending(
              tool === 'draw'
                ? { tool, x: p.x, y: p.y, w: 0, h: 0, points: [p] }
                : { tool, x: p.x, y: p.y, w: 0, h: 0 },
            )
            // A pin is a single click, so it is complete on press.
            if (tool === 'pin') setDragFrom(null)
          }}
          onPointerMove={(e) => {
            if (!tool || !dragFrom) return
            const p = pointFrom(e)
            if (tool === 'draw') {
              setPending((r) =>
                r ? { ...r, points: [...(r.points ?? []), p] } : r,
              )
              return
            }
            if (tool === 'arrow' || tool === 'line') {
              // Direction matters, so keep the raw delta rather than normalising.
              setPending({ tool, x: dragFrom.x, y: dragFrom.y, w: p.x - dragFrom.x, h: p.y - dragFrom.y })
              return
            }
            setPending({
              tool,
              x: Math.min(dragFrom.x, p.x),
              y: Math.min(dragFrom.y, p.y),
              w: Math.abs(p.x - dragFrom.x),
              h: Math.abs(p.y - dragFrom.y),
            })
          }}
          onPointerUp={() => setDragFrom(null)}
          className={cx(
            'relative aspect-video w-full overflow-hidden rounded-xl bg-black select-none',
            tool && 'cursor-crosshair',
          )}
        >
          {/*
            Two encodes, because one is not portable. H.264 is what Safari and
            most Chrome builds want; Chromium builds without proprietary codecs
            (including the one CI drives) can only play VP9. The browser picks.
            `key` forces a reload of the <source> list when the cut changes —
            React will not re-run source selection on its own.
          */}
          <video
            key={asset.id}
            ref={videoRef}
            playsInline
            preload="auto"
            className="h-full w-full"
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={() => {
              if (tool) return
              const v = videoRef.current!
              v.paused ? void v.play() : v.pause()
            }}
          >
            <source src={`${asset.src}.mp4`} type="video/mp4" />
            <source src={`${asset.src}.webm`} type="video/webm" />
          </video>

          {/* Regions of notes near the playhead, plus the one being drawn. */}
          {visible
            .filter((c) => c.region && Math.abs(c.timecodeSec - time) < 0.6)
            .map((c) => (
              <Region key={c.id} region={c.region!} label={member(c.authorId).initials} />
            ))}
          {pending && <Region region={pending} pendingLabel />}

          {tool && !pending && (
            <p className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-[12px] font-medium text-white/90">
              {tool === 'pin'
                ? 'Click the frame to drop a pin'
                : 'Drag on the frame to mark it'}
            </p>
          )}
        </div>

        {/* Transport */}
        <div className="mt-3">
          <Timeline
            duration={asset.durationSec}
            time={time}
            comments={visible}
            fps={asset.fps}
            onSeek={seek}
          />

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => step(-1)} aria-label="Previous frame">
              <ChevronLeft size={14} />
            </Button>
            <Button
              size="sm"
              variant="primary"
              aria-label={playing ? 'Pause' : 'Play'}
              onClick={() => {
                const v = videoRef.current!
                v.paused ? void v.play() : v.pause()
              }}
            >
              {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" />}
            </Button>
            <Button size="sm" onClick={() => step(1)} aria-label="Next frame">
              <ChevronRight size={14} />
            </Button>

            <span
              className="ml-1 rounded-md bg-zinc-100 px-2 py-1 font-mono text-[12px] tabular-nums"
              aria-label="Current timecode"
            >
              {timecode(time, asset.fps)}
            </span>
            <span className="text-[11px] text-subtle">
              / {timecode(asset.durationSec, asset.fps)} · {asset.fps} fps
            </span>

            <span className="ml-auto flex items-center gap-1.5">
              <span className="flex items-center gap-0.5 rounded-lg border border-line p-0.5">
                <span className="px-1.5 text-[11px] text-subtle">Annotate</span>
                {TOOLS.map((t) => (
                  <button
                    key={t.id}
                    title={t.label}
                    aria-label={t.label}
                    aria-pressed={tool === t.id}
                    onClick={() => {
                      setTool((cur) => (cur === t.id ? null : t.id))
                      setPending(null)
                    }}
                    className={cx(
                      'grid h-6 w-6 place-items-center rounded text-[13px] transition-colors',
                      tool === t.id
                        ? 'bg-brand text-white'
                        : 'text-subtle hover:bg-zinc-100 hover:text-ink',
                    )}
                  >
                    {t.glyph}
                  </button>
                ))}
                <button
                  title="Undo mark"
                  aria-label="Undo mark"
                  disabled={!pending}
                  onClick={() => setPending(null)}
                  className="grid h-6 w-6 place-items-center rounded text-[13px] text-subtle hover:bg-zinc-100 hover:text-ink disabled:opacity-40"
                >
                  ↶
                </button>
              </span>

              <label className="flex items-center gap-1 text-[11px] text-subtle">
                <span className="sr-only">Playback speed</span>
                <select
                  value={rate}
                  onChange={(e) => {
                    const r = Number(e.target.value)
                    setRate(r)
                    if (videoRef.current) videoRef.current.playbackRate = r
                  }}
                  className="rounded-md border border-line px-1.5 py-1 text-[11px]"
                >
                  {SPEEDS.map((r) => (
                    <option key={r} value={r}>
                      {r}x
                    </option>
                  ))}
                </select>
              </label>
              <Button size="sm" variant="primary" onClick={() => decide('approved')}>
                <Check size={13} />
                Approve
              </Button>
              <Button size="sm" onClick={() => decide('changes requested')}>
                <MessageCircleWarning size={13} />
                Request changes
              </Button>
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-subtle">
            ← → step one frame · shift + ← → one second · space plays
          </p>
        </div>
      </div>

      {/* Notes rail */}
      <aside className="flex w-80 shrink-0 flex-col border-l border-line bg-white">
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <h2 className="text-[13px] font-semibold">Notes</h2>
          <Badge tone={open ? 'amber' : 'green'}>{open} open</Badge>
          <button
            onClick={() => setShowResolved((v) => !v)}
            className="ml-auto text-[11px] font-medium text-subtle hover:text-ink"
          >
            {showResolved ? 'Hide resolved' : 'Show resolved'}
          </button>
        </header>

        <ul className="min-h-0 flex-1 divide-y divide-line overflow-y-auto">
          {visible.length === 0 && (
            <li className="px-4 py-8 text-center text-[12px] text-subtle">
              No open notes on this cut.
            </li>
          )}
          {visible.map((c) => (
            <li key={c.id} className={cx('px-3 py-2.5', c.resolved && 'opacity-55')}>
              <div className="flex items-start gap-2">
                <Avatar id={c.authorId} size={24} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 text-[11px]">
                    <span className="font-semibold">{member(c.authorId).name}</span>
                    <button
                      onClick={() => seek(c.timecodeSec)}
                      className="rounded bg-brand-soft px-1 font-mono font-medium text-brand tabular-nums hover:underline"
                    >
                      {timecode(c.timecodeSec, asset.fps)}
                    </button>
                    {c.region && <Pencil size={10} className="text-subtle" />}
                  </p>
                  <p className={cx('mt-0.5 text-[12.5px]', c.resolved && 'line-through')}>
                    {c.body}
                  </p>
                  <p className="mt-0.5 text-[10px] text-subtle">{relative(c.at)}</p>
                </div>
                <div className="flex shrink-0 flex-col gap-0.5">
                  <button
                    onClick={() => toggleReviewComment(c.id)}
                    aria-label={c.resolved ? 'Reopen note' : 'Resolve note'}
                    title={c.resolved ? 'Reopen' : 'Resolve'}
                    className={cx(
                      'grid h-6 w-6 place-items-center rounded hover:bg-zinc-100',
                      c.resolved ? 'text-emerald-600' : 'text-subtle',
                    )}
                  >
                    <Check size={13} />
                  </button>
                  <button
                    onClick={() => deleteReviewComment(c.id)}
                    aria-label="Delete note"
                    className="grid h-6 w-6 place-items-center rounded text-subtle hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>

        <form onSubmit={submit} className="border-t border-line p-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-subtle">
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono font-medium tabular-nums">
              {timecode(time, asset.fps)}
            </span>
            {pending ? (
              <span className="flex items-center gap-1 font-medium text-brand">
                <Pencil size={11} /> area marked
                <button
                  type="button"
                  onClick={() => setPending(null)}
                  aria-label="Clear marked area"
                  className="text-subtle hover:text-ink"
                >
                  <X size={11} />
                </button>
              </span>
            ) : (
              <span>note pins to this frame</span>
            )}
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit(e)
              }
            }}
            rows={2}
            placeholder="Leave a note on this frame…"
            aria-label="Leave a note on this frame"
            className="w-full resize-none rounded-lg border border-line px-2.5 py-1.5 text-[12.5px] outline-none focus:border-brand"
          />
          <Button
            type="submit"
            variant="primary"
            size="sm"
            className="mt-1.5 w-full"
            disabled={!draft.trim()}
          >
            Add note
          </Button>
        </form>
      </aside>
    </div>
  )
}

/**
 * One mark on the frame. Rendered in a normalised 0–1 SVG viewBox so every
 * shape scales with the player without recomputing coordinates.
 */
function Region({
  region,
  label,
  pendingLabel,
}: {
  region: ReviewRegion
  label?: string
  pendingLabel?: boolean
}) {
  const stroke = pendingLabel ? 'var(--color-brand)' : '#fbbf24'
  const fill = pendingLabel ? 'rgba(47,107,255,0.15)' : 'rgba(251,191,36,0.15)'
  const { tool, x, y, w, h } = region

  return (
    <svg
      aria-hidden
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <defs>
        <marker
          id={`head-${pendingLabel ? 'p' : 'a'}`}
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L6,3 L0,6 Z" fill={stroke} />
        </marker>
      </defs>

      {tool === 'rect' && (
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          fill={fill}
          stroke={stroke}
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          rx={0.01}
        />
      )}

      {(tool === 'arrow' || tool === 'line') && (
        <line
          x1={x}
          y1={y}
          x2={x + w}
          y2={y + h}
          stroke={stroke}
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          strokeLinecap="round"
          markerEnd={tool === 'arrow' ? `url(#head-${pendingLabel ? 'p' : 'a'})` : undefined}
        />
      )}

      {tool === 'pin' && (
        <>
          <circle cx={x} cy={y} r={0.018} fill={stroke} />
          <circle
            cx={x}
            cy={y}
            r={0.038}
            fill="none"
            stroke={stroke}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}

      {tool === 'draw' && region.points && region.points.length > 1 && (
        <polyline
          points={region.points.map((p) => `${p.x},${p.y}`).join(' ')}
          fill="none"
          stroke={stroke}
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {label && (
        <text
          x={x}
          y={Math.max(0.03, y - 0.012)}
          fill={stroke}
          fontSize={0.035}
          fontWeight="700"
        >
          {label}
        </text>
      )}
    </svg>
  )
}

function Timeline({
  duration,
  time,
  comments,
  fps,
  onSeek,
}: {
  duration: number
  time: number
  comments: ReviewComment[]
  fps: number
  onSeek: (s: number) => void
}) {
  const pct = duration ? (time / duration) * 100 : 0
  return (
    <div className="relative">
      <div
        role="slider"
        tabIndex={0}
        aria-label="Timeline"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={timecode(time, fps)}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          onSeek(((e.clientX - r.left) / r.width) * duration)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Home') onSeek(0)
          if (e.key === 'End') onSeek(duration)
        }}
        className="relative h-9 cursor-pointer rounded-lg bg-zinc-100"
      >
        <div
          className="pointer-events-none absolute inset-y-0 left-0 rounded-l-lg bg-brand/15"
          style={{ width: `${pct}%` }}
        />
        <div
          className="pointer-events-none absolute inset-y-0 w-0.5 bg-brand"
          style={{ left: `${pct}%` }}
        />
        {comments.map((c, i) => {
          // Notes within ~0.4s land on the same pixel; stagger so each stays
          // clickable instead of the last one swallowing the others' clicks.
          const cluster = comments
            .slice(0, i)
            .filter((o) => Math.abs(o.timecodeSec - c.timecodeSec) < 0.4).length
          return (
          <button
            key={c.id}
            title={`${timecode(c.timecodeSec, fps)} — ${c.body}`}
            aria-label={`Jump to note at ${timecode(c.timecodeSec, fps)}`}
            onClick={(e) => {
              e.stopPropagation()
              onSeek(c.timecodeSec)
            }}
            style={{
              left: `${(c.timecodeSec / duration) * 100}%`,
              top: 6 + (cluster % 3) * 8,
            }}
            className={cx(
              'absolute -ml-1.5 h-3 w-3 rounded-full border-2 border-white shadow',
              c.resolved ? 'bg-zinc-400' : 'bg-amber-400',
            )}
          />
          )
        })}
      </div>
    </div>
  )
}
