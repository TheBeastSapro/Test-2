import { describe, expect, it } from 'vitest';
import type { CapabilityProfile, Task } from '@agentswitch/contracts';
import {
  SIM_ALPHA_PROFILE,
  SIM_BETA_PROFILE,
  SIM_GAMMA_PROFILE,
  DEMO_TASK,
  route,
} from '@agentswitch/worker-core';

const task = (overrides: Partial<Task> = {}): Task => ({ ...DEMO_TASK, ...overrides });

const findCandidate = (
  decision: ReturnType<typeof route>,
  adapterId: string,
) => {
  const found = decision.candidates.find((c) => c.adapterId === adapterId);
  if (!found) throw new Error(`candidate ${adapterId} missing from decision`);
  return found;
};

const ALL: CapabilityProfile[] = [SIM_ALPHA_PROFILE, SIM_BETA_PROFILE, SIM_GAMMA_PROFILE];

describe('routing: quality floor', () => {
  it('selects sim-beta in Balanced mode when sim-alpha is being replaced', () => {
    const decision = route({
      task: task({ qualityMode: 'balanced' }),
      departing: SIM_ALPHA_PROFILE,
      candidates: ALL,
    });

    expect(decision.outcome).toBe('selected');
    expect(decision.selectedAdapterId).toBe('sim-beta');
    // Floor is relative to the departing agent, never an absolute constant.
    expect(decision.departingScore).toBe(88);
    expect(decision.requiredScore).toBe(74.8);
  });

  it('rejects sim-gamma on the quality floor, not on any hard gate', () => {
    const decision = route({
      task: task({ qualityMode: 'balanced' }),
      departing: SIM_ALPHA_PROFILE,
      candidates: ALL,
    });

    const gamma = findCandidate(decision, 'sim-gamma');
    // This is the assertion that matters: gamma passed every gate, so its
    // rejection can only be the floor. A gate failure here would make the
    // test pass for the wrong reason.
    expect(gamma.gateFailures).toEqual([]);
    expect(gamma.eligible).toBe(true);
    expect(gamma.score).toBe(55);
    expect(gamma.aboveFloor).toBe(false);
    expect(decision.selectedAdapterId).not.toBe('sim-gamma');
    expect(decision.explanation).toContain('below the floor (55 < 74.8)');
  });

  it('excludes the departing agent from its own replacement search', () => {
    const decision = route({
      task: task({ qualityMode: 'balanced' }),
      departing: SIM_ALPHA_PROFILE,
      candidates: ALL,
    });

    expect(findCandidate(decision, 'sim-alpha').gateFailures).toContain('is_departing_agent');
  });

  it('pauses in Strict mode when only sim-gamma is available', () => {
    const decision = route({
      task: task({ qualityMode: 'strict' }),
      departing: SIM_ALPHA_PROFILE,
      candidates: [SIM_GAMMA_PROFILE],
    });

    expect(decision.outcome).toBe('paused_no_candidate_clears_floor');
    expect(decision.selectedAdapterId).toBeNull();
    expect(decision.requiredScore).toBe(83.6);
    expect(decision.explanation).toContain('paused instead of');
  });

  it('still accepts sim-beta in Strict mode, so Strict is a floor and not a block', () => {
    const decision = route({
      task: task({ qualityMode: 'strict' }),
      departing: SIM_ALPHA_PROFILE,
      candidates: ALL,
    });

    expect(decision.selectedAdapterId).toBe('sim-beta');
  });
});

describe('routing: determinism', () => {
  const input = {
    task: task({ qualityMode: 'balanced' }),
    departing: SIM_ALPHA_PROFILE,
    candidates: ALL,
  };

  it('produces a byte-identical decision across repeated runs', () => {
    const first = JSON.stringify(route(input));
    for (let i = 0; i < 25; i += 1) {
      expect(JSON.stringify(route(input))).toBe(first);
    }
  });

  it('is independent of the order candidates are supplied in', () => {
    const baseline = JSON.stringify(route(input));
    const permutations: CapabilityProfile[][] = [
      [SIM_ALPHA_PROFILE, SIM_BETA_PROFILE, SIM_GAMMA_PROFILE],
      [SIM_GAMMA_PROFILE, SIM_BETA_PROFILE, SIM_ALPHA_PROFILE],
      [SIM_BETA_PROFILE, SIM_ALPHA_PROFILE, SIM_GAMMA_PROFILE],
      [SIM_GAMMA_PROFILE, SIM_ALPHA_PROFILE, SIM_BETA_PROFILE],
    ];

    for (const candidates of permutations) {
      expect(JSON.stringify(route({ ...input, candidates }))).toBe(baseline);
    }
  });
});
