import {
  MAX_ENVELOPE_JSON_BYTES,
  MAX_ENVELOPE_LIFETIME_MS,
  SEALED_ENVELOPE_VERSION,
  SealedEnvelopeSchema,
  WorkerIdentitySchema,
  type DeliveryReceipt,
  type SealedEnvelope,
  type WorkerIdentity,
} from '@agentswitch/contracts';

/**
 * The relay.
 *
 * This module has no private key, no decryption function, and no dependency on
 * any crypto library. That is not an accident of implementation - it is the
 * security property. It holds opaque ciphertext for at most five minutes, hands
 * it to exactly one worker, and deletes it on acknowledgement.
 *
 * It also never validates a credential. Validation requires plaintext, and the
 * relay is designed so that plaintext can never reach it.
 */

export type RelayRejection =
  | 'malformed'
  | 'too_large'
  | 'unsupported_version'
  | 'expired'
  | 'unknown_worker'
  | 'duplicate';

export type SubmitResult =
  | { ok: true; envelopeId: string }
  | { ok: false; rejection: RelayRejection };

const WORKER_ONLINE_WINDOW_MS = 15_000;

/** UTF-8 byte length without depending on a DOM or Node global. */
function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.codePointAt(i) as number;
    if (code > 0xffff) i += 1;
    bytes += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
  }
  return bytes;
}

export interface RelayOptions {
  /** Injected for deterministic tests. */
  now?: () => Date;
  maxEnvelopes?: number;
}

export class EnvelopeRelay {
  readonly #workers = new Map<string, WorkerIdentity>();
  readonly #envelopes = new Map<string, SealedEnvelope>();
  readonly #receipts = new Map<string, DeliveryReceipt>();
  readonly #consumedIds = new Set<string>();
  readonly #now: () => Date;
  readonly #maxEnvelopes: number;

  constructor(options: RelayOptions = {}) {
    this.#now = options.now ?? (() => new Date());
    this.#maxEnvelopes = options.maxEnvelopes ?? 100;
  }

  /* ---------------- workers: public keys only ---------------- */

  registerWorker(input: unknown): WorkerIdentity | null {
    const parsed = WorkerIdentitySchema.omit({ online: true, lastSeenAt: true }).safeParse(input);
    if (!parsed.success) return null;

    const identity: WorkerIdentity = {
      ...parsed.data,
      lastSeenAt: this.#now().toISOString(),
      online: true,
    };
    this.#workers.set(identity.workerId, identity);
    return identity;
  }

  heartbeat(workerId: string): boolean {
    const worker = this.#workers.get(workerId);
    if (!worker) return false;
    this.#workers.set(workerId, { ...worker, lastSeenAt: this.#now().toISOString(), online: true });
    return true;
  }

  listWorkers(): WorkerIdentity[] {
    const cutoff = this.#now().getTime() - WORKER_ONLINE_WINDOW_MS;
    return [...this.#workers.values()]
      .map((w) => ({ ...w, online: Date.parse(w.lastSeenAt) >= cutoff }))
      .sort((a, b) => a.workerId.localeCompare(b.workerId));
  }

  /* ---------------- envelopes: opaque ciphertext ---------------- */

  /**
   * Accepts a sealed envelope. Every check here is on routing metadata or
   * size. Nothing inspects, decodes or interprets the ciphertext.
   */
  submit(raw: unknown, serialisedByteLength?: number): SubmitResult {
    this.sweep();

    // Byte length, not string length: multi-byte characters must count fully.
    const size = serialisedByteLength ?? utf8ByteLength(JSON.stringify(raw ?? null));
    if (size > MAX_ENVELOPE_JSON_BYTES) return { ok: false, rejection: 'too_large' };

    const version = (raw as { v?: unknown } | null)?.v;
    if (typeof version === 'number' && version !== SEALED_ENVELOPE_VERSION) {
      return { ok: false, rejection: 'unsupported_version' };
    }

    const parsed = SealedEnvelopeSchema.safeParse(raw);
    if (!parsed.success) return { ok: false, rejection: 'malformed' };
    const envelope = parsed.data;

    if (!this.#workers.has(envelope.destinationWorkerId)) {
      return { ok: false, rejection: 'unknown_worker' };
    }

    // An id that has already been delivered can never be resubmitted, even
    // after its ciphertext has been deleted.
    if (this.#envelopes.has(envelope.envelopeId) || this.#consumedIds.has(envelope.envelopeId)) {
      return { ok: false, rejection: 'duplicate' };
    }

    const now = this.#now().getTime();
    const createdAt = Date.parse(envelope.createdAt);
    const expiresAt = Date.parse(envelope.expiresAt);
    if (!Number.isFinite(createdAt) || !Number.isFinite(expiresAt)) {
      return { ok: false, rejection: 'malformed' };
    }
    if (expiresAt - createdAt > MAX_ENVELOPE_LIFETIME_MS) {
      return { ok: false, rejection: 'malformed' };
    }
    if (now >= expiresAt) return { ok: false, rejection: 'expired' };

    if (this.#envelopes.size >= this.#maxEnvelopes) {
      return { ok: false, rejection: 'too_large' };
    }

    this.#envelopes.set(envelope.envelopeId, envelope);
    return { ok: true, envelopeId: envelope.envelopeId };
  }

  /** A worker only ever sees envelopes addressed to it. */
  fetchFor(workerId: string): SealedEnvelope[] {
    this.sweep();
    return [...this.#envelopes.values()].filter((e) => e.destinationWorkerId === workerId);
  }

  /**
   * Acknowledgement deletes the ciphertext. The receipt that replaces it
   * carries only non-secret metadata.
   */
  acknowledge(envelopeId: string, workerId: string, receipt: DeliveryReceipt): boolean {
    const envelope = this.#envelopes.get(envelopeId);
    if (!envelope || envelope.destinationWorkerId !== workerId) return false;

    this.#envelopes.delete(envelopeId);
    this.#consumedIds.add(envelopeId);
    this.#receipts.set(envelopeId, receipt);
    return true;
  }

  receipt(envelopeId: string): DeliveryReceipt | null {
    return this.#receipts.get(envelopeId) ?? null;
  }

  /** Expired ciphertext is deleted whether or not anyone collected it. */
  sweep(): number {
    const now = this.#now().getTime();
    let removed = 0;
    for (const [id, envelope] of this.#envelopes) {
      if (now >= Date.parse(envelope.expiresAt)) {
        this.#envelopes.delete(id);
        this.#consumedIds.add(id);
        removed += 1;
      }
    }
    return removed;
  }

  /** Test/introspection helper. Returns stored ciphertext-bearing records. */
  storedEnvelopes(): SealedEnvelope[] {
    return [...this.#envelopes.values()];
  }

  get pendingCount(): number {
    return this.#envelopes.size;
  }
}
