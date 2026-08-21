import {
  MAX_ENVELOPE_JSON_BYTES,
  MAX_ENVELOPE_LIFETIME_MS,
  MAX_SECRET_BYTES,
  SEALED_ENVELOPE_VERSION,
  SealedEnvelopeSchema,
  SealedPayloadHeaderSchema,
  type CredentialTypeId,
  type DeliveryFailure,
  type ProviderId,
  type SealedEnvelope,
  type SealedPayloadHeader,
} from '@agentswitch/contracts';
import { sodiumReady, wipeWith, type Sodium } from './sodium.js';

/**
 * Sealed payload layout, encrypted as one unit:
 *
 *   [4-byte big-endian header length][header JSON, UTF-8][secret bytes]
 *
 * Binary rather than JSON-with-a-string-field on purpose: the secret stays a
 * Uint8Array we can zero afterwards, instead of becoming an immutable
 * JavaScript string that cannot be wiped at all.
 */
const HEADER_LENGTH_BYTES = 4;
const MAX_HEADER_BYTES = 4096;

function packPayload(
  sodium: Sodium,
  header: SealedPayloadHeader,
  secret: Uint8Array,
): Uint8Array {
  const headerBytes = sodium.from_string(JSON.stringify(header));
  if (headerBytes.length > MAX_HEADER_BYTES) throw new Error('header too large');

  const out = new Uint8Array(HEADER_LENGTH_BYTES + headerBytes.length + secret.length);
  new DataView(out.buffer).setUint32(0, headerBytes.length, false);
  out.set(headerBytes, HEADER_LENGTH_BYTES);
  out.set(secret, HEADER_LENGTH_BYTES + headerBytes.length);
  return out;
}

function unpackPayload(
  sodium: Sodium,
  packed: Uint8Array,
): { header: unknown; secret: Uint8Array } | null {
  if (packed.length < HEADER_LENGTH_BYTES) return null;

  const headerLength = new DataView(
    packed.buffer,
    packed.byteOffset,
    packed.byteLength,
  ).getUint32(0, false);

  if (headerLength > MAX_HEADER_BYTES) return null;
  if (HEADER_LENGTH_BYTES + headerLength > packed.length) return null;

  const headerBytes = packed.subarray(HEADER_LENGTH_BYTES, HEADER_LENGTH_BYTES + headerLength);
  const secret = packed.slice(HEADER_LENGTH_BYTES + headerLength);

  try {
    return { header: JSON.parse(sodium.to_string(headerBytes)), secret };
  } catch {
    return null;
  }
}

export interface SealCredentialInput {
  secret: Uint8Array;
  recipientPublicKey: Uint8Array;
  destinationWorkerId: string;
  workerKeyFingerprint: string;
  provider: ProviderId;
  credentialType: CredentialTypeId;
  /** Authenticated, and never visible to the relay: it lives inside the seal. */
  metadata?: Record<string, string>;
  /** Injected so tests are deterministic; defaults to the wall clock. */
  now?: Date;
  lifetimeMs?: number;
}

/**
 * Browser side. Produces an envelope whose every secret-bearing byte is
 * already encrypted to the destination worker before it leaves this function.
 */
export async function sealCredential(input: SealCredentialInput): Promise<SealedEnvelope> {
  const sodium = await sodiumReady();

  if (input.secret.length === 0) throw new Error('empty secret');
  if (input.secret.length > MAX_SECRET_BYTES) throw new Error('secret too large');

  const lifetime = Math.min(input.lifetimeMs ?? MAX_ENVELOPE_LIFETIME_MS, MAX_ENVELOPE_LIFETIME_MS);
  const now = input.now ?? new Date();

  const header: SealedPayloadHeader = {
    v: SEALED_ENVELOPE_VERSION,
    envelopeId: sodium.to_hex(sodium.randombytes_buf(16)),
    destinationWorkerId: input.destinationWorkerId,
    workerKeyFingerprint: input.workerKeyFingerprint,
    provider: input.provider,
    credentialType: input.credentialType,
    replayNonce: sodium.to_hex(sodium.randombytes_buf(16)),
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + lifetime).toISOString(),
    ...(input.metadata ? { metadata: input.metadata } : {}),
  };

  const packed = packPayload(sodium, header, input.secret);
  try {
    const ciphertext = sodium.crypto_box_seal(packed, input.recipientPublicKey);
    const { metadata: _omitted, ...routing } = header;
    return {
      ...routing,
      ciphertext: sodium.to_base64(ciphertext, sodium.base64_variants.ORIGINAL),
    };
  } finally {
    // The packed copy of the secret dies here regardless of outcome.
    wipeWith(sodium, packed);
  }
}

export type OpenEnvelopeResult =
  | { ok: true; secret: Uint8Array; header: SealedPayloadHeader }
  | { ok: false; failure: DeliveryFailure };

export interface OpenEnvelopeInput {
  envelope: unknown;
  workerId: string;
  workerFingerprint: string;
  publicKey: Uint8Array;
  privateKey: Uint8Array;
  now?: Date;
  /** Returns true when this nonce has already been consumed by this worker. */
  isReplay?: (replayNonce: string) => boolean;
}

/**
 * Worker side. Every check is a rejection reason, and the reasons returned are
 * coarse on purpose - a precise error is an oracle.
 *
 * The caller owns the returned secret buffer and must wipe it.
 */
export async function openEnvelope(input: OpenEnvelopeInput): Promise<OpenEnvelopeResult> {
  const sodium = await sodiumReady();

  const serialised = JSON.stringify(input.envelope ?? null);
  if (sodium.from_string(serialised).length > MAX_ENVELOPE_JSON_BYTES) {
    return { ok: false, failure: 'too_large' };
  }

  const parsed = SealedEnvelopeSchema.safeParse(input.envelope);
  if (!parsed.success) {
    // A recognisable but unsupported version is reported as such; anything
    // else is simply malformed.
    const version = (input.envelope as { v?: unknown } | null)?.v;
    if (typeof version === 'number' && version !== SEALED_ENVELOPE_VERSION) {
      return { ok: false, failure: 'unsupported_version' };
    }
    return { ok: false, failure: 'malformed' };
  }
  const envelope = parsed.data;

  if (envelope.destinationWorkerId !== input.workerId) {
    return { ok: false, failure: 'wrong_worker' };
  }
  if (envelope.workerKeyFingerprint !== input.workerFingerprint) {
    return { ok: false, failure: 'fingerprint_mismatch' };
  }

  const now = (input.now ?? new Date()).getTime();
  const createdAt = Date.parse(envelope.createdAt);
  const expiresAt = Date.parse(envelope.expiresAt);
  if (!Number.isFinite(createdAt) || !Number.isFinite(expiresAt)) {
    return { ok: false, failure: 'malformed' };
  }
  if (expiresAt - createdAt > MAX_ENVELOPE_LIFETIME_MS) {
    return { ok: false, failure: 'malformed' };
  }
  if (now >= expiresAt) {
    return { ok: false, failure: 'expired' };
  }

  if (input.isReplay?.(envelope.replayNonce)) {
    return { ok: false, failure: 'replayed' };
  }

  let ciphertext: Uint8Array;
  try {
    ciphertext = sodium.from_base64(envelope.ciphertext, sodium.base64_variants.ORIGINAL);
  } catch {
    return { ok: false, failure: 'malformed' };
  }

  let packed: Uint8Array;
  try {
    packed = sodium.crypto_box_seal_open(ciphertext, input.publicKey, input.privateKey);
  } catch {
    // Covers tampered ciphertext and envelopes sealed to a different worker.
    return { ok: false, failure: 'decryption_failed' };
  }

  try {
    const unpacked = unpackPayload(sodium, packed);
    if (!unpacked) return { ok: false, failure: 'malformed' };

    const headerResult = SealedPayloadHeaderSchema.safeParse(unpacked.header);
    if (!headerResult.success) {
      wipeWith(sodium, unpacked.secret);
      return { ok: false, failure: 'malformed' };
    }
    const header = headerResult.data;

    // The authenticated header must match the routing fields the relay saw.
    // Any edit in transit surfaces here.
    const mismatched =
      header.v !== envelope.v ||
      header.envelopeId !== envelope.envelopeId ||
      header.destinationWorkerId !== envelope.destinationWorkerId ||
      header.workerKeyFingerprint !== envelope.workerKeyFingerprint ||
      header.provider !== envelope.provider ||
      header.credentialType !== envelope.credentialType ||
      header.replayNonce !== envelope.replayNonce ||
      header.createdAt !== envelope.createdAt ||
      header.expiresAt !== envelope.expiresAt;

    if (mismatched) {
      wipeWith(sodium, unpacked.secret);
      return { ok: false, failure: 'header_mismatch' };
    }

    return { ok: true, secret: unpacked.secret, header };
  } finally {
    wipeWith(sodium, packed);
  }
}
