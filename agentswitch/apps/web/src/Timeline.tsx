import { useState } from 'react';
import type { TimelineEvent } from '@agentswitch/contracts';

/** Only the states worth surfacing to a person. The rest is machinery. */
const VISIBLE_STATES = new Set(['limit_suspected', 'limit_confirmed', 'paused']);

function StateNote({ text }: { text: string }) {
  return <div className="row row-state">{text}</div>;
}

function Row({ event }: { event: TimelineEvent }) {
  const [showWhy, setShowWhy] = useState(false);
  const p = event.payload;

  switch (p.type) {
    case 'session_started':
      return (
        <div className="row row-session">
          <span className="agent-badge">{p.displayName}</span>
          <span>
            {p.mode === 'handoff'
              ? 'picked up the task (read-only until it verifies the work)'
              : 'started working'}
          </span>
        </div>
      );

    case 'text_delta':
      return <p className="row row-text">{p.text}</p>;

    case 'thinking_marker':
      return <div className="row row-thinking">thinking…</div>;

    case 'tool_call':
      return (
        <div className="row row-card">
          <span className="card-kind">{p.name}</span>
          <code>{p.summary}</code>
        </div>
      );

    case 'tool_result':
      return <div className="row row-subtle">→ {p.summary}</div>;

    case 'file_change':
      return (
        <div className="row row-card">
          <span className="card-kind">{p.kind}</span>
          <code>{p.path}</code>
          <span className="diffstat">
            <span className="added">+{p.added}</span>{' '}
            <span className="removed">−{p.removed}</span>
          </span>
        </div>
      );

    case 'command_run':
      return (
        <div className="row row-card">
          <span className="card-kind">run</span>
          <code>{p.command}</code>
          <span className={p.exitCode === 0 ? 'chip chip-ok' : 'chip chip-warn'}>
            exit {p.exitCode}
          </span>
        </div>
      );

    case 'test_result':
      return (
        <div className="row row-tests">
          <span className={p.failed === 0 ? 'chip chip-ok' : 'chip chip-warn'}>
            {p.passed} passed · {p.failed} failed
          </span>
          {p.failing.length > 0 && <span className="failing">{p.failing.join(', ')}</span>}
        </div>
      );

    case 'limit_signal':
      return (
        <div className="row row-limit">
          {p.kind === 'approaching' ? 'Usage limit may be close' : 'Usage limit reached'} —{' '}
          <span className="evidence">{p.evidence}</span>
        </div>
      );

    case 'verification_result':
      return (
        <div className={p.agrees ? 'row row-verified' : 'row row-limit'}>
          {p.agrees ? 'Verified' : 'Could not verify'} — inspected {p.filesInspected} files.{' '}
          {p.notes}
        </div>
      );

    case 'session_ended':
      return <div className="row row-subtle">session ended ({p.reason.replace(/_/g, ' ')})</div>;

    case 'failover_state_changed':
      return VISIBLE_STATES.has(p.to) ? <StateNote text={p.note} /> : null;

    case 'checkpoint_created': {
      const c = p.checkpoint;
      return (
        <div className="row row-checkpoint">
          <strong>Checkpoint saved.</strong> {c.filesChanged.length} files changed,{' '}
          {c.lastTestResult
            ? `${c.lastTestResult.passed} passing / ${c.lastTestResult.failed} failing`
            : 'no tests run yet'}
          . {c.remainingWork.length} items remaining.
        </div>
      );
    }

    case 'routing_completed':
      return (
        <div className="row row-routing">
          <div className="row-routing-head">
            <span>
              {p.decision.selectedAdapterId
                ? 'Chose a replacement agent.'
                : 'No replacement met the quality floor.'}
            </span>
            <button
              type="button"
              className="link-btn"
              aria-expanded={showWhy}
              onClick={() => setShowWhy((v) => !v)}
            >
              {showWhy ? 'Hide reasoning' : 'Why this agent?'}
            </button>
          </div>
          {showWhy && <pre className="explanation">{p.decision.explanation}</pre>}
        </div>
      );

    case 'transition':
      return (
        <div className="transition" role="separator">
          <div className="transition-line" />
          <div className="transition-body">
            <span className="transition-icon" aria-hidden="true">
              ⚡
            </span>
            <div>
              <div className="transition-title">{p.detail.summary}</div>
              <div className="transition-sub">
                Work verified from checkpoint {p.detail.checkpointSequence}
                {p.detail.resetAt ? ` · original resets ${p.detail.resetAt}` : ''}
              </div>
            </div>
          </div>
          <div className="transition-line" />
        </div>
      );

    case 'paused':
      return (
        <div className="row row-paused">
          <strong>Paused — nothing was downgraded.</strong>
          <p>{p.reason}</p>
          <ul>
            {p.options.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </div>
      );

    default:
      return null;
  }
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="timeline-empty">
        Press <strong>Start demo task</strong> to watch a task survive a usage limit.
      </div>
    );
  }

  return (
    <div className="timeline" role="log" aria-live="polite" aria-relevant="additions">
      {events.map((event) => (
        <Row key={event.seq} event={event} />
      ))}
    </div>
  );
}
