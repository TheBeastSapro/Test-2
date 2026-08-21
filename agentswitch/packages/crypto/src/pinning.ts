import type { WorkerIdentity } from '@agentswitch/contracts';

export type PinStatus = 'unconfirmed' | 'confirmed' | 'key_changed';

export interface PinnedWorker {
  workerId: string;
  publicKey: string;
  fingerprint: string;
}

/**
 * Records which worker keys a person has actually looked at and confirmed.
 *
 * Nothing is trusted until a human has compared the fingerprint the browser
 * shows against the one the worker printed itself. If a previously confirmed
 * worker later presents a different public key, the pin does not silently
 * update - it reports `key_changed`, delivery is blocked, and confirmation
 * must happen again. A malicious or compromised control plane substituting its
 * own key is exactly what that check exists to catch.
 *
 * Deliberately in memory only for this milestone: a page refresh clears every
 * pin and forces re-confirmation.
 */
export class WorkerKeyPin {
  readonly #pins = new Map<string, PinnedWorker>();

  status(worker: Pick<WorkerIdentity, 'workerId' | 'publicKey'>): PinStatus {
    const pinned = this.#pins.get(worker.workerId);
    if (!pinned) return 'unconfirmed';
    return pinned.publicKey === worker.publicKey ? 'confirmed' : 'key_changed';
  }

  /** Only ever called from an explicit user action. */
  confirm(worker: Pick<WorkerIdentity, 'workerId' | 'publicKey' | 'fingerprint'>): void {
    this.#pins.set(worker.workerId, {
      workerId: worker.workerId,
      publicKey: worker.publicKey,
      fingerprint: worker.fingerprint,
    });
  }

  pinned(workerId: string): PinnedWorker | null {
    return this.#pins.get(workerId) ?? null;
  }

  clear(workerId?: string): void {
    if (workerId === undefined) this.#pins.clear();
    else this.#pins.delete(workerId);
  }
}
