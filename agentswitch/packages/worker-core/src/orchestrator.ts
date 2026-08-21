import type {
  AgentAdapter,
  AgentEvent,
  CapabilityProfile,
  Task,
  TimelineEvent,
  TimelinePayload,
} from '@agentswitch/contracts';
import { FailoverMachine } from './failover.js';
import { ObservedState, buildCheckpoint, buildContinuityPackage } from './checkpoint.js';
import { route } from './router.js';

export interface RunTaskConfig {
  task: Task;
  /** Every adapter installed on this worker. */
  adapters: AgentAdapter[];
  startingAdapterId: string;
  /** Adapter ids the router may consider as replacements. */
  failoverPool: string[];
}

/**
 * Drives one task end to end and yields ONE continuous timeline.
 *
 * The two properties that matter, and that the tests assert:
 *   - `seq` is 1-based and contiguous for the life of the task. A provider
 *     change does not reset it.
 *   - `taskId` never changes. A switch is an event inside a task, not a new
 *     task.
 *
 * Deterministic by construction: no wall-clock reads, no randomness. The same
 * config always produces a byte-identical timeline.
 */
export async function* runTask(
  config: RunTaskConfig,
): AsyncGenerator<TimelineEvent, void, void> {
  const { task } = config;
  const byId = new Map(config.adapters.map((a) => [a.id, a]));

  const starting = byId.get(config.startingAdapterId);
  if (!starting) {
    throw new Error(`Unknown starting adapter: ${config.startingAdapterId}`);
  }

  const candidateProfiles: CapabilityProfile[] = config.failoverPool.map((id) => {
    const adapter = byId.get(id);
    if (!adapter) throw new Error(`Unknown adapter in failover pool: ${id}`);
    return adapter.profile;
  });

  let seq = 0;
  const machine = new FailoverMachine('running');
  const observed = new ObservedState();

  const emit = (
    payload: TimelinePayload,
    adapterId: string | null,
  ): TimelineEvent => ({
    seq: ++seq,
    taskId: task.id,
    source: { kind: adapterId === null ? 'orchestrator' : 'agent', adapterId },
    payload,
  });

  const stateChange = (to: Parameters<FailoverMachine['transitionTo']>[0], note: string) => {
    const { from } = machine.transitionTo(to);
    return emit({ type: 'failover_state_changed', from, to, note }, null);
  };

  yield emit(
    { type: 'failover_state_changed', from: null, to: 'running', note: 'Task started.' },
    null,
  );

  /**
   * Streams an adapter phase, recording observable state as it goes.
   *
   * `after` runs once the agent event has already been given its sequence
   * number, so any orchestrator event it produces is numbered - and yielded -
   * strictly after the event that caused it. Doing this the other way round
   * silently emits the timeline out of order.
   */
  async function* phase(
    adapter: AgentAdapter,
    mode: Parameters<AgentAdapter['run']>[0],
    after?: (e: AgentEvent) => TimelineEvent[],
  ): AsyncGenerator<TimelineEvent, void, void> {
    for await (const event of adapter.run(mode)) {
      observed.record(event);
      yield emit(event, adapter.id);
      for (const follow of after?.(event) ?? []) {
        yield follow;
      }
    }
  }

  // ---- Phase 1: the starting agent works -------------------------------
  let limitResetAt: string | null = null;

  const handleAgentEvent = (event: AgentEvent): TimelineEvent[] => {
    if (event.type !== 'limit_signal') return [];
    const follow: TimelineEvent[] = [];

    if (event.kind === 'approaching' && machine.state === 'running') {
      follow.push(stateChange('limit_suspected', `Possible usage limit: ${event.evidence}`));
      return follow;
    }

    if (event.kind === 'reached') {
      limitResetAt = event.resetAt;
      // A limit is only ever acted on after an explicit confirmation step, so
      // the suspected -> confirmed hop is always visible in the timeline even
      // when the provider skips straight to a hard stop.
      if (machine.state === 'running') {
        follow.push(stateChange('limit_suspected', `Possible usage limit: ${event.evidence}`));
      }
      if (machine.state === 'limit_suspected') {
        follow.push(stateChange('limit_confirmed', `Usage limit confirmed: ${event.evidence}`));
      }
    }

    return follow;
  };

  for await (const timelineEvent of phase(
    starting,
    { kind: 'initial', task },
    handleAgentEvent,
  )) {
    yield timelineEvent;
  }

  if (machine.state !== 'limit_confirmed') {
    // Finished without a confirmed failure. Nothing to fail over from.
    return;
  }

  // ---- Phase 2: checkpoint --------------------------------------------
  yield stateChange('checkpoint_requested', 'Saving a checkpoint before switching.');
  const checkpoint = buildCheckpoint(task, observed, 1, seq);
  yield emit({ type: 'checkpoint_created', checkpoint }, null);

  // ---- Phase 3: route --------------------------------------------------
  yield stateChange('routing', 'Looking for a comparable available agent.');
  const decision = route({
    task,
    departing: starting.profile,
    candidates: candidateProfiles,
  });
  yield emit({ type: 'routing_completed', decision }, null);

  if (decision.outcome !== 'selected' || decision.selectedAdapterId === null) {
    yield stateChange('paused', 'No comparable agent available.');
    yield emit(
      {
        type: 'paused',
        reason:
          decision.outcome === 'paused_user_confirmation_required'
            ? 'Quality mode is "ask me", so AgentSwitch is waiting for your choice.'
            : 'No available agent met the quality floor for this task.',
        resetAt: limitResetAt,
        options: [
          'Wait for the original agent to become available again',
          'Switch this task to Balanced or Continue at Any Cost',
          'Bring another computer or agent online',
        ],
      },
      null,
    );
    return;
  }

  const replacement = byId.get(decision.selectedAdapterId);
  if (!replacement) {
    throw new Error(`Router selected an unknown adapter: ${decision.selectedAdapterId}`);
  }

  // ---- Phase 4: the visible transition ---------------------------------
  yield emit(
    {
      type: 'transition',
      detail: {
        reason: 'usage_limit',
        fromAdapterId: starting.id,
        fromDisplayName: starting.profile.displayName,
        toAdapterId: replacement.id,
        toDisplayName: replacement.profile.displayName,
        resetAt: limitResetAt,
        checkpointSequence: checkpoint.sequence,
        summary:
          `${starting.profile.displayName} reached its usage limit. ` +
          `Continuing with ${replacement.profile.displayName}.`,
      },
    },
    null,
  );

  // ---- Phase 5: read-only verification before any write ----------------
  yield stateChange(
    'handoff_verification',
    `${replacement.profile.displayName} is checking the existing work.`,
  );

  const handoff = buildContinuityPackage(task, checkpoint);
  let verified = false;

  for await (const timelineEvent of phase(
    replacement,
    { kind: 'verify', task, handoff },
    (event) => {
      if (event.type === 'verification_result') verified = event.agrees;
      return [];
    },
  )) {
    yield timelineEvent;
  }

  if (!verified) {
    yield stateChange('paused', 'The replacement disagreed with the checkpoint.');
    yield emit(
      {
        type: 'paused',
        reason:
          'The replacement agent could not confirm the inherited work matches the ' +
          'checkpoint, so it stopped rather than building on an unclear state.',
        resetAt: limitResetAt,
        options: ['Review the checkpoint and the current diff', 'Undo the switch'],
      },
      null,
    );
    return;
  }

  // ---- Phase 6: continue, same task, same timeline ---------------------
  yield stateChange('running', `${replacement.profile.displayName} is continuing the work.`);

  for await (const timelineEvent of phase(replacement, { kind: 'continue', task, handoff })) {
    yield timelineEvent;
  }
}

/** Convenience for callers that want the whole timeline at once (tests, CLI). */
export async function collectTimeline(config: RunTaskConfig): Promise<TimelineEvent[]> {
  const events: TimelineEvent[] = [];
  for await (const event of runTask(config)) {
    events.push(event);
  }
  return events;
}
