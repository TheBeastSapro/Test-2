import type { FailoverState } from '@agentswitch/contracts';

/**
 * Legal transitions. Anything not listed is a bug, and throwing here is
 * deliberate: a failover machine that silently accepts an impossible
 * transition is how a switch happens without a checkpoint behind it.
 */
const ALLOWED: Readonly<Record<FailoverState, readonly FailoverState[]>> = Object.freeze({
  running: ['limit_suspected'],
  // A suspected limit that fails to confirm returns to running. One ambiguous
  // signal must never be enough to move work off a provider.
  limit_suspected: ['limit_confirmed', 'running'],
  limit_confirmed: ['checkpoint_requested'],
  checkpoint_requested: ['routing'],
  routing: ['handoff_verification', 'paused'],
  // Verification disagreeing pauses rather than proceeding.
  handoff_verification: ['running', 'paused'],
  // Paused work resumes by routing again once a resource returns.
  paused: ['routing'],
});

export class InvalidFailoverTransitionError extends Error {
  constructor(
    readonly from: FailoverState,
    readonly to: FailoverState,
  ) {
    super(`Invalid failover transition: ${from} -> ${to}`);
    this.name = 'InvalidFailoverTransitionError';
  }
}

export class FailoverMachine {
  #state: FailoverState;

  constructor(initial: FailoverState = 'running') {
    this.#state = initial;
  }

  get state(): FailoverState {
    return this.#state;
  }

  canTransitionTo(next: FailoverState): boolean {
    return ALLOWED[this.#state].includes(next);
  }

  transitionTo(next: FailoverState): { from: FailoverState; to: FailoverState } {
    const from = this.#state;
    if (!this.canTransitionTo(next)) {
      throw new InvalidFailoverTransitionError(from, next);
    }
    this.#state = next;
    return { from, to: next };
  }
}
