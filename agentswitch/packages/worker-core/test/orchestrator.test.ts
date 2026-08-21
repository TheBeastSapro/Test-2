import { describe, expect, it } from 'vitest';
import { TimelineEventSchema, type TimelineEvent } from '@agentswitch/contracts';
import {
  FailoverMachine,
  InvalidFailoverTransitionError,
  collectTimeline,
  demoConfig,
} from '@agentswitch/worker-core';

const ALL_POOL = ['sim-alpha', 'sim-beta', 'sim-gamma'];

const payloads = (events: TimelineEvent[], type: TimelineEvent['payload']['type']) =>
  events.filter((e) => e.payload.type === type);

describe('orchestrator: one continuous timeline across a switch', () => {
  it('keeps a single task id and contiguous sequence numbers through the handoff', async () => {
    const events = await collectTimeline(
      demoConfig({ qualityMode: 'balanced', failoverPool: ALL_POOL }),
    );

    expect(events.length).toBeGreaterThan(20);

    // Every event validates against the shared contract.
    for (const event of events) {
      expect(() => TimelineEventSchema.parse(event)).not.toThrow();
    }

    // One task, one stream: no reset, no gaps, no restart.
    expect(new Set(events.map((e) => e.taskId)).size).toBe(1);
    expect(events.map((e) => e.seq)).toEqual(
      Array.from({ length: events.length }, (_, i) => i + 1),
    );
  });

  it('shows exactly one transition, with both agents on the same stream', async () => {
    const events = await collectTimeline(
      demoConfig({ qualityMode: 'balanced', failoverPool: ALL_POOL }),
    );

    const transitions = payloads(events, 'transition');
    expect(transitions).toHaveLength(1);

    const transition = transitions[0]!;
    if (transition.payload.type !== 'transition') throw new Error('unreachable');
    expect(transition.payload.detail.fromAdapterId).toBe('sim-alpha');
    expect(transition.payload.detail.toAdapterId).toBe('sim-beta');

    const before = events.filter((e) => e.seq < transition.seq);
    const after = events.filter((e) => e.seq > transition.seq);

    // sim-alpha works before the marker, sim-beta after it, in one stream.
    expect(before.some((e) => e.source.adapterId === 'sim-alpha')).toBe(true);
    expect(before.some((e) => e.source.adapterId === 'sim-beta')).toBe(false);
    expect(after.some((e) => e.source.adapterId === 'sim-beta')).toBe(true);

    // The replacement's session starts as a handoff, and the sequence keeps
    // climbing rather than restarting at 1.
    const handoffStart = after.find(
      (e) => e.payload.type === 'session_started' && e.payload.mode === 'handoff',
    );
    expect(handoffStart).toBeDefined();
    expect(handoffStart!.seq).toBeGreaterThan(transition.seq);
  });

  it('checkpoints before routing and verifies read-only before writing', async () => {
    const events = await collectTimeline(
      demoConfig({ qualityMode: 'balanced', failoverPool: ALL_POOL }),
    );

    const seqOf = (type: TimelineEvent['payload']['type']) => payloads(events, type)[0]!.seq;

    // Order is the guarantee: checkpoint -> route -> transition -> verify.
    expect(seqOf('checkpoint_created')).toBeLessThan(seqOf('routing_completed'));
    expect(seqOf('routing_completed')).toBeLessThan(seqOf('transition'));

    const verification = payloads(events, 'verification_result')[0]!;
    if (verification.payload.type !== 'verification_result') throw new Error('unreachable');
    expect(verification.payload.agrees).toBe(true);

    // No file was written by the replacement before it verified.
    const writesBeforeVerification = events.filter(
      (e) =>
        e.seq < verification.seq &&
        e.source.adapterId === 'sim-beta' &&
        e.payload.type === 'file_change',
    );
    expect(writesBeforeVerification).toEqual([]);

    // The checkpoint records observable state only.
    const checkpoint = payloads(events, 'checkpoint_created')[0]!;
    if (checkpoint.payload.type !== 'checkpoint_created') throw new Error('unreachable');
    expect(checkpoint.payload.checkpoint.filesChanged.map((f) => f.path)).toEqual([
      'src/api/client.ts',
      'src/api/retry.ts',
    ]);
    expect(checkpoint.payload.checkpoint.lastTestResult).toEqual({ passed: 11, failed: 2 });
  });

  it('finishes the task on the replacement', async () => {
    const events = await collectTimeline(
      demoConfig({ qualityMode: 'balanced', failoverPool: ALL_POOL }),
    );

    const last = events[events.length - 1]!;
    expect(last.payload.type).toBe('session_ended');
    if (last.payload.type !== 'session_ended') throw new Error('unreachable');
    expect(last.payload.reason).toBe('completed');
    expect(last.source.adapterId).toBe('sim-beta');
  });
});

describe('orchestrator: pausing instead of downgrading', () => {
  it('pauses in Strict mode when only sim-gamma is available', async () => {
    const events = await collectTimeline(
      demoConfig({ qualityMode: 'strict', failoverPool: ['sim-gamma'] }),
    );

    expect(payloads(events, 'transition')).toHaveLength(0);

    const paused = payloads(events, 'paused');
    expect(paused).toHaveLength(1);

    const states = events.flatMap((e) =>
      e.payload.type === 'failover_state_changed' ? [e.payload.to] : [],
    );
    expect(states).toEqual([
      'running',
      'limit_suspected',
      'limit_confirmed',
      'checkpoint_requested',
      'routing',
      'paused',
    ]);

    // The work is still checkpointed even though nothing took over.
    expect(payloads(events, 'checkpoint_created')).toHaveLength(1);
    // And sim-gamma never ran.
    expect(events.some((e) => e.source.adapterId === 'sim-gamma')).toBe(false);
  });

  it('produces byte-identical timelines for identical configuration', async () => {
    const run = () =>
      collectTimeline(demoConfig({ qualityMode: 'balanced', failoverPool: ALL_POOL }));

    expect(JSON.stringify(await run())).toBe(JSON.stringify(await run()));
  });
});

describe('failover machine', () => {
  it('rejects transitions that would skip the checkpoint', () => {
    const machine = new FailoverMachine('running');
    expect(() => machine.transitionTo('routing')).toThrow(InvalidFailoverTransitionError);
  });

  it('allows a suspected limit that never confirms to return to running', () => {
    const machine = new FailoverMachine('running');
    machine.transitionTo('limit_suspected');
    expect(() => machine.transitionTo('running')).not.toThrow();
    expect(machine.state).toBe('running');
  });
});
