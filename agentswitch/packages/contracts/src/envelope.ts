import { z } from 'zod';

/**
 * Sealed-envelope contracts for encrypted credential transport.
 *
 * Two structures, deliberately separated:
 *
 *  - SealedPayload  - the plaintext that gets encrypted. Carries the secret
 *                     AND a copy of the routing header, so the header is
 *                     authenticated by the sealed box itself.
 *  - SealedEnvelope - what the relay actually sees and stores. Routing
 *                     metadata plus opaque ciphertext. No secret, ever.
 *
 * The worker verifies the inner header against the outer envelope. Editing an
 * outer field in transit therefore produces a mismatch, and editing the
 * ciphertext fails the sealed box's own authentication. That is why no custom
 * cryptography is needed to bind metadata to a delivery.
 */

export const SEALED_ENVELOPE_VERSION = 1 as const;

/** Envelopes live minutes, not hours. Five is the ceiling, not a default. */
export const MAX_ENVELOPE_LIFETIME_MS = 5 * 60 * 1000;

/** Plaintext credential ceiling. Comfortably above any real token format. */
export const MAX_SECRET_BYTES = 4096;

/** Hard cap on a serialised envelope, enforced before any parsing. */
export const MAX_ENVELOPE_JSON_BYTES = 16_384;

export const ProviderIdSchema = z.enum(['claude', 'codex', 'gemini']);
export type ProviderId = z.infer<typeof ProviderIdSchema>;

export const CredentialTypeIdSchema = z.enum(['api-key', 'access-token', 'test-value']);
export type CredentialTypeId = z.infer<typeof CredentialTypeIdSchema>;

/** Fields shared by the encrypted payload and the relayed envelope. */
const RoutingHeaderShape = {
  v: z.literal(SEALED_ENVELOPE_VERSION),
  envelopeId: z.string().min(8).max(128),
  destinationWorkerId: z.string().min(1).max(128),
  /** Fingerprint of the public key the browser sealed to. */
  workerKeyFingerprint: z.string().min(8).max(128),
  provider: ProviderIdSchema,
  credentialType: CredentialTypeIdSchema,
  /** Unique per delivery. Rejected if seen again by the same worker. */
  replayNonce: z.string().min(16).max(128),
  createdAt: z.string().datetime(),
  expiresAt: z.string().datetime(),
} as const;

export const RoutingHeaderSchema = z.object(RoutingHeaderShape);
export type RoutingHeader = z.infer<typeof RoutingHeaderSchema>;

/**
 * The authenticated header as it exists INSIDE the ciphertext. Optional
 * metadata lives here rather than on the outer envelope, so it is both
 * authenticated and invisible to the relay.
 */
export const SealedPayloadHeaderSchema = RoutingHeaderSchema.extend({
  metadata: z.record(z.string(), z.string()).optional(),
});
export type SealedPayloadHeader = z.infer<typeof SealedPayloadHeaderSchema>;

/** What the control plane receives, holds briefly, and deletes. */
export const SealedEnvelopeSchema = RoutingHeaderSchema.extend({
  /** base64 sealed box. Opaque to everything except the destination worker. */
  ciphertext: z.string().min(1).max(MAX_ENVELOPE_JSON_BYTES),
});
export type SealedEnvelope = z.infer<typeof SealedEnvelopeSchema>;

/** A worker's public identity. The private key never appears in any contract. */
export const WorkerIdentitySchema = z.object({
  workerId: z.string().min(1).max(128),
  displayName: z.string().min(1).max(128),
  publicKey: z.string().min(1).max(256),
  fingerprint: z.string().min(8).max(128),
  lastSeenAt: z.string().datetime(),
  online: z.boolean(),
});
export type WorkerIdentity = z.infer<typeof WorkerIdentitySchema>;

/**
 * Why a delivery was refused. Deliberately coarse: the relay and the UI both
 * surface these verbatim, and a precise reason is an oracle for an attacker.
 */
export const DeliveryFailureSchema = z.enum([
  'malformed',
  'unsupported_version',
  'too_large',
  'expired',
  'replayed',
  'wrong_worker',
  'fingerprint_mismatch',
  'decryption_failed',
  'header_mismatch',
]);
export type DeliveryFailure = z.infer<typeof DeliveryFailureSchema>;

/**
 * What the worker reports back. Non-secret by construction: there is no field
 * here that could carry the credential or anything derived from it.
 */
export const DeliveryReceiptSchema = z.object({
  envelopeId: z.string(),
  ok: z.boolean(),
  workerId: z.string(),
  provider: ProviderIdSchema.nullable(),
  credentialType: CredentialTypeIdSchema.nullable(),
  /** Test-path only: did the decrypted bytes equal the worker's canary? */
  canaryMatched: z.boolean().nullable(),
  failure: DeliveryFailureSchema.nullable(),
  receivedAt: z.string().datetime(),
});
export type DeliveryReceipt = z.infer<typeof DeliveryReceiptSchema>;
