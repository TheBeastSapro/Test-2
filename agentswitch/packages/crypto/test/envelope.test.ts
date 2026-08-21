import { beforeAll, describe, expect, it } from 'vitest';
import {
  MAX_ENVELOPE_JSON_BYTES,
  MAX_SECRET_BYTES,
  type SealedEnvelope,
} from '@agentswitch/contracts';
import {
  createWorkerContext,
  fingerprintPublicKey,
  generateWorkerKeyPair,
  openEnvelope,
  receiveEnvelope,
  sealCredential,
  sodiumReady,
  type WorkerKeyPair,
} from '@agentswitch/crypto';

const CANARY = 'AGENTSWITCH-CANARY-4f8c1d92a7e34b06-TEST-VALUE-ONLY';
const WORKER_ID = 'worker-test-1';
const T0 = new Date('2026-08-21T12:00:00.000Z');

let keyPair: WorkerKeyPair;
let fingerprint: string;
let other: { keyPair: WorkerKeyPair; fingerprint: string };

beforeAll(async () => {
  await sodiumReady();
  keyPair = await generateWorkerKeyPair();
  fingerprint = await fingerprintPublicKey(keyPair.publicKey);
  const otherPair = await generateWorkerKeyPair();
  other = { keyPair: otherPair, fingerprint: await fingerprintPublicKey(otherPair.publicKey) };
});

const seal = (overrides: Partial<Parameters<typeof sealCredential>[0]> = {}) =>
  sealCredential({
    secret: new TextEncoder().encode(CANARY),
    recipientPublicKey: keyPair.publicKey,
    destinationWorkerId: WORKER_ID,
    workerKeyFingerprint: fingerprint,
    provider: 'codex',
    credentialType: 'test-value',
    now: T0,
    ...overrides,
  });

const open = (envelope: unknown, now = new Date(T0.getTime() + 1000)) =>
  openEnvelope({
    envelope,
    workerId: WORKER_ID,
    workerFingerprint: fingerprint,
    publicKey: keyPair.publicKey,
    privateKey: keyPair.privateKey,
    now,
  });

describe('sealed envelope: the happy path', () => {
  it('round-trips the exact plaintext bytes', async () => {
    const envelope = await seal();
    const result = await open(envelope);

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error('unreachable');
    expect(new TextDecoder().decode(result.secret)).toBe(CANARY);
  });

  it('produces ciphertext that is not the plaintext and does not contain it', async () => {
    const envelope = await seal();

    expect(envelope.ciphertext).not.toBe(CANARY);
    expect(envelope.ciphertext).not.toContain(CANARY);
    // The whole serialised envelope is what the relay sees. It must be clean.
    expect(JSON.stringify(envelope)).not.toContain(CANARY);
    // And the plaintext must not survive as base64 either.
    expect(envelope.ciphertext).not.toContain(Buffer.from(CANARY).toString('base64'));
  });

  it('carries no secret-bearing field on the relayed envelope', async () => {
    const envelope = await seal();
    expect(Object.keys(envelope).sort()).toEqual([
      'ciphertext',
      'createdAt',
      'credentialType',
      'destinationWorkerId',
      'envelopeId',
      'expiresAt',
      'provider',
      'replayNonce',
      'v',
      'workerKeyFingerprint',
    ]);
  });

  it('keeps optional metadata inside the seal, invisible to the relay', async () => {
    const envelope = await seal({ metadata: { origin: 'unit-test' } });
    expect(JSON.stringify(envelope)).not.toContain('unit-test');

    const result = await open(envelope);
    if (!result.ok) throw new Error('unreachable');
    expect(result.header.metadata).toEqual({ origin: 'unit-test' });
  });
});

describe('sealed envelope: rejections', () => {
  it('rejects tampered ciphertext', async () => {
    const envelope = await seal();
    const bytes = Buffer.from(envelope.ciphertext, 'base64');
    const last = bytes.length - 1;
    bytes[last] = (bytes[last] ?? 0) ^ 0xff;
    const tampered = { ...envelope, ciphertext: bytes.toString('base64') };

    expect(await open(tampered)).toEqual({ ok: false, failure: 'decryption_failed' });
  });

  it('rejects a tampered routing field, because the header is authenticated', async () => {
    const envelope = await seal();
    // The relay's copy says "api-key"; the sealed copy still says "test-value".
    const tampered: SealedEnvelope = { ...envelope, credentialType: 'api-key' };

    expect(await open(tampered)).toEqual({ ok: false, failure: 'header_mismatch' });
  });

  it('cannot be opened by a worker holding a different key', async () => {
    const envelope = await seal();

    const result = await openEnvelope({
      envelope,
      workerId: WORKER_ID,
      workerFingerprint: fingerprint,
      publicKey: other.keyPair.publicKey,
      privateKey: other.keyPair.privateKey,
      now: new Date(T0.getTime() + 1000),
    });

    expect(result).toEqual({ ok: false, failure: 'decryption_failed' });
  });

  it('rejects an envelope addressed to a different worker', async () => {
    const envelope = await seal({ destinationWorkerId: 'worker-somewhere-else' });
    expect(await open(envelope)).toEqual({ ok: false, failure: 'wrong_worker' });
  });

  it('rejects a fingerprint that does not match the receiving key', async () => {
    const envelope = await seal({ workerKeyFingerprint: other.fingerprint });
    expect(await open(envelope)).toEqual({ ok: false, failure: 'fingerprint_mismatch' });
  });

  it('rejects an expired envelope', async () => {
    const envelope = await seal();
    const wellAfterExpiry = new Date(T0.getTime() + 6 * 60 * 1000);
    expect(await open(envelope, wellAfterExpiry)).toEqual({ ok: false, failure: 'expired' });
  });

  it('caps the lifetime at five minutes even if asked for longer', async () => {
    const envelope = await seal({ lifetimeMs: 60 * 60 * 1000 });
    const lifetime = Date.parse(envelope.expiresAt) - Date.parse(envelope.createdAt);
    expect(lifetime).toBe(5 * 60 * 1000);
  });

  it('rejects an oversized envelope before parsing it', async () => {
    const envelope = await seal();
    const oversized = { ...envelope, ciphertext: 'A'.repeat(MAX_ENVELOPE_JSON_BYTES + 1) };
    expect(await open(oversized)).toEqual({ ok: false, failure: 'too_large' });
  });

  it('refuses to seal a secret larger than the cap', async () => {
    await expect(seal({ secret: new Uint8Array(MAX_SECRET_BYTES + 1).fill(65) })).rejects.toThrow(
      /too large/,
    );
  });

  it('rejects an unsupported version', async () => {
    const envelope = await seal();
    expect(await open({ ...envelope, v: 99 })).toEqual({
      ok: false,
      failure: 'unsupported_version',
    });
  });

  it('rejects malformed input', async () => {
    expect(await open({ nonsense: true })).toEqual({ ok: false, failure: 'malformed' });
    expect(await open(null)).toEqual({ ok: false, failure: 'malformed' });
  });
});

describe('worker receipt', () => {
  const context = () => createWorkerContext(WORKER_ID, fingerprint, keyPair, CANARY);

  it('reports success and a canary match without returning the secret', async () => {
    const receipt = await receiveEnvelope(context(), await seal(), new Date(T0.getTime() + 1000));

    expect(receipt.ok).toBe(true);
    expect(receipt.canaryMatched).toBe(true);
    expect(receipt.provider).toBe('codex');
    expect(receipt.credentialType).toBe('test-value');
    expect(receipt.failure).toBeNull();
    // The receipt is the only thing that leaves the worker. It must be clean.
    expect(JSON.stringify(receipt)).not.toContain(CANARY);
    expect(Object.keys(receipt).sort()).toEqual([
      'canaryMatched',
      'credentialType',
      'envelopeId',
      'failure',
      'ok',
      'provider',
      'receivedAt',
      'workerId',
    ]);
  });

  it('reports a canary mismatch without revealing what arrived', async () => {
    const envelope = await seal({ secret: new TextEncoder().encode('a-different-value') });
    const receipt = await receiveEnvelope(context(), envelope, new Date(T0.getTime() + 1000));

    expect(receipt.ok).toBe(true);
    expect(receipt.canaryMatched).toBe(false);
    expect(JSON.stringify(receipt)).not.toContain('a-different-value');
  });

  it('rejects a replayed envelope on second delivery', async () => {
    const ctx = context();
    const envelope = await seal();
    const at = new Date(T0.getTime() + 1000);

    expect((await receiveEnvelope(ctx, envelope, at)).ok).toBe(true);

    const replayed = await receiveEnvelope(ctx, envelope, at);
    expect(replayed.ok).toBe(false);
    expect(replayed.failure).toBe('replayed');
    expect(replayed.canaryMatched).toBeNull();
  });
});
