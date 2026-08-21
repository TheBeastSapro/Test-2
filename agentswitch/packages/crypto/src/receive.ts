import {
  MAX_ENVELOPE_LIFETIME_MS,
  type DeliveryReceipt,
  type SealedPayloadHeader,
} from '@agentswitch/contracts';
import { ReplayGuard } from './replay.js';
import { openEnvelope } from './envelope.js';
import { sodiumReady, wipe } from './sodium.js';
import type { WorkerKeyPair } from './identity.js';

/**
 * Worker-side receipt of one sealed envelope.
 *
 * Milestone 2A deliberately stops at "it decrypted, and the bytes were right".
 * The decrypted value is never written to a file, a database or a secret
 * store, and no provider is contacted. Persistence is Milestone 2B.
 */
export interface WorkerContext {
  workerId: string;
  fingerprint: string;
  keyPair: WorkerKeyPair;
  replayGuard: ReplayGuard;
  /**
   * Test-path canary. When set, the worker reports whether the decrypted bytes
   * matched it - which is what proves end-to-end byte fidelity without ever
   * revealing, storing or returning the value itself.
   */
  expectedCanary?: string | undefined;
}

export function createWorkerContext(
  workerId: string,
  fingerprint: string,
  keyPair: WorkerKeyPair,
  expectedCanary?: string | undefined,
): WorkerContext {
  return {
    workerId,
    fingerprint,
    keyPair,
    replayGuard: new ReplayGuard(MAX_ENVELOPE_LIFETIME_MS * 2),
    expectedCanary,
  };
}

/** Constant-time-ish comparison over bytes. Avoids leaking length via early exit. */
function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= (a[i] as number) ^ (b[i] as number);
  return diff === 0;
}

export async function receiveEnvelope(
  context: WorkerContext,
  envelope: unknown,
  now: Date = new Date(),
): Promise<DeliveryReceipt> {
  const base = {
    workerId: context.workerId,
    receivedAt: now.toISOString(),
  };

  const result = await openEnvelope({
    envelope,
    workerId: context.workerId,
    workerFingerprint: context.fingerprint,
    publicKey: context.keyPair.publicKey,
    privateKey: context.keyPair.privateKey,
    now,
    isReplay: (nonce) => context.replayGuard.has(nonce, now),
  });

  if (!result.ok) {
    return {
      ...base,
      envelopeId: readEnvelopeId(envelope),
      ok: false,
      provider: null,
      credentialType: null,
      canaryMatched: null,
      failure: result.failure,
    };
  }

  const header: SealedPayloadHeader = result.header;
  context.replayGuard.consume(header.replayNonce, now);

  let canaryMatched: boolean | null = null;
  try {
    if (context.expectedCanary !== undefined) {
      const sodium = await sodiumReady();
      const expected = sodium.from_string(context.expectedCanary);
      canaryMatched = bytesEqual(result.secret, expected);
      await wipe(expected);
    }
  } finally {
    // The decrypted credential leaves this function only as a boolean.
    await wipe(result.secret);
  }

  return {
    ...base,
    envelopeId: header.envelopeId,
    ok: true,
    provider: header.provider,
    credentialType: header.credentialType,
    canaryMatched,
    failure: null,
  };
}

/** Best-effort id extraction for a rejected envelope, so the relay can be acked. */
function readEnvelopeId(envelope: unknown): string {
  const id = (envelope as { envelopeId?: unknown } | null)?.envelopeId;
  return typeof id === 'string' && id.length > 0 && id.length <= 128 ? id : 'unknown';
}
