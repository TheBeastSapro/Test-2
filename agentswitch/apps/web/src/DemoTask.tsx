import { useCallback, useEffect, useRef, useState } from 'react';
import type { QualityMode, TimelineEvent } from '@agentswitch/contracts';
import { DEMO_TASK, demoConfig, runTask } from '@agentswitch/worker-core';
import { Timeline } from './Timeline';

const ALL_ADAPTERS = [
  { id: 'sim-alpha', label: 'Sim Alpha', note: 'strong — the agent that starts the task' },
  { id: 'sim-beta', label: 'Sim Beta', note: 'comparable — clears the floor' },
  { id: 'sim-gamma', label: 'Sim Gamma', note: 'weak — must fail the floor' },
] as const;

const MODES: Array<{ value: QualityMode; label: string; note: string }> = [
  { value: 'balanced', label: 'Balanced', note: 'accepts a small step down (85% of the floor)' },
  { value: 'strict', label: 'Strict', note: 'near-equal or better only (95%)' },
];

/** Paced so the stream reads like work happening, not a log dump. */
function delayFor(event: TimelineEvent): number {
  switch (event.payload.type) {
    case 'text_delta':
      return 260;
    case 'transition':
      return 800;
    case 'checkpoint_created':
    case 'routing_completed':
    case 'paused':
      return 500;
    case 'thinking_marker':
      return 350;
    default:
      return 150;
  }
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function DemoTask() {
  const [qualityMode, setQualityMode] = useState<QualityMode>('balanced');
  const [pool, setPool] = useState<string[]>(['sim-alpha', 'sim-beta', 'sim-gamma']);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [running, setRunning] = useState(false);

  // Bumped on every start/unmount so a stale run can never write to state.
  const runToken = useRef(0);
  useEffect(() => () => { runToken.current += 1; }, []);

  const togglePool = (id: string) => {
    setPool((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );
  };

  const start = useCallback(async () => {
    runToken.current += 1;
    const token = runToken.current;

    setEvents([]);
    setRunning(true);

    try {
      for await (const event of runTask(demoConfig({ qualityMode, failoverPool: pool }))) {
        if (runToken.current !== token) return;
        setEvents((current) => [...current, event]);
        await sleep(delayFor(event));
      }
    } finally {
      if (runToken.current === token) setRunning(false);
    }
  }, [qualityMode, pool]);

  const strictGammaOnly = qualityMode === 'strict' && pool.length === 1 && pool[0] === 'sim-gamma';

  return (
    <div className="task-view">
      <aside className="panel controls">
        <h1>Failover demo</h1>
        <p className="objective">{DEMO_TASK.objective}</p>
        <dl className="meta">
          <div>
            <dt>Task type</dt>
            <dd>{DEMO_TASK.taskClass.replace(/_/g, ' ')}</dd>
          </div>
          <div>
            <dt>Starting agent</dt>
            <dd>Sim Alpha</dd>
          </div>
        </dl>

        <fieldset className="field">
          <legend>Quality mode</legend>
          {MODES.map((m) => (
            <label key={m.value} className="opt">
              <input
                type="radio"
                name="quality-mode"
                value={m.value}
                checked={qualityMode === m.value}
                disabled={running}
                onChange={() => setQualityMode(m.value)}
              />
              <span>
                <strong>{m.label}</strong>
                <em>{m.note}</em>
              </span>
            </label>
          ))}
        </fieldset>

        <fieldset className="field">
          <legend>Agents available to take over</legend>
          {ALL_ADAPTERS.map((a) => (
            <label key={a.id} className="opt">
              <input
                type="checkbox"
                checked={pool.includes(a.id)}
                disabled={running}
                onChange={() => togglePool(a.id)}
              />
              <span>
                <strong>{a.label}</strong>
                <em>{a.note}</em>
              </span>
            </label>
          ))}
        </fieldset>

        {strictGammaOnly && (
          <p className="hint">
            Strict mode with only Sim Gamma available — AgentSwitch will pause rather than
            hand your work to a weaker agent.
          </p>
        )}

        <button type="button" className="primary" onClick={start} disabled={running}>
          {running ? 'Running…' : 'Start demo task'}
        </button>

        <p className="fineprint">
          These are simulated agents. No provider, credential or network call is involved.
        </p>
      </aside>

      <section className="panel stream" aria-label="Task timeline">
        <Timeline events={events} />
      </section>
    </div>
  );
}
